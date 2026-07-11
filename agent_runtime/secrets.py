from __future__ import annotations

import base64
import ctypes
import json
import os
import platform
import subprocess
from ctypes import wintypes
from pathlib import Path
from threading import RLock
from typing import Any, Optional


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class SecretStore:
    """Small platform-backed store. Secret values never enter agent documents or API responses."""

    def __init__(self, path: Path, backend: str = "auto"):
        self.path = path
        self.backend = self._resolve_backend(backend)
        self.keychain_service = os.environ.get("AGENT_LAB_KEYCHAIN_SERVICE", f"ai-agent-sims:{self.path.resolve()}")
        self.lock = RLock()
        self.data = self._load()

    def status(self, agent_id: Optional[str] = None) -> dict[str, Any]:
        agents = self.data.get("agents", {})
        return {
            "project_configured": bool(self.data.get("project")),
            "agent_configured": bool(agent_id and agents.get(agent_id)),
            "backend": self.backend,
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
            self._delete_stored(self.data.get("project"))
            self.data["project"] = ""
            self._save()

    def delete_agent(self, agent_id: str) -> None:
        with self.lock:
            stored = self.data.setdefault("agents", {}).pop(agent_id, None)
            self._delete_stored(stored)
            self._save()

    def _set(self, section: str, agent_id: Optional[str], value: str) -> None:
        value = value.strip()
        if len(value) < 8 or len(value) > 4096:
            raise ValueError("API key must contain between 8 and 4096 characters")
        encrypted = self._protect(value, self._account(section, agent_id))
        with self.lock:
            if agent_id is None:
                self.data[section] = encrypted
            else:
                self.data.setdefault(section, {})[agent_id] = encrypted
            self._save()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"version": 2, "project": "", "agents": {}}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            "version": int(payload.get("version", 1) or 1),
            "project": payload.get("project", ""),
            "agents": payload.get("agents", {}),
        }

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def _decrypt_optional(self, encoded: Optional[Any]) -> Optional[str]:
        try:
            return self._unprotect(encoded) if encoded else None
        except RuntimeError:
            return None

    @staticmethod
    def _resolve_backend(requested: str) -> str:
        requested = (requested or "auto").strip().lower()
        if requested != "auto":
            return requested
        env_backend = os.environ.get("AGENT_LAB_SECRET_BACKEND", "").strip().lower()
        if env_backend:
            return env_backend
        if os.name == "nt":
            return "windows-dpapi"
        if platform.system() == "Darwin":
            return "macos-keychain"
        return "unsupported"

    @staticmethod
    def _account(section: str, agent_id: Optional[str]) -> str:
        return "project" if agent_id is None else f"agent:{agent_id}"

    def _protect(self, value: str, account: str) -> dict[str, str]:
        if self.backend == "macos-keychain":
            self._keychain_set(account, value)
            return {
                "backend": "macos-keychain",
                "service": self.keychain_service,
                "account": account,
            }
        if self.backend == "windows-dpapi":
            return {"backend": "windows-dpapi", "value": self._protect_dpapi(value)}
        if self.backend == "local-test":
            encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
            return {"backend": "local-test", "value": encoded}
        raise RuntimeError(
            "Persistent API keys are supported on macOS Keychain and Windows DPAPI. "
            "For development tests only, set AGENT_LAB_SECRET_BACKEND=local-test."
        )

    def _unprotect(self, stored: Any) -> str:
        if isinstance(stored, str):
            if os.name == "nt":
                return self._unprotect_dpapi(stored)
            raise RuntimeError("Legacy secret record can only be read on Windows DPAPI")
        if not isinstance(stored, dict):
            raise RuntimeError("Invalid secret record")
        backend = stored.get("backend")
        if backend == "macos-keychain":
            return self._keychain_get(
                str(stored.get("account", "")),
                str(stored.get("service", self.keychain_service) or self.keychain_service),
            )
        if backend == "windows-dpapi":
            return self._unprotect_dpapi(str(stored.get("value", "")))
        if backend == "local-test":
            return base64.b64decode(str(stored.get("value", ""))).decode("utf-8")
        raise RuntimeError(f"Unsupported secret backend: {backend}")

    def _delete_stored(self, stored: Any) -> None:
        if not isinstance(stored, dict):
            return
        if stored.get("backend") == "macos-keychain":
            self._keychain_delete(
                str(stored.get("account", "")),
                str(stored.get("service", self.keychain_service) or self.keychain_service),
            )

    def _keychain_set(self, account: str, value: str) -> None:
        if not account:
            raise RuntimeError("Missing Keychain account")
        self._run_security(
            [
                "add-generic-password",
                "-a",
                account,
                "-s",
                self.keychain_service,
                "-w",
                value,
                "-U",
            ],
            redact=True,
        )

    def _keychain_get(self, account: str, service: str) -> str:
        if not account or not service:
            raise RuntimeError("Missing Keychain account/service")
        completed = self._run_security(["find-generic-password", "-a", account, "-s", service, "-w"])
        value = completed.stdout.rstrip("\n")
        if not value:
            raise RuntimeError("Keychain item is empty")
        return value

    def _keychain_delete(self, account: str, service: str) -> None:
        if not account or not service:
            return
        completed = subprocess.run(
            ["security", "delete-generic-password", "-a", account, "-s", service],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode not in {0, 44}:
            message = (completed.stderr or completed.stdout or "security delete-generic-password failed").strip()
            if "could not be found" not in message.lower():
                raise RuntimeError(message)

    @staticmethod
    def _run_security(arguments: list[str], redact: bool = False) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                ["security", *arguments],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as error:
            raise RuntimeError("macOS Keychain command not found: security") from error
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "security command failed").strip()
            if redact:
                message = message.replace(arguments[-2], "[redacted]") if len(arguments) >= 2 else message
            raise RuntimeError(message)
        return completed

    @staticmethod
    def _protect_dpapi(value: str) -> str:
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
    def _unprotect_dpapi(encoded: str) -> str:
        if os.name != "nt":
            raise RuntimeError("Windows DPAPI secret cannot be read on this platform")
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
