"""Isolated Runpod Pod and ComfyUI infrastructure adapter."""
from __future__ import annotations

import json
import mimetypes
import time
from copy import deepcopy
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import RunPodSettings


class RunPodManagerError(RuntimeError):
    pass


class RunPodManager:
    graphql_url = "https://api.runpod.io/graphql"
    rest_url = "https://api.runpod.io"

    def __init__(self, settings: RunPodSettings, api_key: str | None):
        self.settings = settings
        self.api_key = api_key or ""

    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "configured": bool(self.api_key and self.settings.network_volume_id and (self.settings.template_id or self.settings.container_image)),
            "api_key_configured": bool(self.api_key), "network_volume_id": self.settings.network_volume_id,
            "data_center_id": self.settings.data_center_id, "template_id": self.settings.template_id,
            "container_image_configured": bool(self.settings.container_image), "preferred_gpu": self.settings.preferred_gpu,
            "max_hourly_cost": self.settings.max_hourly_cost, "volume_mount_path": self.settings.volume_mount_path,
            "comfyui_port": self.settings.comfyui_port, "idle_action": self.settings.idle_action,
            "pods": [], "error": "",
        }
        try:
            result["pods"] = self.list_pods()
        except RunPodManagerError as error:
            result["error"] = str(error)
        return result

    def list_pods(self) -> list[dict[str, str]]:
        payload = self._graphql("query { myself { pods { id name desiredStatus runtime { uptimeInSeconds } } } }")
        pods = ((payload.get("data") or {}).get("myself") or {}).get("pods") or []
        return [{"id": str(p.get("id", "")), "name": str(p.get("name", "")), "status": str(p.get("desiredStatus", ""))} for p in pods if isinstance(p, dict)]

    def list_datacenters(self) -> list[dict[str, object]]:
        payload = self._json_request(
            f"{self.rest_url}/v2/catalog/datacenters?include=GPU_AVAILABILITY",
            method="GET",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )
        datacenters = payload.get("dataCenters") or payload.get("datacenters") or []
        return [item for item in datacenters if isinstance(item, dict) and str(item.get("id", "")).strip()]

    def get_datacenter(self, data_center_id: str) -> dict[str, object]:
        safe_id = self._pod_id(data_center_id)
        payload = self._json_request(
            f"{self.rest_url}/v2/catalog/datacenters/{safe_id}?include=GPU_AVAILABILITY",
            method="GET",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )
        if not payload.get("id"):
            raise RunPodManagerError(f"Runpod did not return data center '{safe_id}'.")
        return payload

    def list_network_volumes(self) -> list[dict[str, object]]:
        payload = self._json_request(
            f"{self.rest_url}/v2/network-volumes",
            method="GET",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )
        volumes = payload.get("networkVolumes") or []
        return [item for item in volumes if isinstance(item, dict) and str(item.get("id", "")).strip()]

    def get_network_volume(self, volume_id: str) -> dict[str, object]:
        safe_id = self._pod_id(volume_id)
        payload = self._json_request(
            f"{self.rest_url}/v2/network-volumes/{safe_id}",
            method="GET",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )
        if not payload.get("id"):
            raise RunPodManagerError("Runpod did not return the requested Network Volume.")
        return payload

    def list_gpu_types(self, data_center_id: str = "") -> list[dict[str, object]]:
        payload = self._graphql("query { gpuTypes { id displayName memoryInGb securePrice communityPrice } }")
        gpu_types = [
            {
                "id": str(item.get("id", "")),
                "name": str(item.get("displayName", item.get("id", ""))),
                "memory_gb": item.get("memoryInGb"),
                "secure_price": item.get("securePrice"),
                "community_price": item.get("communityPrice"),
            }
            for item in ((payload.get("data") or {}).get("gpuTypes") or [])
            if isinstance(item, dict)
        ]
        target_data_center = str(data_center_id or "").strip()
        if not target_data_center:
            return gpu_types

        datacenters = self.list_datacenters()
        target = next(
            (item for item in datacenters if isinstance(item, dict) and str(item.get("id", "")) == target_data_center),
            None,
        )
        if target is None:
            target = self.get_datacenter(target_data_center)
        availability = target.get("gpuAvailability") or []
        by_id = {str(item["id"]): dict(item) for item in gpu_types if item.get("id")}
        filtered: list[dict[str, object]] = []
        for item in availability:
            if not isinstance(item, dict):
                continue
            gpu_id = str(item.get("id") or item.get("gpuTypeId") or "").strip()
            if not gpu_id:
                continue
            merged = by_id.get(gpu_id, {"id": gpu_id, "name": str(item.get("displayName", gpu_id))})
            stock_status = str(item.get("availability") or item.get("stockStatus") or "Unknown")
            merged["stock_status"] = stock_status
            merged["available"] = bool(item.get("available")) or stock_status.upper() not in {"", "NONE", "UNAVAILABLE"}
            filtered.append(merged)
        return filtered

    def create_pod(self, *, name: str = "Agent Lab ComfyUI", gpu_id: str = "") -> dict[str, object]:
        self._require_deploy_configuration()
        gpu = (gpu_id or self.settings.preferred_gpu).strip()
        if not gpu:
            raise RunPodManagerError("Choose a preferred GPU before creating a Pod.")
        fields: dict[str, object] = {
            "gpuCount": 1, "volumeInGb": 0, "containerDiskInGb": 20,
            "minVcpuCount": 2, "minMemoryInGb": 15, "gpuTypeId": gpu,
            "name": name.strip() or "Agent Lab ComfyUI", "networkVolumeId": self.settings.network_volume_id,
            "volumeMountPath": self.settings.volume_mount_path,
            "ports": f"{self.settings.comfyui_port}/http,8888/http",
        }
        if self.settings.template_id:
            fields["templateId"] = self.settings.template_id
        else:
            fields["imageName"] = self.settings.container_image
        if self.settings.data_center_id:
            fields["dataCenterId"] = self.settings.data_center_id
        input_fields = "cloudType: SECURE, " + ", ".join(f"{key}: {self._graphql_value(value)}" for key, value in fields.items())
        payload = self._graphql("mutation { podFindAndDeployOnDemand(input: { " + input_fields + " }) { id name desiredStatus imageName machineId } }")
        return self._pod_payload((payload.get("data") or {}).get("podFindAndDeployOnDemand"))

    def start_pod(self, pod_id: str) -> dict[str, object]:
        # Runpod calls the start operation podResume for stopped GPU Pods.
        payload = self._graphql(f"mutation {{ podResume(input: {{ podId: {self._graphql_value(self._pod_id(pod_id))} }}) {{ id name desiredStatus }} }}")
        return self._pod_payload((payload.get("data") or {}).get("podResume"))

    def stop_pod(self, pod_id: str) -> dict[str, object]:
        payload = self._graphql(f"mutation {{ podStop(input: {{ podId: {self._graphql_value(self._pod_id(pod_id))} }}) {{ id name desiredStatus }} }}")
        return self._pod_payload((payload.get("data") or {}).get("podStop"))

    def terminate_pod(self, pod_id: str) -> dict[str, object]:
        payload = self._graphql(f"mutation {{ podTerminate(input: {{ podId: {self._graphql_value(self._pod_id(pod_id))} }}) }}")
        return {"id": self._pod_id(pod_id), "terminated": bool((payload.get("data") or {}).get("podTerminate"))}

    def comfyui_url(self, pod_id: str) -> str:
        return f"https://{self._pod_id(pod_id)}-{self.settings.comfyui_port}.proxy.runpod.net"

    def comfyui_health(self, pod_id: str) -> dict[str, object]:
        url = f"{self.comfyui_url(pod_id)}/system_stats"
        try:
            return {"ok": True, "url": url, "system_stats": self._json_request(url, method="GET", timeout=20)}
        except RunPodManagerError as error:
            return {"ok": False, "url": url, "error": str(error)}

    def validate_comfyui_workflow(self, pod_id: str, workflow: dict[str, object]) -> None:
        """Fail before queueing when the Pod lacks workflow custom nodes."""
        object_info = self._json_request(f"{self.comfyui_url(pod_id)}/object_info", method="GET", timeout=45)
        available = set(object_info)
        required = {
            str(node.get("class_type", "")).strip()
            for node in workflow.values()
            if isinstance(node, dict) and str(node.get("class_type", "")).strip()
        }
        missing = sorted(required - available)
        if missing:
            raise RunPodManagerError(
                "ComfyUI is missing workflow node(s): " + ", ".join(missing[:20])
                + ". Install the required custom nodes/models on the Network Volume before running this preset."
            )

    def queue_comfyui_prompt(self, pod_id: str, workflow: dict[str, object]) -> dict[str, object]:
        if not isinstance(workflow, dict) or not workflow:
            raise RunPodManagerError("A non-empty ComfyUI workflow is required.")
        return self._json_request(f"{self.comfyui_url(pod_id)}/prompt", method="POST", payload={"prompt": workflow}, timeout=60)

    def upload_comfyui_media(self, pod_id: str, filename: str, content: bytes, overwrite: bool = True) -> dict[str, object]:
        safe_filename = str(filename or "upload.png").replace("/", "_").replace("\\", "_").strip()[:240] or "upload.png"
        if not content:
            raise RunPodManagerError("The media file is empty.")
        if len(content) > 25 * 1024 * 1024:
            raise RunPodManagerError("Media upload is limited to 25 MB.")
        mime_type = mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
        return self._multipart_json_request(
            f"{self.comfyui_url(pod_id)}/upload/image",
            fields={"overwrite": "true" if overwrite else "false", "type": "input"},
            file_field="image",
            filename=safe_filename,
            content=content,
            mime_type=mime_type,
            timeout=120,
        )

    def upload_comfyui_image(self, pod_id: str, filename: str, content: bytes, overwrite: bool = True) -> dict[str, object]:
        """Backward-compatible image alias for the generic ComfyUI input upload."""
        return self.upload_comfyui_media(pod_id, filename, content, overwrite)

    @staticmethod
    def inject_comfyui_media(
        workflow: dict[str, object],
        media_name: str,
        media_kind: str = "",
        loader_id: str = "",
    ) -> tuple[dict[str, object], int]:
        name = str(media_name or "").strip()
        if not name:
            return workflow, 0
        kind = str(media_kind or "").strip().lower()
        if kind not in {"image", "video"}:
            suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            kind = "video" if suffix in {"mp4", "webm", "mov", "mkv", "avi"} else "image"
        patched = deepcopy(workflow)
        injected = 0
        requested_loader_id = str(loader_id or "").strip()
        if requested_loader_id and requested_loader_id not in patched:
            raise RunPodManagerError(f"The selected media loader node '{requested_loader_id}' is not in this workflow.")
        for node_id, node in patched.items():
            if not isinstance(node, dict):
                continue
            if requested_loader_id and str(node_id) != requested_loader_id:
                continue
            class_type = str(node.get("class_type", "")).lower()
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            if kind == "image" and "loadimage" in class_type:
                inputs["image"] = name
                injected += 1
            elif kind == "video" and "loadvideo" in class_type:
                key = "video" if "video" in inputs or "video_name" not in inputs else "video_name"
                inputs[key] = name
                injected += 1
        if requested_loader_id and injected == 0:
            expected = "LoadVideo" if kind == "video" else "LoadImage"
            raise RunPodManagerError(f"Selected node '{requested_loader_id}' is not a compatible {expected} loader.")
        return patched, injected

    @staticmethod
    def inject_comfyui_prompt(workflow: dict[str, object], prompt: str) -> tuple[dict[str, object], int]:
        """Apply a Creative Director prompt to the positive text encoder.

        API workflow node IDs differ per workflow. A non-empty text encoder is
        normally the positive conditioning; blank encoders are commonly the
        negative prompt and are intentionally left unchanged.
        """
        text = str(prompt or "").strip()
        if not text:
            return deepcopy(workflow), 0
        patched = deepcopy(workflow)
        candidates: list[dict[str, object]] = []
        for node in patched.values():
            if not isinstance(node, dict) or "textencode" not in str(node.get("class_type", "")).lower():
                continue
            inputs = node.get("inputs")
            if isinstance(inputs, dict) and "text" in inputs:
                candidates.append(inputs)
        if not candidates:
            raise RunPodManagerError("This workflow has no compatible text prompt node.")
        target = next((entry for entry in candidates if str(entry.get("text", "")).strip()), candidates[0])
        target["text"] = text
        return patched, 1

    def comfyui_history(self, pod_id: str, prompt_id: str) -> dict[str, object]:
        return self._json_request(f"{self.comfyui_url(pod_id)}/history/{self._pod_id(prompt_id)}", method="GET", timeout=30)

    def download_comfyui_output(self, pod_id: str, output: dict[str, object]) -> bytes:
        filename = str(output.get("filename", "")).strip()
        if not filename:
            raise RunPodManagerError("ComfyUI output has no filename.")
        query = urlencode({
            "filename": filename,
            "subfolder": str(output.get("subfolder", "") or ""),
            "type": str(output.get("type", "output") or "output"),
        })
        url = f"{self.comfyui_url(pod_id)}/view?{query}"
        headers = {
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            # Runpod's proxy/Cloudflare can deny urllib's default Python UA.
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": f"{self.comfyui_url(pod_id)}/",
        }
        last_error: Exception | None = None
        for attempt in range(3):
            request = Request(url, headers=headers, method="GET")
            try:
                with urlopen(request, timeout=120) as response:  # nosec B310 - fixed RunPod proxy URL
                    payload = response.read()
                if not payload:
                    raise RunPodManagerError(f"ComfyUI returned an empty output file for '{filename}'.")
                return payload
            except HTTPError as error:
                # 403/404 are not assumed transient; retry once in case the
                # RunPod proxy is still syncing the generated output, then
                # surface response details instead of hiding the cause.
                body = error.read(1200).decode("utf-8", errors="replace")
                last_error = RunPodManagerError(
                    f"Could not download ComfyUI output '{filename}': HTTP {error.code} {error.reason}; "
                    f"url={url}; response={body or '<empty>'}"
                )
                if error.code not in {403, 404, 429, 500, 502, 503, 504} or attempt >= 2:
                    raise last_error from error
            except (URLError, TimeoutError, OSError) as error:
                last_error = error
                if attempt >= 2:
                    raise RunPodManagerError(f"Could not download ComfyUI output '{filename}': {error}; url={url}") from error
            time.sleep(1.5 * (attempt + 1))
        raise RunPodManagerError(f"Could not download ComfyUI output '{filename}': {last_error}")

    def _require_enabled(self) -> None:
        if not self.settings.enabled:
            raise RunPodManagerError("Runpod Manager is disabled in Global Settings.")
        if not self.api_key:
            raise RunPodManagerError("Runpod API key is not configured.")

    def _require_deploy_configuration(self) -> None:
        self._require_enabled()
        if not self.settings.network_volume_id:
            raise RunPodManagerError("Network Volume ID is required before creating a Pod.")
        if not (self.settings.template_id or self.settings.container_image):
            raise RunPodManagerError("Set a ComfyUI Template ID or container image before creating a Pod.")

    @staticmethod
    def _pod_id(value: str) -> str:
        pod_id = str(value or "").strip()
        if not pod_id or len(pod_id) > 120 or not all(char.isalnum() or char in "-_" for char in pod_id):
            raise RunPodManagerError("Invalid Pod ID.")
        return pod_id

    @staticmethod
    def _graphql_value(value: object) -> str:
        return str(value) if isinstance(value, (int, float)) else json.dumps(str(value))

    @staticmethod
    def _pod_payload(pod: object) -> dict[str, object]:
        if not isinstance(pod, dict) or not pod.get("id"):
            raise RunPodManagerError("Runpod did not return the expected Pod payload.")
        return {"id": str(pod.get("id", "")), "name": str(pod.get("name", "")), "status": str(pod.get("desiredStatus", "")), "image": str(pod.get("imageName", "")), "machine_id": str(pod.get("machineId", ""))}

    def _graphql(self, query: str) -> dict[str, Any]:
        self._require_enabled()
        # Queries are safe to retry.  Mutations are deliberately attempted only
        # once: retrying a lost deploy response could create a second paid Pod.
        attempts = 3 if query.lstrip().startswith("query") else 1
        last_error: RunPodManagerError | None = None
        payload: dict[str, object] | None = None
        for attempt in range(attempts):
            try:
                payload = self._json_request(self.graphql_url, method="POST", payload={"query": query}, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=30)
                break
            except RunPodManagerError as error:
                last_error = error
                if attempt + 1 >= attempts:
                    raise
                time.sleep(1.0 * (attempt + 1))
        if payload is None:
            raise last_error or RunPodManagerError("Runpod GraphQL query failed.")
        errors = payload.get("errors") if isinstance(payload, dict) else None
        if errors:
            first = errors[0] if isinstance(errors, list) and errors else {}
            message = first.get("message") if isinstance(first, dict) else str(first)
            raise RunPodManagerError(f"Runpod GraphQL error: {message or 'unknown error'}")
        return payload

    @staticmethod
    def _json_request(url: str, *, method: str, payload: dict[str, object] | None = None, headers: dict[str, str] | None = None, timeout: int = 30) -> dict[str, object]:
        request_headers = {
            "Accept": "application/json",
            # Runpod's Cloudflare proxy blocks urllib's default user agent (error 1010).
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            **(headers or {}),
        }
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        try:
            with urlopen(Request(url, data=data, headers=request_headers, method=method), timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as error:
            raise RunPodManagerError(f"HTTP {error.code} from {url}: {error.read().decode('utf-8', errors='replace')[:1000]}") from error
        except (URLError, TimeoutError, ValueError) as error:
            raise RunPodManagerError(f"Request to {url} failed: {error}") from error
        try:
            decoded = json.loads(raw) if raw else {}
        except json.JSONDecodeError as error:
            raise RunPodManagerError(f"Non-JSON response from {url}: {raw[:300]}") from error
        return decoded if isinstance(decoded, dict) else {"result": decoded}

    @staticmethod
    def _multipart_json_request(
        url: str,
        *,
        fields: dict[str, str],
        file_field: str,
        filename: str,
        content: bytes,
        mime_type: str,
        timeout: int,
    ) -> dict[str, object]:
        boundary = "----AgentLabRunpodUploadBoundary"
        chunks: list[bytes] = []
        for name, value in fields.items():
            chunks.extend([
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode(), b"\r\n",
            ])
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {mime_type}\r\n\r\n".encode(), content, b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ])
        try:
            headers = {
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            }
            with urlopen(Request(url, data=b"".join(chunks), headers=headers, method="POST"), timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as error:
            raise RunPodManagerError(f"HTTP {error.code} from {url}: {error.read().decode('utf-8', errors='replace')[:1000]}") from error
        except (URLError, TimeoutError, ValueError) as error:
            raise RunPodManagerError(f"Request to {url} failed: {error}") from error
        try:
            decoded = json.loads(raw) if raw else {}
        except json.JSONDecodeError as error:
            raise RunPodManagerError(f"Non-JSON response from {url}: {raw[:300]}") from error
        return decoded if isinstance(decoded, dict) else {"result": decoded}
