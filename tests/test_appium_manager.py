from __future__ import annotations

import unittest
import subprocess
import base64
from unittest.mock import MagicMock, patch

from agent_runtime import appium_manager
from agent_runtime.appium_manager import AppiumManager, AppiumManagerError
from agent_runtime.models import AppiumSettings


class AppiumManagerTests(unittest.TestCase):
    def test_status_reports_server_and_adb_device_inventory(self) -> None:
        settings = AppiumSettings(enabled=True, server_url="http://127.0.0.1:4723/")
        with (
            patch.object(AppiumManager, "_get_status", return_value={"value": {"ready": True, "build": {"version": "2.11.0"}}}),
            patch.object(AppiumManager, "_list_android_devices", return_value=([{"id": "emulator-5554", "state": "device", "model": "Pixel_8", "product": "pixel", "device": "husky"}], True, "")),
            patch.object(AppiumManager, "_list_ios_devices", return_value=([], "iOS discovery unavailable")),
        ):
            status = AppiumManager(settings).status()

        self.assertTrue(status["server_connected"])
        self.assertEqual("2.11.0", status["server_version"])
        self.assertEqual("http://127.0.0.1:4723", status["server_url"])
        self.assertEqual(1, status["device_count"])
        self.assertEqual("emulator-5554", status["devices"][0]["id"])
        self.assertFalse(status["control_enabled"])

    def test_counts_ios_devices_with_android_inventory(self) -> None:
        with (
            patch.object(AppiumManager, "_get_status", return_value={"value": {"ready": True}}),
            patch.object(AppiumManager, "_list_android_devices", return_value=([], True, "")),
            patch.object(AppiumManager, "_list_ios_devices", return_value=([{"id": "iphone-udid", "platform": "iOS", "state": "device", "model": "iPhone / iPad"}], "iOS discovery ready")),
        ):
            status = AppiumManager(AppiumSettings(enabled=True)).status()

        self.assertEqual(1, status["device_count"])
        self.assertEqual(1, status["ios_device_count"])
        self.assertEqual("iOS", status["devices"][0]["platform"])

    def test_finds_idevice_id_in_homebrew_path_when_not_on_runtime_path(self) -> None:
        def which(path: str) -> str | None:
            return "/opt/homebrew/bin/idevice_id" if path == "/opt/homebrew/bin/idevice_id" else None

        completed = subprocess.CompletedProcess(
            args=["/opt/homebrew/bin/idevice_id", "-l"], returncode=0,
            stdout="iphone-udid\n", stderr="",
        )
        with (
            patch("agent_runtime.appium_manager.shutil.which", side_effect=which),
            patch("agent_runtime.appium_manager.subprocess.run", return_value=completed) as run,
        ):
            devices, detail = AppiumManager(AppiumSettings())._list_ios_devices()

        self.assertEqual("iOS discovery ready", detail)
        self.assertEqual("iphone-udid", devices[0]["id"])
        self.assertEqual("/opt/homebrew/bin/idevice_id", run.call_args.args[0][0])

    def test_disabled_integration_does_not_probe_appium(self) -> None:
        with (
            patch.object(AppiumManager, "_get_status") as get_status,
            patch.object(AppiumManager, "_list_android_devices", return_value=([], False, "ADB missing")),
        ):
            status = AppiumManager(AppiumSettings(enabled=False)).status()

        get_status.assert_not_called()
        self.assertFalse(status["server_connected"])
        self.assertIn("disabled", status["server_error"].lower())
        self.assertEqual("ADB missing", status["adb_error"])

    def test_rejects_server_url_with_embedded_credentials(self) -> None:
        with self.assertRaises(AppiumManagerError):
            AppiumManager(AppiumSettings(enabled=True, server_url="http://user:pass@127.0.0.1:4723")).status()

    def test_start_server_uses_local_project_install_and_appium_home(self) -> None:
        process = MagicMock()
        process.poll.return_value = None
        process.pid = 1234
        appium_manager._SERVER_PROCESS = None
        appium_manager._SERVER_LOG = None
        with (
            patch.object(AppiumManager, "_server_is_reachable", return_value=False),
            patch("agent_runtime.appium_manager.Path.mkdir"),
            patch("agent_runtime.appium_manager.Path.open", return_value=MagicMock()),
            patch("agent_runtime.appium_manager.subprocess.Popen", return_value=process) as popen,
        ):
            result = AppiumManager(AppiumSettings(enabled=True)).start_server()

        self.assertTrue(result["started"])
        self.assertEqual(1234, result["pid"])
        command = popen.call_args.args[0]
        self.assertIn("tools/appium/node_modules/.bin/appium", command[0])
        self.assertEqual("127.0.0.1", command[command.index("--address") + 1])
        self.assertIn("tools/appium/.appium", popen.call_args.kwargs["env"]["APPIUM_HOME"])
        appium_manager._SERVER_PROCESS = None
        appium_manager._SERVER_LOG = None

    def test_stop_only_terminates_server_owned_by_manager(self) -> None:
        process = MagicMock()
        process.poll.return_value = None
        process.wait.return_value = 0
        appium_manager._SERVER_PROCESS = process
        appium_manager._SERVER_LOG = None

        result = AppiumManager(AppiumSettings(enabled=True)).stop_server()

        self.assertTrue(result["stopped"])
        process.terminate.assert_called_once()
        appium_manager._SERVER_PROCESS = None

    def test_lists_installed_ios_apps_and_closes_temporary_session(self) -> None:
        manager = AppiumManager(AppiumSettings(enabled=True))
        with (
            patch.object(manager, "status", return_value={"server_connected": True, "server_error": "", "devices": [{"id": "iphone-udid", "platform": "iOS", "state": "device"}]}),
            patch.object(manager, "_create_ios_session", return_value="session-1"),
            patch.object(manager, "_appium_request", return_value={"value": {"lt.manodrabuziai.fr": {"CFBundleName": "Vinted", "CFBundleVersion": "123"}}}) as request,
            patch.object(manager, "_delete_session") as delete,
        ):
            apps = manager.list_ios_apps("iphone-udid")

        self.assertEqual([{"bundle_id": "lt.manodrabuziai.fr", "name": "Vinted", "version": "123"}], apps)
        request.assert_called_once()
        self.assertEqual("POST", request.call_args.args[0])
        delete.assert_called_once_with("session-1")

    def test_launches_only_selected_connected_ios_app_and_tracks_session(self) -> None:
        manager = AppiumManager(AppiumSettings(enabled=True))
        appium_manager._DEVICE_SESSION_ID = ""
        appium_manager._DEVICE_SESSION_ID_UDID = ""
        appium_manager._DEVICE_SESSION_BUNDLE_ID = ""
        with (
            patch.object(manager, "status", return_value={"server_connected": True, "server_error": "", "devices": [{"id": "iphone-udid", "platform": "iOS", "state": "device"}]}),
            patch.object(manager, "_create_ios_session", return_value="session-2") as create,
        ):
            result = manager.launch_ios_app("iphone-udid", "lt.manodrabuziai.fr")

        self.assertTrue(result["launched"])
        self.assertEqual("session-2", appium_manager._DEVICE_SESSION_ID)
        self.assertEqual("lt.manodrabuziai.fr", appium_manager._DEVICE_SESSION_BUNDLE_ID)
        create.assert_called_once_with("iphone-udid", bundle_id="lt.manodrabuziai.fr")
        appium_manager._DEVICE_SESSION_ID = ""
        appium_manager._DEVICE_SESSION_ID_UDID = ""
        appium_manager._DEVICE_SESSION_BUNDLE_ID = ""

    def test_rejects_malformed_bundle_id(self) -> None:
        with self.assertRaises(AppiumManagerError):
            AppiumManager._validate_bundle_id("Vinted / invalid")

    def test_screenshot_requires_active_session_and_returns_valid_png(self) -> None:
        manager = AppiumManager(AppiumSettings(enabled=True))
        appium_manager._DEVICE_SESSION_ID = "session-screen"
        png = b"\x89PNG\r\n\x1a\nsmall-png"
        with patch.object(manager, "_appium_request", return_value={"value": base64.b64encode(png).decode()}) as request:
            self.assertEqual(png, manager.get_device_screenshot())
        request.assert_called_once_with("GET", "/session/session-screen/screenshot")
        appium_manager._DEVICE_SESSION_ID = ""


if __name__ == "__main__":
    unittest.main()
