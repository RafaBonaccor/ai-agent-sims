from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from agent_runtime.models import RunPodSettings
from agent_runtime.runpod_batches import RunPodBatchService
from agent_runtime.runpod_manager import RunPodManager


class FakeManager(RunPodManager):
    def __init__(self) -> None:
        super().__init__(RunPodSettings(enabled=True, network_volume_id="vol", container_image="image"), "key")
        self.pods: list[dict[str, str]] = []
        self.uploaded: list[str] = []
        self.stopped: list[str] = []
        self.terminated: list[str] = []
        self.prompt_count = 0
        self.gpus_available = True

    def list_pods(self):  # type: ignore[no-untyped-def]
        return self.pods

    def create_pod(self, *, name="", gpu_id=""):  # type: ignore[no-untyped-def]
        self.pods = [{"id": "newpod", "name": name, "status": "RUNNING"}]
        return {"id": "newpod", "name": name, "status": "RUNNING"}

    def list_gpu_types(self, data_center_id=""):  # type: ignore[no-untyped-def]
        return [{"id": "NVIDIA GeForce RTX 4090", "name": "RTX 4090", "memory_gb": 24, "available": self.gpus_available, "community_price": 0.3}]

    def get_network_volume(self, volume_id):  # type: ignore[no-untyped-def]
        return {"id": volume_id, "dataCenter": "EUR-IS-1"}

    def comfyui_health(self, pod_id):  # type: ignore[no-untyped-def]
        return {"ok": True}

    def validate_comfyui_workflow(self, pod_id, workflow):  # type: ignore[no-untyped-def]
        return None

    def upload_comfyui_media(self, pod_id, filename, content, overwrite=True):  # type: ignore[no-untyped-def]
        self.uploaded.append(filename)
        return {"name": filename, "subfolder": ""}

    def queue_comfyui_prompt(self, pod_id, workflow):  # type: ignore[no-untyped-def]
        self.prompt_count += 1
        return {"prompt_id": f"prompt-{self.prompt_count}"}

    def comfyui_history(self, pod_id, prompt_id):  # type: ignore[no-untyped-def]
        return {prompt_id: {"status": {"status_str": "success"}, "outputs": {"9": {"images": [{"filename": f"{prompt_id}.png", "subfolder": "", "type": "output"}]}}}}

    def download_comfyui_output(self, pod_id, output):  # type: ignore[no-untyped-def]
        return b"test-output"

    def stop_pod(self, pod_id):  # type: ignore[no-untyped-def]
        self.stopped.append(pod_id)
        return {"id": pod_id, "status": "STOPPED"}

    def terminate_pod(self, pod_id):  # type: ignore[no-untyped-def]
        self.terminated.append(pod_id)
        return {"id": pod_id, "terminated": True}


class RunPodBatchTests(unittest.TestCase):
    workflow = {"52": {"class_type": "LoadImage", "inputs": {"image": "old.png"}}}

    def wait_for(self, service: RunPodBatchService, batch_id: str):
        for _ in range(80):
            batch = service.get_batch(batch_id)
            if batch["status"] in {"completed", "completed_with_errors", "failed", "cancelled"}:
                return batch
            time.sleep(0.05)
        self.fail("batch did not finish")

    def test_auto_deploy_processes_every_item_and_stops_owned_pod(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = FakeManager()
            service = RunPodBatchService(Path(directory), lambda: manager)
            batch = service.create_batch(self.workflow, media_loader_id="52", auto_deploy=True, auto_shutdown=True)
            service.add_item(batch["id"], "one.png", b"one")
            service.add_item(batch["id"], "two.png", b"two")
            service.start_batch(batch["id"])
            completed = self.wait_for(service, batch["id"])
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(manager.uploaded, ["one.png", "two.png"])
            self.assertEqual(manager.stopped, ["newpod"])
            self.assertEqual([item["status"] for item in completed["items"]], ["completed", "completed"])
            self.assertEqual(completed["items"][0]["outputs"][0]["filename"], "prompt-1.png")
            self.assertTrue(completed["items"][0]["outputs"][0]["local_path"])
            self.assertEqual(service.output_file(batch["id"], completed["items"][0]["id"], 0).read_bytes(), b"test-output")

    def test_existing_pod_is_not_stopped_automatically(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = FakeManager()
            manager.pods = [{"id": "manualpod", "name": "manual", "status": "RUNNING"}]
            service = RunPodBatchService(Path(directory), lambda: manager)
            batch = service.create_batch(self.workflow, media_loader_id="52")
            service.add_item(batch["id"], "one.png", b"one")
            service.start_batch(batch["id"])
            completed = self.wait_for(service, batch["id"])
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(completed["pod_id"], "manualpod")
            self.assertFalse(completed["pod_owned"])
            self.assertEqual(manager.stopped, [])

    def test_one_failed_item_does_not_stop_later_items(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = FakeManager()
            original_upload = manager.upload_comfyui_media

            def fail_one(pod_id, filename, content, overwrite=True):
                if filename == "bad.png":
                    raise RuntimeError("synthetic bad file")
                return original_upload(pod_id, filename, content, overwrite)

            manager.upload_comfyui_media = fail_one  # type: ignore[method-assign]
            service = RunPodBatchService(Path(directory), lambda: manager)
            batch = service.create_batch(self.workflow, media_loader_id="52")
            service.add_item(batch["id"], "bad.png", b"bad")
            service.add_item(batch["id"], "good.png", b"good")
            service.start_batch(batch["id"])
            completed = self.wait_for(service, batch["id"])
            self.assertEqual(completed["status"], "completed_with_errors")
            self.assertEqual([item["status"] for item in completed["items"]], ["failed", "completed"])
            self.assertEqual(manager.uploaded, ["good.png"])

    def test_waiting_batch_resumes_when_gpu_watch_finds_compatible_stock(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = FakeManager()
            manager.gpus_available = False
            service = RunPodBatchService(Path(directory), lambda: manager)
            batch = service.create_batch(self.workflow, media_loader_id="52", min_vram_gb=24)
            service.add_item(batch["id"], "one.png", b"one")
            service.start_batch(batch["id"])
            for _ in range(40):
                waiting = service.get_batch(batch["id"])
                if waiting["status"] == "waiting_for_gpu":
                    break
                time.sleep(0.05)
            self.assertEqual(waiting["status"], "waiting_for_gpu")
            self.assertIn("24 GB", waiting["error"])
            manager.gpus_available = True
            service.resume_waiting_batches()
            completed = self.wait_for(service, batch["id"])
            self.assertEqual(completed["status"], "completed")

