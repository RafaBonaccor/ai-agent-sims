from __future__ import annotations

import base64
import json
import mimetypes
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import SystemSettings


def build_error_report_message(source: str, message: str, context: Optional[dict[str, Any]] = None) -> str:
    normalized_source = str(source or "runtime").strip() or "runtime"
    normalized_message = str(message or "Unknown error").strip() or "Unknown error"
    payload = context if isinstance(context, dict) else {}
    lines = [
        "⚠️ Agent Lab error report",
        f"Source: {normalized_source}",
        f"Message: {normalized_message}",
        f"Time: {datetime.now().isoformat(timespec='seconds')}",
    ]
    for key in ("path", "project_id", "job_id", "agent_id", "current_url", "phase"):
        value = str(payload.get(key, "") or "").strip()
        if value:
            lines.append(f"{key}: {value}")
    trimmed_context = {
        str(key): value
        for key, value in payload.items()
        if str(key) not in {"path", "project_id", "job_id", "agent_id", "current_url", "phase"}
    }
    if trimmed_context:
        lines.append("")
        lines.append("Context:")
        lines.append(json.dumps(trimmed_context, ensure_ascii=False, indent=2, default=str)[:3000])
    return "\n".join(lines)


def send_discord_webhook_message(
    webhook_url: str,
    content: str,
    *,
    attachment_paths: Optional[Iterable[str | Path]] = None,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    normalized_url = str(webhook_url or "").strip()
    payload = {
        "content": str(content or "").strip(),
        "allowed_mentions": {"parse": []},
    }
    sent_at = datetime.now().isoformat(timespec="seconds")
    attachments = [
        Path(path).expanduser().resolve()
        for path in (attachment_paths or [])
        if str(path or "").strip()
    ]
    try:
        if attachments:
            boundary = f"----AgentLabBoundary{uuid.uuid4().hex}"
            data, content_type = _multipart_webhook_payload(payload, attachments, boundary)
        else:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            content_type = "application/json"
        request = Request(
            normalized_url,
            data=data,
            headers={
                "Content-Type": content_type,
                "Accept": "application/json, text/plain, */*",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36 AgentLab/1.0"
                ),
            },
            method="POST",
        )
        with urlopen(request, timeout=max(float(timeout_seconds or 0), 1.0)) as response:
            status_code = int(getattr(response, "status", 200) or 200)
            response_body = response.read().decode("utf-8", errors="replace")
        return {
            "ok": 200 <= status_code < 300,
            "status_code": status_code,
            "response_body": response_body,
            "sent_at": sent_at,
            "error": "",
            "attachments": [str(path) for path in attachments],
        }
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status_code": int(exc.code or 0),
            "response_body": body,
            "sent_at": sent_at,
            "error": f"HTTP {exc.code}: {body or exc.reason}",
            "attachments": [str(path) for path in attachments],
        }
    except URLError as exc:
        return {
            "ok": False,
            "status_code": 0,
            "response_body": "",
            "sent_at": sent_at,
            "error": f"URL error: {exc.reason}",
            "attachments": [str(path) for path in attachments],
        }
    except Exception as exc:  # pragma: no cover
        return {
            "ok": False,
            "status_code": 0,
            "response_body": "",
            "sent_at": sent_at,
            "error": f"{type(exc).__name__}: {exc}",
            "attachments": [str(path) for path in attachments],
        }


def save_data_url_image(data_url: str, destination_dir: Path, filename_stem: str = "game-error") -> Path:
    raw = str(data_url or "").strip()
    if not raw.startswith("data:image/"):
        raise ValueError("Screenshot payload must be a data:image/* URL.")
    header, encoded = raw.split(",", 1)
    extension = "png"
    if "image/jpeg" in header:
        extension = "jpg"
    elif "image/webp" in header:
        extension = "webp"
    destination_dir.mkdir(parents=True, exist_ok=True)
    path = destination_dir / f"{filename_stem}.{extension}"
    path.write_bytes(base64.b64decode(encoded))
    return path


def recent_project_screenshot_paths(project_root: Path, *, max_age_seconds: int = 900, limit: int = 3) -> list[Path]:
    now = datetime.now().timestamp()
    candidates: list[Path] = []
    for relative_root in ("error_logs", "output", "runtime"):
        base = (project_root / relative_root).resolve()
        if not base.is_dir():
            continue
        for pattern in ("**/screenshot.png", "**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.webp"):
            for path in base.glob(pattern):
                if not path.is_file():
                    continue
                try:
                    age_seconds = now - path.stat().st_mtime
                except OSError:
                    continue
                if age_seconds < 0 or age_seconds > max_age_seconds:
                    continue
                candidates.append(path)
    unique = sorted({path.resolve() for path in candidates}, key=lambda item: item.stat().st_mtime, reverse=True)
    return unique[: max(0, int(limit))]


class RuntimeErrorReporter:
    def __init__(self, root: Path, settings_provider: Callable[[], SystemSettings]):
        self.root = root.resolve()
        self.settings_provider = settings_provider
        self.output_dir = self.root / "runtime" / "error_reports"

    async def report(
        self,
        *,
        source: str,
        message: str,
        context: Optional[dict[str, Any]] = None,
        screenshot_data_url: str = "",
        attachment_paths: Optional[Iterable[str | Path]] = None,
    ) -> dict[str, Any]:
        settings = self.settings_provider()
        diagnostics = getattr(settings, "diagnostics", None)
        enabled = bool(getattr(diagnostics, "discord_error_notifications", False))
        webhook_url = str(getattr(diagnostics, "discord_webhook_url", "") or "").strip()
        if not enabled or not webhook_url:
            return {"ok": False, "skipped": True, "reason": "diagnostics_disabled"}
        report_dir = self.output_dir / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        attachments: list[Path] = []
        if screenshot_data_url:
            try:
                attachments.append(save_data_url_image(screenshot_data_url, report_dir, "game-screenshot"))
            except Exception:
                pass
        for item in attachment_paths or []:
            path = Path(item).expanduser().resolve()
            if path.is_file():
                attachments.append(path)
        return send_discord_webhook_message(
            webhook_url,
            build_error_report_message(source, message, context),
            attachment_paths=attachments,
        )


def _multipart_webhook_payload(
    payload: dict[str, Any],
    attachments: list[Path],
    boundary: str,
) -> tuple[bytes, str]:
    chunks: list[bytes] = []

    def add_text(name: str, value: str, *, content_type: str = "text/plain; charset=utf-8") -> None:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"\r\nContent-Type: {content_type}\r\n\r\n'.encode("utf-8")
        )
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")

    add_text("payload_json", json.dumps(payload, ensure_ascii=False), content_type="application/json")
    for index, path in enumerate(attachments):
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="files[{index}]"; filename="{path.name}"\r\n'
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(path.read_bytes())
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"
