from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent_runtime.codex_bridge import CodexCliBridge


class CodexCliBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.temporary_directory.name)
        self.calls: list[dict[str, object]] = []
        self.runner_stdout: list[str] = []

        def fake_runner(args, prompt, cwd, env, output_file):
            self.calls.append(
                {
                    "args": list(args),
                    "prompt": prompt,
                    "cwd": str(cwd),
                    "env": dict(env),
                    "output_file": str(output_file),
                }
            )
            stdout = self.runner_stdout.pop(0) if self.runner_stdout else ""
            Path(output_file).write_text("bridge reply", encoding="utf-8")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

        self.bridge = CodexCliBridge(self.workspace_root, runner=fake_runner)
        self.bridge.codex_binary = "/usr/local/bin/codex"

    async def asyncTearDown(self):
        self.temporary_directory.cleanup()

    async def test_ask_persists_history_and_builds_prompt(self):
        self.runner_stdout = [
            "\n".join(
                [
                    '{"type":"thread.started","thread_id":"thread-123"}',
                    '{"type":"item.completed","item":{"type":"message","content":"bridge reply"}}',
                ]
            ),
            "\n".join(
                [
                    '{"type":"item.completed","item":{"type":"message","content":"bridge reply"}}',
                ]
            ),
        ]
        first = await self.bridge.ask("discord-channel", "ciao")
        second = await self.bridge.ask("discord-channel", "come va?")

        self.assertEqual("bridge reply", first.final_response)
        self.assertEqual("bridge reply", second.final_response)
        self.assertEqual(2, len(self.calls))
        self.assertIn("USER: ciao", str(self.calls[0]["prompt"]))
        self.assertIn("ASSISTANT:", str(self.calls[0]["prompt"]))
        self.assertEqual("ciao", str(self.calls[0]["prompt"]).strip().splitlines()[-2].removeprefix("USER: ").strip())
        self.assertEqual("resume", str(self.calls[1]["args"][1]))
        self.assertEqual("thread-123", str(self.calls[1]["args"][-2]))
        self.assertEqual("come va?", str(self.calls[1]["args"][-1]))
        self.assertTrue((self.workspace_root / "data" / "discord_codex_bridge.json").is_file())
        payload = json.loads((self.workspace_root / "data" / "discord_codex_bridge.json").read_text(encoding="utf-8"))
        self.assertIn("discord-channel", payload["channels"])
        self.assertEqual("thread-123", payload["channels"]["discord-channel"]["session_id"])

    async def test_sync_auth_material_copies_source_auth(self):
        source_home = self.workspace_root / "source-codex-home"
        source_home.mkdir(parents=True, exist_ok=True)
        auth_path = source_home / "auth.json"
        auth_path.write_text('{"tokens":{"access_token":"token"}}', encoding="utf-8")
        bridge = CodexCliBridge(self.workspace_root, codex_home=self.workspace_root / "bridge-home", runner=lambda *args: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""))
        bridge.source_codex_home = source_home

        bridge._sync_auth_material()

        copied = (self.workspace_root / "bridge-home" / "auth.json").read_text(encoding="utf-8")
        self.assertIn("access_token", copied)

    async def test_channel_model_override_is_persisted(self):
        self.assertEqual("", self.bridge.get_channel_model("discord-channel"))
        self.assertEqual("gpt-5.1-codex", self.bridge.set_channel_model("discord-channel", "gpt-5.1-codex"))
        self.assertEqual("gpt-5.1-codex", self.bridge.get_channel_model("discord-channel"))

        payload = json.loads((self.workspace_root / "data" / "discord_codex_bridge.json").read_text(encoding="utf-8"))
        self.assertEqual("gpt-5.1-codex", payload["channels"]["discord-channel"]["model"])

        self.bridge.clear_channel_model("discord-channel")
        self.assertEqual("", self.bridge.get_channel_model("discord-channel"))
