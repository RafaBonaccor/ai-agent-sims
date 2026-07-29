from __future__ import annotations

import base64
import json
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_VINTED_AI_MODEL = "gpt-image-2"
DEFAULT_VINTED_AI_SIZE = "1024x1536"
VINTED_AI_SUPPORTED_SIZES = (
    "1024x1024",
    "1024x1536",
    "1536x1024",
    "auto",
)


def generate_vinted_ai_variants(
    *,
    api_key: str,
    photo_paths: list[str],
    prompt: str,
    output_dir: str | Path,
    model: str = DEFAULT_VINTED_AI_MODEL,
    size: str = DEFAULT_VINTED_AI_SIZE,
    variants: int = 1,
    base_url: str | None = None,
) -> dict[str, object]:
    resolved_paths = _validate_photo_paths(photo_paths)
    cleaned_prompt = str(prompt or "").strip()
    if not cleaned_prompt:
        raise ValueError("Prompt AI missing")
    if not str(api_key or "").strip():
        raise ValueError("Project API key missing")

    variant_count = max(1, min(int(variants or 1), 4))
    target_dir = _prepare_output_dir(output_dir)
    log_path = target_dir / "generation_log.json"
    log_payload: dict[str, object] = {
        "source": "agent_runtime",
        "ok": False,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "model": str(model or DEFAULT_VINTED_AI_MODEL).strip() or DEFAULT_VINTED_AI_MODEL,
        "size": str(size or DEFAULT_VINTED_AI_SIZE).strip() or DEFAULT_VINTED_AI_SIZE,
        "variants_requested": variant_count,
        "prompt": cleaned_prompt,
        "source_photo_paths": [str(path.resolve()) for path in resolved_paths],
        "output_dir": str(target_dir.resolve()),
        "steps": [
            {"at": datetime.now().isoformat(timespec="seconds"), "message": "Validated input photos and prompt."},
            {"at": datetime.now().isoformat(timespec="seconds"), "message": "Preparing OpenAI image edit request."},
        ],
    }
    _write_log(log_path, log_payload)

    client = _build_openai_client(api_key=api_key, base_url=base_url)
    generated_paths: list[str] = []

    try:
        with ExitStack() as stack:
            image_handles = [stack.enter_context(path.open("rb")) for path in resolved_paths]
            image_input: Any = image_handles[0] if len(image_handles) == 1 else image_handles
            request_kwargs: dict[str, Any] = {
                "model": str(model or DEFAULT_VINTED_AI_MODEL).strip() or DEFAULT_VINTED_AI_MODEL,
                "image": image_input,
                "prompt": cleaned_prompt,
                "n": variant_count,
            }
            normalized_size = str(size or DEFAULT_VINTED_AI_SIZE).strip() or DEFAULT_VINTED_AI_SIZE
            if normalized_size.lower() != "auto":
                request_kwargs["size"] = normalized_size
            response = client.images.edit(**request_kwargs)

        data = list(getattr(response, "data", []) or [])
        log_payload["steps"] = list(log_payload.get("steps", [])) + [
            {"at": datetime.now().isoformat(timespec="seconds"), "message": f"OpenAI response received with {len(data)} candidate(s)."}
        ]
        if not data:
            raise RuntimeError("OpenAI returned no image data")

        for index, item in enumerate(data, start=1):
            b64_payload = getattr(item, "b64_json", None)
            if b64_payload is None and isinstance(item, dict):
                b64_payload = item.get("b64_json")
            if not b64_payload:
                raise RuntimeError("Missing b64_json in OpenAI image response")
            image_bytes = base64.b64decode(str(b64_payload))
            output_path = target_dir / f"ai_variant_{index:02d}.png"
            output_path.write_bytes(image_bytes)
            generated_paths.append(str(output_path.resolve()))

        result = {
            "ok": True,
            "model": str(model or DEFAULT_VINTED_AI_MODEL).strip() or DEFAULT_VINTED_AI_MODEL,
            "size": str(size or DEFAULT_VINTED_AI_SIZE).strip() or DEFAULT_VINTED_AI_SIZE,
            "prompt": cleaned_prompt,
            "source_photo_paths": [str(path.resolve()) for path in resolved_paths],
            "generated_photo_paths": generated_paths,
            "output_dir": str(target_dir.resolve()),
            "variants": len(generated_paths),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "log_path": str(log_path.resolve()),
            "backend": "agent_runtime",
            "runtime_url": "",
        }
        log_payload.update(
            {
                "ok": True,
                "completed_at": result["generated_at"],
                "generated_photo_paths": generated_paths,
                "variants_generated": len(generated_paths),
            }
        )
        log_payload["steps"] = list(log_payload.get("steps", [])) + [
            {"at": result["generated_at"], "message": f"Saved {len(generated_paths)} image(s) to disk."}
        ]
        _write_log(log_path, log_payload)
        return result
    except Exception as exc:
        failed_at = datetime.now().isoformat(timespec="seconds")
        log_payload.update(
            {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "completed_at": failed_at,
            }
        )
        log_payload["steps"] = list(log_payload.get("steps", [])) + [
            {"at": failed_at, "message": f"Generation failed: {type(exc).__name__}: {exc}"}
        ]
        _write_log(log_path, log_payload)
        raise


def _validate_photo_paths(photo_paths: list[str]) -> list[Path]:
    resolved_paths = [Path(path).expanduser().resolve() for path in photo_paths if str(path or "").strip()]
    if not resolved_paths:
        raise ValueError("At least one reference photo is required")
    for path in resolved_paths:
        if not path.exists():
            raise FileNotFoundError(f"Photo not found: {path}")
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError(f"Unsupported image format: {path.suffix}")
    return resolved_paths


def _prepare_output_dir(output_dir: str | Path) -> Path:
    root = Path(output_dir).expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = root / timestamp
    target.mkdir(parents=True, exist_ok=True)
    return target


def _write_log(log_path: Path, payload: dict[str, object]) -> None:
    try:
        log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def _build_openai_client(*, api_key: str, base_url: str | None) -> Any:
    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The 'openai' package is not installed in the runtime environment."
        ) from exc

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    return OpenAI(**client_kwargs)
