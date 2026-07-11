from __future__ import annotations

import argparse
import json
import sys
import traceback
from typing import Any

from botasaurus.browser import Driver, Wait, browser

from scraper_app.browser_helpers import (
    click_visible_button_by_text,
    click_visible_button_containing_text,
    current_page_url,
    navigate_with_retries,
)
from scraper_app.browser_runtime import resolve_browser_arguments, resolve_browser_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JSONL Botasaurus bridge for agent browser control.")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--url", default="")
    parser.add_argument("--browser-mode", default="sessione_persistente")
    parser.add_argument("--browser-user-data-dir", default="")
    parser.add_argument("--browser-profile-directory", default="Default")
    parser.add_argument("--refresh-browser-profile", action="store_true")
    return parser.parse_args()


def write_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def session_payload(session_id: str, driver: Driver, state: str = "ready") -> dict[str, Any]:
    return {
        "id": session_id,
        "backend": "botasaurus",
        "state": state,
        "current_url": current_page_url(driver),
    }


def click_selector(driver: Driver, selector: str) -> dict[str, Any]:
    clicked = bool(
        driver.run_js(
            """
const selector = args.selector;
const element = document.querySelector(selector);
if (!element) {
  return false;
}
element.scrollIntoView({ block: "center", inline: "center" });
element.click();
return true;
            """,
            {"selector": selector},
        )
    )
    return {"clicked": clicked, "selector": selector}


def type_into_selector(driver: Driver, selector: str, value: str, clear: bool = True) -> dict[str, Any]:
    typed = bool(
        driver.run_js(
            """
const selector = args.selector;
const value = args.value;
const clear = !!args.clear;
const element = document.querySelector(selector);
if (!element) {
  return false;
}
element.focus();
const tag = (element.tagName || "").toUpperCase();
if (tag === "TEXTAREA" || tag === "INPUT") {
  if (clear) {
    element.value = "";
  }
  const prototype = tag === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
  if (descriptor && descriptor.set) {
    descriptor.set.call(element, clear ? value : `${element.value || ""}${value}`);
  } else {
    element.value = clear ? value : `${element.value || ""}${value}`;
  }
} else if (element.isContentEditable) {
  if (clear) {
    element.textContent = "";
  }
  element.textContent = clear ? value : `${element.textContent || ""}${value}`;
} else {
  element.textContent = clear ? value : `${element.textContent || ""}${value}`;
}
element.dispatchEvent(new InputEvent("input", { bubbles: true, data: value, inputType: "insertText" }));
element.dispatchEvent(new Event("change", { bubbles: true }));
return true;
            """,
            {"selector": selector, "value": value, "clear": clear},
        )
    )
    return {"typed": typed, "selector": selector, "characters": len(value)}


def extract_selector(driver: Driver, selector: str, mode: str = "text", all_matches: bool = False) -> dict[str, Any]:
    payload = driver.run_js(
        """
const selector = args.selector || "body";
const mode = args.mode || "text";
const allMatches = !!args.all;
const elements = [...document.querySelectorAll(selector)];
const read = (element) => {
  if (mode === "html") return element.innerHTML || "";
  if (mode === "outer_html") return element.outerHTML || "";
  if (mode && mode.startsWith("attr:")) return element.getAttribute(mode.slice(5)) || "";
  return (element.innerText || element.textContent || "").replace(/\\s+/g, " ").trim();
};
if (allMatches) {
  return elements.map(read);
}
return elements[0] ? read(elements[0]) : "";
        """,
        {"selector": selector, "mode": mode, "all": all_matches},
    )
    return {"selector": selector, "mode": mode, "value": payload}


def snapshot(driver: Driver) -> dict[str, Any]:
    payload = driver.run_js(
        """
return {
  url: window.location.href || "",
  title: document.title || "",
  text: (document.body && (document.body.innerText || document.body.textContent) || "").replace(/\\s+/g, " ").trim().slice(0, 8000)
};
        """
    )
    return payload if isinstance(payload, dict) else {"url": current_page_url(driver), "title": "", "text": ""}


def screenshot(driver: Driver, path: str) -> dict[str, Any]:
    if not path:
        return {"available": False, "path": "", "reason": "Missing screenshot path."}
    for method_name in ("save_screenshot", "get_screenshot_as_file"):
        method = getattr(driver, method_name, None)
        if callable(method):
            ok = method(path)
            return {"available": bool(ok is None or ok), "path": path}
    return {"available": False, "path": "", "reason": "Botasaurus driver screenshot method was not found."}


