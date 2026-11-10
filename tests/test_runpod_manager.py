from __future__ import annotations

import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO

from agent_runtime.models import RunPodSettings
from agent_runtime.runpod_manager import RunPodManager


class RunPodManagerTests(unittest.TestCase):
    def test_output_download_uses_proxy_headers_and_retries_transient_403(self) -> None:
        from agent_runtime import runpod_manager as module

        calls = []

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return b"image-bytes"

        def fake_urlopen(request, timeout):
            calls.append((request, timeout))
            if len(calls) == 1:
                raise HTTPError(request.full_url, 403, "Forbidden", {}, BytesIO(b"proxy warming"))
            return Response()

        manager = RunPodManager(RunPodSettings(enabled=True), "test-key")
        with patch.object(module, "urlopen", side_effect=fake_urlopen), patch.object(module.time, "sleep"):
            data = manager.download_comfyui_output("pod-123", {"filename": "result.png", "type": "output"})

        self.assertEqual(data, b"image-bytes")
        self.assertEqual(len(calls), 2)
        self.assertIn("Mozilla/5.0", calls[0][0].get_header("User-agent"))
        self.assertEqual(calls[0][0].get_header("Referer"), "https://pod-123-8188.proxy.runpod.net/")

    def test_disabled_manager_never_queries_network(self) -> None:
        status = RunPodManager(RunPodSettings(), "a" * 20).status()

        self.assertFalse(status["configured"])
        self.assertEqual(status["pods"], [])
        self.assertIn("disabled", status["error"].lower())

    def test_missing_key_is_reported_without_network(self) -> None:
        settings = RunPodSettings(enabled=True, network_volume_id="volume", template_id="template")
        status = RunPodManager(settings, None).status()

        self.assertFalse(status["configured"])
        self.assertIn("API key", status["error"])

    def test_comfyui_proxy_url_uses_configured_port(self) -> None:
        manager = RunPodManager(RunPodSettings(comfyui_port=8288), None)

        self.assertEqual(manager.comfyui_url("pod-123"), "https://pod-123-8288.proxy.runpod.net")

    def test_create_pod_builds_network_volume_request(self) -> None:
        class FakeManager(RunPodManager):
            query = ""

            def _graphql(self, query: str):  # type: ignore[override]
                self.query = query
                return {"data": {"podFindAndDeployOnDemand": {"id": "pod-123", "name": "media", "desiredStatus": "RUNNING"}}}

        settings = RunPodSettings(
            enabled=True,
            network_volume_id="volume-1",
            template_id="template-1",
            preferred_gpu="NVIDIA RTX A5000",
            volume_mount_path="/workspace",
        )
        manager = FakeManager(settings, "test-key")

        result = manager.create_pod(name="media", gpu_id="gpu-1")

        self.assertEqual(result["id"], "pod-123")
        self.assertIn("cloudType: SECURE", manager.query)
        self.assertNotIn('cloudType: "SECURE"', manager.query)
        self.assertIn('networkVolumeId: "volume-1"', manager.query)
        self.assertIn('templateId: "template-1"', manager.query)
        self.assertIn('gpuTypeId: "gpu-1"', manager.query)

    def test_gpu_list_filters_to_selected_data_center(self) -> None:
        class FakeManager(RunPodManager):
            def _graphql(self, query: str):  # type: ignore[override]
                if "gpuTypes" in query:
                    return {"data": {"gpuTypes": [
                        {"id": "gpu-a", "displayName": "GPU A", "memoryInGb": 24, "securePrice": 1, "communityPrice": 0.5},
                        {"id": "gpu-b", "displayName": "GPU B", "memoryInGb": 48, "securePrice": 2, "communityPrice": 1},
                    ]}}
                raise AssertionError("Unexpected GraphQL query")

            def list_datacenters(self):  # type: ignore[override]
                return [{"id": "EUR-IS-1", "gpuAvailability": [{"id": "gpu-b", "displayName": "GPU B", "availability": "HIGH"}]}]

        gpus = FakeManager(RunPodSettings(enabled=True), "test-key").list_gpu_types("EUR-IS-1")

        self.assertEqual(gpus, [{"id": "gpu-b", "name": "GPU B", "memory_gb": 48, "secure_price": 2, "community_price": 1, "stock_status": "HIGH", "available": True}])

    def test_network_volume_list_uses_rest_catalog(self) -> None:
        class FakeManager(RunPodManager):
            @staticmethod
            def _json_request(url, **kwargs):  # type: ignore[override]
                self = kwargs
                assert url.endswith("/v2/network-volumes")
                return {"networkVolumes": [{"id": "volume-1", "name": "media", "dataCenter": "EU-FR-1"}]}

        volumes = FakeManager(RunPodSettings(enabled=True), "test-key").list_network_volumes()

        self.assertEqual(volumes[0]["dataCenter"], "EU-FR-1")

    def test_media_is_injected_into_matching_comfy_loader_without_mutating_original(self) -> None:
        workflow = {
            "1": {"class_type": "LoadImage", "inputs": {"image": "old.png"}},
            "2": {"class_type": "VHS_LoadVideo", "inputs": {"video": "old.mp4"}},
        }

        image_workflow, image_count = RunPodManager.inject_comfyui_media(workflow, "catalog/bracelet.png", "image")
        video_workflow, video_count = RunPodManager.inject_comfyui_media(workflow, "catalog/bracelet.mp4", "video")

        self.assertEqual(image_count, 1)
        self.assertEqual(image_workflow["1"]["inputs"]["image"], "catalog/bracelet.png")
        self.assertEqual(video_count, 1)
        self.assertEqual(video_workflow["2"]["inputs"]["video"], "catalog/bracelet.mp4")
        self.assertEqual(workflow["1"]["inputs"]["image"], "old.png")

    def test_media_can_target_one_explicit_loader_node(self) -> None:
        workflow = {
            "first": {"class_type": "LoadImage", "inputs": {"image": "first.png"}},
            "second": {"class_type": "LoadImage", "inputs": {"image": "second.png"}},
        }

        patched, injected = RunPodManager.inject_comfyui_media(workflow, "new.png", "image", "second")

        self.assertEqual(injected, 1)
        self.assertEqual(patched["first"]["inputs"]["image"], "first.png")
        self.assertEqual(patched["second"]["inputs"]["image"], "new.png")


if __name__ == "__main__":
    unittest.main()
