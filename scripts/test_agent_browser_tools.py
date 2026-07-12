#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_runtime.browser_control import BrowserControl
from agent_runtime.execution import ModelExecutor
from agent_runtime.models import AgentSnapshot, ModelSettings, TaskRecord
from agent_runtime.storage import RuntimeStore


HTML = """
<!doctype html>
<title>Agent Browser Tool Test</title>
<main>
  <h1>Agent Browser Tool Test</h1>
  <label>Query <input id="q" value=""></label>
  <button id="go" onclick="document.querySelector('#out').textContent=document.querySelector('#q').value">Go</button>
  <p id="out">empty</p>
</main>
""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test browser tools through the agent model/tool loop.")
    parser.add_argument("--backend", choices=["mock", "botasaurus"], default="mock")
    parser.add_argument("--browser-mode", default="isolated")
    parser.add_argument("--value", default="agent browser ok")
    return parser.parse_args()


def test_url() -> str:
    return "data:text/html;charset=utf-8," + quote(HTML)


async def run() -> int:
    args = parse_args()
    with tempfile.TemporaryDirectory() as temporary_directory:
        store = RuntimeStore(Path(temporary_directory) / "runtime.db")
        control = BrowserControl(PROJECT_ROOT, default_backend=args.backend)
        executor = ModelExecutor(store, browser_control=control)
        executor._resolve_api_key = lambda _agent: "test-key"

        agent = AgentSnapshot(
            id="browser-agent",
            name="Browser Agent",
            role="browser",
            toolsets=["browser"],
            model=ModelSettings(
                provider="openai-compatible",
                model="tool-loop-smoke",
                base_url="http://model.test/v1",
            ),
        )
        task = TaskRecord(
            title="Drive browser tools",
            description="Open a page, type into an input, click a button, and report the output.",
        )

        calls = {"count": 0, "session_id": "", "output": ""}

        def fake_post(_endpoint, payload, _api_key, extra_headers=None):
            calls["count"] += 1
            latest_tool = latest_tool_payload(payload)
            if latest_tool and "session" in latest_tool:
                calls["session_id"] = latest_tool["session"]["id"]
            if latest_tool and latest_tool.get("selector") in {"#out", "#q"}:
                calls["output"] = str(latest_tool.get("value", ""))

            if calls["count"] == 1:
                arguments = {
                    "backend": args.backend,
                    "url": test_url(),
                    "browser_mode": args.browser_mode,
                    "page_text": "Agent Browser Mock Page",
                    "title": "Agent Browser Mock Page",
                }
                return tool_response("call-open", "browser_open", arguments)

            if calls["count"] == 2:
                selector = "h1" if args.backend == "botasaurus" else "body"
                return tool_response("call-heading", "browser_extract", {"session_id": calls["session_id"], "selector": selector})

            if calls["count"] == 3:
                return tool_response(
                    "call-type",
                    "browser_type",
                    {"session_id": calls["session_id"], "selector": "#q", "value": args.value},
                )

            if calls["count"] == 4 and args.backend == "botasaurus":
                return tool_response(
                    "call-click",
                    "browser_click_selector",
                    {"session_id": calls["session_id"], "selector": "#go"},
                )

            if (calls["count"] == 4 and args.backend == "mock") or (calls["count"] == 5 and args.backend == "botasaurus"):
                selector = "#out" if args.backend == "botasaurus" else "#q"
                return tool_response("call-output", "browser_extract", {"session_id": calls["session_id"], "selector": selector})

            if (calls["count"] == 5 and args.backend == "mock") or (calls["count"] == 6 and args.backend == "botasaurus"):
                return tool_response("call-snapshot", "browser_snapshot", {"session_id": calls["session_id"]})

            if (calls["count"] == 6 and args.backend == "mock") or (calls["count"] == 7 and args.backend == "botasaurus"):
                return tool_response("call-close", "browser_close", {"session_id": calls["session_id"]})

            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": f"Agent browser output: {calls['output']}",
                        }
                    }
                ]
            }

        executor._post_json = fake_post
        events = []

        async def emit(event):
            events.append(event)

        try:
            result = await executor._run_openai_compatible(agent, task, emit)
            assert result["summary"] == f"Agent browser output: {args.value}", result
            assert not control.list_sessions(), control.list_sessions()
            print(json.dumps({"result": result, "tool_events": [event.type for event in events]}, indent=2))
            print("agent browser tool-loop smoke test: OK")
            return 0
        except Exception as error:
            print(f"agent browser tool-loop smoke test: FAILED: {type(error).__name__}: {error}")
            return 1
        finally:
            await control.shutdown()
            store.close()


def tool_response(call_id: str, name: str, arguments: dict) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                    ],
                }
            }
        ]
    }


def latest_tool_payload(payload: dict) -> dict:
    for message in reversed(payload.get("messages", [])):
        if message.get("role") != "tool":
            continue
        try:
            value = json.loads(message.get("content") or "{}")
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}
    return {}


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
