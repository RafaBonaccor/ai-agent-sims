from __future__ import annotations

import asyncio
import logging
import os
import re
import json
from urllib.parse import urlencode
from pathlib import Path
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from .codex_bridge import CodexCliBridge
from .discord_projects import DiscordAttachment, DiscordProjectBridge, PendingDiscordProjectJob
from .engine import AgentRuntime
from .models import SystemSettings
from .models import RuntimeEvent, TaskCreate
from .project_gateway import ProjectGateway
from .vinted_reports import write_vinted_report_html
from .vinted_reports import build_vinted_report
from .runpod_manager import RunPodManager, RunPodManagerError
from .runpod_batches import RunPodBatchError, RunPodBatchService


LOGGER = logging.getLogger("agent_lab.discord")
SendMessage = Callable[..., Awaitable[None]]
DiscordAttachmentType = Any


@dataclass(frozen=True)
class DiscordGatewayConfig:
    token: str = ""
    command_prefix: str = "!"
    default_agent_id: str = ""
    allowed_guild_ids: set[int] = field(default_factory=set)
    allowed_channel_ids: set[int] = field(default_factory=set)
    enable_message_content: bool = False
    sync_commands: bool = True

    @classmethod
    def from_env(cls) -> "DiscordGatewayConfig":
        return cls(
            token=os.environ.get("AGENT_LAB_DISCORD_TOKEN", "").strip(),
            command_prefix=os.environ.get("AGENT_LAB_DISCORD_PREFIX", "!").strip() or "!",
            default_agent_id=os.environ.get("AGENT_LAB_DISCORD_DEFAULT_AGENT", "").strip(),
            allowed_guild_ids=parse_id_set(os.environ.get("AGENT_LAB_DISCORD_ALLOWED_GUILDS", "")),
            allowed_channel_ids=parse_id_set(os.environ.get("AGENT_LAB_DISCORD_ALLOWED_CHANNELS", "")),
            enable_message_content=parse_bool(os.environ.get("AGENT_LAB_DISCORD_MESSAGE_CONTENT", "")),
            sync_commands=not parse_bool(os.environ.get("AGENT_LAB_DISCORD_SKIP_COMMAND_SYNC", "")),
        )

    @classmethod
    def from_system_settings(cls, settings: SystemSettings, token: str) -> "DiscordGatewayConfig":
        discord = getattr(settings, "discord", None)
        if not discord or not bool(getattr(discord, "enabled", False)):
            return cls()
        return cls(
            token=str(token or "").strip(),
            command_prefix=str(getattr(discord, "command_prefix", "!") or "!").strip() or "!",
            default_agent_id=str(getattr(discord, "default_agent_id", "") or "").strip(),
            allowed_guild_ids={int(item) for item in list(getattr(discord, "allowed_guild_ids", []) or []) if int(item) > 0},
            allowed_channel_ids={int(item) for item in list(getattr(discord, "allowed_channel_ids", []) or []) if int(item) > 0},
            enable_message_content=bool(getattr(discord, "message_content", False)),
            sync_commands=bool(getattr(discord, "sync_commands", True)),
        )


@dataclass
class PendingDiscordTask:
    agent_id: str
    prompt: str
    send: SendMessage


@dataclass(frozen=True)
class ParsedDiscordCommand:
    action: str
    agent_id: str = ""
    prompt: str = ""


