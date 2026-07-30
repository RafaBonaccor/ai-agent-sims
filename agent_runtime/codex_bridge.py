from __future__ import annotations

import contextlib
import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


CodexRunner = Callable[[list[str], str, Path, dict[str, str], Path], subprocess.CompletedProcess[str]]


@dataclass
class CodexConversationState:
    messages: list[dict[str, str]] = field(default_factory=list)
    session_id: str = ""
    model: str = ""


@dataclass
class CodexTurnResult:
    messages: list[str] = field(default_factory=list)
    final_response: str = ""
    session_id: str = ""


class CodexCliBridge:
    """Local bridge to the Codex CLI for Discord chat.

    The bridge keeps a lightweight conversation history per Discord channel and
    feeds it back into `codex exec` on every message so the interaction stays
    continuous without depending on a live TUI attachment.
    """

    def __init__(
        self,
        workspace_root: Path,
        *,
        logger: Optional[logging.Logger] = None,
        codex_home: Optional[Path] = None,
        runner: Optional[CodexRunner] = None,
    ):
        self.workspace_root = workspace_root.resolve()
        self.logger = logger or logging.getLogger("agent_lab.codex_bridge")
        self.codex_binary = shutil.which("codex")
        self.codex_home = codex_home or (self.workspace_root / ".codex-discord-bridge")
        self.source_codex_home = Path(
            os.environ.get("AGENT_LAB_CODEX_SOURCE_HOME")
            or os.environ.get("CODEX_HOME")
            or (Path.home() / ".codex")
        ).expanduser().resolve()
        self.state_path = self.workspace_root / "data" / "discord_codex_bridge.json"
        self._runner = runner or self._default_runner
        self._lock = asyncio.Lock()
        self._state = self._load_state()

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.codex_binary),
            "codexBinary": self.codex_binary or "",
            "codexHome": str(self.codex_home),
            "defaultModel": self._default_model(),
            "channels": len(self._state.get("channels", {})),
        }

    async def ask(self, channel_key: str, prompt: str) -> CodexTurnResult:
        channel_key = str(channel_key or "").strip() or "default"
        prompt = str(prompt or "").strip()
        if not prompt:
            raise ValueError("Prompt is empty.")
        async with self._lock:
            channel_state = self._channel_state(channel_key)
            result = await asyncio.to_thread(
                self._invoke_codex,
                channel_state,
                prompt,
            )
            channel_state.messages.extend(
                [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": result.final_response or ""},
                ]
            )
            channel_state.messages = channel_state.messages[-24:]
            if result.session_id:
                channel_state.session_id = result.session_id
                self._state.setdefault("channels", {}).setdefault(channel_key, {})["session_id"] = result.session_id
            self._save_state()
            return result

    def get_channel_model(self, channel_key: str) -> str:
        return self._channel_state(channel_key).model.strip()

    def set_channel_model(self, channel_key: str, model: str) -> str:
        channel_key = str(channel_key or "").strip() or "default"
        model = str(model or "").strip()
        channel_state = self._channel_state(channel_key)
        channel_state.model = model
        self._state.setdefault("channels", {}).setdefault(channel_key, {})["model"] = model
        self._save_state()
        return model

    def clear_channel_model(self, channel_key: str) -> None:
        self.set_channel_model(channel_key, "")

    def _channel_state(self, channel_key: str) -> CodexConversationState:
        channels = self._state.setdefault("channels", {})
        raw_state = channels.get(channel_key)
        if not isinstance(raw_state, dict):
            raw_state = {}
        state = CodexConversationState(
            messages=[
                {
                    "role": str(message.get("role", "user")),
                    "content": str(message.get("content", "")),
                }
                for message in list(raw_state.get("messages", []) or [])
                if isinstance(message, dict)
            ],
            session_id=str(raw_state.get("session_id", "") or ""),
            model=str(raw_state.get("model", "") or ""),
        )
        channels[channel_key] = {
            "messages": state.messages,
            "session_id": state.session_id,
            "model": state.model,
        }
        return state

    def _invoke_codex(self, state: CodexConversationState, prompt: str) -> CodexTurnResult:
        if not self.codex_binary:
            raise RuntimeError("Codex CLI executable not found on PATH.")
        self.codex_home.mkdir(parents=True, exist_ok=True)
        self._sync_auth_material()
        temp_dir = self.workspace_root / "data" / "codex_bridge"
        temp_dir.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix="codex-last-", suffix=".txt", dir=temp_dir)
        os.close(fd)
        last_message_path = Path(temp_path)
        env = os.environ.copy()
        env["CODEX_HOME"] = str(self.codex_home)
        model = str(state.model or os.environ.get("AGENT_LAB_CODEX_MODEL", "") or "").strip()
        completed = self._invoke_session(
            state.session_id,
            prompt,
            last_message_path,
            env,
            model,
        )
        if completed.returncode != 0:
            if state.session_id:
                self.logger.warning(
                    "codex_resume_failed channel_session=%s; falling back to exec",
                    state.session_id,
                )
                state.session_id = ""
                completed = self._invoke_session(
                    "",
                    self._build_prompt(state.messages, prompt),
                    last_message_path,
                    env,
                    model,
                )
                if completed.returncode != 0:
                    raise RuntimeError(self._format_failure(completed))
            else:
                raise RuntimeError(self._format_failure(completed))
        transcript = self._collect_transcript(completed.stdout)
        session_id = self._read_session_id(completed.stdout) or state.session_id
        if not transcript.final_response:
            with contextlib.suppress(FileNotFoundError):
                if last_message_path.exists():
                    transcript.final_response = last_message_path.read_text(encoding="utf-8").strip()
                    if transcript.final_response:
                        transcript.messages.append(transcript.final_response)
        if not transcript.final_response:
            raise RuntimeError("Codex CLI returned an empty response.")
        with contextlib.suppress(FileNotFoundError):
            if last_message_path.exists():
                last_message_path.unlink()
        transcript.session_id = session_id
        return transcript

    def _sync_auth_material(self) -> None:
        source_auth = self.source_codex_home / "auth.json"
        destination_auth = self.codex_home / "auth.json"
        if not source_auth.exists():
            return
        try:
            source_mtime = source_auth.stat().st_mtime_ns
            destination_mtime = destination_auth.stat().st_mtime_ns if destination_auth.exists() else -1
        except OSError:
            source_mtime = 0
            destination_mtime = -1
        if destination_auth.exists() and destination_mtime >= source_mtime:
            return
        destination_auth.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_auth, destination_auth)

    @staticmethod
    def _default_model() -> str:
        return str(os.environ.get("AGENT_LAB_CODEX_MODEL", "") or "").strip()

    def _invoke_session(
        self,
        session_id: str,
        prompt: str,
        last_message_path: Path,
        env: dict[str, str],
        model: str,
    ) -> subprocess.CompletedProcess[str]:
        if session_id:
            args = [
                self.codex_binary or "codex",
                "resume",
                "--json",
                "--output-last-message",
                str(last_message_path),
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                session_id,
                prompt,
            ]
        else:
            args = [
                self.codex_binary or "codex",
                "exec",
                "--json",
                "--output-last-message",
                str(last_message_path),
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
            ]
            if model:
                args.extend(["-m", model])
            return self._runner(args, self._build_prompt([], prompt), self.workspace_root, env, last_message_path)
        if model:
            args.extend(["-m", model])
        return self._runner(args, prompt, self.workspace_root, env, last_message_path)

    @staticmethod
    def _build_prompt(history: list[dict[str, str]], prompt: str) -> str:
        lines = [
            "You are Codex, the user's terminal assistant connected through a Discord bridge.",
            "Keep continuity with the recent conversation and answer directly.",
            "If the user asks for code or architecture changes, be explicit about the next step and the tradeoff.",
            "Do not mention bridge internals unless the user asks about the connection itself.",
            "",
            "Conversation so far:",
        ]
        for message in history[-16:]:
            role = str(message.get("role", "user")).strip().upper() or "USER"
            content = str(message.get("content", "")).strip()
            if content:
                lines.append(f"{role}: {content}")
        lines.extend(
            [
                "",
                f"USER: {prompt}",
                "ASSISTANT:",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _collect_transcript(stdout: str) -> CodexTurnResult:
        transcript = CodexTurnResult()
        for raw_line in str(stdout or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("type") != "item.completed":
                continue
            item = payload.get("item", {})
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", "") or "").strip()
            if item_type == "reasoning":
                text = str(item.get("text", "") or "").strip()
                if text:
                    transcript.messages.append(f"🧠 {text}")
                continue
            if item_type == "agent_message":
                text = str(item.get("text", "") or "").strip()
                if text:
                    transcript.messages.append(text)
                    transcript.final_response = text
                continue
            if item_type == "command_execution":
                command = str(item.get("command", "") or "").strip()
                output = str(item.get("aggregated_output", "") or "").rstrip()
                if command or output:
                    chunk = "```text\n"
                    if command:
                        chunk += f"$ {command}\n"
                    if output:
                        chunk += output
                        if not output.endswith("\n"):
                            chunk += "\n"
                    chunk += "```"
                    transcript.messages.append(chunk)
                continue
            text = str(item.get("text", "") or item.get("content", "") or item.get("message", "") or "").strip()
            if text:
                transcript.messages.append(text)
                transcript.final_response = text
        return transcript

    @staticmethod
    def _read_session_id(stdout: str) -> str:
        for raw_line in str(stdout or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("type") == "thread.started":
                thread_id = str(payload.get("thread_id", "") or payload.get("id", "") or "").strip()
                if thread_id:
                    return thread_id
        return ""

    @staticmethod
    def _format_failure(completed: subprocess.CompletedProcess[str]) -> str:
        stderr = str(completed.stderr or "").strip()
        stdout = str(completed.stdout or "").strip()
        details = stderr or stdout or "unknown Codex CLI failure"
        return f"Codex CLI failed with exit code {completed.returncode}: {details}"

    @staticmethod
    def _default_runner(
        args: list[str],
        prompt: str,
        cwd: Path,
        env: dict[str, str],
        output_file: Path,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            input=prompt,
            text=True,
            capture_output=True,
            cwd=str(cwd),
            env=env,
            check=False,
        )

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"version": 1, "channels": {}}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "channels": {}}
        channels = payload.get("channels", {})
        if not isinstance(channels, dict):
            channels = {}
        return {"version": 1, "channels": channels}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._state, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, self.state_path)
