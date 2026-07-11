from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from .models import utc_now


class BrowserControlError(RuntimeError):
    """Raised when a live browser session cannot execute a command."""


@dataclass
class BrowserSessionInfo:
    id: str
    backend: str
    project_id: str
    state: str = "opening"
    current_url: str = ""
    created_at: str = field(default_factory=lambda: utc_now().isoformat())
    updated_at: str = field(default_factory=lambda: utc_now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "backend": self.backend,
            "project_id": self.project_id,
            "state": self.state,
            "current_url": self.current_url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    def touch(self, current_url: str = "") -> None:
        if current_url:
            self.current_url = current_url
        self.updated_at = utc_now().isoformat()


class BrowserSession:
    info: BrowserSessionInfo

    async def command(self, command: str, parameters: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError


class MockBrowserSession(BrowserSession):
    """Deterministic in-memory browser for end-to-end runtime tests."""

    def __init__(
        self,
        session_id: str,
        project_id: str,
        url: str = "",
        page_text: str = "",
        title: str = "Mock browser page",
    ):
        self.info = BrowserSessionInfo(
            id=session_id,
            backend="mock",
            project_id=project_id,
            state="ready",
            current_url=url,
            metadata={"title": title, "test_backend": True},
        )
        self.page_text = page_text or "Mock browser page"
        self.title = title
        self.typed_values: dict[str, str] = {}
        self.clicked: list[dict[str, str]] = []
        self.history: list[dict[str, Any]] = []

    async def command(self, command: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if self.info.state == "closed":
            raise BrowserControlError(f"Browser session is closed: {self.info.id}")
        clean_command = command.strip().lower().replace("-", "_")
        self.history.append({"command": clean_command, "parameters": dict(parameters)})

        if clean_command == "current_url":
            return self._result({"url": self.info.current_url})
        if clean_command == "goto":
            url = str(parameters.get("url", "")).strip()
            if not url:
                raise BrowserControlError("browser.goto requires a non-empty url")
            self.info.current_url = url
            self.title = str(parameters.get("title", "") or self.title)
            self.page_text = str(parameters.get("page_text", "") or self.page_text)
            return self._result({"url": self.info.current_url, "navigated": True})
        if clean_command == "click_text":
            text = str(parameters.get("text", "")).strip()
            if not text:
                raise BrowserControlError("browser.click_text requires text")
            self.clicked.append({"type": "text", "value": text})
            return self._result({"clicked": True, "text": text})
        if clean_command == "click_selector":
            selector = str(parameters.get("selector", "")).strip()
            if not selector:
                raise BrowserControlError("browser.click_selector requires selector")
            self.clicked.append({"type": "selector", "value": selector})
            return self._result({"clicked": True, "selector": selector})
        if clean_command == "type":
            selector = str(parameters.get("selector", "")).strip()
            value = str(parameters.get("value", ""))
            if not selector:
                raise BrowserControlError("browser.type requires selector")
            self.typed_values[selector] = value
            return self._result({"typed": True, "selector": selector, "characters": len(value)})
        if clean_command == "extract":
            return self._result(self._extract(parameters))
        if clean_command == "snapshot":
            return self._result(self._snapshot())
        if clean_command == "screenshot":
            return self._result(
                {
                    "available": False,
                    "path": "",
                    "reason": "The mock backend does not create bitmap screenshots.",
                }
            )
        if clean_command == "close":
            await self.close()
            return {"closed": True}
        raise BrowserControlError(f"Unsupported browser command: {command}")

    async def close(self) -> None:
        self.info.state = "closed"
        self.info.touch()

    def _result(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.info.touch(str(payload.get("url", "") or ""))
        return {"session": self.info.as_dict(), **payload}

    def _extract(self, parameters: dict[str, Any]) -> dict[str, Any]:
        selector = str(parameters.get("selector", "body") or "body").strip()
        mode = str(parameters.get("mode", "text") or "text").strip().lower()
        all_matches = bool(parameters.get("all", False))

        if selector in {"title", "head title"}:
            value: Any = self.title
        elif selector in self.typed_values:
            value = self.typed_values[selector]
        elif selector in {"body", "main", "html", "*"}:
            value = self.page_text
        else:
            value = ""

        if mode == "html" and value:
            value = f"<div>{value}</div>"
        if all_matches and isinstance(value, str):
            value = [value] if value else []
        return {"selector": selector, "mode": mode, "value": value}

    def _snapshot(self) -> dict[str, Any]:
        return {
            "url": self.info.current_url,
            "title": self.title,
            "text": self.page_text,
            "typed_values": dict(self.typed_values),
            "clicked": list(self.clicked),
            "history": list(self.history),
        }


class SubprocessBrowserSession(BrowserSession):
    """JSONL client for the Botasaurus bridge process."""

    def __init__(
        self,
        session_id: str,
        project_id: str,
        python_executable: Path,
        bridge_script: Path,
        project_root: Path,
        config: dict[str, Any],
        timeout_seconds: float = 30.0,
    ):
        self.info = BrowserSessionInfo(
            id=session_id,
            backend="botasaurus",
            project_id=project_id,
            metadata={
                "project_root": str(project_root),
                "bridge_script": str(bridge_script),
                "browser_mode": config.get("browser_mode", ""),
            },
        )
        self.python_executable = python_executable
        self.bridge_script = bridge_script
        self.project_root = project_root
        self.config = config
        self.timeout_seconds = timeout_seconds
        self.process: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = (
            str(self.project_root)
            if not env.get("PYTHONPATH")
            else f"{self.project_root}{os.pathsep}{env['PYTHONPATH']}"
        )
        arguments = [
            str(self.python_executable),
            str(self.bridge_script),
            "--session-id",
            self.info.id,
            "--browser-mode",
            str(self.config.get("browser_mode", "sessione_persistente")),
            "--browser-user-data-dir",
            str(self.config.get("browser_user_data_dir", "")),
            "--browser-profile-directory",
            str(self.config.get("browser_profile_directory", "Default")),
        ]
        if self.config.get("refresh_browser_profile"):
            arguments.append("--refresh-browser-profile")
        initial_url = str(self.config.get("url", "") or "").strip()
        if initial_url:
            arguments.extend(["--url", initial_url])

        self.process = await asyncio.create_subprocess_exec(
            *arguments,
            cwd=str(self.project_root),
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        ready = await self._read_response(expected_type="ready", timeout=self.timeout_seconds)
        if not ready.get("ok", False):
            raise BrowserControlError(str(ready.get("error") or "Botasaurus bridge failed to start"))
        self.info.state = "ready"
        result = ready.get("result") or {}
        if isinstance(result, dict):
            self.info.touch(str(result.get("url", "") or ""))

    async def command(self, command: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if self.info.state == "closed":
            raise BrowserControlError(f"Browser session is closed: {self.info.id}")
        if self.process is None or self.process.stdin is None:
            raise BrowserControlError("Browser bridge process is not running")
        async with self._lock:
            request_id = f"cmd-{uuid4().hex[:12]}"
            payload = {
                "id": request_id,
                "command": command,
                "parameters": parameters,
            }
            self.process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
            await self.process.stdin.drain()
            response = await self._read_response(expected_id=request_id, timeout=self.timeout_seconds)
        if not response.get("ok", False):
            raise BrowserControlError(str(response.get("error") or f"Browser command failed: {command}"))
        result = response.get("result") or {}
        if not isinstance(result, dict):
            result = {"value": result}
        if command.strip().lower().replace("-", "_") == "close":
            self.info.state = "closed"
        session = result.get("session")
        if isinstance(session, dict):
            self.info.current_url = str(session.get("current_url", self.info.current_url) or "")
            self.info.state = str(session.get("state", self.info.state) or self.info.state)
            self.info.touch()
        else:
            self.info.touch(str(result.get("url", "") or ""))
        return result

    async def close(self) -> None:
        if self.info.state == "closed":
            return
        try:
            await self.command("close", {})
        except Exception:
            pass
        self.info.state = "closed"
        self.info.touch()
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=3)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()

    async def _read_response(
        self,
        expected_id: str = "",
        expected_type: str = "",
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        if self.process is None or self.process.stdout is None:
            raise BrowserControlError("Browser bridge process is not running")
        deadline = time.monotonic() + timeout
        ignored_lines: list[str] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BrowserControlError(
                    f"Timed out waiting for browser bridge response; ignored={ignored_lines[-3:]}"
                )
            line = await asyncio.wait_for(self.process.stdout.readline(), timeout=remaining)
            if not line:
                stderr = await self._read_stderr_tail()
                raise BrowserControlError(f"Browser bridge exited before responding. {stderr}".strip())
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                ignored_lines.append(text[:300])
                continue
            if expected_id and payload.get("id") != expected_id:
                ignored_lines.append(text[:300])
                continue
            if expected_type and payload.get("type") != expected_type:
                ignored_lines.append(text[:300])
                continue
            return payload

    async def _read_stderr_tail(self) -> str:
        if self.process is None or self.process.stderr is None:
            return ""
        try:
            data = await asyncio.wait_for(self.process.stderr.read(4000), timeout=0.2)
        except asyncio.TimeoutError:
            return ""
        text = data.decode("utf-8", errors="replace").strip()
        return text[-1000:] if text else ""


class BrowserControl:
    """Hybrid browser control manager.

    - `mock` sessions are deterministic and used for tests.
    - `botasaurus` sessions run the integration bridge against The Main Scraper.
    """

    def __init__(
        self,
        root: Path,
        default_project_id: str = "main-scraper",
        default_backend: str = "botasaurus",
        bridge_script: Optional[Path] = None,
    ):
        self.root = root.resolve()
        self.default_project_id = default_project_id
        self.default_backend = default_backend
        self.bridge_script = bridge_script.resolve() if bridge_script else None
        self.sessions: dict[str, BrowserSession] = {}

    def list_sessions(self) -> list[dict[str, Any]]:
        return [session.info.as_dict() for session in self.sessions.values()]

    async def open_session(
        self,
        *,
        project_id: str = "",
        backend: str = "",
        url: str = "",
        browser_mode: str = "sessione_persistente",
        browser_user_data_dir: str = "",
        browser_profile_directory: str = "Default",
        refresh_browser_profile: bool = False,
        page_text: str = "",
        title: str = "",
    ) -> dict[str, Any]:
        selected_project = project_id or self.default_project_id
        selected_backend = (backend or os.environ.get("AGENT_BROWSER_BACKEND") or self.default_backend).strip().lower()
        if selected_backend == "auto":
            selected_backend = self.default_backend
        session_id = f"browser-{uuid4().hex[:12]}"

        if selected_backend == "mock":
            session = MockBrowserSession(
                session_id=session_id,
                project_id=selected_project,
                url=url,
                page_text=page_text,
                title=title or "Mock browser page",
            )
            self.sessions[session_id] = session
            return {"session": session.info.as_dict()}

        if selected_backend != "botasaurus":
            raise BrowserControlError(f"Unsupported browser backend: {selected_backend}")

        project_root = self._project_root(selected_project)
        bridge_script = self.bridge_script or (self.root / "integrations" / selected_project / "botasaurus_bridge.py")
        if not bridge_script.is_file():
            raise BrowserControlError(f"Botasaurus bridge script is missing: {bridge_script}")
        python_executable = self._python_executable(selected_project, project_root)
        config = {
            "url": url,
            "browser_mode": browser_mode,
            "browser_user_data_dir": browser_user_data_dir,
            "browser_profile_directory": browser_profile_directory,
            "refresh_browser_profile": refresh_browser_profile,
        }
        session = SubprocessBrowserSession(
            session_id=session_id,
            project_id=selected_project,
            python_executable=python_executable,
            bridge_script=bridge_script,
            project_root=project_root,
            config=config,
        )
        self.sessions[session_id] = session
        try:
            await session.start()
        except Exception:
            self.sessions.pop(session_id, None)
            raise
        return {"session": session.info.as_dict()}

    async def command(self, session_id: str, command: str, parameters: dict[str, Any]) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        if session is None:
            raise BrowserControlError(f"Browser session not found: {session_id}")
        result = await session.command(command, parameters)
        if session.info.state == "closed":
            self.sessions.pop(session_id, None)
        return result

    async def close_session(self, session_id: str) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        if session is None:
            raise BrowserControlError(f"Browser session not found: {session_id}")
        await session.close()
        self.sessions.pop(session_id, None)
        return {"closed": True, "session_id": session_id}

    async def shutdown(self) -> None:
        for session_id in list(self.sessions):
            try:
                await self.close_session(session_id)
            except Exception:
                self.sessions.pop(session_id, None)

    def _project_entry(self, project_id: str) -> dict[str, Any]:
        registry_path = self.root / "config" / "projects.json"
        if not registry_path.is_file():
            raise BrowserControlError(f"Project registry is missing: {registry_path}")
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        for entry in registry.get("projects", []):
            if entry.get("id") == project_id:
                return entry
        raise BrowserControlError(f"Project is not registered: {project_id}")

    def _project_root(self, project_id: str) -> Path:
        entry = self._project_entry(project_id)
        path = (self.root / entry["root"]).resolve()
        if not path.is_relative_to(self.root / "projects"):
            raise BrowserControlError("Project root must remain inside projects/")
        if not path.is_dir():
            raise BrowserControlError(f"Project root is missing: {path}")
        return path

    def _python_executable(self, project_id: str, project_root: Path) -> Path:
        local_path = self.root / "config" / "projects.local.json"
        if local_path.exists():
            local = json.loads(local_path.read_text(encoding="utf-8"))
            configured = local.get("projects", {}).get(project_id, {}).get("pythonExecutable")
            if configured:
                path = Path(configured).expanduser()
                if path.is_file():
                    return path
        manifest = self._manifest(project_id)
        candidates = [
            *manifest.get("runtime", {}).get("venvCandidates", []),
            ".venv/bin/python",
            "../.venv/bin/python",
        ]
        for candidate in candidates:
            path = project_root / candidate
            if path.is_file():
                return path
        return Path(sys.executable).resolve()

    def _manifest(self, project_id: str) -> dict[str, Any]:
        entry = self._project_entry(project_id)
        path = (self.root / entry["integration"]).resolve()
        if not path.is_relative_to(self.root / "integrations"):
            raise BrowserControlError("Integration manifest must remain inside integrations/")
        if not path.is_file():
            raise BrowserControlError(f"Integration manifest is missing: {path}")
        return json.loads(path.read_text(encoding="utf-8"))
