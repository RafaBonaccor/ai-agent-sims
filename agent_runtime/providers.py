from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .models import ModelSettings


@dataclass(frozen=True)
class ProviderProfile:
    id: str
    label: str
    api_mode: str
    base_url: str = ""
    env_vars: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    auth: str = "none"
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedProvider:
    profile: ProviderProfile
    settings: ModelSettings
    api_key: Optional[str]
    api_key_env: str
    source: str


class ProviderRegistry:
    """Provider profiles plus shared runtime credential/endpoint resolution."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.profiles: dict[str, ProviderProfile] = {}
        self._register_builtins()
        self._discover_json_profiles()

    def register(self, profile: ProviderProfile) -> None:
        if not profile.id or profile.id in {".", ".."}:
            raise ValueError("Provider profile id is invalid")
        self.profiles[profile.id] = profile

    def _register_builtins(self) -> None:
        profiles = [
            ProviderProfile(
                id="simulated",
                label="Native simulator",
                api_mode="simulated",
                models=("native-simulator", "native-supervisor"),
            ),
            ProviderProfile(
                id="codex-cli",
                label="Codex CLI",
                api_mode="codex_cli",
                models=("default",),
                auth="Codex local login",
            ),
            ProviderProfile(
                id="openai-responses",
                label="OpenAI Responses API",
                api_mode="responses",
                base_url="https://api.openai.com/v1",
                env_vars=("OPENAI_API_KEY",),
                models=("gpt-5.4-mini", "gpt-5.4"),
                auth="OPENAI_API_KEY",
            ),
            ProviderProfile(
                id="openai-compatible",
                label="OpenAI-compatible API",
                api_mode="chat_completions",
                auth="Configured per agent",
            ),
        ]
        for profile in profiles:
            self.register(profile)

    def _discover_json_profiles(self) -> None:
        directory = self.workspace_root / "config" / "providers"
        if not directory.is_dir():
            return
        for path in sorted(directory.glob("*.json")):
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                profile = ProviderProfile(
                    id=str(document["id"]),
                    label=str(document.get("label") or document["id"]),
                    api_mode=str(document.get("api_mode") or "chat_completions"),
                    base_url=str(document.get("base_url") or ""),
                    env_vars=tuple(str(value) for value in document.get("env_vars", [])),
                    models=tuple(str(value) for value in document.get("models", [])),
                    auth=str(document.get("auth") or "Configured provider"),
                    metadata={"source": str(path.relative_to(self.workspace_root))},
                )
                if profile.api_mode not in {
                    "simulated",
                    "codex_cli",
                    "responses",
                    "chat_completions",
                }:
                    continue
                self.register(profile)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue

    def get(self, provider_id: str) -> ProviderProfile:
        profile = self.profiles.get(provider_id)
        if profile is None:
            raise ValueError(f"Unknown provider profile: {provider_id}")
        return profile

    def resolve(self, settings: ModelSettings) -> ResolvedProvider:
        profile = self.get(settings.provider)
        base_url = settings.base_url.strip() or profile.base_url
        env_candidates = (
            (settings.api_key_env,) if settings.api_key_env else profile.env_vars
        )
        api_key_env = next(
            (name for name in env_candidates if name and os.environ.get(name)),
            env_candidates[0] if env_candidates else "",
        )
        api_key = os.environ.get(api_key_env) if api_key_env else None
        if profile.api_mode in {"responses", "chat_completions"}:
            if not base_url:
                raise ValueError(f"Provider {profile.id} requires a base URL")
            if env_candidates and not api_key:
                raise RuntimeError(
                    f"Missing API key environment variable: {api_key_env or env_candidates[0]}"
                )
        resolved_settings = settings.model_copy(
            update={"base_url": base_url, "api_key_env": api_key_env}
        )
        source = "agent-settings" if settings.base_url or settings.api_key_env else "provider-profile"
        return ResolvedProvider(
            profile=profile,
            settings=resolved_settings,
            api_key=api_key,
            api_key_env=api_key_env,
            source=source,
        )

    def statuses(self) -> list[dict[str, object]]:
        statuses = []
        for profile in self.profiles.values():
            available = True
            if profile.env_vars:
                available = any(os.environ.get(name) for name in profile.env_vars)
            statuses.append(
                {
                    "id": profile.id,
                    "label": profile.label,
                    "apiMode": profile.api_mode,
                    "available": available,
                    "auth": profile.auth,
                    "models": list(profile.models),
                    "source": profile.metadata.get("source", "builtin"),
                }
            )
        return statuses