class DiscordGateway:
    """Optional Discord bot bridge for the runtime.

    The module imports discord.py lazily so the runtime still starts without the
    optional dependency when Discord is not configured.
    """

    def __init__(
        self,
        runtime: AgentRuntime,
        project_gateway: Optional[ProjectGateway] = None,
        project_bridge: Optional[DiscordProjectBridge] = None,
        config: Optional[DiscordGatewayConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.runtime = runtime
        self.project_gateway = project_gateway
        self.config = config or DiscordGatewayConfig.from_env()
        self.logger = logger or LOGGER
        self.project_bridge = project_bridge
        if self.project_bridge is None and self.project_gateway is not None:
            self.project_bridge = DiscordProjectBridge(Path(__file__).resolve().parent.parent, self.project_gateway)
        self.codex_bridge = CodexCliBridge(Path(__file__).resolve().parent.parent, logger=self.logger)
        self.runpod_batches = RunPodBatchService(
            Path(__file__).resolve().parent.parent / "data" / "runpod_batches",
            self.runpod_manager,
        )
        self.pending: dict[str, PendingDiscordTask] = {}
        self.pending_project_jobs: dict[str, tuple[PendingDiscordProjectJob, SendMessage]] = {}
        self.channel_defaults: dict[str, str] = {}
        self.last_allowed_channel_id: int = self._load_last_allowed_channel_id()
        self.connected = False
        self.enabled = bool(self.config.token)
        self._bot: Any = None
        self._discord: Any = None
        self._bot_task: Optional[asyncio.Task[None]] = None
        self._event_task: Optional[asyncio.Task[None]] = None
        self._event_queue: Optional[asyncio.Queue[RuntimeEvent]] = None
        self._commands_synced = False

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "connected": self.connected,
            "pendingTasks": len(self.pending),
            "pendingProjectJobs": len(self.pending_project_jobs),
            "codexBridge": self.codex_bridge.status() if self.codex_bridge else {"enabled": False},
            "messageContent": self.config.enable_message_content,
            "allowedGuilds": sorted(self.config.allowed_guild_ids),
            "allowedChannels": sorted(self.config.allowed_channel_ids),
            "notificationTargetConfigured": bool(self._notification_channel_id()),
        }

    @property
    def _last_channel_path(self) -> Path:
        return Path(__file__).resolve().parent.parent / "data" / "discord_last_channel.json"

    def _load_last_allowed_channel_id(self) -> int:
        try:
            value = json.loads(self._last_channel_path.read_text(encoding="utf-8")).get("channel_id", 0)
            return max(0, int(value or 0))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return 0

    def _remember_allowed_channel(self, channel_id: int) -> None:
        channel_id = max(0, int(channel_id or 0))
        if not channel_id:
            return
        self.last_allowed_channel_id = channel_id
        try:
            self._last_channel_path.parent.mkdir(parents=True, exist_ok=True)
            self._last_channel_path.write_text(json.dumps({"channel_id": channel_id}) + "\n", encoding="utf-8")
        except OSError:
            self.logger.exception("discord_last_channel_persist_failed")

    def _notification_channel_id(self) -> int:
        if self.last_allowed_channel_id:
            return self.last_allowed_channel_id
        return min(self.config.allowed_channel_ids) if self.config.allowed_channel_ids else 0

    async def watch_task_result(self, task: Any) -> None:
        """Route a scheduled agent task result to the last active Discord channel."""
        channel_id = self._notification_channel_id()
        if not channel_id:
            self.logger.warning("discord_scheduled_task_no_target task=%s", getattr(task, "id", ""))
            return

        async def send(message: str, **_kwargs: Any) -> None:
            if self._bot is None:
                raise RuntimeError("Discord bot is not running")
            channel = self._bot.get_channel(channel_id)
            if channel is None:
                channel = await self._bot.fetch_channel(channel_id)
            for chunk in chunk_discord_message(str(message or "")):
                await channel.send(chunk, allowed_mentions=self._discord.AllowedMentions.none())

        task_id = str(getattr(task, "id", "") or "")
        agent_id = str(getattr(task, "requested_agent_id", "") or "ai-news-navigator")
        description = str(getattr(task, "description", "") or "")
        if task_id:
            self.pending[task_id] = PendingDiscordTask(agent_id=agent_id, prompt=description, send=send)
            self.logger.info("discord_scheduled_task_delivery_registered task=%s channel=%s", task_id, channel_id)

    def runpod_manager(self) -> RunPodManager:
        secrets = getattr(getattr(self.runtime, "executor", None), "secrets", None)
        api_key = secrets.get_runpod_api_key() if secrets is not None else None
        return RunPodManager(self.runtime.get_system_settings().runpod, api_key)

    def load_runpod_workflow_preset(self, preset_id: str) -> tuple[dict[str, object], str, dict[str, object]]:
        """Load only project-owned saved presets; Discord never accepts arbitrary paths."""
        requested = str(preset_id or "").strip()
        library_path = Path(__file__).resolve().parent.parent / "config" / "runpod_workflows.json"
        try:
            library = json.loads(library_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RunPodBatchError(f"Workflow library cannot be read: {error}") from error
        presets = library.get("presets", []) if isinstance(library, dict) else []
        preset = next((item for item in presets if isinstance(item, dict) and str(item.get("id", "")) == requested), None)
        if not isinstance(preset, dict):
            raise RunPodBatchError("Unknown workflow preset. Use `wan-14b-image-to-video` or `seedvr2-native-video`.")
        path = Path(str(preset.get("path", ""))).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        try:
            workflow = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RunPodBatchError(f"Saved workflow cannot be read: {error}") from error
        if not isinstance(workflow, dict) or "nodes" in workflow or "links" in workflow:
            raise RunPodBatchError("Saved workflow is not ComfyUI API format.")
        return workflow, str(preset.get("name", requested)), preset

    @staticmethod
    def find_runpod_media_loader(workflow: dict[str, object], media_kind: str) -> str:
        """Select the actual upload node, never helper/list loader nodes."""
        kind = str(media_kind).lower()
        exact = "loadimage" if kind == "image" else "loadvideo"
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            class_type = str(node.get("class_type", "")).strip().lower()
            if class_type == exact or (kind == "video" and "loadvideo" in class_type):
                return str(node_id)
        raise RunPodBatchError(f"Saved preset has no compatible {exact.title()} input node.")

    async def _announce_runpod_batch_completion(self, batch_id: str, send: SendMessage) -> None:
        while True:
            await asyncio.sleep(8)
            try:
                batch = self.runpod_batches.get_batch(batch_id)
            except RunPodBatchError:
                return
            status = str(batch.get("status", ""))
            if status not in {"completed", "completed_with_errors", "failed", "cancelled"}:
                continue
            counts = batch.get("counts", {}) if isinstance(batch.get("counts"), dict) else {}
            summary = f"RunPod batch `{batch_id}` {status}. Completed: {counts.get('completed', 0)} · failed: {counts.get('failed', 0)} · cancelled: {counts.get('cancelled', 0)}."
            error = str(batch.get("error", "") or "")
            if error:
                summary += f"\nError: {error[:700]}"
            archived_files: list[Path] = []
            for item in batch.get("items", []) if isinstance(batch.get("items"), list) else []:
                if not isinstance(item, dict):
                    continue
                for index, output in enumerate(item.get("outputs", []) if isinstance(item.get("outputs"), list) else []):
                    if not isinstance(output, dict):
                        continue
                    if output.get("local_path"):
                        try:
                            archived_files.append(self.runpod_batches.output_file(batch_id, str(item.get("id", "")), index))
                        except RunPodBatchError as error:
                            summary += f"\nCould not attach {output.get('filename', 'output')}: {error}"
            if archived_files:
                summary += f"\nAttached {len(archived_files)} generated output file(s)."
            await send(summary, files=archived_files[:10])
            return

    def resolve_runpod_pod_id(self, pod_id: str) -> str:
        requested = str(pod_id or "").strip()
        if requested:
            return requested
        pods = self.runpod_manager().list_pods()
        running = [pod for pod in pods if str(pod.get("status", "")).upper() == "RUNNING"]
        candidates = running or pods
        if len(candidates) != 1:
            raise RunPodManagerError("Specify pod_id because there is not exactly one current Pod.")
        return str(candidates[0].get("id", ""))

    def format_runpod_status(self) -> str:
        manager = self.runpod_manager()
        status = manager.status()
        if status.get("error"):
            return f"Runpod status unavailable: {status['error']}"
        pods = list(status.get("pods") or [])
        lines = [
            "**Runpod Manager**",
            f"Volume: `{status.get('network_volume_id') or 'not configured'}` · region `{status.get('data_center_id') or 'derived from volume'}`",
            f"GPU: `{status.get('preferred_gpu') or 'not selected'}`",
        ]
        if not pods:
            lines.append("Pods: none")
        else:
            lines.append("Pods:")
            lines.extend(f"- `{pod.get('name') or pod.get('id')}` — **{pod.get('status') or 'unknown'}** (`{pod.get('id')}`)" for pod in pods)
        return "\n".join(lines)

    def format_runpod_gpus(self) -> str:
        manager = self.runpod_manager()
        settings = self.runtime.get_system_settings().runpod
        volume = manager.get_network_volume(settings.network_volume_id) if settings.network_volume_id else {}
        data_center = str(volume.get("dataCenter") or settings.data_center_id or "").strip()
        if not data_center:
            raise RunPodManagerError("Configure a Network Volume or data center first.")
        gpus = manager.list_gpu_types(data_center)
        lines = [f"**Runpod GPUs for `{data_center}`** ({len(gpus)} available)"]
        for gpu in gpus[:20]:
            price = gpu.get("secure_price") or gpu.get("community_price") or "?"
            lines.append(f"- `{gpu.get('id')}` · {gpu.get('memory_gb', '?')} GB · {gpu.get('stock_status', 'unknown')} · from ${price}/h")
        return "\n".join(lines)

    @staticmethod
    def format_runpod_pod_result(action: str, result: dict[str, object]) -> str:
        return f"{action} Pod `{result.get('name') or result.get('id')}` — **{result.get('status') or 'requested'}**."

    @staticmethod
    def format_runpod_health(result: dict[str, object]) -> str:
        if result.get("ok"):
            return f"ComfyUI is **ready** at `{result.get('url')}`."
        return f"ComfyUI is not ready: {result.get('error') or 'unknown error'}"

    async def start(self) -> None:
        if not self.config.token:
            self.logger.info("discord_disabled reason=no_token")
            return

        try:
            import discord
            from discord import app_commands
            from discord.ext import commands
        except ImportError as error:
            self.enabled = False
            self.logger.error(
                "discord_disabled reason=missing_dependency dependency=discord.py error=%s",
                error,
            )
            return

        self._discord = discord
        globals()["DiscordAttachmentType"] = discord.Attachment
        intents = discord.Intents.none()
        intents.guilds = True
        if self.config.enable_message_content:
            intents.messages = True
            intents.message_content = True
            intents.dm_messages = True

        bot = commands.Bot(command_prefix=self.config.command_prefix, intents=intents)
        self._bot = bot
        gateway = self

        async def agent_autocomplete(_interaction: Any, current: str) -> list[Any]:
            current_lower = current.lower()
            choices = []
            for agent in gateway.runtime.list_agents():
                label = f"{agent.name} ({agent.id})"
                if current_lower and current_lower not in agent.id.lower() and current_lower not in agent.name.lower():
                    continue
                choices.append(app_commands.Choice(name=label[:100], value=agent.id))
                if len(choices) >= 25:
                    break
            return choices

        @bot.event
        async def on_ready() -> None:
            gateway.connected = True
            if gateway.config.sync_commands and not gateway._commands_synced:
                await gateway._sync_commands()
            gateway.logger.info(
                "discord_connected bot=%s guilds=%s message_content=%s",
                getattr(bot.user, "id", "-"),
                len(getattr(bot, "guilds", []) or []),
                gateway.config.enable_message_content,
            )

        @bot.event
        async def on_disconnect() -> None:
            gateway.connected = False
            gateway.logger.warning("discord_disconnected")

        @bot.event
        async def on_message(message: Any) -> None:
            if not gateway.config.enable_message_content:
                return
            await gateway._handle_text_message(message)

        @bot.tree.command(name="agents", description="List Agent Lab agents")
        async def agents_command(interaction: Any) -> None:
            if not await gateway._allow_interaction(interaction):
                return
            await interaction.response.send_message(gateway.format_agents(), ephemeral=True)

        @bot.tree.command(name="runpod_status", description="Show Runpod Pods, their state, and the configured volume")
        async def runpod_status_command(interaction: Any) -> None:
            if not await gateway._allow_interaction(interaction):
                return
            try:
                await interaction.response.send_message(gateway.format_runpod_status(), ephemeral=True)
            except RunPodManagerError as error:
                await interaction.response.send_message(f"Runpod unavailable: {error}", ephemeral=True)

        @bot.tree.command(name="runpod_gpus", description="List GPUs available in the selected Network Volume region")
        async def runpod_gpus_command(interaction: Any) -> None:
            if not await gateway._allow_interaction(interaction):
                return
            await interaction.response.defer(thinking=True, ephemeral=True)
            try:
                await interaction.followup.send(gateway.format_runpod_gpus(), ephemeral=True)
            except RunPodManagerError as error:
                await interaction.followup.send(f"Runpod GPU lookup failed: {error}", ephemeral=True)

        @bot.tree.command(name="runpod_start", description="Start a stopped Runpod Pod")
        @app_commands.describe(pod_id="Pod ID; leave empty to use the only/current Pod")
        async def runpod_start_command(interaction: Any, pod_id: str = "") -> None:
            if not await gateway._allow_interaction(interaction):
                return
            await interaction.response.defer(thinking=True, ephemeral=True)
            try:
                result = gateway.runpod_manager().start_pod(gateway.resolve_runpod_pod_id(pod_id))
                await interaction.followup.send(gateway.format_runpod_pod_result("Started", result), ephemeral=True)
            except RunPodManagerError as error:
                await interaction.followup.send(f"Runpod start failed: {error}", ephemeral=True)

        @bot.tree.command(name="runpod_stop", description="Stop a Runpod Pod and release its GPU")
        @app_commands.describe(pod_id="Pod ID; leave empty to use the only/current Pod", confirm="Must be true to stop the Pod")
        async def runpod_stop_command(interaction: Any, confirm: bool = False, pod_id: str = "") -> None:
            if not await gateway._allow_interaction(interaction):
                return
            if not confirm:
                await interaction.response.send_message("Set `confirm` to true to stop the Pod.", ephemeral=True)
                return
            await interaction.response.defer(thinking=True, ephemeral=True)
            try:
                result = gateway.runpod_manager().stop_pod(gateway.resolve_runpod_pod_id(pod_id))
                await interaction.followup.send(gateway.format_runpod_pod_result("Stopped", result), ephemeral=True)
            except RunPodManagerError as error:
                await interaction.followup.send(f"Runpod stop failed: {error}", ephemeral=True)

        @bot.tree.command(name="runpod_terminate", description="Permanently terminate a Runpod Pod")
        @app_commands.describe(pod_id="Pod ID", confirm="Must be true to terminate the Pod")
        async def runpod_terminate_command(interaction: Any, pod_id: str, confirm: bool = False) -> None:
            if not await gateway._allow_interaction(interaction):
                return
            if not confirm:
                await interaction.response.send_message("Set `confirm` to true to permanently terminate the Pod.", ephemeral=True)
                return
            await interaction.response.defer(thinking=True, ephemeral=True)
            try:
                result = gateway.runpod_manager().terminate_pod(gateway.resolve_runpod_pod_id(pod_id))
                await interaction.followup.send(f"Terminated Pod `{result['id']}`.", ephemeral=True)
            except RunPodManagerError as error:
                await interaction.followup.send(f"Runpod termination failed: {error}", ephemeral=True)

        @bot.tree.command(name="runpod_health", description="Check whether ComfyUI is ready on a Runpod Pod")
        @app_commands.describe(pod_id="Pod ID; leave empty to use the only/current Pod")
        async def runpod_health_command(interaction: Any, pod_id: str = "") -> None:
            if not await gateway._allow_interaction(interaction):
                return
            await interaction.response.defer(thinking=True, ephemeral=True)
            try:
                result = gateway.runpod_manager().comfyui_health(gateway.resolve_runpod_pod_id(pod_id))
                await interaction.followup.send(gateway.format_runpod_health(result), ephemeral=True)
            except RunPodManagerError as error:
                await interaction.followup.send(f"ComfyUI health check failed: {error}", ephemeral=True)

        @bot.tree.command(name="runpod_upload_image", description="Upload an attached PNG, JPEG, or WebP image to ComfyUI")
        @app_commands.describe(image="Image to upload", pod_id="Pod ID; leave empty to use the only/current Pod")
        async def runpod_upload_image_command(interaction: Any, image: DiscordAttachmentType, pod_id: str = "") -> None:
            if not await gateway._allow_interaction(interaction):
                return
            content_type = str(getattr(image, "content_type", "") or "")
            if not content_type.startswith("image/"):
                await interaction.response.send_message("Attach a PNG, JPEG, or WebP image.", ephemeral=True)
                return
            await interaction.response.defer(thinking=True, ephemeral=True)
            try:
                content = await image.read()
                result = gateway.runpod_manager().upload_comfyui_image(
                    gateway.resolve_runpod_pod_id(pod_id),
                    str(getattr(image, "filename", "upload.png") or "upload.png"),
                    content,
                )
                uploaded_name = "/".join(part for part in [str(result.get("subfolder", "") or "").strip(), str(result.get("name", "") or "").strip()] if part)
                await interaction.followup.send(f"Uploaded to ComfyUI. Set `LoadImage.image` to `{uploaded_name}`.", ephemeral=True)
            except RunPodManagerError as error:
                await interaction.followup.send(f"Runpod image upload failed: {error}", ephemeral=True)

        @bot.tree.command(name="runpod_upload_media", description="Upload an attached image or video to ComfyUI")
        @app_commands.describe(media="PNG, JPEG, WebP, MP4, WebM, or MOV file", pod_id="Pod ID; leave empty to use the only/current Pod")
        async def runpod_upload_media_command(interaction: Any, media: DiscordAttachmentType, pod_id: str = "") -> None:
            if not await gateway._allow_interaction(interaction):
                return
            content_type = str(getattr(media, "content_type", "") or "")
            filename = str(getattr(media, "filename", "upload") or "upload")
            suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            is_video = content_type.startswith("video/") or suffix in {"mp4", "webm", "mov"}
            is_image = content_type.startswith("image/") or suffix in {"png", "jpg", "jpeg", "webp"}
            if not (is_video or is_image):
                await interaction.response.send_message("Attach a PNG, JPEG, WebP, MP4, WebM, or MOV file.", ephemeral=True)
                return
            await interaction.response.defer(thinking=True, ephemeral=True)
            try:
                content = await media.read()
                result = gateway.runpod_manager().upload_comfyui_media(
                    gateway.resolve_runpod_pod_id(pod_id), filename, content,
                )
                uploaded_name = "/".join(part for part in [str(result.get("subfolder", "") or "").strip(), str(result.get("name", "") or "").strip()] if part)
                loader = "LoadVideo" if is_video else "LoadImage"
                await interaction.followup.send(
                    f"Uploaded {('video' if is_video else 'image')} to ComfyUI as `{uploaded_name}`. "
                    f"Attach it to `/runpod_workflow` as `media` to fill compatible `{loader}` nodes automatically.",
                    ephemeral=True,
                )
            except RunPodManagerError as error:
                await interaction.followup.send(f"Runpod media upload failed: {error}", ephemeral=True)

        @bot.tree.command(name="runpod_batch", description="Run a saved ComfyUI workflow on several attached media files")
        @app_commands.describe(
            preset="wan-14b-image-to-video, seedvr2-native-video, or seedvr2-image-upscale",
            media1="First image/video", media2="Optional media", media3="Optional media", media4="Optional media", media5="Optional media",
        )
        async def runpod_batch_command(
            interaction: Any,
            preset: str,
            media1: DiscordAttachmentType,
            media2: Optional[DiscordAttachmentType] = None,
            media3: Optional[DiscordAttachmentType] = None,
            media4: Optional[DiscordAttachmentType] = None,
            media5: Optional[DiscordAttachmentType] = None,
        ) -> None:
            if not await gateway._allow_interaction(interaction):
                return
            attachments = [item for item in (media1, media2, media3, media4, media5) if item is not None]
            await interaction.response.defer(thinking=True)
            try:
                workflow, workflow_name, metadata = gateway.load_runpod_workflow_preset(preset)
                required_kind = str(metadata.get("input_kind", "image") or "image").lower()
                loader_id = gateway.find_runpod_media_loader(workflow, required_kind)
                batch = gateway.runpod_batches.create_batch(
                    workflow, media_loader_id=loader_id, auto_deploy=True, auto_shutdown=True,
                    min_vram_gb=int(metadata.get("min_vram_gb", 0) or 0), workflow_id=str(metadata.get("id", preset)),
                )
                batch_id = str(batch["id"])
                for attachment in attachments:
                    filename = str(getattr(attachment, "filename", "upload") or "upload")
                    suffix = Path(filename).suffix.lower()
                    kind = "video" if suffix in {".mp4", ".webm", ".mov", ".mkv", ".avi"} else "image"
                    if kind != required_kind:
                        raise RunPodBatchError(f"{filename} is {kind}; preset `{preset}` requires {required_kind} input.")
                    gateway.runpod_batches.add_item(batch_id, filename, await attachment.read())
                gateway.runpod_batches.start_batch(batch_id)
            except (RunPodBatchError, RunPodManagerError) as error:
                await interaction.followup.send(f"RunPod batch failed to start: {error}", ephemeral=True)
                return
            async def send(reply: str, *, files: list[Path] | None = None) -> None:
                attachments = [discord.File(str(path), filename=path.name) for path in (files or [])]
                await interaction.followup.send(reply, files=attachments or None, allowed_mentions=discord.AllowedMentions.none())
            await send(
                f"RunPod batch `{batch_id}` started · `{workflow_name}` · {len(attachments)} item(s). "
                "It deploys a Pod only if necessary and closes only a Pod created by this batch."
            )
            asyncio.create_task(gateway._announce_runpod_batch_completion(batch_id, send), name=f"discord-runpod-batch-{batch_id}")

        @bot.tree.command(name="runpod_workflow", description="Queue an attached ComfyUI API workflow JSON on a Pod")
        @app_commands.describe(workflow="ComfyUI API workflow JSON file", media="Optional image/video to insert into loader nodes", pod_id="Pod ID; leave empty to use the only/current Pod")
        async def runpod_workflow_command(interaction: Any, workflow: DiscordAttachmentType, media: Optional[DiscordAttachmentType] = None, pod_id: str = "") -> None:
            if not await gateway._allow_interaction(interaction):
                return
            if not str(getattr(workflow, "filename", "") or "").lower().endswith(".json"):
                await interaction.response.send_message("Attach a ComfyUI API workflow `.json` file.", ephemeral=True)
                return
            await interaction.response.defer(thinking=True, ephemeral=True)
            try:
                import json

                payload = json.loads((await workflow.read()).decode("utf-8"))
                manager = gateway.runpod_manager()
                resolved_pod_id = gateway.resolve_runpod_pod_id(pod_id)
                media_name = ""
                media_kind = ""
                injected_nodes = 0
                if media is not None:
                    filename = str(getattr(media, "filename", "upload") or "upload")
                    content_type = str(getattr(media, "content_type", "") or "")
                    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                    media_kind = "video" if content_type.startswith("video/") or suffix in {"mp4", "webm", "mov"} else "image"
                    upload = manager.upload_comfyui_media(resolved_pod_id, filename, await media.read())
                    media_name = "/".join(part for part in [str(upload.get("subfolder", "") or "").strip(), str(upload.get("name", "") or "").strip()] if part)
                    payload, injected_nodes = manager.inject_comfyui_media(payload, media_name, media_kind)
                result = gateway.runpod_manager().queue_comfyui_prompt(
                    resolved_pod_id, payload,
                )
                prompt_id = str(result.get("prompt_id") or result.get("promptId") or "")
                await interaction.followup.send(
                    f"Workflow queued{f' · prompt `{prompt_id}`' if prompt_id else ''}"
                    f"{f' · inserted {media_kind} into {injected_nodes} loader node(s)' if media_name else ''}.",
                    ephemeral=True,
                )
            except (UnicodeDecodeError, json.JSONDecodeError, RunPodManagerError) as error:
                await interaction.followup.send(f"Runpod workflow failed: {error}", ephemeral=True)

        @bot.tree.command(name="report", description="Generate and download the marketplace intelligence HTML report")
        @app_commands.describe(days="Report period in days, from 1 to 365")
        async def report_command(interaction: Any, days: int = 30) -> None:
            if not await gateway._allow_interaction(interaction):
                return
            await interaction.response.defer(thinking=True)
            try:
                report_path = await gateway.create_marketplace_report(days)
            except (OSError, ValueError) as error:
                gateway.logger.exception("discord_report_generation_failed channel_id=%s days=%s", interaction.channel_id, days)
                await interaction.followup.send(f"Report generation failed: {error}", ephemeral=True)
                return
            gateway.logger.info(
                "discord_report_generation_ok channel_id=%s days=%s path=%s size_bytes=%s",
                interaction.channel_id,
                gateway.normalize_report_days(days),
                report_path,
                report_path.stat().st_size,
            )
            await interaction.followup.send(
                content=f"Marketplace report ready · last {gateway.normalize_report_days(days)} days.",
                file=discord.File(str(report_path), filename=report_path.name),
                allowed_mentions=discord.AllowedMentions.none(),
            )

        @bot.tree.command(name="sold_deals", description="Show sold marketplace deals filtered by sale time")
        @app_commands.describe(
            time_range="Sale-time range: under-1, 1-6, 6-12, 12-24, or over-24",
            days="Look-back period in days, from 1 to 365",
        )
        async def sold_deals_command(interaction: Any, time_range: str = "1-6", days: int = 30) -> None:
            if not await gateway._allow_interaction(interaction):
                return
            await interaction.response.defer(thinking=True)
            try:
                normalized_range, articles = await gateway.load_sold_deals(time_range, days)
            except ValueError as error:
                await interaction.followup.send(str(error), ephemeral=True)
                return
            await gateway.send_sold_deals(
                lambda **kwargs: interaction.followup.send(**kwargs),
                articles,
                time_range=normalized_range,
                days=gateway.normalize_report_days(days),
            )

        @bot.tree.command(name="use", description="Set the default Agent Lab agent for this Discord channel")
        @app_commands.describe(agent="Agent id, for example researcher")
        async def use_command(interaction: Any, agent: str) -> None:
            if not await gateway._allow_interaction(interaction):
                return
            agent_id = agent.strip()
            if agent_id not in gateway.runtime.agents:
                await interaction.response.send_message(gateway.unknown_agent_message(agent_id), ephemeral=True)
                return
            gateway.channel_defaults[str(interaction.channel_id)] = agent_id
            await interaction.response.send_message(
                f"Default agent for this channel: `{agent_id}`.",
                ephemeral=True,
            )

        @bot.tree.command(name="ask", description="Send a chat message to an Agent Lab agent")
        @app_commands.describe(agent="Agent id, for example researcher", prompt="Message for the agent")
        async def ask_command(interaction: Any, agent: str, prompt: str) -> None:
            if not await gateway._allow_interaction(interaction):
                return
            await interaction.response.defer(thinking=True)

            async def send(content: str) -> None:
                for chunk in chunk_discord_message(content):
                    await interaction.followup.send(chunk, allowed_mentions=discord.AllowedMentions.none())

            try:
                task = await gateway.submit_chat(agent, prompt, send)
            except ValueError as error:
                await interaction.followup.send(str(error), ephemeral=True)
                return
            await interaction.followup.send(
                f"Queued `{task.id}` for `{agent}`. I will post the answer here.",
                allowed_mentions=discord.AllowedMentions.none(),
            )

        @bot.tree.command(name="chat", description="Chat with the default Agent Lab agent for this channel")
        @app_commands.describe(prompt="Message for the default agent")
        async def chat_command(interaction: Any, prompt: str) -> None:
            if not await gateway._allow_interaction(interaction):
                return
            agent_id = gateway.channel_defaults.get(str(interaction.channel_id), gateway.config.default_agent_id).strip()
            if not agent_id:
                await interaction.response.send_message(
                    "No default agent is configured for this channel. Use `/use agent:<id>` first or run `/ask agent:<id> prompt:<message>`.",
                    ephemeral=True,
                )
                return
            await interaction.response.defer(thinking=True)

            async def send(content: str) -> None:
                for chunk in chunk_discord_message(content):
                    await interaction.followup.send(chunk, allowed_mentions=discord.AllowedMentions.none())

            try:
                task = await gateway.submit_chat(agent_id, prompt, send)
            except ValueError as error:
                await interaction.followup.send(str(error), ephemeral=True)
                return
            await interaction.followup.send(
                f"Queued `{task.id}` for `{agent_id}`. I will post the answer here.",
                allowed_mentions=discord.AllowedMentions.none(),
            )

        @bot.tree.command(name="codex", description="Talk to the Codex assistant agent")
        @app_commands.describe(prompt="Message for Codex")
        async def codex_command(interaction: Any, prompt: str) -> None:
            if not await gateway._allow_interaction(interaction):
                return
            await interaction.response.defer(thinking=True)

            async def send(content: str) -> None:
                for chunk in chunk_discord_message(content):
                    await interaction.followup.send(chunk, allowed_mentions=discord.AllowedMentions.none())

            try:
                result = await gateway.send_codex_prompt(str(interaction.channel_id), prompt)
            except ValueError as error:
                await interaction.followup.send(str(error), ephemeral=True)
                return
            except RuntimeError as error:
                await interaction.followup.send(f"Codex bridge failed: {error}", ephemeral=True)
                return
            await gateway.send_codex_result(send, result)

        @bot.tree.command(name="codex_model", description="View or change the Codex model used by the Discord bridge")
        @app_commands.describe(
            action="show the current model, set a per-channel override, or clear the override",
            model="Codex model name, for example gpt-5.1-codex",
        )
        async def codex_model_command(interaction: Any, action: str, model: str = "") -> None:
            if not await gateway._allow_interaction(interaction):
                return
            action_normalized = str(action or "").strip().lower()
            channel_key = str(interaction.channel_id)
            if action_normalized == "show":
                await interaction.response.send_message(
                    gateway.format_codex_model_status(channel_key),
                    ephemeral=True,
                )
                return
            if action_normalized == "set":
                model_name = gateway.codex_bridge.set_channel_model(channel_key, model)
                await interaction.response.send_message(
                    gateway.format_codex_model_status(channel_key, override=model_name),
                    ephemeral=True,
                )
                return
            if action_normalized == "clear":
                gateway.codex_bridge.clear_channel_model(channel_key)
                await interaction.response.send_message(
                    gateway.format_codex_model_status(channel_key),
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                "Invalid action. Use `show`, `set`, or `clear`.",
                ephemeral=True,
            )

        @bot.tree.command(name="vinted_upload", description="Prepare or publish a Vinted upload job from Discord")
        @app_commands.describe(
            title="Listing title",
            description="Listing description",
            category="Vinted category label",
            brand="Brand label",
            condition="Condition label",
            material="Material label",
            price="Listing price. Leave empty to take it from a metadata attachment.",
            photo1="First product photo",
            photo2="Optional second product photo",
            photo3="Optional third product photo",
            photo4="Optional fourth product photo",
            metadata="Optional text/JSON attachment with fields like price/category/brand",
            submit="Publish instead of prepare only",
            enhance_photos="Improve attached photos with OpenAI before uploading to Vinted",
            agent="Optional agent id to attribute the job to",
        )
        async def vinted_upload_command(
            interaction: Any,
            title: str,
            description: str,
            category: str,
            brand: str,
            condition: str,
            material: str,
            photo1: DiscordAttachmentType,
            price: str = "",
            photo2: Optional[DiscordAttachmentType] = None,
            photo3: Optional[DiscordAttachmentType] = None,
            photo4: Optional[DiscordAttachmentType] = None,
            metadata: Optional[DiscordAttachmentType] = None,
            submit: bool = False,
            enhance_photos: bool = False,
            agent: str = "",
        ) -> None:
            if not await gateway._allow_interaction(interaction):
                return
            if gateway.project_bridge is None:
                await interaction.response.send_message("Project upload bridge is not configured.", ephemeral=True)
                return
            await interaction.response.defer(thinking=True)

            async def send(content: str) -> None:
                for chunk in chunk_discord_message(content):
                    await interaction.followup.send(chunk, allowed_mentions=discord.AllowedMentions.none())

            try:
                job, requested_agent = await gateway._submit_vinted_upload_interaction(
                    interaction=interaction,
                    title=title,
                    description=description,
                    category=category,
                    brand=brand,
                    condition=condition,
                    material=material,
                    photo1=photo1,
                    price=price,
                    photo2=photo2,
                    photo3=photo3,
                    photo4=photo4,
                    metadata=metadata,
                    submit=submit,
                    enhance_photos=enhance_photos,
                    agent=agent,
                )
            except ValueError as error:
                await interaction.followup.send(str(error), ephemeral=True)
                return
            gateway.pending_project_jobs[job.id] = (
                PendingDiscordProjectJob(
                    job_id=job.id,
                    project_id=job.project_id,
                    action=job.action,
                    agent_id=requested_agent,
                ),
                send,
            )
            await interaction.followup.send(
                gateway.project_bridge.format_job_queued(job),
                allowed_mentions=discord.AllowedMentions.none(),
            )

        @bot.tree.command(name="upload_ai_photo", description="Generate AI Vinted photos and prepare or publish the upload job")
        @app_commands.describe(
            title="Listing title",
            description="Listing description",
            category="Vinted category label",
            brand="Brand label",
            condition="Condition label",
            material="Material label",
            price="Listing price. Leave empty to take it from a metadata attachment.",
            photo1="First product photo",
            photo2="Optional second product photo",
            photo3="Optional third product photo",
            photo4="Optional fourth product photo",
            metadata="Optional text/JSON attachment with fields like price/category/brand",
            submit="Publish instead of prepare only",
            agent="Optional agent id to attribute the job to",
        )
        async def upload_ai_photo_command(
            interaction: Any,
            title: str,
            description: str,
            category: str,
            brand: str,
            condition: str,
            material: str,
            photo1: DiscordAttachmentType,
            price: str = "",
            photo2: Optional[DiscordAttachmentType] = None,
            photo3: Optional[DiscordAttachmentType] = None,
            photo4: Optional[DiscordAttachmentType] = None,
            metadata: Optional[DiscordAttachmentType] = None,
            submit: bool = False,
            agent: str = "",
        ) -> None:
            if not await gateway._allow_interaction(interaction):
                return
            if gateway.project_bridge is None:
                await interaction.response.send_message("Project upload bridge is not configured.", ephemeral=True)
                return
            await interaction.response.defer(thinking=True)
            try:
                job, requested_agent = await gateway._submit_vinted_upload_interaction(
                    interaction=interaction,
                    title=title,
                    description=description,
                    category=category,
                    brand=brand,
                    condition=condition,
                    material=material,
                    photo1=photo1,
                    price=price,
                    photo2=photo2,
                    photo3=photo3,
                    photo4=photo4,
                    metadata=metadata,
                    submit=submit,
                    enhance_photos=True,
                    agent=agent,
                )
            except ValueError as error:
                await interaction.followup.send(str(error), ephemeral=True)
                return
            gateway.pending_project_jobs[job.id] = (
                PendingDiscordProjectJob(
                    job_id=job.id,
                    project_id=job.project_id,
                    action=job.action,
                    agent_id=requested_agent,
                ),
                lambda content: interaction.followup.send(content, allowed_mentions=discord.AllowedMentions.none()),
            )
            await interaction.followup.send(
                gateway.project_bridge.format_job_queued(job),
                allowed_mentions=discord.AllowedMentions.none(),
            )

        @bot.tree.command(name="accordi_upload", description="Create a product on accordijewelry.com from Discord")
        @app_commands.describe(
            price="Product price, for example 10 or 10.50",
            photo1="Product photo",
            photo2="Optional second product photo for AI analysis",
            photo3="Optional third product photo for AI analysis",
            photo4="Optional fourth product photo for AI analysis",
            name="Optional product name override",
            description="Optional product description override",
            category="Optional category override",
            material="Optional material override",
            collection_id="Optional collection id",
            featured="Whether the product should be featured",
        )
        async def accordi_upload_command(
            interaction: Any,
            price: str,
            photo1: DiscordAttachmentType,
            photo2: Optional[DiscordAttachmentType] = None,
            photo3: Optional[DiscordAttachmentType] = None,
            photo4: Optional[DiscordAttachmentType] = None,
            name: str = "",
            description: str = "",
            category: str = "",
            material: str = "",
            collection_id: str = "",
            featured: bool = True,
        ) -> None:
            if not await gateway._allow_interaction(interaction):
                return
            if gateway.project_bridge is None:
                await interaction.response.send_message("Project upload bridge is not configured.", ephemeral=True)
                return
            gateway.logger.info(
                "discord_slash_accordi_upload channel_id=%s price=%s attachments=%s name=%s category=%s material=%s collection_id=%s featured=%s",
                str(interaction.channel_id),
                price,
                len([item for item in (photo1, photo2, photo3, photo4) if item is not None]),
                name,
                category,
                material,
                collection_id,
                featured,
            )
            await interaction.response.defer(thinking=True)
            attachments = [
                DiscordAttachment(
                    url=str(getattr(item, "url", "") or "").strip(),
                    filename=str(getattr(item, "filename", "") or "").strip(),
                    content_type=str(getattr(item, "content_type", "") or "").strip(),
                )
                for item in (photo1, photo2, photo3, photo4)
                if item is not None
            ]
            content = "\n".join(
                line
                for line in (
                    f"name: {name}" if name.strip() else "",
                    f"description: {description}" if description.strip() else "",
                    f"price: {price}" if price.strip() else "",
                    f"category: {category}" if category.strip() else "",
                    f"material: {material}" if material.strip() else "",
                    f"collection_id: {collection_id}" if collection_id.strip() else "",
                    f"featured: {'true' if featured else 'false'}",
                )
                if line
            )
            try:
                result = await gateway.project_bridge.submit_accordi_product_upload(
                    content=content,
                    attachments=attachments,
                )
            except ValueError as error:
                await interaction.followup.send(str(error), ephemeral=True)
                return
            await interaction.followup.send(
                gateway.project_bridge.format_accordi_result(result),
                allowed_mentions=discord.AllowedMentions.none(),
            )

        @bot.tree.command(name="accordi_update", description="Update an existing accordijewelry.com product from Discord")
        @app_commands.describe(
            product_id="Existing product id",
            price="Product price, for example 10 or 10.50",
            photo1="Product photo",
            photo2="Optional second product photo for AI analysis",
            photo3="Optional third product photo for AI analysis",
            photo4="Optional fourth product photo for AI analysis",
            name="Optional product name override",
            description="Optional product description override",
            category="Optional category override",
            material="Optional material override",
            collection_id="Optional collection id",
            featured="Whether the product should be featured",
        )
        async def accordi_update_command(
            interaction: Any,
            product_id: str,
            price: str,
            photo1: DiscordAttachmentType,
            photo2: Optional[DiscordAttachmentType] = None,
            photo3: Optional[DiscordAttachmentType] = None,
            photo4: Optional[DiscordAttachmentType] = None,
            name: str = "",
            description: str = "",
            category: str = "",
            material: str = "",
            collection_id: str = "",
            featured: bool = True,
        ) -> None:
            if not await gateway._allow_interaction(interaction):
                return
            if gateway.project_bridge is None:
                await interaction.response.send_message("Project upload bridge is not configured.", ephemeral=True)
                return
            gateway.logger.info(
                "discord_slash_accordi_update channel_id=%s product_id=%s price=%s attachments=%s name=%s category=%s material=%s collection_id=%s featured=%s",
                str(interaction.channel_id),
                product_id,
                price,
                len([item for item in (photo1, photo2, photo3, photo4) if item is not None]),
                name,
                category,
                material,
                collection_id,
                featured,
            )
            await interaction.response.defer(thinking=True)
            attachments = [
                DiscordAttachment(
                    url=str(getattr(item, "url", "") or "").strip(),
                    filename=str(getattr(item, "filename", "") or "").strip(),
                    content_type=str(getattr(item, "content_type", "") or "").strip(),
                )
                for item in (photo1, photo2, photo3, photo4)
                if item is not None
            ]
            content = "\n".join(
                line
                for line in (
                    f"name: {name}" if name.strip() else "",
                    f"description: {description}" if description.strip() else "",
                    f"price: {price}" if price.strip() else "",
                    f"category: {category}" if category.strip() else "",
                    f"material: {material}" if material.strip() else "",
                    f"collection_id: {collection_id}" if collection_id.strip() else "",
                    f"featured: {'true' if featured else 'false'}",
                    f"product_id: {product_id}",
                )
                if line
            )
            try:
                result = await gateway.project_bridge.submit_accordi_product_upload(
                    content=content,
                    attachments=attachments,
                    product_id=product_id,
                )
            except ValueError as error:
                await interaction.followup.send(str(error), ephemeral=True)
                return
            await interaction.followup.send(
                gateway.project_bridge.format_accordi_result(result),
                allowed_mentions=discord.AllowedMentions.none(),
            )

        ask_command.autocomplete("agent")(agent_autocomplete)
        use_command.autocomplete("agent")(agent_autocomplete)
        vinted_upload_command.autocomplete("agent")(agent_autocomplete)
        upload_ai_photo_command.autocomplete("agent")(agent_autocomplete)

        self._event_queue = self.runtime.subscribe()
        self._event_task = asyncio.create_task(self._event_loop(), name="discord-runtime-events")
        self._bot_task = asyncio.create_task(bot.start(self.config.token), name="discord-gateway")

    async def shutdown(self) -> None:
        if self._event_queue is not None:
            self.runtime.unsubscribe(self._event_queue)
            self._event_queue = None

        if self._bot is not None:
            with suppress(Exception):
                await self._bot.close()

        for task in (self._event_task, self._bot_task):
            if task is None:
                continue
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        self._event_task = None
        self._bot_task = None
        self.connected = False

    async def submit_chat(self, agent_id: str, prompt: str, send: SendMessage) -> Any:
        agent_id = agent_id.strip()
        prompt = prompt.strip()
        if agent_id not in self.runtime.agents:
            raise ValueError(self.unknown_agent_message(agent_id))
        if not prompt:
            raise ValueError("Prompt is empty.")
        if len(prompt) > 4000:
            prompt = prompt[:4000].rstrip()
        title = prompt[:160] if len(prompt) >= 3 else f"Chat: {prompt}"
        task = await self.runtime.create_task(
            TaskCreate(
                title=title,
                description=prompt,
                priority=3,
                requested_agent_id=agent_id,
                channel="chat",
            )
        )
        self.pending[task.id] = PendingDiscordTask(agent_id=agent_id, prompt=prompt, send=send)
        return task

    async def _event_loop(self) -> None:
        queue = self._event_queue
        if queue is None:
            return
        while True:
            event = await queue.get()
            await self._handle_runtime_event(event)

    async def _handle_runtime_event(self, event: RuntimeEvent) -> None:
        if event.type == "runpod.gpu.available":
            channel_id = self.last_allowed_channel_id or next(iter(self.config.allowed_channel_ids), 0)
            channel = self._bot.get_channel(channel_id) if self._bot is not None and channel_id else None
            if channel is not None:
                name = str(event.data.get("name") or event.entity_id or "RunPod GPU")
                region = str(event.data.get("region") or "configured region")
                memory = event.data.get("memory_gb")
                price = event.data.get("community_price")
                details = " · ".join(part for part in [f"{memory} GB" if memory else "", f"community ${price}/h" if price else ""] if part)
                await channel.send(f"🟢 **RunPod GPU available**\n{name} · {region}{f' · {details}' if details else ''}", allowed_mentions=self._discord.AllowedMentions.none())
            return
        task_id = event.task_id or ""
        if not task_id or task_id not in self.pending:
            job_id = event.entity_id or ""
            if job_id and job_id in self.pending_project_jobs:
                pending, send = self.pending_project_jobs[job_id]
                if event.type in {"project.job.completed", "project.job.failed"}:
                    self.pending_project_jobs.pop(job_id, None)
                await send(DiscordProjectBridge.format_job_event(event.type, event.data.get("job", {})))
            return

        if event.type == "protocol.message":
            message = event.data.get("message", {})
            if not isinstance(message, dict) or message.get("type") != "task.result":
                return
            pending = self.pending.pop(task_id, None)
            if pending is None:
                return
            await pending.send(self.format_task_result(task_id, pending.agent_id, message.get("payload", {})))
            return

        if event.type == "task.state.changed" and event.data.get("to") == "failed":
            pending = self.pending.pop(task_id, None)
            if pending is None:
                return
            task = event.data.get("task", {})
            error = "Task failed."
            if isinstance(task, dict) and task.get("error"):
                error = str(task["error"])
            await pending.send(f"**{pending.agent_id} failed** (`{task_id}`)\n{error}")

    async def _sync_commands(self) -> None:
        if self._bot is None or self._discord is None:
            return
        if self.config.allowed_guild_ids:
            for guild_id in self.config.allowed_guild_ids:
                guild = self._discord.Object(id=guild_id)
                self._bot.tree.copy_global_to(guild=guild)
                synced = await self._bot.tree.sync(guild=guild)
                self.logger.info("discord_commands_synced guild=%s commands=%s", guild_id, len(synced))
        else:
            synced = await self._bot.tree.sync()
            self.logger.info("discord_commands_synced scope=global commands=%s", len(synced))
        self._commands_synced = True

    async def _allow_interaction(self, interaction: Any) -> bool:
        guild_id = int(interaction.guild_id or 0)
        channel_id = int(interaction.channel_id or 0)
        if not self._is_allowed(guild_id, channel_id):
            await interaction.response.send_message(
                "This Discord guild/channel is not allowed to control Agent Lab.",
                ephemeral=True,
            )
            return False
        self._remember_allowed_channel(channel_id)
        return True

    async def _handle_text_message(self, message: Any) -> None:
        author = getattr(message, "author", None)
        if getattr(author, "bot", False):
            return
        guild_id = int(getattr(getattr(message, "guild", None), "id", 0) or 0)
        channel = getattr(message, "channel", None)
        channel_id = int(getattr(channel, "id", 0) or 0)
        if not self._is_allowed(guild_id, channel_id):
            return
        self._remember_allowed_channel(channel_id)

        content = str(getattr(message, "content", "") or "").strip()
        mentioned = self._bot is not None and self._bot.user in getattr(message, "mentions", [])
        attachments = list(getattr(message, "attachments", []) or [])
        self.logger.info(
            "discord_message_received channel_id=%s guild_id=%s mentioned=%s content=%s attachments=%s attachment_meta=%s",
            channel_id,
            guild_id,
            mentioned,
            content,
            len(attachments),
            [
                {
                    "filename": str(getattr(item, "filename", "") or "").strip(),
                    "content_type": str(getattr(item, "content_type", "") or "").strip(),
                    "url_present": bool(str(getattr(item, "url", "") or "").strip()),
                }
                for item in attachments
            ],
        )
        content = self._strip_bot_mention(content).strip() if mentioned else content
        default_agent = self.channel_defaults.get(str(channel_id), self.config.default_agent_id)
        parsed = parse_text_command(content, self.config.command_prefix, default_agent, mentioned)
        async def send(reply: str, *, files: list[Path] | None = None) -> None:
            if files:
                await channel.send(
                    content=reply,
                    files=[self._discord.File(str(path), filename=path.name) for path in files],
                    allowed_mentions=self._discord.AllowedMentions.none() if self._discord else None,
                )
            else:
                await self._send_channel_message(channel, reply)

        batch_prefix = f"{self.config.command_prefix}runpod-batch"
        image_upscale_prefix = f"{self.config.command_prefix}upscale-image"
        video_upscale_prefix = f"{self.config.command_prefix}upscale-video"
        if content.lower().startswith((batch_prefix, image_upscale_prefix, video_upscale_prefix)):
            if content.lower().startswith(image_upscale_prefix):
                preset_id = "seedvr2-image-upscale"
            elif content.lower().startswith(video_upscale_prefix):
                preset_id = "seedvr2-native-video"
            else:
                preset_id = content[len(batch_prefix):].strip().split(maxsplit=1)[0] if content[len(batch_prefix):].strip() else ""
            if not preset_id:
                await send("Usage: `!runpod-batch wan-14b-image-to-video`, `!upscale-image`, or `!upscale-video` + attach media.")
                return
            valid_attachments = []
            for item in attachments:
                filename = str(getattr(item, "filename", "") or "").strip()
                suffix = Path(filename).suffix.lower()
                if suffix in {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm", ".mov"}:
                    valid_attachments.append(item)
            if not valid_attachments:
                await send("Attach one or more PNG, JPEG, WebP, MP4, WebM, or MOV files with the batch command.")
                return
            try:
                workflow, workflow_name, metadata = self.load_runpod_workflow_preset(preset_id)
                required_kind = str(metadata.get("input_kind", "image") or "image").lower()
                loader_id = self.find_runpod_media_loader(workflow, required_kind)
                batch = self.runpod_batches.create_batch(
                    workflow, media_loader_id=loader_id, auto_deploy=True, auto_shutdown=True,
                    min_vram_gb=int(metadata.get("min_vram_gb", 0) or 0), workflow_id=str(metadata.get("id", preset_id)),
                )
                batch_id = str(batch["id"])
                for attachment in valid_attachments:
                    self.runpod_batches.add_item(
                        batch_id,
                        str(getattr(attachment, "filename", "upload") or "upload"),
                        await attachment.read(),
                    )
                self.runpod_batches.start_batch(batch_id)
            except (RunPodBatchError, RunPodManagerError) as error:
                await send(f"RunPod batch failed to start: {error}")
                return
            self.logger.info("discord_runpod_batch_started channel_id=%s batch_id=%s preset=%s items=%s", channel_id, batch_id, preset_id, len(valid_attachments))
            await send(
                f"RunPod batch `{batch_id}` started · `{workflow_name}` · {len(valid_attachments)} item(s). "
                "It will deploy a Pod only if none is active, process sequentially, then stop the Pod only if the batch created it."
            )
            asyncio.create_task(self._announce_runpod_batch_completion(batch_id, send), name=f"discord-runpod-batch-{batch_id}")
            return

        if (content or attachments) and parsed is None and self.project_bridge is not None:
            eleven_command = self.project_bridge.parse_eleven_script_text_command(
                content,
                prefix=self.config.command_prefix,
                mentioned=mentioned,
            )
            if eleven_command is not None:
                self.logger.info(
                    "discord_text_eleven_command action=%s attachments=%s channel_id=%s",
                    eleven_command.action,
                    len(attachments),
                    channel_id,
                )
                try:
                    result = await self.project_bridge.submit_eleven_script(
                        content=str((eleven_command.payload or {}).get("body", "") or ""),
                        attachments=[
                            DiscordAttachment(
                                url=str(getattr(item, "url", "") or "").strip(),
                                filename=str(getattr(item, "filename", "") or "").strip(),
                                content_type=str(getattr(item, "content_type", "") or "").strip(),
                            )
                            for item in attachments
                        ],
                    )
                except ValueError as error:
                    await send(str(error))
                    return
                await send(self.project_bridge.format_eleven_script_result(result))
                return
            accordi_command = self.project_bridge.parse_accordi_upload_text_command(
                content,
                prefix=self.config.command_prefix,
                mentioned=mentioned,
            )
            if accordi_command is not None:
                self.logger.info(
                    "discord_text_accordi_command action=%s product_id=%s attachments=%s channel_id=%s",
                    accordi_command.action,
                    str((accordi_command.payload or {}).get("product_id", "") or "").strip() or "-",
                    len(attachments),
                    channel_id,
                )
                try:
                    result = await self.project_bridge.submit_accordi_product_upload(
                        content=str((accordi_command.payload or {}).get("body", "") or ""),
                        attachments=[
                            DiscordAttachment(
                                url=str(getattr(item, "url", "") or "").strip(),
                                filename=str(getattr(item, "filename", "") or "").strip(),
                                content_type=str(getattr(item, "content_type", "") or "").strip(),
                            )
                            for item in attachments
                        ],
                        product_id=str((accordi_command.payload or {}).get("product_id", "") or "").strip(),
                    )
                except ValueError as error:
                    await send(str(error))
                    return
                await send(self.project_bridge.format_accordi_result(result))
                return
            project_command = self.project_bridge.parse_vinted_upload_text_command(
                content,
                prefix=self.config.command_prefix,
                default_agent_id=default_agent,
                mentioned=mentioned,
            )
            if project_command is not None:
                self.logger.info(
                    "discord_text_project_command action=%s agent_id=%s enhance_photos=%s attachments=%s channel_id=%s",
                    project_command.action,
                    project_command.agent_id or default_agent or "-",
                    bool((project_command.payload or {}).get("enhance_photos", False)),
                    len(attachments),
                    channel_id,
                )
                try:
                    job = await self.project_bridge.submit_vinted_upload(
                        content=str((project_command.payload or {}).get("body", "") or ""),
                        attachments=[
                            DiscordAttachment(
                                url=str(getattr(item, "url", "") or "").strip(),
                                filename=str(getattr(item, "filename", "") or "").strip(),
                                content_type=str(getattr(item, "content_type", "") or "").strip(),
                            )
                            for item in attachments
                        ],
                        agent_id=project_command.agent_id or default_agent,
                        enhance_photos=bool((project_command.payload or {}).get("enhance_photos", False)),
                    )
                except ValueError as error:
                    await send(str(error))
                    return
                self.pending_project_jobs[job.id] = (
                    PendingDiscordProjectJob(
                        job_id=job.id,
                        project_id=job.project_id,
                        action=job.action,
                        agent_id=project_command.agent_id or default_agent,
                    ),
                    send,
                )
                await send(self.project_bridge.format_job_queued(job))
                return

        if parsed is None:
            return

        if parsed.action == "agents":
            await send(self.format_agents())
            return
        if parsed.action == "report":
            try:
                report_path = await self.create_marketplace_report(parsed.prompt or "30")
            except (OSError, ValueError) as error:
                self.logger.exception("discord_report_generation_failed channel_id=%s days=%s", channel_id, parsed.prompt)
                await send(f"Report generation failed: {error}")
                return
            self.logger.info(
                "discord_report_generation_ok channel_id=%s days=%s path=%s size_bytes=%s",
                channel_id,
                self.normalize_report_days(parsed.prompt or "30"),
                report_path,
                report_path.stat().st_size,
            )
            await channel.send(
                content=f"Marketplace report ready · last {self.normalize_report_days(parsed.prompt or '30')} days.",
                file=self._discord.File(str(report_path), filename=report_path.name),
                allowed_mentions=self._discord.AllowedMentions.none(),
            )
            return
        if parsed.action == "sold_deals":
            try:
                normalized_range, articles = await self.load_sold_deals(parsed.agent_id or "1-6", parsed.prompt or "30")
            except ValueError as error:
                await send(str(error))
                return
            await self.send_sold_deals(
                lambda **kwargs: channel.send(**kwargs),
                articles,
                time_range=normalized_range,
                days=self.normalize_report_days(parsed.prompt or "30"),
            )
            return
        if parsed.action == "use":
            if parsed.agent_id not in self.runtime.agents:
                await send(self.unknown_agent_message(parsed.agent_id))
                return
            self.channel_defaults[str(channel_id)] = parsed.agent_id
            await send(f"Default agent for this channel: `{parsed.agent_id}`.")
            return
        if parsed.action == "ask":
            try:
                task = await self.submit_chat(parsed.agent_id, parsed.prompt, send)
            except ValueError as error:
                await send(str(error))
                return
            await send(f"Queued `{task.id}` for `{parsed.agent_id}`. I will post the answer here.")
            return
        if parsed.action == "codex":
            try:
                result = await self.send_codex_prompt(str(channel_id), parsed.prompt)
            except ValueError as error:
                await send(str(error))
                return
            except RuntimeError as error:
                await send(f"Codex bridge failed: {error}")
                return
            await self.send_codex_result(send, result)
            return
        if parsed.action == "codex_model":
            action = str(parsed.agent_id or "").strip().lower()
            model = str(parsed.prompt or "").strip()
            if action == "show":
                await send(self.format_codex_model_status(str(channel_id)))
                return
            if action == "set":
                self.codex_bridge.set_channel_model(str(channel_id), model)
                await send(self.format_codex_model_status(str(channel_id), override=model))
                return
            if action == "clear":
                self.codex_bridge.clear_channel_model(str(channel_id))
                await send(self.format_codex_model_status(str(channel_id)))
                return
            await send("Invalid action. Use `show`, `set`, or `clear`.")
            return
        if parsed.action == "chat":
            agent_id = self.channel_defaults.get(str(channel_id), self.config.default_agent_id).strip()
            if not agent_id:
                await send(
                    "No default agent is configured for this channel. Use `!use <agent_id>` first or send `!ask <agent_id> <message>`."
                )
                return
            try:
                task = await self.submit_chat(agent_id, parsed.prompt, send)
            except ValueError as error:
                await send(str(error))
                return
            await send(f"Queued `{task.id}` for `{agent_id}`. I will post the answer here.")

    async def _send_channel_message(self, channel: Any, content: str) -> None:
        if channel is None:
            return
        allowed_mentions = self._discord.AllowedMentions.none() if self._discord else None
        for chunk in chunk_discord_message(content):
            await channel.send(chunk, allowed_mentions=allowed_mentions)

    @staticmethod
    def normalize_report_days(value: object) -> int:
        try:
            return max(1, min(int(str(value or "30").strip()), 365))
        except (TypeError, ValueError):
            raise ValueError("Report days must be a number between 1 and 365.") from None

    async def create_marketplace_report(self, days: object = 30) -> Path:
        normalized_days = self.normalize_report_days(days)
        project_root = Path(__file__).resolve().parent.parent
        return await asyncio.to_thread(
            write_vinted_report_html,
            project_root,
            days=normalized_days,
            limit=500,
        )

    @staticmethod
    def normalize_sold_time_range(value: object) -> str:
        normalized = str(value or "1-6").strip().lower().replace(" ", "").replace("h", "")
        aliases = {
            "<1": "under-1",
            "0-1": "under-1",
            "under-1": "under-1",
            "1-6": "1-6",
            "6-12": "6-12",
            "12-24": "12-24",
            ">24": "over-24",
            "24+": "over-24",
            "over-24": "over-24",
            "all": "all",
            "tutti": "all",
        }
        if normalized not in aliases:
            raise ValueError("Invalid sale-time range. Use `under-1`, `1-6`, `6-12`, `12-24`, `over-24`, or `all`.")
        return aliases[normalized]

    @staticmethod
    def sold_deal_matches_range(article: dict[str, Any], time_range: str) -> bool:
        if str(article.get("status", "") or "").lower() != "sold":
            return False
        if time_range == "all":
            return True
        seconds = article.get("sold_after_seconds")
        if not isinstance(seconds, (int, float)):
            return False
        hours = max(float(seconds), 0.0) / 3600
        bounds = {
            "under-1": (0, 1),
            "1-6": (1, 6),
            "6-12": (6, 12),
            "12-24": (12, 24),
            "over-24": (24, float("inf")),
        }
        minimum, maximum = bounds[time_range]
        return minimum <= hours < maximum

    async def load_sold_deals(self, time_range: object = "1-6", days: object = 30) -> tuple[str, list[dict[str, Any]]]:
        normalized_range = self.normalize_sold_time_range(time_range)
        normalized_days = self.normalize_report_days(days)
        project_root = Path(__file__).resolve().parent.parent
        snapshot = await asyncio.to_thread(
            build_vinted_report,
            project_root,
            days=normalized_days,
            limit=500,
        )
        if not snapshot.get("available"):
            raise ValueError("The marketplace report database is not available yet.")
        articles = [
            article
            for article in snapshot.get("articles", [])
            if isinstance(article, dict) and self.sold_deal_matches_range(article, normalized_range)
        ]
        articles.sort(key=lambda article: str(article.get("sold_at", "") or ""), reverse=True)
        self.logger.info(
            "discord_sold_deals_loaded range=%s days=%s count=%s",
            normalized_range,
            normalized_days,
            len(articles),
        )
        return normalized_range, articles

    async def send_sold_deals(
        self,
        send: Callable[..., Awaitable[Any]],
        articles: list[dict[str, Any]],
        *,
        time_range: str,
        days: int,
    ) -> None:
        allowed_mentions = self._discord.AllowedMentions.none() if self._discord else None
        if not articles:
            await send(
                content=f"No sold deals found in the `{time_range}` hour range during the last {days} days.",
                allowed_mentions=allowed_mentions,
            )
            return
        for offset in range(0, len(articles), 10):
            batch = articles[offset : offset + 10]
            embeds = []
            for article in batch:
                embed = self._discord.Embed(
                    title=str(article.get("name", "") or "Marketplace item")[:256],
                    url=str(article.get("link", "") or "") or None,
                    description=(
                        f"**Price:** {article.get('price') or '—'}\n"
                        f"**Sold in:** {article.get('sold_after_text') or '—'}\n"
                        f"**Search:** {article.get('search_term') or '—'}\n"
                        f"**Sold at:** {article.get('sold_at') or '—'}"
                    )[:4096],
                    color=0x14B8A6,
                )
                image_url = str(article.get("image_url", "") or "").strip()
                if image_url:
                    embed.set_thumbnail(url=image_url)
                embeds.append(embed)
            prefix = (
                f"**Sold deals · {time_range} hours · last {days} days**\n"
                f"Found: **{len(articles)}**"
                if offset == 0
                else f"Sold deals continued · {offset + 1}–{min(offset + len(batch), len(articles))} of {len(articles)}"
            )
            await send(content=prefix, embeds=embeds, allowed_mentions=allowed_mentions)

    async def _submit_vinted_upload_interaction(
        self,
        *,
        interaction: Any,
        title: str,
        description: str,
        category: str,
        brand: str,
        condition: str,
        material: str,
        photo1: Any,
        price: str = "",
        photo2: Any = None,
        photo3: Any = None,
        photo4: Any = None,
        metadata: Any = None,
        submit: bool = False,
        enhance_photos: bool = False,
        agent: str = "",
    ) -> tuple[ProjectJob, str]:
        if self.project_bridge is None:
            raise ValueError("Project upload bridge is not configured.")
        attachments = [
            DiscordAttachment(
                url=str(getattr(item, "url", "") or "").strip(),
                filename=str(getattr(item, "filename", "") or "").strip(),
                content_type=str(getattr(item, "content_type", "") or "").strip(),
            )
            for item in (photo1, photo2, photo3, photo4, metadata)
            if item is not None
        ]
        requested_agent = agent.strip() or self.channel_defaults.get(str(interaction.channel_id), self.config.default_agent_id)
        job = await self.project_bridge.submit_vinted_upload_payload(
            payload={
                "title": title,
                "description": description,
                "price": price,
                "category": category,
                "brand": brand,
                "condition": condition,
                "material": material,
                "submit": submit,
                "enhance_photos": enhance_photos,
            },
            attachments=attachments,
            agent_id=requested_agent,
        )
        return job, requested_agent

    def _is_allowed(self, guild_id: int, channel_id: int) -> bool:
        if self.config.allowed_guild_ids and guild_id not in self.config.allowed_guild_ids:
            return False
        if self.config.allowed_channel_ids and channel_id not in self.config.allowed_channel_ids:
            return False
        return True

    @staticmethod
    def _strip_bot_mention(content: str) -> str:
        return re.sub(r"<@!?\d+>", "", content, count=1).strip()

    def format_agents(self) -> str:
        agents = self.runtime.list_agents()
        if not agents:
            return "No Agent Lab agents are configured."
        lines = ["**Agent Lab agents**"]
        for agent in agents:
            lines.append(
                f"- `{agent.id}` — {agent.name} / {agent.role} "
                f"({agent.model.provider}:{agent.model.model})"
            )
        lines.append("")
        lines.append("Use `/chat prompt:<message>` to talk with the default agent for this channel.")
        lines.append("Use `/ask agent:<id> prompt:<message>` to talk with one specific agent.")
        return "\n".join(lines)

    def format_codex_model_status(self, channel_key: str, override: str = "") -> str:
        effective_override = str(override or self.codex_bridge.get_channel_model(channel_key)).strip()
        default_model = str(self.codex_bridge.status().get("defaultModel", "") or "").strip()
        if effective_override:
            return (
                f"Codex model for this channel: `{effective_override}`\n"
                f"Default Codex model: `{default_model or 'not set'}`\n"
                "Use `set` to change it or `clear` to fall back to the default."
            )
        return (
            f"Codex model for this channel: `{default_model or 'not set'}`\n"
            "No per-channel override is configured."
        )

    def format_task_result(self, task_id: str, agent_id: str, payload: Any) -> str:
        summary = "Task completed."
        sources: list[dict[str, str]] = []
        if isinstance(payload, dict):
            summary = str(payload.get("summary") or summary).strip() or summary
            raw_sources = payload.get("sources") or []
            if isinstance(raw_sources, list):
                sources = [item for item in raw_sources if isinstance(item, dict)]
        agent = self.runtime.agents.get(agent_id)
        title = agent.name if agent else agent_id
        lines = [f"**{title}** (`{task_id}`)", summary]
        if sources:
            lines.append("")
            lines.append("Sources:")
            for index, source in enumerate(sources[:5], start=1):
                url = str(source.get("url", "") or "").strip()
                label = str(source.get("title", "") or url).strip()
                if url:
                    lines.append(f"{index}. {label} — {url}")
        return "\n".join(lines)

    def unknown_agent_message(self, agent_id: str) -> str:
        ids = ", ".join(f"`{agent.id}`" for agent in self.runtime.list_agents()) or "none"
        return f"Unknown agent `{agent_id}`. Available agents: {ids}."

    async def send_codex_prompt(self, channel_key: str, prompt: str) -> Any:
        if self.codex_bridge is None:
            raise RuntimeError("Codex bridge is not available.")
        return await self.codex_bridge.ask(channel_key, prompt)

    async def send_codex_result(self, send: SendMessage, result: Any) -> None:
        final_response = str(getattr(result, "final_response", "") or "").strip()
        if final_response:
            for chunk in chunk_discord_message(final_response):
                await send(chunk)
            return
        messages = list(getattr(result, "messages", []) or [])
        if messages:
            fallback = str(messages[-1] or "").strip()
            if fallback:
                for chunk in chunk_discord_message(self._format_codex_message(fallback)):
                    await send(chunk)
                return
        await send("(empty)")

    @staticmethod
    def _format_codex_message(message: str) -> str:
        text = str(message or "").strip()
        if not text:
            return "(empty)"
        if text.startswith("```"):
            return text
        if text.startswith("🧠 "):
            quoted_lines = "\n".join(f"> {line}" if line else ">" for line in text.splitlines())
            return quoted_lines
        return text


def parse_text_command(
    content: str,
    prefix: str = "!",
    default_agent_id: str = "",
    mentioned: bool = False,
) -> Optional[ParsedDiscordCommand]:
    text = content.strip()
    prefix = prefix or "!"
    if not text:
        return None

    if text == f"{prefix}agents" or (mentioned and text == "agents"):
        return ParsedDiscordCommand(action="agents")

    report_prefixes = (f"{prefix}report", f"{prefix}market-report")
    for report_prefix in report_prefixes:
        if text == report_prefix or text.startswith(f"{report_prefix} "):
            days = text[len(report_prefix) :].strip() or "30"
            return ParsedDiscordCommand(action="report", prompt=days)
    if mentioned and (text == "report" or text.startswith("report ")):
        return ParsedDiscordCommand(action="report", prompt=text[6:].strip() or "30")

    sold_prefixes = (f"{prefix}sold", f"{prefix}sold-deals", f"{prefix}sold-report")
    for sold_prefix in sold_prefixes:
        if text == sold_prefix or text.startswith(f"{sold_prefix} "):
            parts = text[len(sold_prefix) :].strip().split()
            return ParsedDiscordCommand(
                action="sold_deals",
                agent_id=parts[0] if parts else "1-6",
                prompt=parts[1] if len(parts) > 1 else "30",
            )
    if mentioned and (text == "sold" or text.startswith("sold ")):
        parts = text[4:].strip().split()
        return ParsedDiscordCommand(
            action="sold_deals",
            agent_id=parts[0] if parts else "1-6",
            prompt=parts[1] if len(parts) > 1 else "30",
        )

    if text == f"{prefix}codex" or text.startswith(f"{prefix}codex "):
        body = text[len(f"{prefix}codex") :].strip()
        if body:
            return ParsedDiscordCommand(action="codex", prompt=body)
        return None
    if mentioned and (text == "codex" or text.startswith("codex ")):
        body = text[5:].strip()
        if body:
            return ParsedDiscordCommand(action="codex", prompt=body)
        return None

    codex_model_prefix = f"{prefix}codex-model "
    if text.startswith(codex_model_prefix):
        body = text[len(codex_model_prefix) :].strip().split(maxsplit=1)
        if not body:
            return None
        action = body[0]
        model = body[1] if len(body) > 1 else ""
        return ParsedDiscordCommand(action="codex_model", agent_id=action, prompt=model)
    if text == f"{prefix}codex-model":
        return None
    if mentioned and text.startswith("codex-model "):
        body = text[len("codex-model ") :].strip().split(maxsplit=1)
        if not body:
            return None
        action = body[0]
        model = body[1] if len(body) > 1 else ""
        return ParsedDiscordCommand(action="codex_model", agent_id=action, prompt=model)

    if text == f"{prefix}chat" or text.startswith(f"{prefix}chat "):
        body = text[len(f"{prefix}chat") :].strip()
        if body:
            return ParsedDiscordCommand(action="chat", prompt=body)
        return None
    if mentioned and (text == "chat" or text.startswith("chat ")):
        body = text[4:].strip()
        if body:
            return ParsedDiscordCommand(action="chat", prompt=body)
        return None

    use_prefix = f"{prefix}use "
    if text.startswith(use_prefix):
        body = text[len(use_prefix) :].strip().split()
        return ParsedDiscordCommand(action="use", agent_id=body[0]) if body else None
    if mentioned and text.startswith("use "):
        body = text[4:].strip().split()
        return ParsedDiscordCommand(action="use", agent_id=body[0]) if body else None

    for marker in (f"{prefix}ask ", f"{prefix}agent "):
        if text.startswith(marker):
            body = text[len(marker) :].strip()
            parts = body.split(maxsplit=1)
            if len(parts) == 1 and default_agent_id:
                return ParsedDiscordCommand(action="ask", agent_id=default_agent_id, prompt=parts[0])
            if len(parts) >= 2:
                return ParsedDiscordCommand(action="ask", agent_id=parts[0], prompt=parts[1])
            return None

    if mentioned:
        if default_agent_id:
            return ParsedDiscordCommand(action="ask", agent_id=default_agent_id, prompt=text)
        parts = text.split(maxsplit=1)
        if len(parts) >= 2:
            return ParsedDiscordCommand(action="ask", agent_id=parts[0], prompt=parts[1])
        return None

    if default_agent_id and text.startswith(f"{prefix}ask "):
        return ParsedDiscordCommand(action="ask", agent_id=default_agent_id, prompt=text[5:].strip())

    return None


def chunk_discord_message(content: str, limit: int = 1900) -> list[str]:
    text = str(content or "").strip() or "(empty)"
    chunks: list[str] = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(text[:split_at].rstrip())
        text = text[split_at:].lstrip()
    chunks.append(text)
    return chunks


def parse_id_set(value: str) -> set[int]:
    ids: set[int] = set()
    for raw in str(value or "").replace(";", ",").split(","):
        item = raw.strip()
        if not item:
            continue
        try:
            ids.add(int(item))
        except ValueError:
            LOGGER.warning("discord_invalid_id value=%s", item)
    return ids


def parse_bool(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}
