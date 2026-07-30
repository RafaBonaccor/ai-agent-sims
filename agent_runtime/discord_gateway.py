from __future__ import annotations

import asyncio
import logging
import os
import re
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


LOGGER = logging.getLogger("agent_lab.discord")
SendMessage = Callable[[str], Awaitable[None]]
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
        self.pending: dict[str, PendingDiscordTask] = {}
        self.pending_project_jobs: dict[str, tuple[PendingDiscordProjectJob, SendMessage]] = {}
        self.channel_defaults: dict[str, str] = {}
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
        }

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

            attachments = [
                DiscordAttachment(
                    url=str(getattr(item, "url", "") or "").strip(),
                    filename=str(getattr(item, "filename", "") or "").strip(),
                    content_type=str(getattr(item, "content_type", "") or "").strip(),
                )
                for item in (photo1, photo2, photo3, photo4, metadata)
                if item is not None
            ]
            requested_agent = agent.strip() or gateway.channel_defaults.get(str(interaction.channel_id), gateway.config.default_agent_id)
            try:
                job = await gateway.project_bridge.submit_vinted_upload_payload(
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

        ask_command.autocomplete("agent")(agent_autocomplete)
        use_command.autocomplete("agent")(agent_autocomplete)
        vinted_upload_command.autocomplete("agent")(agent_autocomplete)

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

        content = str(getattr(message, "content", "") or "").strip()
        mentioned = self._bot is not None and self._bot.user in getattr(message, "mentions", [])
        content = self._strip_bot_mention(content).strip() if mentioned else content
        default_agent = self.channel_defaults.get(str(channel_id), self.config.default_agent_id)
        parsed = parse_text_command(content, self.config.command_prefix, default_agent, mentioned)
        async def send(reply: str) -> None:
            await self._send_channel_message(channel, reply)

        if (content or getattr(message, "attachments", None)) and parsed is None and self.project_bridge is not None:
            project_command = self.project_bridge.parse_vinted_upload_text_command(
                content,
                prefix=self.config.command_prefix,
                default_agent_id=default_agent,
                mentioned=mentioned,
            )
            if project_command is not None:
                try:
                    job = await self.project_bridge.submit_vinted_upload(
                        content=str((project_command.payload or {}).get("body", "") or ""),
                        attachments=[
                            DiscordAttachment(
                                url=str(getattr(item, "url", "") or "").strip(),
                                filename=str(getattr(item, "filename", "") or "").strip(),
                                content_type=str(getattr(item, "content_type", "") or "").strip(),
                            )
                            for item in list(getattr(message, "attachments", []) or [])
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
