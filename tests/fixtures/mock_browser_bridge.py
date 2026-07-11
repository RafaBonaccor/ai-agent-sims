from __future__ import annotations

import argparse
import json
import sys


def write(payload):
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


parser = argparse.ArgumentParser()
parser.add_argument("--session-id", required=True)
parser.add_argument("--url", default="")
parser.add_argument("--browser-mode", default="")
parser.add_argument("--browser-user-data-dir", default="")
parser.add_argument("--browser-profile-directory", default="")
parser.add_argument("--refresh-browser-profile", action="store_true")
args = parser.parse_args()

current_url = args.url
page_text = "Fixture bridge body"

write(
    {
        "type": "ready",
        "ok": True,
        "result": {
            "url": current_url,
            "session": {
                "id": args.session_id,
                "backend": "botasaurus",
                "state": "ready",
                "current_url": current_url,
            },
        },
    }
)

for line in sys.stdin:
    request = json.loads(line)
    command = str(request.get("command", "")).replace("-", "_")
    params = request.get("parameters") or {}
    if command == "goto":
        current_url = params["url"]
        result = {"url": current_url, "navigated": True}
    elif command == "current_url":
        result = {"url": current_url}
    elif command == "extract":
        result = {"selector": params.get("selector", "body"), "mode": params.get("mode", "text"), "value": page_text}
    elif command == "close":
        result = {"closed": True}
    else:
        result = {"ok": True, "command": command}
    result["session"] = {
        "id": args.session_id,
        "backend": "botasaurus",
        "state": "closed" if command == "close" else "ready",
        "current_url": current_url,
    }
    write({"id": request["id"], "ok": True, "result": result})
    if command == "close":
        break
