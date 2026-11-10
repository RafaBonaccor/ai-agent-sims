"""Appium server, device discovery, and explicit iOS app launch controls."""
from __future__ import annotations

import json
import base64
import binascii
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .models import AppiumSettings


class AppiumManagerError(RuntimeError):
    pass


_SERVER_LOCK = threading.Lock()
_SERVER_PROCESS: subprocess.Popen | None = None
_SERVER_LOG = None
_DEVICE_SESSION_ID = ""
_DEVICE_SESSION_ID_UDID = ""
_DEVICE_SESSION_BUNDLE_ID = ""


class AppiumManager:
    """Manage a localhost Appium server and explicitly launch installed iOS apps."""

    def __init__(self, settings: AppiumSettings):
        self.settings = settings

    def status(self) -> dict[str, Any]:
        server_url = self._normalize_server_url(self.settings.server_url)
        result: dict[str, Any] = {
            "enabled": bool(self.settings.enabled),
            "server_url": server_url,
            "server_connected": False,
            "server_version": "",
            "server_error": "",
            "adb_available": False,
            "adb_error": "",
            "ios_discovery": "",
            "devices": [],
            "device_count": 0,
            "android_device_count": 0,
            "ios_device_count": 0,
            "control_enabled": False,
            "active_session": bool(_DEVICE_SESSION_ID),
            "active_app_bundle_id": _DEVICE_SESSION_BUNDLE_ID,
        }
        if self.settings.enabled:
            try:
                payload = self._get_status(server_url)
                value = payload.get("value") if isinstance(payload.get("value"), dict) else payload
                result["server_connected"] = bool(value.get("ready", True))
                build = value.get("build") if isinstance(value.get("build"), dict) else {}
                result["server_version"] = str(build.get("version") or value.get("version") or "")
                if not result["server_connected"]:
                    result["server_error"] = str(value.get("message") or "Appium reports that it is not ready.")
            except AppiumManagerError as error:
                result["server_error"] = str(error)
        else:
            result["server_error"] = "Appium integration is disabled. Enable it to check the server."

        android_devices, adb_available, adb_error = self._list_android_devices()
        ios_devices, ios_discovery = self._list_ios_devices()
        result["devices"] = android_devices + ios_devices
        result["adb_available"] = adb_available
        result["adb_error"] = adb_error
        result["ios_discovery"] = ios_discovery
        result["android_device_count"] = sum(device["state"] == "device" for device in android_devices)
        result["ios_device_count"] = sum(device["state"] == "device" for device in ios_devices)
        result["device_count"] = result["android_device_count"] + result["ios_device_count"]
        result["control_enabled"] = bool(result["server_connected"] and result["ios_device_count"])
        return result

    def list_ios_apps(self, device_id: str) -> list[dict[str, str]]:
        """Read installed user apps through XCUITest; this may initialize WDA."""
        device_id = self._validate_ios_device(device_id)
        temporary_session = not (_DEVICE_SESSION_ID and _DEVICE_SESSION_ID_UDID == device_id)
        if _DEVICE_SESSION_ID and _DEVICE_SESSION_ID_UDID != device_id:
            self.close_device_session()
        session_id = self._create_ios_session(device_id) if temporary_session else _DEVICE_SESSION_ID
        try:
            payload = self._appium_request(
                "POST", f"/session/{session_id}/execute/sync",
                {"script": "mobile: listApps", "args": [{
                    "applicationType": "User",
                    "returnAttributes": ["CFBundleIdentifier", "CFBundleName", "CFBundleVersion"],
                }]},
            )
            value = payload.get("value", payload)
            if isinstance(value, list):
                entries = value
            elif isinstance(value, dict):
                entries = [dict(attributes or {}, CFBundleIdentifier=bundle_id) for bundle_id, attributes in value.items()]
            else:
                raise AppiumManagerError("Appium returned an unexpected installed-app inventory.")
            apps = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                bundle_id = str(entry.get("CFBundleIdentifier") or entry.get("bundleId") or "").strip()
                if not bundle_id:
                    continue
                apps.append({
                    "bundle_id": bundle_id,
                    "name": str(entry.get("CFBundleName") or entry.get("name") or bundle_id).strip(),
                    "version": str(entry.get("CFBundleVersion") or entry.get("version") or "").strip(),
                })
            return sorted(apps, key=lambda app: (app["name"].casefold(), app["bundle_id"]))
        finally:
            if temporary_session:
                self._delete_session(session_id)

    def launch_ios_app(self, device_id: str, bundle_id: str) -> dict[str, Any]:
        """Launch an already-installed iOS app and retain its Appium session."""
        global _DEVICE_SESSION_ID, _DEVICE_SESSION_ID_UDID, _DEVICE_SESSION_BUNDLE_ID
        device_id = self._validate_ios_device(device_id)
        bundle_id = self._validate_bundle_id(bundle_id)
        if _DEVICE_SESSION_ID:
            self.close_device_session()
        session_id = self._create_ios_session(device_id, bundle_id=bundle_id)
        _DEVICE_SESSION_ID = session_id
        _DEVICE_SESSION_ID_UDID = device_id
        _DEVICE_SESSION_BUNDLE_ID = bundle_id
        return {"launched": True, "device_id": device_id, "bundle_id": bundle_id, "session_id": session_id}

    def close_device_session(self) -> dict[str, Any]:
        global _DEVICE_SESSION_ID, _DEVICE_SESSION_ID_UDID, _DEVICE_SESSION_BUNDLE_ID
        session_id = _DEVICE_SESSION_ID
        if not session_id:
            return {"closed": False, "already_closed": True}
        try:
            self._delete_session(session_id)
        finally:
            _DEVICE_SESSION_ID = ""
            _DEVICE_SESSION_ID_UDID = ""
            _DEVICE_SESSION_BUNDLE_ID = ""
        return {"closed": True, "already_closed": False}

    def get_device_screenshot(self) -> bytes:
        if not _DEVICE_SESSION_ID:
            raise AppiumManagerError("Apri prima un’app per avviare una sessione Appium.")
        payload = self._appium_request("GET", f"/session/{_DEVICE_SESSION_ID}/screenshot")
        value = payload.get("value")
        if not isinstance(value, str) or not value:
            raise AppiumManagerError("Appium non ha restituito uno screenshot del dispositivo.")
        try:
            image = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as error:
            raise AppiumManagerError("Appium ha restituito uno screenshot non valido.") from error
        if not image.startswith(b"\x89PNG\r\n\x1a\n"):
            raise AppiumManagerError("Lo screenshot Appium non è un PNG valido.")
        return image

    def _validate_ios_device(self, device_id: str) -> str:
        device_id = str(device_id or "").strip()
        if not device_id:
            raise AppiumManagerError("Select a connected iPhone or iPad first.")
        if not self.settings.enabled:
            raise AppiumManagerError("Enable Appium in the Mobile Automation settings first.")
        status = self.status()
        if not status["server_connected"]:
            raise AppiumManagerError(status["server_error"] or "Appium server is unavailable.")
        if not any(device.get("id") == device_id and device.get("platform") == "iOS" and device.get("state") == "device" for device in status["devices"]):
            raise AppiumManagerError("The selected iOS device is not currently connected and ready.")
        return device_id

    @staticmethod
    def _validate_bundle_id(bundle_id: str) -> str:
        bundle_id = str(bundle_id or "").strip()
        if len(bundle_id) > 255 or not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", bundle_id):
            raise AppiumManagerError("Enter a valid iOS bundle identifier (for example, com.example.app).")
        return bundle_id

    def _create_ios_session(self, device_id: str, *, bundle_id: str = "") -> str:
        capabilities: dict[str, Any] = {
            "platformName": "iOS",
            "appium:automationName": "XCUITest",
            "appium:udid": device_id,
            "appium:noReset": True,
            "appium:newCommandTimeout": 3600,
        }
        if bundle_id:
            capabilities["appium:bundleId"] = bundle_id
        payload = self._appium_request("POST", "/session", {"capabilities": {"alwaysMatch": capabilities, "firstMatch": [{}]}})
        value = payload.get("value") if isinstance(payload.get("value"), dict) else payload
        session_id = str(value.get("sessionId") or payload.get("sessionId") or "").strip()
        if not session_id:
            raise AppiumManagerError("Appium did not return a WebDriver session ID.")
        return session_id

    def _delete_session(self, session_id: str) -> None:
        try:
            self._appium_request("DELETE", f"/session/{session_id}")
        except AppiumManagerError:
            # Listing apps should not fail solely because WDA disconnected during cleanup.
            pass

    def _appium_request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        server_url = self._normalize_server_url(self.settings.server_url)
        base = server_url.rstrip("/")
        candidates = [f"{base}{path}"]
        if not urlsplit(server_url).path.endswith("/wd/hub"):
            candidates.append(f"{base}/wd/hub{path}")
        last_error = "Appium command failed."
        for url in candidates:
            data = json.dumps(payload).encode("utf-8") if payload is not None else None
            request = Request(url, data=data, headers={"Accept": "application/json", "Content-Type": "application/json"}, method=method)
            try:
                with urlopen(request, timeout=180) as response:
                    value = json.loads(response.read().decode("utf-8"))
                if not isinstance(value, dict):
                    raise AppiumManagerError("Appium returned an unexpected response.")
                if isinstance(value.get("value"), dict) and value["value"].get("error"):
                    detail = value["value"].get("message") or value["value"].get("error")
                    raise AppiumManagerError(f"Appium: {detail}")
                return value
            except HTTPError as error:
                body = error.read().decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(body)
                    nested = parsed.get("value", parsed)
                    detail = nested.get("message") or nested.get("error") if isinstance(nested, dict) else body
                except json.JSONDecodeError:
                    detail = body
                last_error = f"Appium HTTP {error.code}: {detail}"[:1200]
                if error.code == 404:
                    continue
                break
            except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
                last_error = f"Cannot reach Appium server: {error}"
                break
            except AppiumManagerError:
                raise
        raise AppiumManagerError(last_error)

    def start_server(self) -> dict[str, Any]:
        """Start the repository-local Appium server without requiring a global install."""
        global _SERVER_PROCESS, _SERVER_LOG
        if not self.settings.enabled:
            raise AppiumManagerError("Enable Appium in the Mobile Automation agent settings first.")
        server_url = self._normalize_server_url(self.settings.server_url)
        parsed = urlsplit(server_url)
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise AppiumManagerError("For safety, the managed Appium server can only bind to localhost.")
        if parsed.scheme != "http":
            raise AppiumManagerError("The project-managed Appium server currently supports local http:// URLs only.")
        app_root = Path(__file__).resolve().parents[1]
        appium_root = app_root / "tools" / "appium"
        appium_bin = appium_root / "node_modules" / ".bin" / "appium"
        if not appium_bin.exists():
            raise AppiumManagerError("Project-local Appium is not installed yet. Run the Appium setup command from the project README.")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with _SERVER_LOCK:
            if _SERVER_PROCESS is not None and _SERVER_PROCESS.poll() is None:
                return {"started": False, "already_running": True, "server_url": server_url, "pid": _SERVER_PROCESS.pid}
            if self._server_is_reachable(server_url):
                return {"started": False, "already_running": True, "server_url": server_url, "pid": None}
            log_dir = app_root / "data"
            log_dir.mkdir(parents=True, exist_ok=True)
            _SERVER_LOG = (log_dir / "appium.log").open("a", encoding="utf-8", buffering=1)
            env = dict(os.environ)
            env["APPIUM_HOME"] = str(appium_root / ".appium")
            node_dir = str(Path(shutil.which("node") or "/opt/homebrew/bin/node").parent)
            env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")
            command = [str(appium_bin), "--address", host, "--port", str(port)]
            base_path = parsed.path.rstrip("/")
            if base_path:
                command.extend(["--base-path", base_path])
            _SERVER_PROCESS = subprocess.Popen(
                command,
                cwd=str(appium_root), env=env, stdout=_SERVER_LOG, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            return {"started": True, "already_running": False, "server_url": server_url, "pid": _SERVER_PROCESS.pid}

    def stop_server(self) -> dict[str, Any]:
        """Stop only the Appium process started by this runtime; never kill an external server."""
        global _SERVER_PROCESS, _SERVER_LOG
        with _SERVER_LOCK:
            process = _SERVER_PROCESS
            if process is None or process.poll() is not None:
                _SERVER_PROCESS = None
                return {"stopped": False, "already_stopped": True}
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            _SERVER_PROCESS = None
            if _SERVER_LOG is not None:
                _SERVER_LOG.close()
                _SERVER_LOG = None
            return {"stopped": True, "already_stopped": False}

    @classmethod
    def _server_is_reachable(cls, server_url: str) -> bool:
        try:
            cls._get_status(server_url)
            return True
        except AppiumManagerError:
            return False

    @staticmethod
    def _normalize_server_url(value: str) -> str:
        raw = str(value or "").strip().rstrip("/")
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise AppiumManagerError("Appium server URL must be an http(s) URL without embedded credentials.")
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))

    @classmethod
    def _get_status(cls, server_url: str) -> dict[str, Any]:
        candidates = [f"{server_url}/status"]
        if not urlsplit(server_url).path.endswith("/wd/hub"):
            candidates.append(f"{server_url}/wd/hub/status")
        last_error = "Appium status endpoint did not respond."
        for url in candidates:
            request = Request(url, headers={"Accept": "application/json"}, method="GET")
            try:
                with urlopen(request, timeout=3) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if isinstance(payload, dict):
                    return payload
                last_error = "Appium returned an unexpected status payload."
            except HTTPError as error:
                last_error = f"Appium status returned HTTP {error.code}."
                if error.code != 404:
                    break
            except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
                last_error = f"Cannot reach Appium server: {error}"
                break
        raise AppiumManagerError(last_error)

    def _list_android_devices(self) -> tuple[list[dict[str, str]], bool, str]:
        executable = str(self.settings.adb_path or "adb").strip() or "adb"
        resolved = shutil.which(executable)
        if not resolved:
            return [], False, f"ADB executable not found: {executable}"
        try:
            completed = subprocess.run(
                [resolved, "devices", "-l"], capture_output=True, text=True,
                timeout=8, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return [], True, f"Could not query ADB devices: {error}"
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "ADB command failed.").strip()
            return [], True, message[:500]

        devices: list[dict[str, str]] = []
        for line in completed.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 2:
                continue
            details = {
                key: value for part in parts[2:] if ":" in part
                for key, value in [part.split(":", 1)]
            }
            devices.append({
                "id": parts[0],
                "platform": "Android",
                "state": parts[1],
                "model": details.get("model", "").replace("_", " "),
                "product": details.get("product", ""),
                "device": details.get("device", ""),
            })
        return devices, True, ""

    def _list_ios_devices(self) -> tuple[list[dict[str, str]], str]:
        devices: list[dict[str, str]] = []
        executable = str(self.settings.ios_device_tool or "idevice_id").strip() or "idevice_id"
        resolved = shutil.which(executable)
        if not resolved and not executable.startswith("/"):
            # GUI-launched runtime processes often do not inherit Homebrew's PATH.
            # Check the standard Apple Silicon and Intel Homebrew locations too.
            resolved = next(
                (
                    candidate
                    for candidate in (
                        "/opt/homebrew/bin/idevice_id",
                        "/usr/local/bin/idevice_id",
                    )
                    if shutil.which(candidate)
                ),
                None,
            )
        if resolved:
            try:
                completed = subprocess.run([resolved, "-l"], capture_output=True, text=True, timeout=8, check=False)
                if completed.returncode == 0:
                    devices.extend({
                        "id": line.strip(), "platform": "iOS", "state": "device",
                        "model": "iPhone / iPad", "product": "", "device": "",
                    } for line in completed.stdout.splitlines() if line.strip())
            except (OSError, subprocess.TimeoutExpired):
                pass

        xcrun = shutil.which("xcrun")
        if xcrun:
            try:
                completed = subprocess.run(
                    [xcrun, "simctl", "list", "devices", "booted", "--json"],
                    capture_output=True, text=True, timeout=8, check=False,
                )
                if completed.returncode == 0:
                    payload = json.loads(completed.stdout)
                    groups = payload.get("devices") if isinstance(payload, dict) else {}
                    for runtime_devices in groups.values() if isinstance(groups, dict) else []:
                        for device in runtime_devices if isinstance(runtime_devices, list) else []:
                            if not isinstance(device, dict) or not device.get("udid"):
                                continue
                            devices.append({
                                "id": str(device["udid"]), "platform": "iOS Simulator",
                                "state": "device" if device.get("state") == "Booted" else str(device.get("state", "unknown")),
                                "model": str(device.get("name") or "iOS Simulator"),
                                "product": "", "device": "",
                            })
            except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
                pass

        deduplicated = {device["id"]: device for device in devices}
        detail = "iOS discovery ready" if resolved or xcrun else f"For connected iPhones install/configure {executable}; xcrun is used for booted simulators."
        return list(deduplicated.values()), detail
