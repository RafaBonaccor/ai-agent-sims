"""Persistent, sequential ComfyUI batches with optional ephemeral RunPod Pods."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .runpod_manager import RunPodManager, RunPodManagerError
from .runpod_gpu_watch import DEFAULT_GPU_IDS


class RunPodBatchError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _media_kind(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return "video" if suffix in {".mp4", ".webm", ".mov", ".mkv", ".avi"} else "image"


class RunPodBatchService:
    """Keeps the batch queue local and intentionally runs one ComfyUI job at a time.

    A Pod created by this service is stopped/terminated when the batch ends. An
    already-running Pod is never stopped automatically: it may belong to a
    manual workflow outside the batch.
    """

    def __init__(
        self,
        root: Path,
        manager_factory: Callable[[], RunPodManager],
        allowed_gpu_ids_factory: Callable[[], list[str]] | None = None,
        on_gpu_check: Callable[[str, list[dict[str, object]]], None] | None = None,
    ):
        self.root = root
        self.files_root = root / "files"
        self.db_path = root / "batches.sqlite"
        self.manager_factory = manager_factory
        self.allowed_gpu_ids_factory = allowed_gpu_ids_factory or (lambda: list(DEFAULT_GPU_IDS))
        self.on_gpu_check = on_gpu_check
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self.root.mkdir(parents=True, exist_ok=True)
        self.files_root.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runpod_batches (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    workflow_json TEXT NOT NULL,
                    media_loader_id TEXT NOT NULL DEFAULT '',
                    auto_deploy INTEGER NOT NULL DEFAULT 1,
                    auto_shutdown INTEGER NOT NULL DEFAULT 1,
                    min_vram_gb INTEGER NOT NULL DEFAULT 0,
                    workflow_id TEXT NOT NULL DEFAULT '',
                    creative_prompt TEXT NOT NULL DEFAULT '',
                    pod_id TEXT NOT NULL DEFAULT '',
                    pod_owned INTEGER NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS runpod_batch_items (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    media_kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    prompt_id TEXT NOT NULL DEFAULT '',
                    uploaded_name TEXT NOT NULL DEFAULT '',
                    output_json TEXT NOT NULL DEFAULT '[]',
                    error TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(batch_id) REFERENCES runpod_batches(id)
                );
                CREATE INDEX IF NOT EXISTS idx_runpod_batch_items_batch ON runpod_batch_items(batch_id, ordinal);
                """
            )
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(runpod_batches)").fetchall()}
            if "min_vram_gb" not in columns:
                conn.execute("ALTER TABLE runpod_batches ADD COLUMN min_vram_gb INTEGER NOT NULL DEFAULT 0")
            if "workflow_id" not in columns:
                conn.execute("ALTER TABLE runpod_batches ADD COLUMN workflow_id TEXT NOT NULL DEFAULT ''")
            if "creative_prompt" not in columns:
                conn.execute("ALTER TABLE runpod_batches ADD COLUMN creative_prompt TEXT NOT NULL DEFAULT ''")

    def create_batch(
        self,
        workflow: dict[str, object],
        *,
        media_loader_id: str = "",
        auto_deploy: bool = True,
        auto_shutdown: bool = True,
        min_vram_gb: int = 0,
        workflow_id: str = "",
        creative_prompt: str = "",
    ) -> dict[str, object]:
        if not isinstance(workflow, dict) or not workflow:
            raise RunPodBatchError("A non-empty ComfyUI API workflow is required.")
        batch_id = f"batch-{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO runpod_batches
                (id, created_at, updated_at, status, workflow_json, media_loader_id, auto_deploy, auto_shutdown, min_vram_gb, workflow_id, creative_prompt)
                VALUES (?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?)""",
                (batch_id, now, now, json.dumps(workflow), str(media_loader_id or ""), int(auto_deploy), int(auto_shutdown), max(0, int(min_vram_gb)), str(workflow_id or "")[:120], str(creative_prompt or "")[:12000]),
            )
        (self.files_root / batch_id).mkdir(parents=True, exist_ok=True)
        return self.get_batch(batch_id)

    def add_item(self, batch_id: str, filename: str, content: bytes) -> dict[str, object]:
        safe_batch_id = self._batch_id(batch_id)
        if not content:
            raise RunPodBatchError("Batch media file is empty.")
        if len(content) > 25 * 1024 * 1024:
            raise RunPodBatchError("Each batch media file is limited to 25 MB.")
        safe_name = Path(str(filename or "upload.png")).name.strip()[:180] or "upload.png"
        with self._connect() as conn:
            row = conn.execute("SELECT status FROM runpod_batches WHERE id = ?", (safe_batch_id,)).fetchone()
            if row is None:
                raise RunPodBatchError("Batch not found.")
            if str(row["status"]) != "draft":
                raise RunPodBatchError("Files can only be added while the batch is still a draft.")
            ordinal = int(conn.execute("SELECT COUNT(*) FROM runpod_batch_items WHERE batch_id = ?", (safe_batch_id,)).fetchone()[0]) + 1
            item_id = f"item-{uuid.uuid4().hex[:12]}"
            stored_name = f"{ordinal:04d}_{item_id}_{safe_name}"
            relative_path = f"{safe_batch_id}/{stored_name}"
            output_path = self.files_root / relative_path
            output_path.write_bytes(content)
            conn.execute(
                """INSERT INTO runpod_batch_items
                (id, batch_id, ordinal, filename, file_path, media_kind, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'queued', ?)""",
                (item_id, safe_batch_id, ordinal, safe_name, relative_path, _media_kind(safe_name), _now()),
            )
        return self.get_batch(safe_batch_id)

    def start_batch(self, batch_id: str) -> dict[str, object]:
        safe_batch_id = self._batch_id(batch_id)
        with self._lock:
            if safe_batch_id in self._threads and self._threads[safe_batch_id].is_alive():
                return self.get_batch(safe_batch_id)
            with self._connect() as conn:
                row = conn.execute("SELECT status FROM runpod_batches WHERE id = ?", (safe_batch_id,)).fetchone()
                count = int(conn.execute("SELECT COUNT(*) FROM runpod_batch_items WHERE batch_id = ?", (safe_batch_id,)).fetchone()[0])
                if row is None:
                    raise RunPodBatchError("Batch not found.")
                if count == 0:
                    raise RunPodBatchError("Add at least one image or video before starting a batch.")
                previous_status = str(row["status"])
                if previous_status not in {"draft", "failed", "cancelled", "completed_with_errors", "waiting_for_gpu"}:
                    raise RunPodBatchError("Batch is already running or completed. Create a new batch to run it again.")
                conn.execute("UPDATE runpod_batches SET status = 'starting', error = '', cancel_requested = 0, updated_at = ? WHERE id = ?", (_now(), safe_batch_id))
                if previous_status != "waiting_for_gpu":
                    conn.execute("UPDATE runpod_batch_items SET status = 'queued', prompt_id = '', uploaded_name = '', output_json = '[]', error = '', updated_at = ? WHERE batch_id = ?", (_now(), safe_batch_id))
            thread = threading.Thread(target=self._run_batch, args=(safe_batch_id,), daemon=True, name=f"runpod-batch-{safe_batch_id}")
            self._threads[safe_batch_id] = thread
            thread.start()
        return self.get_batch(safe_batch_id)

    def resume_waiting_batches(self) -> list[dict[str, object]]:
        """Resume durable queue entries only after the GPU watcher sees stock."""
        with self._connect() as conn:
            rows = conn.execute("SELECT id FROM runpod_batches WHERE status = 'waiting_for_gpu' AND cancel_requested = 0 ORDER BY created_at").fetchall()
        resumed: list[dict[str, object]] = []
        for row in rows:
            try:
                resumed.append(self.start_batch(str(row["id"])))
            except RunPodBatchError:
                continue
        return resumed

    def cancel_batch(self, batch_id: str) -> dict[str, object]:
        safe_batch_id = self._batch_id(batch_id)
        with self._connect() as conn:
            cursor = conn.execute("UPDATE runpod_batches SET cancel_requested = 1, updated_at = ? WHERE id = ?", (_now(), safe_batch_id))
            if cursor.rowcount == 0:
                raise RunPodBatchError("Batch not found.")
        return self.get_batch(safe_batch_id)

    def list_batches(self, limit: int = 30) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id FROM runpod_batches ORDER BY created_at DESC LIMIT ?", (max(1, min(int(limit), 100)),)).fetchall()
        return [self.get_batch(str(row["id"])) for row in rows]

    def get_batch(self, batch_id: str) -> dict[str, object]:
        safe_batch_id = self._batch_id(batch_id)
        with self._connect() as conn:
            batch = conn.execute("SELECT * FROM runpod_batches WHERE id = ?", (safe_batch_id,)).fetchone()
            if batch is None:
                raise RunPodBatchError("Batch not found.")
            items = conn.execute("SELECT * FROM runpod_batch_items WHERE batch_id = ? ORDER BY ordinal", (safe_batch_id,)).fetchall()
        values = dict(batch)
        serialised_items: list[dict[str, object]] = []
        for item in items:
            result = dict(item)
            try:
                result["outputs"] = json.loads(str(result.pop("output_json") or "[]"))
            except json.JSONDecodeError:
                result["outputs"] = []
            result.pop("file_path", None)
            serialised_items.append(result)
        values.pop("workflow_json", None)
        values["auto_deploy"] = bool(values["auto_deploy"])
        values["auto_shutdown"] = bool(values["auto_shutdown"])
        values["pod_owned"] = bool(values["pod_owned"])
        values["cancel_requested"] = bool(values["cancel_requested"])
        values["items"] = serialised_items
        values["counts"] = {status: sum(1 for item in serialised_items if item["status"] == status) for status in {str(item["status"]) for item in serialised_items}}
        return values

    def _run_batch(self, batch_id: str) -> None:
        manager: RunPodManager | None = None
        owned_pod = False
        pod_id = ""
        try:
            batch = self._raw_batch(batch_id)
            manager = self.manager_factory()
            workflow = json.loads(str(batch["workflow_json"]))
            workflow, _ = manager.inject_comfyui_prompt(workflow, str(batch["creative_prompt"] or ""))
            try:
                pod_id, owned_pod = self._resolve_pod(manager, bool(batch["auto_deploy"]), int(batch["min_vram_gb"] or 0))
            except RunPodBatchError as error:
                if str(error).startswith("Waiting for"):
                    self._update_batch(batch_id, status="waiting_for_gpu", error=str(error))
                    return
                raise
            self._update_batch(batch_id, status="waiting_for_comfyui", pod_id=pod_id, pod_owned=int(owned_pod))
            self._wait_for_comfyui(batch_id, manager, pod_id)
            manager.validate_comfyui_workflow(pod_id, workflow)
            self._update_batch(batch_id, status="running")
            loader_id = str(batch["media_loader_id"] or "")
            for item in self._raw_items(batch_id):
                if self._cancelled(batch_id):
                    self._update_item(str(item["id"]), status="cancelled", error="Cancelled by user")
                    self._update_batch(batch_id, status="cancelled")
                    break
                try:
                    self._run_item(batch_id, manager, pod_id, workflow, loader_id, item)
                except Exception as error:
                    # One corrupt upload or ComfyUI prompt must not discard the
                    # rest of a batch. The item records its own actionable error.
                    self._update_item(str(item["id"]), status="failed", error=f"{type(error).__name__}: {error}")
                    if self._cancelled(batch_id):
                        self._update_batch(batch_id, status="cancelled")
                        break
            else:
                failed_count = sum(1 for item in self._raw_items(batch_id) if str(item["status"]) == "failed")
                if failed_count:
                    self._update_batch(batch_id, status="completed_with_errors", error=f"{failed_count} batch item(s) failed; review item errors.")
                else:
                    self._update_batch(batch_id, status="completed")
        except Exception as error:  # worker must persist every unexpected failure
            self._update_batch(batch_id, status="failed", error=f"{type(error).__name__}: {error}")
        finally:
            if manager is not None and owned_pod:
                try:
                    batch = self._raw_batch(batch_id)
                    if bool(batch["auto_shutdown"]):
                        if manager.settings.idle_action == "terminate":
                            manager.terminate_pod(pod_id)
                            self._update_batch(batch_id, status=self._raw_batch(batch_id)["status"], error="", pod_id=pod_id)
                        else:
                            manager.stop_pod(pod_id)
                except Exception as error:
                    self._append_batch_error(batch_id, f"Automatic Pod cleanup failed: {error}")

    def _resolve_pod(self, manager: RunPodManager, auto_deploy: bool, min_vram_gb: int = 0) -> tuple[str, bool]:
        pods = manager.list_pods()
        active = [pod for pod in pods if str(pod.get("status", "")).upper() in {"RUNNING", "ONDEMAND", "STARTED"}]
        if len(active) == 1:
            return str(active[0]["id"]), False
        if len(active) > 1:
            raise RunPodBatchError("More than one active Pod exists. Stop/select Pods manually before automatic batch execution.")
        if not auto_deploy:
            raise RunPodBatchError("No active RunPod Pod is available and automatic deployment is disabled.")
        region = str(manager.settings.data_center_id or "").strip()
        if not region and manager.settings.network_volume_id:
            volume = manager.get_network_volume(manager.settings.network_volume_id)
            region = str(volume.get("dataCenter") or volume.get("dataCenterId") or "").strip()
        configured_gpu_ids = self.allowed_gpu_ids_factory() or list(DEFAULT_GPU_IDS)
        allowed_gpu_ids = {str(value).strip() for value in configured_gpu_ids if str(value).strip()}
        inventory = manager.list_gpu_types(region)
        if self.on_gpu_check:
            self.on_gpu_check(region, inventory)
        candidates = [
            gpu for gpu in inventory
            if str(gpu.get("id", "")) in allowed_gpu_ids
            and bool(gpu.get("available"))
            and int(gpu.get("memory_gb") or 0) >= min_vram_gb
        ]
        if not candidates:
            allowed_text = ", ".join(sorted(allowed_gpu_ids)) or "configured whitelist"
            raise RunPodBatchError(f"Waiting for a whitelisted compatible GPU with at least {min_vram_gb} GB VRAM. Allowed: {allowed_text}.")
        candidates.sort(key=lambda gpu: float(gpu.get("community_price") or gpu.get("secure_price") or 9999))
        created = manager.create_pod(name="Agent Lab Batch", gpu_id=str(candidates[0]["id"]))
        return str(created["id"]), True

    def _wait_for_comfyui(self, batch_id: str, manager: RunPodManager, pod_id: str) -> None:
        deadline = time.monotonic() + 900
        last_error = ""
        while time.monotonic() < deadline:
            if self._cancelled(batch_id):
                raise RunPodBatchError("Batch cancelled while waiting for ComfyUI.")
            health = manager.comfyui_health(pod_id)
            if bool(health.get("ok")):
                return
            last_error = str(health.get("error", "ComfyUI is not ready"))
            time.sleep(8)
        raise RunPodBatchError(f"ComfyUI did not become ready within 15 minutes: {last_error}")

    def _run_item(self, batch_id: str, manager: RunPodManager, pod_id: str, workflow: dict[str, object], loader_id: str, item: sqlite3.Row) -> None:
        item_id = str(item["id"])
        self._update_item(item_id, status="uploading")
        source = self.files_root / str(item["file_path"])
        if not source.is_file():
            raise RunPodBatchError(f"Input file disappeared: {item['filename']}")
        uploaded = manager.upload_comfyui_media(pod_id, str(item["filename"]), source.read_bytes())
        uploaded_name = "/".join(part for part in [str(uploaded.get("subfolder", "") or "").strip(), str(uploaded.get("name", "") or "").strip()] if part)
        patched, injected = manager.inject_comfyui_media(workflow, uploaded_name, str(item["media_kind"]), loader_id)
        if injected != 1:
            raise RunPodBatchError(f"Expected exactly one media loader injection for {item['filename']}; got {injected}.")
        self._update_item(item_id, status="queued", uploaded_name=uploaded_name)
        response = manager.queue_comfyui_prompt(pod_id, patched)
        prompt_id = str(response.get("prompt_id") or response.get("promptId") or "")
        if not prompt_id:
            raise RunPodBatchError(f"ComfyUI did not return a prompt ID for {item['filename']}.")
        self._update_item(item_id, status="processing", prompt_id=prompt_id)
        history = self._wait_for_prompt(batch_id, manager, pod_id, prompt_id)
        outputs = self._extract_outputs(history, prompt_id)
        outputs = self._archive_outputs(batch_id, item_id, manager, pod_id, outputs)
        self._update_item(item_id, status="completed", output_json=json.dumps(outputs))

    def _archive_outputs(self, batch_id: str, item_id: str, manager: RunPodManager, pod_id: str, outputs: list[dict[str, object]]) -> list[dict[str, object]]:
        """Copy outputs before automatic Pod cleanup makes their proxy unavailable."""
        archive = self.files_root / batch_id / "outputs"
        archive.mkdir(parents=True, exist_ok=True)
        archived: list[dict[str, object]] = []
        for index, output in enumerate(outputs):
            filename = Path(str(output.get("filename", "output"))).name or "output"
            stored = f"{item_id}_{index:03d}_{filename}"
            (archive / stored).write_bytes(manager.download_comfyui_output(pod_id, output))
            archived.append({**output, "local_path": f"{batch_id}/outputs/{stored}"})
        return archived

    def output_file(self, batch_id: str, item_id: str, output_index: int) -> Path:
        safe_batch = self._batch_id(batch_id)
        safe_item = self._item_id(item_id)
        batch = self.get_batch(safe_batch)
        item = next((entry for entry in batch["items"] if str(entry["id"]) == safe_item), None)
        if not isinstance(item, dict):
            raise RunPodBatchError("Batch item not found.")
        outputs = item.get("outputs") if isinstance(item.get("outputs"), list) else []
        if output_index < 0 or output_index >= len(outputs):
            raise RunPodBatchError("Batch output not found.")
        relative = str(outputs[output_index].get("local_path", "")) if isinstance(outputs[output_index], dict) else ""
        candidate = (self.files_root / relative).resolve()
        root = self.files_root.resolve()
        if not relative or root not in candidate.parents or not candidate.is_file():
            raise RunPodBatchError("Archived batch output is unavailable.")
        return candidate

    def _wait_for_prompt(self, batch_id: str, manager: RunPodManager, pod_id: str, prompt_id: str) -> dict[str, object]:
        deadline = time.monotonic() + 3600
        transient_errors = 0
        while time.monotonic() < deadline:
            if self._cancelled(batch_id):
                raise RunPodBatchError("Batch cancelled while a ComfyUI prompt was running.")
            try:
                # ComfyUI may not answer /history while a large model is being
                # paged into VRAM. This is normal progress, not a failed prompt.
                history = manager.comfyui_history(pod_id, prompt_id)
                transient_errors = 0
            except RunPodManagerError:
                transient_errors += 1
                time.sleep(min(10, 2 + transient_errors))
                continue
            entry = history.get(prompt_id) if isinstance(history, dict) else None
            if isinstance(entry, dict):
                status = str(((entry.get("status") or {}) if isinstance(entry.get("status"), dict) else {}).get("status_str", "")).lower()
                if status == "error":
                    details = ((entry.get("status") or {}) if isinstance(entry.get("status"), dict) else {}).get("messages", [])
                    detail_text = json.dumps(details, ensure_ascii=False)[:1800] if details else "no error detail returned"
                    raise RunPodBatchError(f"ComfyUI prompt {prompt_id} failed: {detail_text}")
                if status in {"success", "completed"} or entry.get("outputs"):
                    return history
            time.sleep(5)
        raise RunPodBatchError(f"ComfyUI prompt {prompt_id} exceeded the 60 minute batch timeout.")

    @staticmethod
    def _extract_outputs(history: dict[str, object], prompt_id: str) -> list[dict[str, object]]:
        entry = history.get(prompt_id, {}) if isinstance(history, dict) else {}
        outputs = entry.get("outputs", {}) if isinstance(entry, dict) else {}
        files: list[dict[str, object]] = []
        if not isinstance(outputs, dict):
            return files
        for node_id, node_output in outputs.items():
            if not isinstance(node_output, dict):
                continue
            for output_type in ("images", "gifs", "videos"):
                for file in node_output.get(output_type, []) if isinstance(node_output.get(output_type), list) else []:
                    if isinstance(file, dict):
                        files.append({"node_id": str(node_id), "type": output_type, **file})
        return files

    def _raw_batch(self, batch_id: str) -> sqlite3.Row:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runpod_batches WHERE id = ?", (batch_id,)).fetchone()
        if row is None:
            raise RunPodBatchError("Batch not found.")
        return row

    def _raw_items(self, batch_id: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM runpod_batch_items WHERE batch_id = ? ORDER BY ordinal", (batch_id,)).fetchall()

    def _cancelled(self, batch_id: str) -> bool:
        return bool(self._raw_batch(batch_id)["cancel_requested"])

    def _update_batch(self, batch_id: str, *, status: object, error: str | None = None, pod_id: str | None = None, pod_owned: int | None = None) -> None:
        sets = ["status = ?", "updated_at = ?"]
        values: list[object] = [str(status), _now()]
        if error is not None:
            sets.append("error = ?")
            values.append(error)
        if pod_id is not None:
            sets.append("pod_id = ?")
            values.append(pod_id)
        if pod_owned is not None:
            sets.append("pod_owned = ?")
            values.append(pod_owned)
        values.append(batch_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE runpod_batches SET {', '.join(sets)} WHERE id = ?", values)

    def _append_batch_error(self, batch_id: str, message: str) -> None:
        batch = self._raw_batch(batch_id)
        existing = str(batch["error"] or "")
        self._update_batch(batch_id, status=batch["status"], error=(existing + (" | " if existing else "") + message))

    def _update_item(self, item_id: str, *, status: str, error: str | None = None, prompt_id: str | None = None, uploaded_name: str | None = None, output_json: str | None = None) -> None:
        sets = ["status = ?", "updated_at = ?"]
        values: list[object] = [status, _now()]
        for key, value in (("error", error), ("prompt_id", prompt_id), ("uploaded_name", uploaded_name), ("output_json", output_json)):
            if value is not None:
                sets.append(f"{key} = ?")
                values.append(value)
        values.append(item_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE runpod_batch_items SET {', '.join(sets)} WHERE id = ?", values)

    @staticmethod
    def _batch_id(value: str) -> str:
        result = str(value or "").strip()
        if not result.startswith("batch-") or not all(char.isalnum() or char == "-" for char in result):
            raise RunPodBatchError("Invalid batch ID.")
        return result

    @staticmethod
    def _item_id(value: str) -> str:
        result = str(value or "").strip()
        if not result.startswith("item-") or not all(char.isalnum() or char == "-" for char in result):
            raise RunPodBatchError("Invalid batch item ID.")
        return result
