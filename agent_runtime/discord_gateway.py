from __future__ import annotations

import asyncio
import logging
import os
import re
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from .engine import AgentRuntime
from .models import RuntimeEvent, TaskCreate


LOGGER = logging.getLogger("agent_lab.discord")
SendMessage = Callable[[str], Awaitable[None]]


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
        config: Optional[DiscordGatewayConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.runtime = runtime
        self.config = config or DiscordGatewayConfig.from_env()
        self.logger = logger or LOGGER
        self.pending: dict[str, PendingDiscordTask] = {}
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

        ask_command.autocomplete("agent")(agent_autocomplete)
        use_command.autocomplete("agent")(agent_autocomplete)

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
        assert self._event_queue is not None
        while True:
            event = await self._event_queue.get()
            await self._handle_runtime_event(event)

    async def _handle_runtime_event(self, event: RuntimeEvent) -> None:
        task_id = event.task_id or ""
        if not task_id or task_id not in self.pending:
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
        if not content:
            return
        mentioned = self._bot is not None and self._bot.user in getattr(message, "mentions", [])
        content = self._strip_bot_mention(content).strip() if mentioned else content
        default_agent = self.channel_defaults.get(str(channel_id), self.config.default_agent_id)
        parsed = parse_text_command(content, self.config.command_prefix, default_agent, mentioned)
        if parsed is None:
            return

        async def send(reply: str) -> None:
            await self._send_channel_message(channel, reply)

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
        lines.append("Use `/ask agent:<id> prompt:<message>` to talk with one agent.")
        return "\n".join(lines)

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
