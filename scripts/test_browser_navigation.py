#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_runtime.browser_control import BrowserControl, BrowserControlError


HTML = """
<!doctype html>
<title>Agent Browser Live Test</title>
<main>
  <h1>Agent Browser Live Test</h1>
  <label>Query <input id="q" value=""></label>
  <button id="go" onclick="document.body.setAttribute('data-clicked','yes'); document.querySelector('#out').textContent=document.querySelector('#q').value">Go</button>
  <p id="out">empty</p>
</main>
""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test Agent Lab browser navigation.")
    parser.add_argument("--backend", choices=["mock", "botasaurus"], default="mock")
    parser.add_argument("--project-id", default="main-scraper")
    parser.add_argument("--browser-mode", default="isolated")
    parser.add_argument("--url", default="")
    return parser.parse_args()


def default_url() -> str:
    return "data:text/html;charset=utf-8," + quote(HTML)


async def run() -> int:
    args = parse_args()
    control = BrowserControl(PROJECT_ROOT)
    session_id = ""
    url = args.url.strip() or default_url()

    try:
        opened = await control.open_session(
            project_id=args.project_id,
            backend=args.backend,
            url=url,
            browser_mode=args.browser_mode,
            page_text="Agent Browser Mock Test",
            title="Agent Browser Mock Test",
        )
        session = opened["session"]
        session_id = session["id"]
        print_json("opened", opened)

        current = await control.command(session_id, "current_url", {})
        print_json("current_url", current)

        if args.backend == "mock":
            typed = await control.command(session_id, "type", {"selector": "#q", "value": "mock navigation ok"})
            extracted = await control.command(session_id, "extract", {"selector": "#q"})
            snapshot = await control.command(session_id, "snapshot", {})
            assert typed["typed"] is True
            assert extracted["value"] == "mock navigation ok"
            assert snapshot["url"] == url
            print_json("type", typed)
            print_json("extract", extracted)
            print_json("snapshot", snapshot)
        else:
            heading = await control.command(session_id, "extract", {"selector": "h1"})
            typed = await control.command(session_id, "type", {"selector": "#q", "value": "live navigation ok"})
            clicked = await control.command(session_id, "click_selector", {"selector": "#go"})
            output = await control.command(session_id, "extract", {"selector": "#out"})
            snapshot = await control.command(session_id, "snapshot", {})
            assert "Agent Browser Live Test" in str(heading["value"])
            assert typed["typed"] is True
            assert clicked["clicked"] is True
            assert output["value"] == "live navigation ok"
            print_json("heading", heading)
            print_json("type", typed)
            print_json("click_selector", clicked)
            print_json("output", output)
            print_json("snapshot", snapshot)

        print("browser navigation smoke test: OK")
        return 0
    except (AssertionError, BrowserControlError, RuntimeError, OSError) as error:
        print(f"browser navigation smoke test: FAILED: {type(error).__name__}: {error}")
        if args.backend == "botasaurus":
            print("For live Botasaurus tests on macOS, install Google Chrome and rerun this command.")
        return 1
    finally:
        if session_id:
            try:
                closed = await control.close_session(session_id)
                print_json("closed", closed)
            except Exception as error:
                print(f"close warning: {type(error).__name__}: {error}")


def print_json(label: str, payload: dict) -> None:
    print(f"{label}: {json.dumps(payload, ensure_ascii=False, indent=2)[:2500]}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
