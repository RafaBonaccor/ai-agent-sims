from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path
from threading import RLock
from typing import Optional


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class SecretStore:
    """Small DPAPI-backed store. Secret values never enter agent documents or API responses."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = RLock()
        self.data = self._load()

    def status(self, agent_id: Optional[str] = None) -> dict[str, bool]:
        agents = self.data.get("agents", {})
        return {
            "project_configured": bool(self.data.get("project")),
            "agent_configured": bool(agent_id and agents.get(agent_id)),
        }

    def get_project(self) -> Optional[str]:
        return self._decrypt_optional(self.data.get("project"))

    def get_agent(self, agent_id: str) -> Optional[str]:
        return self._decrypt_optional(self.data.get("agents", {}).get(agent_id))

    def set_project(self, value: str) -> None:
        self._set("project", None, value)

    def set_agent(self, agent_id: str, value: str) -> None:
        self._set("agents", agent_id, value)

    def delete_project(self) -> None:
        with self.lock:
            self.data["project"] = ""
            self._save()

    def delete_agent(self, agent_id: str) -> None:
        with self.lock:
            self.data.setdefault("agents", {}).pop(agent_id, None)
            self._save()

    def _set(self, section: str, agent_id: Optional[str], value: str) -> None:
        value = value.strip()
        if len(value) < 8 or len(value) > 4096:
            raise ValueError("API key must contain between 8 and 4096 characters")
        encrypted = self._protect(value)
        with self.lock:
            if agent_id is None:
                self.data[section] = encrypted
            else:
                self.data.setdefault(section, {})[agent_id] = encrypted
            self._save()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "project": "", "agents": {}}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            "version": 1,
            "project": payload.get("project", ""),
            "agents": payload.get("agents", {}),
        }

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def _decrypt_optional(self, encoded: Optional[str]) -> Optional[str]:
        return self._unprotect(encoded) if encoded else None

    @staticmethod
    def _protect(value: str) -> str:
        if os.name != "nt":
            raise RuntimeError("Persistent API keys currently require Windows DPAPI")
        raw = value.encode("utf-8")
        buffer = ctypes.create_string_buffer(raw)
        source = _DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        target = _DataBlob()
        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(source), "Agent Protocol Lab", None, None, None, 0, ctypes.byref(target)
        ):
            raise ctypes.WinError()
        try:
            encrypted = ctypes.string_at(target.pbData, target.cbData)
            return base64.b64encode(encrypted).decode("ascii")
        finally:
            ctypes.windll.kernel32.LocalFree(target.pbData)

    @staticmethod
    def _unprotect(encoded: str) -> str:
        raw = base64.b64decode(encoded)
        buffer = ctypes.create_string_buffer(raw)
        source = _DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        target = _DataBlob()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)
        ):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(target.pbData, target.cbData).decode("utf-8")
        finally:
            ctypes.windll.kernel32.LocalFree(target.pbData)
