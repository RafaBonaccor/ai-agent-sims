from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.request import Request, urlopen

from .project_gateway import ProjectGateway, ProjectJob, ProjectJobCreate
from .secrets import SecretStore
from .vinted_ai import (
    DEFAULT_VINTED_AI_MODEL,
    DEFAULT_VINTED_AI_SIZE,
    _build_openai_client,
    generate_vinted_ai_variants,
)

LOGGER = logging.getLogger("agent_lab.discord.project_bridge")


TEXT_ATTACHMENT_SUFFIXES = {
    ".json",
    ".txt",
    ".md",
    ".csv",
    ".tsv",
    ".yaml",
    ".yml",
}

FIELD_ALIASES = {
    "title": "title",
    "titolo": "title",
    "description": "description",
    "descrizione": "description",
    "price": "price",
    "prezzo": "price",
    "category": "category",
    "categoria": "category",
    "brand": "brand",
    "marca": "brand",
    "condition": "condition",
    "condizione": "condition",
    "material": "material",
    "materiale": "material",
    "submit": "submit",
    "pubblica": "submit",
    "publish": "submit",
    "photo_urls": "photo_urls",
    "photos": "photo_urls",
    "foto": "photo_urls",
    "enhance_photos": "enhance_photos",
    "enhance": "enhance_photos",
    "ai_photos": "enhance_photos",
    "photo_ai": "enhance_photos",
    "migliora_foto": "enhance_photos",
    "foto_ai": "enhance_photos",
}

VINTED_AI_STANDARD_PROMPT = (
    "Create a cleaner marketplace-ready product photo for Vinted. "
    "Keep the item identity accurate, with true colors, materials, and details. If the photo "
    "contains packaging, boxes, bags, tags, wrapping, branded packaging, shipping materials, or "
    "display supports, remove them completely unless they are physically part of the product. "
    "Only the product for sale must remain visible. Improve lighting and clarity while keeping "
    "the image realistic. Use a simple home-style background that is not empty, softly matched "
    "to the item, minimal, believable, and not studio-like. Remove distractions, keep the "
    "framing natural and vertical, and make the result look authentic and ready for sale on "
    "Vinted."
)

VINTED_AI_UPLOAD_VARIANT_PROMPTS: tuple[tuple[str, str], ...] = (
    (
        "flatlay",
        VINTED_AI_STANDARD_PROMPT,
    ),
    (
        "worn",
        "Create a cleaner marketplace-ready product photo for Vinted. Keep the item identity accurate, "
        "with true colors, materials, and details. Show the item being worn by a woman in a realistic way, "
        "but do not show her face. Only show the relevant body area where the item naturally belongs, such "
        "as the neck, wrist, hand, or ear depending on the product. Keep the composition natural, believable, "
        "and suitable for a second-hand listing. Use a simple home-style setting, soft light, minimal "
        "distractions, and a vertical framing. If the photo contains packaging, boxes, bags, tags, wrapping, "
        "branded packaging, shipping materials, or display supports, remove them completely unless they are "
        "physically part of the product. Only the product for sale must remain visible.",
    ),
    (
        "hand",
        "Create a cleaner marketplace-ready product photo for Vinted. Keep the item identity accurate, "
        "with true colors, materials, and details. Show the item resting naturally on the open palm of a hand "
        "in a realistic home-style photo. Keep the hand natural and believable, with the item clearly visible "
        "and centered. Use a simple but not empty background, soft light, minimal distractions, and vertical "
        "framing suitable for a resale listing. If the photo contains packaging, boxes, bags, tags, wrapping, "
        "branded packaging, shipping materials, or display supports, remove them completely unless they are "
        "physically part of the product. Only the product for sale must remain visible.",
    ),
)

VINTED_LISTING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "price": {"type": "string"},
        "category": {"type": "string"},
        "brand": {"type": "string"},
        "condition": {"type": "string"},
        "material": {"type": "string"},
    },
    "required": ["title", "description", "price", "category", "brand", "condition", "material"],
}
VINTED_LISTING_SYSTEM_PROMPT = """You transform free-form marketplace text into a structured Vinted upload payload.

Rules:
- return valid JSON only;
- keep it concise and practical for filling the Vinted form;
- if the brand is unclear, use "No Label";
- if the condition is unclear, use "Ottime";
- if the material is unclear, use "Altro";
- if the price is missing, leave it as an empty string;
- choose a plausible Vinted category;
- keep the description more complete than the title;
- do not invent critical details unsupported by the text.
"""

