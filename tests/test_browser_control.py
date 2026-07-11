import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from agent_runtime.browser_control import BrowserControl
from agent_runtime.execution import ModelExecutor
from agent_runtime.models import AgentSnapshot, ModelSettings, TaskRecord
from agent_runtime.storage import RuntimeStore


class BrowserControlTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "config").mkdir()
        (self.root / "integrations" / "main-scraper").mkdir(parents=True)
        (self.root / "projects" / "main-scraper").mkdir(parents=True)
        (self.root / "config" / "projects.json").write_text(
            json.dumps(
                {
                    "projects": [
                        {
                            "id": "main-scraper",
                            "name": "The Main Scraper",
                            "root": "projects/main-scraper",
                            "integration": "integrations/main-scraper/adapter.json",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (self.root / "integrations" / "main-scraper" / "adapter.json").write_text(
            json.dumps({"runtime": {"entrypoint": "main.py", "venvCandidates": []}, "actions": {}}),
            encoding="utf-8",
        )

    async def asyncTearDown(self):
        self.temporary_directory.cleanup()

    async def test_mock_session_supports_live_browser_commands(self):
        control = BrowserControl(self.root, default_backend="mock")
        opened = await control.open_session(
            backend="mock",
            url="https://example.test/start",
            page_text="Alpha lead from mock browser",
            title="Alpha",
        )
        session_id = opened["session"]["id"]

        current = await control.command(session_id, "current_url", {})
        self.assertEqual("https://example.test/start", current["url"])

        await control.command(session_id, "goto", {"url": "https://example.test/results"})
        await control.command(session_id, "type", {"selector": "#q", "value": "macbook"})
        await control.command(session_id, "click_text", {"text": "Search"})
        extracted = await control.command(session_id, "extract", {"selector": "body"})
        snapshot = await control.command(session_id, "snapshot", {})

        self.assertEqual("Alpha lead from mock browser", extracted["value"])
        self.assertEqual("macbook", snapshot["typed_values"]["#q"])
        self.assertEqual("Search", snapshot["clicked"][0]["value"])
        await control.close_session(session_id)
        self.assertEqual([], control.list_sessions())

    async def test_subprocess_bridge_uses_the_same_jsonl_protocol_as_botasaurus(self):
        bridge = Path(__file__).parent / "fixtures" / "mock_browser_bridge.py"
        control = BrowserControl(self.root, default_backend="botasaurus", bridge_script=bridge)

        opened = await control.open_session(backend="botasaurus", url="https://example.test")
        session_id = opened["session"]["id"]
        self.assertEqual("botasaurus", opened["session"]["backend"])

        await control.command(session_id, "goto", {"url": "https://example.test/next"})
        current = await control.command(session_id, "current_url", {})
        extracted = await control.command(session_id, "extract", {"selector": "body"})

        self.assertEqual("https://example.test/next", current["url"])
        self.assertEqual("Fixture bridge body", extracted["value"])
        await control.close_session(session_id)

    async def test_model_tool_loop_can_drive_browser_session_end_to_end(self):
        database = self.root / "runtime.db"
        store = RuntimeStore(database)
        control = BrowserControl(self.root, default_backend="mock")
        executor = ModelExecutor(store, browser_control=control)
        executor._resolve_api_key = lambda _agent: "test-key"
        task = TaskRecord(title="Inspect mock browser", description="Read the page")
        agent = AgentSnapshot(
            id="browser-agent",
            name="Browser Agent",
            role="browser",
            toolsets=["browser"],
            model=ModelSettings(provider="openai-compatible", model="test-model", base_url="http://model.test/v1"),
        )
        calls = {"count": 0}

        def fake_post(_endpoint, payload, _api_key, extra_headers=None):
            calls["count"] += 1
            if calls["count"] == 1:
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-open",
                                        "type": "function",
                                        "function": {
                                            "name": "browser_open",
                                            "arguments": json.dumps(
                                                {
                                                    "backend": "mock",
                                                    "url": "https://example.test",
                                                    "page_text": "Readable page context",
                                                }
                                            ),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            if calls["count"] == 2:
                tool_message = next(item for item in reversed(payload["messages"]) if item["role"] == "tool")
                session_id = json.loads(tool_message["content"])["session"]["id"]
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-extract",
                                        "type": "function",
                                        "function": {
                                            "name": "browser_extract",
                                            "arguments": json.dumps({"session_id": session_id, "selector": "body"}),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            tool_message = next(item for item in reversed(payload["messages"]) if item["role"] == "tool")
            value = json.loads(tool_message["content"])["value"]
            return {"choices": [{"message": {"role": "assistant", "content": f"Observed: {value}"}}]}

        executor._post_json = fake_post

        async def emit(_event):
            return None

        result = await executor._run_openai_compatible(agent, task, emit)
        self.assertEqual("Observed: Readable page context", result["summary"])
        self.assertEqual(2, result["tool_calls"])
        self.assertEqual(1, len(control.list_sessions()))
        await control.shutdown()
        store.close()


if __name__ == "__main__":
    unittest.main()