def execute_command(session_id: str, driver: Driver, command: str, parameters: dict[str, Any]) -> dict[str, Any]:
    clean = command.strip().lower().replace("-", "_")
    if clean == "current_url":
        return {"url": current_page_url(driver), "session": session_payload(session_id, driver)}
    if clean == "goto":
        url = str(parameters.get("url", "") or "").strip()
        if not url:
            raise ValueError("goto requires url")
        navigated = navigate_with_retries(driver, url, wait=Wait.LONG, timeout_seconds=float(parameters.get("timeout", 60)))
        return {"url": current_page_url(driver), "navigated": navigated, "session": session_payload(session_id, driver)}
    if clean == "click_text":
        text = str(parameters.get("text", "") or "").strip()
        if not text:
            raise ValueError("click_text requires text")
        contains = bool(parameters.get("contains", True))
        clicked = click_visible_button_containing_text(driver, text) if contains else click_visible_button_by_text(driver, text)
        return {"clicked": bool(clicked), "text": text, "session": session_payload(session_id, driver)}
    if clean == "click_selector":
        selector = str(parameters.get("selector", "") or "").strip()
        if not selector:
            raise ValueError("click_selector requires selector")
        result = click_selector(driver, selector)
        return {**result, "session": session_payload(session_id, driver)}
    if clean == "type":
        selector = str(parameters.get("selector", "") or "").strip()
        value = str(parameters.get("value", "") or "")
        if not selector:
            raise ValueError("type requires selector")
        result = type_into_selector(driver, selector, value, clear=bool(parameters.get("clear", True)))
        return {**result, "session": session_payload(session_id, driver)}
    if clean == "extract":
        selector = str(parameters.get("selector", "body") or "body").strip()
        mode = str(parameters.get("mode", "text") or "text").strip()
        result = extract_selector(driver, selector, mode=mode, all_matches=bool(parameters.get("all", False)))
        return {**result, "session": session_payload(session_id, driver)}
    if clean == "snapshot":
        return {**snapshot(driver), "session": session_payload(session_id, driver)}
    if clean == "screenshot":
        path = str(parameters.get("path", "") or "").strip()
        return {**screenshot(driver, path), "session": session_payload(session_id, driver)}
    if clean == "close":
        return {"closed": True, "session": session_payload(session_id, driver, state="closed")}
    raise ValueError(f"Unsupported browser command: {command}")


@browser(
    profile=resolve_browser_profile,
    add_arguments=resolve_browser_arguments,
    wait_for_complete_page_load=False,
    output=None,
)
def bridge_loop(driver: Driver, config: dict[str, Any]) -> dict[str, Any]:
    session_id = str(config["session_id"])
    initial_url = str(config.get("url", "") or "").strip()
    if initial_url:
        navigate_with_retries(driver, initial_url, wait=Wait.LONG, timeout_seconds=60)
    write_json(
        {
            "type": "ready",
            "ok": True,
            "result": {"url": current_page_url(driver), "session": session_payload(session_id, driver)},
        }
    )

    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        request_id = ""
        try:
            request = json.loads(text)
            request_id = str(request.get("id", ""))
            command = str(request.get("command", ""))
            parameters = request.get("parameters") or {}
            if not isinstance(parameters, dict):
                raise ValueError("parameters must be an object")
            result = execute_command(session_id, driver, command, parameters)
            write_json({"id": request_id, "ok": True, "result": result})
            if command.strip().lower().replace("-", "_") == "close":
                return {"closed": True}
        except Exception as error:
            write_json(
                {
                    "id": request_id,
                    "ok": False,
                    "error": f"{type(error).__name__}: {error}",
                    "trace": traceback.format_exc(limit=4),
                }
            )
    return {"closed": True}


def main() -> None:
    args = parse_args()
    config = {
        "session_id": args.session_id,
        "url": args.url,
        "browser_mode": args.browser_mode,
        "browser_user_data_dir": args.browser_user_data_dir,
        "browser_profile_directory": args.browser_profile_directory,
        "refresh_browser_profile": args.refresh_browser_profile,
    }
    try:
        bridge_loop(config)
    except Exception as error:
        write_json({"type": "ready", "ok": False, "error": f"{type(error).__name__}: {error}"})
        raise


if __name__ == "__main__":
    main()