VINTED_PHOTO_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "category": {
            "type": "string",
            "enum": ["Charm e ciondoli", "Collane", "Braccialetti", "Anelli", "Orecchini"],
        },
    },
    "required": ["title", "description", "category"],
}

VINTED_PHOTO_ANALYSIS_SYSTEM_PROMPT = """You analyze marketplace product photos for a Vinted upload draft.

Return valid JSON only.

Goals:
- infer a concise Italian title from the jewelry shown in the photo;
- infer an Italian description suitable for a Vinted draft;
- choose exactly one category from:
  - Charm e ciondoli
  - Collane
  - Braccialetti
  - Anelli
  - Orecchini

Rules:
- use only what is visually supported by the photo;
- do not mention a price;
- do not invent brand names;
- keep the title short and marketplace-friendly;
- keep the description practical and neutral;
- if uncertain, choose the most visually likely category from the allowed list.
"""


@dataclass(frozen=True)
class DiscordAttachment:
    url: str
    filename: str
    content_type: str = ""


@dataclass(frozen=True)
class DiscordProjectCommand:
    action: str
    agent_id: str = ""
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class PendingDiscordProjectJob:
    job_id: str
    project_id: str
    action: str
    agent_id: str


class DiscordProjectBridge:
    def __init__(self, root: Path, project_gateway: ProjectGateway):
        self.root = root.resolve()
        self.project_gateway = project_gateway
        self.storage_root = self.root / "data" / "discord_ingest"

    async def submit_vinted_upload(
        self,
        *,
        content: str,
        attachments: Iterable[DiscordAttachment],
        agent_id: str = "",
        enhance_photos: bool = False,
    ) -> ProjectJob:
        ai_used = False
        ai_model = ""
        cleaned_content = self._clean_vinted_upload_text(content)
        should_prefer_ai_structuring = self._should_prefer_ai_structuring(cleaned_content)
        payload = (
            self._empty_vinted_upload_payload()
            if not str(cleaned_content or "").strip()
            else self.parse_vinted_upload_payload(cleaned_content)
        )
        photo_paths, attachment_fields = await self._collect_attachment_inputs(attachments)
        merged_payload = self._merge_payload_with_attachment_fields(payload, attachment_fields)
        merged_payload["enhance_photos"] = bool(merged_payload.get("enhance_photos", False) or enhance_photos)
        LOGGER.info(
            "discord_vinted_upload_start agent_id=%s content_chars=%s attachments_photos=%s attachment_fields=%s enhance_photos=%s",
            str(agent_id or "").strip() or "-",
            len(cleaned_content),
            len(photo_paths),
            sorted(str(key) for key in attachment_fields.keys()),
            bool(merged_payload.get("enhance_photos", False)),
        )
        if photo_paths:
            try:
                vision_payload = self._structure_vinted_upload_payload_from_photos_with_ai(
                    photo_paths,
                    price_hint=str(merged_payload.get("price", "") or "").strip(),
                )
            except Exception as exc:
                LOGGER.exception("discord_vinted_upload_photo_analysis_failed")
                raise ValueError(f"Discord photo analysis failed: {exc}") from exc
            merged_payload["title"] = str(vision_payload.get("title", "") or "").strip()
            merged_payload["description"] = str(vision_payload.get("description", "") or "").strip()
            merged_payload["category"] = str(vision_payload.get("category", "") or "").strip()
            ai_used = True
            ai_model = self._append_model_label(ai_model, str(vision_payload.get("model", "") or ""))
            LOGGER.info(
                "discord_vinted_upload_photo_analysis_ok title=%s category=%s model=%s",
                merged_payload["title"],
                merged_payload["category"],
                str(vision_payload.get("model", "") or "").strip() or "-",
            )
        missing_before_ai = self._missing_vinted_fields(merged_payload)
        if (not photo_paths) and (should_prefer_ai_structuring or missing_before_ai):
            try:
                ai_payload = self._structure_vinted_upload_payload_with_ai(cleaned_content)
            except Exception as exc:
                LOGGER.exception("discord_vinted_upload_text_ai_failed")
                raise ValueError(f"Discord AI structuring failed: {exc}") from exc
            merged_payload = self._merge_vinted_payloads(merged_payload, ai_payload)
            ai_used = True
            ai_model = str(ai_payload.get("model", "") or "").strip()
            LOGGER.info(
                "discord_vinted_upload_text_ai_ok title=%s category=%s model=%s",
                str(merged_payload.get("title", "") or "").strip(),
                str(merged_payload.get("category", "") or "").strip(),
                ai_model or "-",
            )
        explicit_photo_urls = self._normalize_photo_urls(merged_payload.get("photo_urls", []))
        if explicit_photo_urls:
            photo_paths.extend(await self._download_url_list(explicit_photo_urls, bucket="vinted_upload_urls"))
            LOGGER.info("discord_vinted_upload_downloaded_photo_urls count=%s", len(explicit_photo_urls))
        if not photo_paths:
            LOGGER.warning("discord_vinted_upload_no_photos")
            raise ValueError("Attach at least one photo in Discord or provide photo URLs in the payload.")
        if bool(merged_payload.get("enhance_photos", False)):
            LOGGER.info("discord_vinted_upload_enhance_start source_photo_count=%s", len(photo_paths))
            photo_paths = await self._enhance_vinted_upload_photos_with_ai(photo_paths)
            ai_used = True
            ai_model = self._append_model_label(ai_model, DEFAULT_VINTED_AI_MODEL)
            LOGGER.info(
                "discord_vinted_upload_enhance_done generated_photo_count=%s generated_photo_paths=%s",
                len(photo_paths),
                [Path(path).name for path in photo_paths],
            )
        else:
            LOGGER.info("discord_vinted_upload_enhance_skipped")
        item = {
            "title": str(merged_payload.get("title", "") or "").strip(),
            "description": str(merged_payload.get("description", "") or "").strip(),
            "price": str(merged_payload.get("price", "") or "").strip(),
            "category": str(merged_payload.get("category", "") or "").strip(),
            "brand": str(merged_payload.get("brand", "") or "No Label").strip() or "No Label",
            "condition": str(merged_payload.get("condition", "") or "Ottime").strip() or "Ottime",
            "material": str(merged_payload.get("material", "") or "Altro").strip() or "Altro",
            "photo_paths": photo_paths,
            "openai_used": ai_used,
            "openai_model": ai_model,
        }
        missing = self._missing_vinted_fields(item)
        if missing:
            LOGGER.warning("discord_vinted_upload_missing_fields fields=%s", ",".join(missing))
            raise ValueError(f"Missing Vinted upload fields: {', '.join(missing)}")
        items_file = self._write_items_file([item], openai_used=ai_used, openai_model=ai_model)
        LOGGER.info(
            "discord_vinted_upload_manifest_ready path=%s photo_paths=%s openai_used=%s openai_model=%s",
            str(items_file),
            [Path(path).name for path in photo_paths],
            ai_used,
            ai_model or "-",
        )
        return await self.project_gateway.create_job(
            ProjectJobCreate(
                project_id="main-scraper",
                action="vinted.upload",
                parameters={
                    "items-file": str(items_file),
                    "submit": bool(merged_payload.get("submit", False)),
                },
                agent_id=agent_id or None,
                approved=True,
            )
        )

    async def submit_vinted_upload_payload(
        self,
        *,
        payload: dict[str, Any],
        attachments: Iterable[DiscordAttachment],
        agent_id: str = "",
    ) -> ProjectJob:
        normalized = self._normalize_payload_fields(payload)
        content_lines: list[str] = []
        for key in ("title", "description", "price", "category", "brand", "condition", "material"):
            value = str(normalized.get(key, "") or "").strip()
            if value:
                content_lines.append(f"{key}: {value}")
        if normalized.get("submit"):
            content_lines.append("submit: true")
        if normalized.get("photo_urls"):
            content_lines.append("photo_urls: " + ", ".join(self._normalize_photo_urls(normalized.get("photo_urls", []))))
        return await self.submit_vinted_upload(
            content="\n".join(content_lines),
            attachments=attachments,
            agent_id=agent_id,
            enhance_photos=bool(normalized.get("enhance_photos", False)),
        )

    @staticmethod
    def parse_vinted_upload_text_command(
        content: str,
        *,
        prefix: str = "!",
        default_agent_id: str = "",
        mentioned: bool = False,
    ) -> Optional[DiscordProjectCommand]:
        text = str(content or "").strip()
        if not text:
            return None
        markers = [f"{prefix}vinted-upload", f"{prefix}upload-vinted", f"{prefix}upload"]
        ai_markers = [
            f"{prefix}vinted-upload-ai",
            f"{prefix}upload-vinted-ai",
            f"{prefix}upload-ai",
            f"{prefix}upload-ai-photo",
        ]
        ai_marker = next((item for item in ai_markers if text.startswith(item)), "")
        if ai_marker:
            marker = ai_marker
        else:
            marker = next((item for item in markers if text.startswith(item)), "")
        lowered = text.lower()
        if not marker and mentioned and lowered.startswith("vinted-upload-ai"):
            marker = "vinted-upload-ai"
        if not marker and mentioned and lowered.startswith("upload-ai-photo"):
            marker = "upload-ai-photo"
        if not marker and mentioned and lowered.startswith("upload-ai"):
            marker = "upload-ai"
        if not marker and mentioned and lowered.startswith("vinted-upload"):
            marker = "vinted-upload"
        if not marker and mentioned and lowered.startswith("upload"):
            marker = "upload"
        if not marker:
            return None
        body = text[len(marker):].lstrip()
        agent_id = default_agent_id
        if body:
            first_line, separator, remainder = body.partition("\n")
            maybe_header = first_line.strip()
            if maybe_header and ":" not in maybe_header and " " not in maybe_header and len(maybe_header) <= 80:
                agent_id = maybe_header
                body = remainder if separator else ""
        return DiscordProjectCommand(
            action="vinted.upload",
            agent_id=agent_id,
            payload={
                "body": body.strip(),
                "enhance_photos": ("upload-ai" in marker) or ("ai-photo" in marker),
            },
        )

    @classmethod
    def parse_vinted_upload_payload(cls, content: str) -> dict[str, Any]:
        text = str(content or "").strip()
        if not text:
            raise ValueError("The Discord upload command is empty.")
        if text.startswith("{"):
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("Discord upload JSON must be an object.")
            return cls._normalize_payload_fields(payload)
        fields: dict[str, Any] = {
            "title": "",
            "description": "",
            "price": "",
            "category": "",
            "brand": "",
            "condition": "",
            "material": "",
            "submit": False,
            "photo_urls": [],
            "enhance_photos": False,
        }
        current_key = ""
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                continue
            match = re.match(
                r"^(title|titolo|description|descrizione|price|prezzo|category|categoria|brand|marca|condition|condizione|material|materiale|submit|pubblica|publish|photo_urls|photos|foto)\s*[:=-]\s*(.*)$",
                line.strip(),
                flags=re.IGNORECASE,
            )
            if match:
                key = FIELD_ALIASES.get(match.group(1).lower(), "")
                value = match.group(2).strip()
                current_key = key
                if key == "submit":
                    fields["submit"] = _parse_bool_value(value)
                elif key == "photo_urls":
                    fields["photo_urls"] = _split_photo_urls(value)
                elif key == "enhance_photos":
                    fields["enhance_photos"] = _parse_bool_value(value)
                elif key:
                    fields[key] = value
                continue
            if current_key == "description":
                existing = str(fields.get("description", "") or "")
                fields["description"] = f"{existing}\n{line.strip()}".strip()
            elif current_key == "photo_urls":
                fields["photo_urls"] = list(fields.get("photo_urls", []) or []) + _split_photo_urls(line.strip())
        fields = cls._augment_vinted_upload_payload_from_free_text(fields, text)
        return fields

    def format_job_queued(self, job: ProjectJob) -> str:
        mode = "publish" if bool(job.parameters.get("submit")) else "prepare"
        return (
            f"Queued `{job.id}` for Vinted upload.\n"
            f"Mode: {mode}\n"
            f"Project: `{job.project_id}`\n"
            f"Action: `{job.action}`"
        )

    @staticmethod
    def format_job_event(event_type: str, job: dict[str, Any]) -> str:
        job_id = str(job.get("id", "") or "")
        action = str(job.get("action", "") or "project job")
        if event_type == "project.job.completed":
            result = job.get("result") if isinstance(job.get("result"), dict) else {}
            preview = str(result.get("command") or result.get("source") or "completed").strip()
            return f"✅ `{job_id}` completed\nAction: `{action}`\nResult: {preview}"
        if event_type == "project.job.failed":
            return f"❌ `{job_id}` failed\nAction: `{action}`\nError: {str(job.get('error', '') or 'Unknown error')}"
        return f"ℹ️ `{job_id}` updated\nAction: `{action}`"

    @classmethod
    def _normalize_payload_fields(cls, payload: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = cls._empty_vinted_upload_payload()
        for raw_key, value in payload.items():
            key = FIELD_ALIASES.get(str(raw_key).strip().lower(), "")
            if not key:
                continue
            if key == "submit":
                normalized["submit"] = _parse_bool_value(value)
            elif key == "enhance_photos":
                normalized["enhance_photos"] = _parse_bool_value(value)
            elif key == "photo_urls":
                normalized["photo_urls"] = value
            else:
                normalized[key] = str(value or "").strip()
        normalized["photo_urls"] = cls._normalize_photo_urls(normalized.get("photo_urls", []))
        return normalized

    @staticmethod
    def _merge_payload_with_attachment_fields(
        payload: dict[str, Any],
        attachment_fields: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(payload)
        for key in ("title", "description", "category", "brand", "condition", "material"):
            if not str(merged.get(key, "") or "").strip():
                merged[key] = str(attachment_fields.get(key, "") or "").strip()
        if str(attachment_fields.get("price", "") or "").strip():
            merged["price"] = str(attachment_fields.get("price", "") or "").strip()
        merged["submit"] = bool(payload.get("submit", False) or attachment_fields.get("submit", False))
        merged["enhance_photos"] = bool(payload.get("enhance_photos", False) or attachment_fields.get("enhance_photos", False))
        merged["photo_urls"] = list(
            dict.fromkeys(
                [
                    *DiscordProjectBridge._normalize_photo_urls(payload.get("photo_urls", [])),
                    *DiscordProjectBridge._normalize_photo_urls(attachment_fields.get("photo_urls", [])),
                ]
            )
        )
        return merged

    @staticmethod
    def _merge_vinted_payloads(base_payload: dict[str, Any], overlay_payload: dict[str, Any]) -> dict[str, Any]:
        merged = dict(overlay_payload)
        for key, value in base_payload.items():
            if key == "photo_urls":
                merged[key] = list(
                    dict.fromkeys(
                        [
                            *DiscordProjectBridge._normalize_photo_urls(overlay_payload.get("photo_urls", [])),
                            *DiscordProjectBridge._normalize_photo_urls(value),
                        ]
                    )
                )
                continue
            if str(value or "").strip():
                merged[key] = value
        return merged

    def _write_items_file(self, items: list[dict[str, Any]], *, openai_used: bool = False, openai_model: str = "") -> Path:
        target_dir = self.storage_root / "vinted_upload_jobs"
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"discord_vinted_upload_{uuid.uuid4().hex[:12]}.json"
        path.write_text(
            json.dumps(
                {
                    "source": "discord",
                    "openai_used": bool(openai_used),
                    "openai_model": str(openai_model or "").strip(),
                    "items": items,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _empty_vinted_upload_payload() -> dict[str, Any]:
        return {
            "title": "",
            "description": "",
            "price": "",
            "category": "",
            "brand": "",
            "condition": "",
            "material": "",
            "submit": False,
            "photo_urls": [],
            "enhance_photos": False,
        }

    @staticmethod
    def _missing_vinted_fields(payload: dict[str, Any]) -> list[str]:
        return [
            key for key in ("title", "description", "price", "category")
            if not str(payload.get(key, "") or "").strip()
        ]

    @classmethod
    def _augment_vinted_upload_payload_from_free_text(cls, fields: dict[str, Any], raw_text: str) -> dict[str, Any]:
        text = re.sub(r"\s+", " ", str(raw_text or "")).strip()
        if not text:
            return fields
        image_stop_labels = ("image", "images", "immagine", "immagini", "photo", "photos", "foto", "pictures")

        def fill(key: str, labels: tuple[str, ...], stop_labels: tuple[str, ...]) -> None:
            if str(fields.get(key, "") or "").strip():
                return
            value = cls._extract_inline_field(text, labels, stop_labels)
            if value:
                fields[key] = value

        fill("title", ("title", "titolo", "nome"), ("description", "descrizione", "price", "prezzo", "category", "categoria", "brand", "marca", "condition", "condizione", "material", "materiale", *image_stop_labels))
        fill("description", ("description", "descrizione"), ("price", "prezzo", "category", "categoria", "brand", "marca", "condition", "condizione", "material", "materiale", *image_stop_labels))
        fill("price", ("price", "prezzo"), ("category", "categoria", "brand", "marca", "condition", "condizione", "material", "materiale", *image_stop_labels))
        fill("category", ("category", "categoria"), ("brand", "marca", "condition", "condizione", "material", "materiale", *image_stop_labels))
        fill("brand", ("brand", "marca"), ("condition", "condizione", "material", "materiale", *image_stop_labels))
        fill("condition", ("condition", "condizione"), ("material", "materiale", *image_stop_labels))
        fill("material", ("material", "materiale"), ("category", "categoria", *image_stop_labels))
        if not str(fields.get("brand", "") or "").strip():
            fields["brand"] = "No Label"
        if not str(fields.get("condition", "") or "").strip():
            fields["condition"] = "Ottime"
        if not str(fields.get("material", "") or "").strip():
            fields["material"] = "Altro"
        if not str(fields.get("description", "") or "").strip() and str(fields.get("title", "") or "").strip():
            fields["description"] = str(fields.get("title", "") or "").strip()
        return fields

    @staticmethod
    def _extract_inline_field(text: str, labels: tuple[str, ...], stop_labels: tuple[str, ...]) -> str:
        labels_pattern = "|".join(re.escape(label) for label in labels if label)
        stop_pattern = "|".join(re.escape(label) for label in stop_labels if label)
        if not labels_pattern:
            return ""
        pattern = rf"(?:^|\b)(?:{labels_pattern})\b\s*(.*?)(?=(?:\b(?:{stop_pattern})\b)|$)" if stop_pattern else rf"(?:^|\b)(?:{labels_pattern})\b\s*(.*)$"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            return ""
        return re.sub(r"\s+", " ", str(match.group(1) or "").strip(" :-,;")).strip()

    @staticmethod
    def _clean_vinted_upload_text(raw_text: str) -> str:
        lines = [str(line or "").rstrip() for line in str(raw_text or "").splitlines()]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and re.match(r"^(?:[!/]\s*)?upload\b", lines[0].strip(), flags=re.IGNORECASE):
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)
        while lines and lines[0].lstrip().startswith(("!", "/")):
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)
        return "\n".join(lines).strip()

    @classmethod
    def _should_prefer_ai_structuring(cls, text: str) -> bool:
        cleaned = str(text or "").strip()
        if not cleaned:
            return False
        if cleaned.startswith("{"):
            return False
        return not cls._has_explicit_upload_fields(cleaned)

    @staticmethod
    def _has_explicit_upload_fields(text: str) -> bool:
        return bool(
            re.search(
                r"^(title|titolo|description|descrizione|price|prezzo|category|categoria|brand|marca|condition|condizione|material|materiale|submit|pubblica|publish|photo_urls|photos|foto)\s*[:=-]",
                str(text or ""),
                flags=re.IGNORECASE | re.MULTILINE,
            )
        )

    def _structure_vinted_upload_payload_with_ai(self, content: str) -> dict[str, Any]:
        text = str(content or "").strip()
        if not text:
            raise ValueError("The Discord upload command is empty.")
        api_key = self._resolve_openai_api_key()
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY not found in the environment or project secret store."
            )
        client = _build_openai_client(api_key=api_key, base_url=None)
        response = client.responses.create(
            model="gpt-4.1-nano",
            store=False,
            temperature=0.2,
            text={
                "verbosity": "medium",
                "format": {
                    "type": "json_schema",
                    "name": "vinted_listing_payload",
                    "strict": True,
                    "schema": VINTED_LISTING_SCHEMA,
                },
            },
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": VINTED_LISTING_SYSTEM_PROMPT}]},
                {"role": "user", "content": [{"type": "input_text", "text": text}]},
            ],
        )
        output_text = str(getattr(response, "output_text", "") or "").strip()
        if not output_text:
            payload = response.model_dump() if hasattr(response, "model_dump") else {}
            for item in payload.get("output", []) or []:
                if str(item.get("type", "") or "") != "message":
                    continue
                for content_item in item.get("content", []) or []:
                    if str(content_item.get("type", "") or "") == "output_text":
                        output_text = str(content_item.get("text", "") or "").strip()
                        if output_text:
                            break
                if output_text:
                    break
        if not output_text:
            raise ValueError("OpenAI returned an empty response.")
        parsed = json.loads(output_text)
        normalized = self._normalize_payload_fields(parsed if isinstance(parsed, dict) else {})
        normalized["model"] = "gpt-4.1-nano"
        return normalized

    def _structure_vinted_upload_payload_from_photos_with_ai(
        self,
        photo_paths: list[str],
        *,
        price_hint: str = "",
    ) -> dict[str, Any]:
        if not photo_paths:
            raise ValueError("At least one photo is required for photo analysis.")
        api_key = self._resolve_openai_api_key()
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in the environment or project secret store.")
        client = _build_openai_client(api_key=api_key, base_url=None)
        user_content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": (
                    "Analyze the attached jewelry photo(s) and return title, description, and category. "
                    f"Price is provided separately by the user as: {price_hint or '(missing)'}."
                ),
            }
        ]
        for photo_path in photo_paths[:4]:
            user_content.append(
                {
                    "type": "input_image",
                    "image_url": _file_path_to_data_url(Path(photo_path)),
                }
            )
        response = client.responses.create(
            model="gpt-4.1-mini",
            store=False,
            temperature=0.2,
            text={
                "verbosity": "medium",
                "format": {
                    "type": "json_schema",
                    "name": "vinted_photo_analysis_payload",
                    "strict": True,
                    "schema": VINTED_PHOTO_ANALYSIS_SCHEMA,
                },
            },
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": VINTED_PHOTO_ANALYSIS_SYSTEM_PROMPT}]},
                {"role": "user", "content": user_content},
            ],
        )
        output_text = str(getattr(response, "output_text", "") or "").strip()
        if not output_text:
            payload = response.model_dump() if hasattr(response, "model_dump") else {}
            for item in payload.get("output", []) or []:
                if str(item.get("type", "") or "") != "message":
                    continue
                for content_item in item.get("content", []) or []:
                    if str(content_item.get("type", "") or "") == "output_text":
                        output_text = str(content_item.get("text", "") or "").strip()
                        if output_text:
                            break
                if output_text:
                    break
        if not output_text:
            raise ValueError("OpenAI returned an empty photo-analysis response.")
        parsed = json.loads(output_text)
        if not isinstance(parsed, dict):
            raise ValueError("OpenAI returned an invalid photo-analysis payload.")
        normalized = {
            "title": str(parsed.get("title", "") or "").strip(),
            "description": str(parsed.get("description", "") or "").strip(),
            "category": str(parsed.get("category", "") or "").strip(),
            "model": "gpt-4.1-mini",
        }
        return normalized

    async def _enhance_vinted_upload_photos_with_ai(self, photo_paths: list[str]) -> list[str]:
        api_key = self._resolve_openai_api_key()
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in the environment or project secret store.")

        async def enhance_single_variant(photo_path: str, variant_name: str, prompt: str) -> list[str]:
            def worker() -> list[str]:
                LOGGER.info(
                    "discord_vinted_ai_variant_start variant=%s source=%s",
                    variant_name,
                    str(Path(photo_path).name),
                )
                result = generate_vinted_ai_variants(
                    api_key=api_key,
                    photo_paths=[photo_path],
                    prompt=prompt,
                    output_dir=self.storage_root / "vinted_ai_photos" / variant_name,
                    model=DEFAULT_VINTED_AI_MODEL,
                    size=DEFAULT_VINTED_AI_SIZE,
                    variants=1,
                )
                generated_paths = [str(path) for path in list(result.get("generated_photo_paths", []) or []) if str(path).strip()]
                LOGGER.info(
                    "discord_vinted_ai_variant_done variant=%s generated=%s",
                    variant_name,
                    [Path(path).name for path in generated_paths],
                )
                return generated_paths

            return await _run_blocking(worker)

        enhanced_paths: list[str] = []
        for photo_path in photo_paths:
            per_photo_generated: list[str] = []
            for variant_name, prompt in VINTED_AI_UPLOAD_VARIANT_PROMPTS:
                try:
                    generated = await enhance_single_variant(photo_path, variant_name, prompt)
                except Exception:
                    LOGGER.exception(
                        "discord_vinted_ai_variant_failed variant=%s source=%s",
                        variant_name,
                        str(Path(photo_path).name),
                    )
                    raise
                if not generated:
                    raise RuntimeError(f"OpenAI returned no enhanced photo for: {photo_path} [{variant_name}]")
                per_photo_generated.extend(generated[:1])
            enhanced_paths.extend(per_photo_generated)
        return enhanced_paths

    @staticmethod
    def _append_model_label(current: str, extra: str) -> str:
        labels = [str(item or "").strip() for item in str(current or "").split(",") if str(item or "").strip()]
        extra_label = str(extra or "").strip()
        if extra_label and extra_label not in labels:
            labels.append(extra_label)
        return ", ".join(labels)

    def _resolve_openai_api_key(self) -> str:
        env_value = str(os.environ.get("OPENAI_API_KEY", "") or "").strip()
        if env_value:
            return env_value
        try:
            project_key = SecretStore(self.root / "data" / "secrets.json").get_project()
        except Exception:
            project_key = ""
        return str(project_key or "").strip()

    async def _collect_attachment_inputs(
        self,
        attachments: Iterable[DiscordAttachment],
    ) -> tuple[list[str], dict[str, Any]]:
        photo_paths: list[str] = []
        metadata: dict[str, Any] = {}
        for attachment in attachments:
            url = str(attachment.url or "").strip()
            if not url:
                continue
            filename = str(attachment.filename or "").strip() or f"{uuid.uuid4().hex}.bin"
            if self._is_text_attachment(attachment):
                saved = await self._download_binary(url, filename=filename, bucket="vinted_upload_meta")
                extracted = self._extract_fields_from_attachment(saved)
                metadata = self._merge_payload_with_attachment_fields(metadata, extracted)
                continue
            saved = await self._download_binary(url, filename=filename, bucket="vinted_upload_photos")
            photo_paths.append(str(saved))
        return photo_paths, metadata

    @staticmethod
    def _is_text_attachment(attachment: DiscordAttachment) -> bool:
        suffix = Path(str(attachment.filename or "")).suffix.lower()
        if suffix in TEXT_ATTACHMENT_SUFFIXES:
            return True
        return str(attachment.content_type or "").lower().startswith("text/")

    def _extract_fields_from_attachment(self, path: Path) -> dict[str, Any]:
        suffix = path.suffix.lower()
        if suffix == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                payload = None
            if isinstance(payload, dict):
                if isinstance(payload.get("items"), list) and payload["items"]:
                    first = payload["items"][0]
                    if isinstance(first, dict):
                        return self._normalize_payload_fields(first)
                return self._normalize_payload_fields(payload)
        text = path.read_text(encoding="utf-8", errors="replace")
        parsed = self.parse_vinted_upload_payload(text)
        if str(parsed.get("price", "") or "").strip():
            return parsed
        price_match = re.search(
            r"(?im)^\s*(?:price|prezzo)\s*[:=-]\s*([0-9]+(?:[.,][0-9]{1,2})?)\s*(?:€|eur|euro)?\s*$",
            text,
        )
        if price_match:
            parsed["price"] = price_match.group(1).strip()
        return parsed

    async def _download_url_list(self, urls: list[str], *, bucket: str) -> list[str]:
        paths: list[str] = []
        for index, url in enumerate(urls, start=1):
            suffix = mimetypes.guess_extension(mimetypes.guess_type(url)[0] or "") or ".bin"
            saved = await self._download_binary(url, filename=f"photo_{index}{suffix}", bucket=bucket)
            paths.append(str(saved))
        return paths

    async def _download_binary(self, url: str, *, filename: str, bucket: str) -> Path:
        target_dir = self.storage_root / bucket / uuid.uuid4().hex[:12]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / _sanitize_filename(filename)

        def worker() -> Path:
            request = Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36 AgentLabDiscord/1.0"
                    )
                },
            )
            with urlopen(request, timeout=30) as response:
                target.write_bytes(response.read())
            return target.resolve()

        return await _run_blocking(worker)

    @staticmethod
    def _normalize_photo_urls(value: Any) -> list[str]:
        if isinstance(value, (list, tuple, set)):
            items = value
        else:
            items = _split_photo_urls(str(value or ""))
        urls: list[str] = []
        for item in items:
            text = str(item or "").strip()
            if text.startswith(("http://", "https://")):
                urls.append(text)
        return list(dict.fromkeys(urls))


def _split_photo_urls(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[\n,;]+", str(value or "")) if item.strip()]


def _parse_bool_value(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "submit", "publish", "pubblica"}


def _sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return cleaned[:160] or f"{uuid.uuid4().hex}.bin"


async def _run_blocking(func):
    try:
        import asyncio
        return await asyncio.to_thread(func)
    except AttributeError:  # pragma: no cover
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, func)


def _file_path_to_data_url(path: Path) -> str:
    file_path = path.expanduser().resolve()
    mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
