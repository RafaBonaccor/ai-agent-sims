from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_runtime.models import RunPodSettings
from agent_runtime.runpod_gpu_watch import RunPodGpuWatch


class FakeManager:
    def __init__(self) -> None:
        self.settings = RunPodSettings(data_center_id="EUR-IS-1")

    def list_gpu_types(self, region: str) -> list[dict[str, object]]:
        assert region == "EUR-IS-1"
        return [
            {"id": "gpu-a", "name": "GPU A", "available": True, "stock_status": "HIGH", "memory_gb": 24},
            {"id": "gpu-b", "name": "GPU B", "available": False, "stock_status": "NONE", "memory_gb": 48},
        ]


class RunPodGpuWatchTests(unittest.TestCase):
    def test_inventory_is_persisted_with_local_timestamp_and_hour_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "watch.json"
            watch = RunPodGpuWatch(config, FakeManager)

            watch.record_inventory("EUR-IS-1", FakeManager().list_gpu_types("EUR-IS-1"), "gpu-picker")

            history = watch.history()
            self.assertEqual(len(history), 1)
            self.assertTrue(history[0]["ok"])
            self.assertEqual(history[0]["region"], "EUR-IS-1")
            self.assertEqual(history[0]["source"], "gpu-picker")
            self.assertEqual(history[0]["available_count"], 1)
            self.assertIn("+", history[0]["checked_at"])
            self.assertTrue(history[0]["gpus"]["gpu-a"]["available"])

            summary = watch.availability_by_hour()
            self.assertEqual(len(summary), 1)
            self.assertEqual(summary[0]["checks"], 1)
            self.assertEqual(summary[0]["average_available"], 1)
            self.assertEqual(summary[0]["gpu_counts"], {"gpu-a": 1})

    def test_history_survives_watcher_recreation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "watch.json"
            first = RunPodGpuWatch(config, FakeManager)
            first.record_inventory("EUR-IS-1", FakeManager().list_gpu_types("EUR-IS-1"))
            second = RunPodGpuWatch(config, FakeManager)

            self.assertEqual(len(second.history()), 1)


if __name__ == "__main__":
    unittest.main()
