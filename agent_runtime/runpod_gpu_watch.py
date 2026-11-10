"""Persistent regional GPU availability watcher for RunPod."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .runpod_manager import RunPodManager, RunPodManagerError


DEFAULT_GPU_IDS = [
    "NVIDIA RTX 4000 Ada Generation",
    "NVIDIA RTX A4000",
    "NVIDIA RTX 2000 Ada Generation",
    "NVIDIA GeForce RTX 4090",
]


class RunPodGpuWatch:
    def __init__(self, path: Path, manager_factory: Callable[[], RunPodManager], on_available: Callable[[dict[str, object]], None] | None = None):
        self.path, self.manager_factory, self.on_available = path, manager_factory, on_available
        self.history_path = path.with_name("runpod_gpu_history.sqlite")
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.state = self._load()
        self._init_history()

    def _init_history(self) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.history_path, timeout=30) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS gpu_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    checked_at TEXT NOT NULL,
                    region TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'watcher',
                    ok INTEGER NOT NULL,
                    available_count INTEGER NOT NULL,
                    gpu_snapshot_json TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT ''
                )"""
            )
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(gpu_checks)").fetchall()}
            if "source" not in columns:
                connection.execute("ALTER TABLE gpu_checks ADD COLUMN source TEXT NOT NULL DEFAULT 'watcher'")

    def _record_check(self, checked_at: str, region: str, gpus: dict[str, object], error: str = "", source: str = "watcher") -> None:
        snapshot = gpus if isinstance(gpus, dict) else {}
        available_count = sum(1 for value in snapshot.values() if isinstance(value, dict) and value.get("available"))
        with sqlite3.connect(self.history_path, timeout=30) as connection:
            connection.execute(
                "INSERT INTO gpu_checks (checked_at, region, source, ok, available_count, gpu_snapshot_json, error) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (checked_at, region, source, int(not error), available_count, json.dumps(snapshot, ensure_ascii=False), error),
            )

    def record_inventory(self, region: str, gpus: list[dict[str, object]], source: str = "gpu-list") -> None:
        """Persist a regional availability result returned by any RunPod UI/workflow check."""
        if not str(region or "").strip():
            return
        snapshot = {
            str(gpu.get("id", "")): {
                "name": str(gpu.get("name") or gpu.get("id", "")),
                "available": bool(gpu.get("available")),
                "stock_status": str(gpu.get("stock_status", "Unknown")),
                "memory_gb": gpu.get("memory_gb"),
                "community_price": gpu.get("community_price"),
                "secure_price": gpu.get("secure_price"),
            }
            for gpu in gpus if isinstance(gpu, dict) and str(gpu.get("id", "")).strip()
        }
        checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self._record_check(checked_at, str(region).strip(), snapshot, source=source)

    def history(self, limit: int = 500) -> list[dict[str, object]]:
        with sqlite3.connect(self.history_path, timeout=30) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM gpu_checks ORDER BY id DESC LIMIT ?", (max(1, min(int(limit), 5000)),)
            ).fetchall()
        result: list[dict[str, object]] = []
        for row in rows:
            try:
                snapshot = json.loads(str(row["gpu_snapshot_json"]))
            except json.JSONDecodeError:
                snapshot = {}
            result.append({
                "id": row["id"], "checked_at": row["checked_at"], "region": row["region"],
                "source": row["source"],
                "ok": bool(row["ok"]), "available_count": row["available_count"],
                "gpus": snapshot, "error": row["error"],
            })
        return result

    def availability_by_hour(self) -> list[dict[str, object]]:
        """Aggregate successful snapshots by local clock hour for easy timing analysis."""
        buckets: dict[tuple[str, int], dict[str, Any]] = {}
        with sqlite3.connect(self.history_path, timeout=30) as connection:
            rows = connection.execute(
                "SELECT checked_at, region, available_count, gpu_snapshot_json FROM gpu_checks WHERE ok = 1"
            )
            for checked_at, region_value, available_count, snapshot_json in rows:
                try:
                    hour = datetime.fromisoformat(str(checked_at)).hour
                except ValueError:
                    continue
                region = str(region_value)
                bucket = buckets.setdefault((region, hour), {"region": region, "hour": hour, "checks": 0, "available_total": 0, "available_max": 0, "gpu_counts": {}})
                bucket["checks"] += 1
                bucket["available_total"] += int(available_count)
                bucket["available_max"] = max(int(bucket["available_max"]), int(available_count))
                try:
                    snapshot = json.loads(str(snapshot_json))
                except json.JSONDecodeError:
                    snapshot = {}
                for gpu_id, details in (snapshot.items() if isinstance(snapshot, dict) else []):
                    if isinstance(details, dict) and details.get("available"):
                        counts = bucket["gpu_counts"]
                        counts[gpu_id] = int(counts.get(gpu_id, 0)) + 1
        result = []
        for bucket in buckets.values():
            total = int(bucket.pop("available_total"))
            count = int(bucket["checks"])
            bucket["average_available"] = round(total / count, 2) if count else 0
            result.append(bucket)
        return sorted(result, key=lambda row: (str(row["region"]), -float(row["average_available"]), int(row["hour"])))

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, dict): return value
        except (OSError, json.JSONDecodeError): pass
        return {"enabled": False, "interval_seconds": 60, "gpu_ids": DEFAULT_GPU_IDS, "last_check": "", "error": "", "gpus": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def configure(self, enabled: bool, gpu_ids: list[str] | None = None, interval_seconds: int = 60) -> dict[str, object]:
        with self._lock:
            self.state["enabled"] = bool(enabled)
            self.state["gpu_ids"] = [str(value).strip() for value in (gpu_ids or DEFAULT_GPU_IDS) if str(value).strip()][:12]
            self.state["interval_seconds"] = max(30, min(int(interval_seconds), 3600))
            self._save()
        if enabled: self.start()
        return self.status()

    def status(self) -> dict[str, object]:
        with self._lock:
            return dict(self.state) | {"running": bool(self._thread and self._thread.is_alive())}

    def start(self) -> None:
        if self._thread and self._thread.is_alive(): return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="runpod-gpu-watch")
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()

    def check_now(self) -> dict[str, object]:
        manager = self.manager_factory()
        region = str(manager.settings.data_center_id or "").strip()
        if not region and str(manager.settings.network_volume_id or "").strip():
            volume = manager.get_network_volume(str(manager.settings.network_volume_id))
            region = str(volume.get("dataCenter") or volume.get("dataCenterId") or "").strip()
        if not region:
            checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
            error = "Select the Network Volume region before enabling GPU monitoring."
            self._record_check(checked_at, "", {}, error)
            raise RunPodManagerError(error)
        wanted = set(self.state.get("gpu_ids", DEFAULT_GPU_IDS))
        available = manager.list_gpu_types(region)
        current: dict[str, dict[str, object]] = {}
        events: list[dict[str, object]] = []
        with self._lock:
            previous = self.state.get("gpus", {}) if isinstance(self.state.get("gpus"), dict) else {}
            for gpu in available:
                identifier = str(gpu.get("id", ""))
                if identifier not in wanted: continue
                now_available = bool(gpu.get("available"))
                before = bool((previous.get(identifier) or {}).get("available"))
                current[identifier] = {"name": str(gpu.get("name", identifier)), "available": now_available, "stock_status": str(gpu.get("stock_status", "Unknown")), "memory_gb": gpu.get("memory_gb"), "community_price": gpu.get("community_price"), "secure_price": gpu.get("secure_price")}
                if now_available and not before: events.append(current[identifier] | {"id": identifier, "region": region})
            checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
            self.state.update({"region": region, "gpus": current, "last_check": checked_at, "error": ""})
            self._save()
            self._record_check(checked_at, region, current)
        for event in events:
            if self.on_available: self.on_available(event)
        return self.status() | {"newly_available": events}

    def _loop(self) -> None:
        while not self._stop.is_set():
            try: self.check_now()
            except Exception as error:
                checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
                error_text = f"{type(error).__name__}: {error}"
                with self._lock:
                    self.state["error"] = error_text
                    self.state["last_check"] = checked_at
                    self._save()
                    self._record_check(checked_at, str(self.state.get("region", "")), self.state.get("gpus", {}), error_text)
            self._stop.wait(max(30, int(self.state.get("interval_seconds", 60))))
