from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.parse import quote
from urllib.request import Request, urlopen

from .browser_control import BrowserControl, BrowserControlError
from .models import AgentChatMessage, AgentSnapshot, MemoryRecord, RuntimeEvent, TaskRecord
from .storage import RuntimeStore
from .secrets import SecretStore


EventSink = Callable[[RuntimeEvent], Awaitable[None]]
LOGGER = logging.getLogger("agent_lab.models")


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    toolset: str
    risk: str
    parameters: dict[str, Any]

    def as_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    DEFINITIONS = {
        "runtime_time": ToolDefinition(
            name="runtime_time",
            description="Return the current UTC runtime time.",
            toolset="runtime",
            risk="read",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        "task_context": ToolDefinition(
            name="task_context",
            description="Return the structured task currently assigned to the agent.",
            toolset="tasks",
            risk="read",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        "memory_read": ToolDefinition(
            name="memory_read",
            description="Read this agent's private persistent memory.",
            toolset="memory",
            risk="read",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        "memory_append": ToolDefinition(
            name="memory_append",
            description="Append a concise durable fact to this agent's private memory.",
            toolset="memory",
            risk="memory-write",
            parameters={
                "type": "object",
                "properties": {"content": {"type": "string", "maxLength": 1000}},
                "required": ["content"],
                "additionalProperties": False,
            },
        ),
        "wiki_read": ToolDefinition(
            name="wiki_read",
            description="Read this agent's persistent conversation wiki.",
            toolset="wiki",
            risk="read",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        "wiki_append": ToolDefinition(
            name="wiki_append",
            description="Append a concise durable fact to this agent's persistent wiki.",
            toolset="wiki",
            risk="memory-write",
            parameters={
                "type": "object",
                "properties": {"content": {"type": "string", "maxLength": 1000}},
                "required": ["content"],
                "additionalProperties": False,
            },
        ),
        "browser_open": ToolDefinition(
            name="browser_open",
            description=(
                "Open a live browser session through the hybrid browser bridge. "
                "Use backend='botasaurus' for The Main Scraper or backend='mock' only in tests."
            ),
            toolset="browser",
            risk="browser-read",
            parameters={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "default": "main-scraper"},
                    "backend": {"type": "string", "enum": ["botasaurus", "mock"], "default": "botasaurus"},
                    "url": {"type": "string", "maxLength": 2000},
                    "browser_mode": {
                        "type": "string",
                        "enum": ["sessione_persistente", "chrome_normale", "profilo_personalizzato", "isolated"],
                        "default": "sessione_persistente",
                    },
                    "browser_user_data_dir": {"type": "string", "maxLength": 1000},
                    "browser_profile_directory": {"type": "string", "default": "Default", "maxLength": 120},
                    "refresh_browser_profile": {"type": "boolean", "default": False},
                    "page_text": {"type": "string", "maxLength": 4000},
                    "title": {"type": "string", "maxLength": 200},
                },
                "additionalProperties": False,
            },
        ),
        "browser_current_url": ToolDefinition(
            name="browser_current_url",
            description="Return the current URL of a live browser session.",
            toolset="browser",
            risk="browser-read",
            parameters={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
                "additionalProperties": False,
            },
        ),
        "browser_goto": ToolDefinition(
            name="browser_goto",
            description="Navigate a live browser session to a URL.",
            toolset="browser",
            risk="browser-read",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "url": {"type": "string", "maxLength": 2000},
                    "timeout": {"type": "number", "default": 60},
                },
                "required": ["session_id", "url"],
                "additionalProperties": False,
            },
        ),
        "browser_click_text": ToolDefinition(
            name="browser_click_text",
            description="Click the first visible button/control containing text in a live browser session.",
            toolset="browser",
            risk="browser-write",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "text": {"type": "string", "maxLength": 300},
                    "contains": {"type": "boolean", "default": True},
                },
                "required": ["session_id", "text"],
                "additionalProperties": False,
            },
        ),
        "browser_click_selector": ToolDefinition(
            name="browser_click_selector",
            description="Click a CSS selector in a live browser session.",
            toolset="browser",
            risk="browser-write",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "selector": {"type": "string", "maxLength": 500},
                },
                "required": ["session_id", "selector"],
                "additionalProperties": False,
            },
        ),
        "browser_type": ToolDefinition(
            name="browser_type",
            description="Type text into a CSS selector in a live browser session.",
            toolset="browser",
            risk="browser-write",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "selector": {"type": "string", "maxLength": 500},
                    "value": {"type": "string", "maxLength": 4000},
                    "clear": {"type": "boolean", "default": True},
                },
                "required": ["session_id", "selector", "value"],
                "additionalProperties": False,
            },
        ),
        "browser_extract": ToolDefinition(
            name="browser_extract",
            description="Extract text, HTML, or an attribute from a CSS selector in a live browser session.",
            toolset="browser",
            risk="browser-read",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "selector": {"type": "string", "default": "body", "maxLength": 500},
                    "mode": {"type": "string", "default": "text", "maxLength": 80},
                    "all": {"type": "boolean", "default": False},
                },
                "required": ["session_id"],
                "additionalProperties": False,
            },
        ),
        "browser_snapshot": ToolDefinition(
            name="browser_snapshot",
            description="Return a compact page snapshot from a live browser session.",
            toolset="browser",
            risk="browser-read",
            parameters={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
                "additionalProperties": False,
            },
        ),
        "browser_close": ToolDefinition(
            name="browser_close",
            description="Close a live browser session.",
            toolset="browser",
            risk="browser-write",
            parameters={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
                "additionalProperties": False,
            },
        ),
    }

    def __init__(self, store: RuntimeStore, browser_control: Optional[BrowserControl] = None):
        self.store = store
        self.browser_control = browser_control

    def available(self, agent: AgentSnapshot) -> list[ToolDefinition]:
        enabled = set(agent.toolsets) | {"runtime"}
        return [definition for definition in self.DEFINITIONS.values() if definition.toolset in enabled]

    async def execute(
        self, name: str, arguments: dict[str, Any], agent: AgentSnapshot, task: TaskRecord
    ) -> dict[str, Any]:
        definition = self.DEFINITIONS.get(name)
        if definition is None or definition not in self.available(agent):
            raise ValueError(f"Tool is not enabled for {agent.id}: {name}")
        if definition.risk in agent.approvals.required_for:
            raise PermissionError(f"Tool requires approval: {name}")
        if name == "runtime_time":
            return {"utc": datetime.now(timezone.utc).isoformat()}
        if name == "task_context":
            return task.model_dump(mode="json")
        if name == "memory_read":
            return self.store.get_memory(agent.id).model_dump(mode="json")
        if name == "memory_append":
            addition = str(arguments.get("content", "")).strip()
            if not addition:
                raise ValueError("memory_append requires non-empty content")
            memory = self.store.get_memory(agent.id)
            memory.content = (memory.content.rstrip() + "\n" + addition).strip()[-8_000:]
            self.store.save_memory(memory)
            return {"saved": True, "characters": len(memory.content)}
        if name == "wiki_read":
            return self.store.get_wiki(agent.id).model_dump(mode="json")
        if name == "wiki_append":
            addition = str(arguments.get("content", "")).strip()
            if not addition:
                raise ValueError("wiki_append requires non-empty content")
            wiki = self.store.get_wiki(agent.id)
            wiki.content = (wiki.content.rstrip() + "\n" + addition).strip()[-8_000:]
            self.store.save_wiki(wiki)
            return {"saved": True, "characters": len(wiki.content)}
        if name.startswith("browser_"):
            return await self._execute_browser_tool(name, arguments)
        raise ValueError(f"Tool has no executor: {name}")

    async def _execute_browser_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.browser_control is None:
            raise BrowserControlError("Browser control is not configured")
        if name == "browser_open":
            return await self.browser_control.open_session(
                project_id=str(arguments.get("project_id", "") or ""),
                backend=str(arguments.get("backend", "") or ""),
                url=str(arguments.get("url", "") or ""),
                browser_mode=str(arguments.get("browser_mode", "sessione_persistente") or "sessione_persistente"),
                browser_user_data_dir=str(arguments.get("browser_user_data_dir", "") or ""),
                browser_profile_directory=str(arguments.get("browser_profile_directory", "Default") or "Default"),
                refresh_browser_profile=bool(arguments.get("refresh_browser_profile", False)),
                page_text=str(arguments.get("page_text", "") or ""),
                title=str(arguments.get("title", "") or ""),
            )

        session_id = str(arguments.get("session_id", "") or "").strip()
        if not session_id:
            raise ValueError(f"{name} requires session_id")
        command_map = {
            "browser_current_url": "current_url",
            "browser_goto": "goto",
            "browser_click_text": "click_text",
            "browser_click_selector": "click_selector",
            "browser_type": "type",
            "browser_extract": "extract",
            "browser_snapshot": "snapshot",
        }
        if name == "browser_close":
            return await self.browser_control.close_session(session_id)
        command = command_map.get(name)
        if not command:
            raise ValueError(f"Unsupported browser tool: {name}")
        payload = {key: value for key, value in arguments.items() if key != "session_id"}
        return await self.browser_control.command(session_id, command, payload)


class ModelExecutor:
    def __init__(
        self,
        store: RuntimeStore,
        secrets: Optional[SecretStore] = None,
        browser_control: Optional[BrowserControl] = None,
    ):
        self.store = store
        self.secrets = secrets
        self.tools = ToolRegistry(store, browser_control)

    async def run(self, agent: AgentSnapshot, task: TaskRecord, emit: EventSink) -> dict[str, Any]:
        LOGGER.info(
            "model_started task=%s agent=%s provider=%s model=%s",
            task.id,
            agent.id,
            agent.model.provider,
            agent.model.model,
        )
        await emit(
            RuntimeEvent(
                type="model.started",
                entity_id=task.id,
                agent_id=agent.id,
                task_id=task.id,
                summary=f"{agent.name} started {agent.model.provider}/{agent.model.model}.",
                data={"provider": agent.model.provider, "model": agent.model.model},
            )
        )
        if agent.model.provider == "simulated":
            result = self._run_simulated(agent, task)
        elif agent.model.provider == "openai-compatible":
            result = await self._run_openai_compatible(agent, task, emit)
        elif agent.model.provider in {"openai", "anthropic", "gemini", "ollama"}:
            result = await asyncio.to_thread(self._run_native_provider, agent, task)
        else:
            raise ValueError(f"Unsupported provider: {agent.model.provider}")
        if task.channel == "chat":
            self._update_chat_wiki(agent, task, result)
        await emit(
            RuntimeEvent(
                type="model.completed",
                entity_id=task.id,
                agent_id=agent.id,
                task_id=task.id,
                summary=f"{agent.name} produced a result with {agent.model.model}.",
                data={"provider": result["provider"], "model": result["model"]},
            )
        )
        LOGGER.info(
            "model_completed task=%s agent=%s provider=%s model=%s",
            task.id,
            agent.id,
            result["provider"],
            result["model"],
        )
        return result

    def _run_simulated(self, agent: AgentSnapshot, task: TaskRecord) -> dict[str, Any]:
        if task.channel == "chat":
            user_text = self._task_message_text(task)
            summary = (
                f"{agent.name} è in modalità simulata locale, quindi non sta chiamando Codex "
                f"né un'API LLM esterna. Ho ricevuto: “{self._truncate(user_text, 500)}”. "
                "Per avere una risposta generativa reale configura il provider dell'agente "
                "su OpenAI, OpenAI-compatible, Anthropic, Gemini oppure Ollama e salva la relativa API key."
            )
            return {
                "summary": summary,
                "details": "Chat fallback from the native deterministic provider.",
                "provider": "simulated",
                "model": agent.model.model,
                "tool_calls": 0,
                "simulated": True,
            }
        return {
            "summary": f"{agent.name} completed {task.title}",
            "details": "Executed by the native deterministic provider.",
            "provider": "simulated",
            "model": agent.model.model,
            "tool_calls": 0,
            "simulated": True,
        }

    def _update_chat_wiki(self, agent: AgentSnapshot, task: TaskRecord, result: dict[str, Any]) -> None:
        user_text = self._task_message_text(task)
        assistant_text = str(result.get("summary", "") or "").strip()
        if not user_text and not assistant_text:
            return
        lines = [
            f"- {task.created_at.isoformat(timespec='seconds')} | user: {self._truncate(user_text, 260)}",
            f"  assistant: {self._truncate(assistant_text, 420)}",
        ]
        sources = result.get("sources") or []
        if sources:
            source_urls = ", ".join(
                str(item.get("url", "") or "").strip()
                for item in sources
                if isinstance(item, dict) and str(item.get("url", "") or "").strip()
            )
            if source_urls:
                lines.append(f"  sources: {self._truncate(source_urls, 420)}")
        wiki = self.store.get_wiki(agent.id)
        wiki.content = (wiki.content.rstrip() + "\n" + "\n".join(lines)).strip()[-8_000:]
        self.store.save_wiki(wiki)

    async def _run_openai_compatible(
        self, agent: AgentSnapshot, task: TaskRecord, emit: EventSink
    ) -> dict[str, Any]:
        endpoint = self._chat_endpoint(agent.model.base_url)
        api_key = self._resolve_api_key(agent)
        system_prompt = self._build_system_prompt(agent, include_chat_history=False)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if task.channel == "chat":
            messages.extend(self._build_chat_messages(agent.id, task.id))
        messages.append({"role": "user", "content": self._build_user_prompt(task)})
        available_tools = self.tools.available(agent)
        tool_call_count = 0

        for _iteration in range(min(agent.limits.max_iterations, 8)):
            payload: dict[str, Any] = {
                "model": agent.model.model,
                "messages": messages,
                "temperature": agent.model.temperature,
            }
            if available_tools:
                payload["tools"] = [tool.as_openai_tool() for tool in available_tools]
                payload["tool_choice"] = "auto"
            response = await asyncio.to_thread(self._post_json, endpoint, payload, api_key)
            message = response["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return {
                    "summary": message.get("content") or "Model returned an empty result.",
                    "provider": "openai-compatible",
                    "model": agent.model.model,
                    "tool_calls": tool_call_count,
                }

            messages.append(message)
            for call in tool_calls:
                name = call["function"]["name"]
                arguments = json.loads(call["function"].get("arguments") or "{}")
                tool_call_count += 1
                await emit(
                    RuntimeEvent(
                        type="tool.started",
                        entity_id=call["id"],
                        agent_id=agent.id,
                        task_id=task.id,
                        summary=f"{agent.name} called {name}.",
                        data={"tool": name},
                    )
                )
                try:
                    output = await self.tools.execute(name, arguments, agent, task)
                    status = "completed"
                except Exception as error:
                    output = {"error": str(error)}
                    status = "failed"
                await emit(
                    RuntimeEvent(
                        type=f"tool.{status}",
                        entity_id=call["id"],
                        agent_id=agent.id,
                        task_id=task.id,
                        summary=f"{name} {status} for {agent.name}.",
                        data={"tool": name, "output": output},
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(output),
                    }
                )
        raise RuntimeError("Model exceeded its tool iteration budget")

    def _resolve_api_key(self, agent: AgentSnapshot) -> Optional[str]:
        if agent.model.provider == "ollama":
            return None
        api_key = None
        if self.secrets:
            if agent.model.api_key_scope == "agent":
                api_key = self.secrets.get_agent(agent.id)
            else:
                api_key = self.secrets.get_project()
        if not api_key and agent.model.api_key_env:
            api_key = os.environ.get(agent.model.api_key_env)
        if not api_key:
            target = "agent" if agent.model.api_key_scope == "agent" else "project"
            raise RuntimeError(f"No API key configured for {target} scope")
        return api_key

    def _run_native_provider(self, agent: AgentSnapshot, task: TaskRecord) -> dict[str, Any]:
        provider = agent.model.provider
        api_key = self._resolve_api_key(agent)
        system = self._build_system_prompt(
            agent,
            include_chat_history=task.channel == "chat",
            current_task_id=task.id,
        )
        user = self._build_user_prompt(task)

        if provider == "openai":
            endpoint = self._provider_endpoint(agent.model.base_url, "https://api.openai.com/v1/responses", "/responses")
            payload = {"model": agent.model.model, "instructions": system, "input": user}
            web_enabled = "web" in agent.toolsets
            if web_enabled:
                payload.update(
                    tools=[{"type": "web_search", "search_context_size": "medium"}],
                    tool_choice="auto",
                    include=["web_search_call.action.sources"],
                )
            response = self._post_json(endpoint, payload, api_key)
            summary = self._openai_response_text(response)
            sources = self._openai_response_sources(response)
        elif provider == "anthropic":
            endpoint = self._provider_endpoint(agent.model.base_url, "https://api.anthropic.com/v1/messages", "/v1/messages")
            payload = {
                "model": agent.model.model,
                "max_tokens": 2048,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }
            response = self._post_json(
                endpoint,
                payload,
                None,
                {"x-api-key": api_key or "", "anthropic-version": "2023-06-01"},
            )
            summary = "\n".join(
                item.get("text", "") for item in response.get("content", []) if item.get("type") == "text"
            )
        elif provider == "gemini":
            base = agent.model.base_url.strip().rstrip("/") or "https://generativelanguage.googleapis.com/v1beta"
            endpoint = f"{base}/models/{quote(agent.model.model, safe='')}:generateContent"
            payload = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
            }
            response = self._post_json(endpoint, payload, None, {"x-goog-api-key": api_key or ""})
            candidates = response.get("candidates", [])
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            summary = "\n".join(part.get("text", "") for part in parts)
        else:
            endpoint = self._provider_endpoint(agent.model.base_url, "http://127.0.0.1:11434/api/chat", "/api/chat")
            payload = {
                "model": agent.model.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            response = self._post_json(endpoint, payload, None)
            summary = response.get("message", {}).get("content", "")

        if not summary.strip():
            raise RuntimeError(f"{provider} returned an empty response")
        return {
            "summary": summary.strip(),
            "provider": provider,
            "model": agent.model.model,
            "tool_calls": sum(1 for item in response.get("output", []) if item.get("type", "").endswith("_call")),
            "sources": sources if provider == "openai" else [],
        }

    def _build_system_prompt(
        self,
        agent: AgentSnapshot,
        include_chat_history: bool = False,
        current_task_id: str = "",
    ) -> str:
        parts = [
            f"You are {agent.name}, role: {agent.role}.",
            agent.instructions or "Complete assigned tasks carefully and return verifiable results.",
        ]
        memory = self.store.get_memory(agent.id).content.strip()
        if memory:
            parts.append(f"Private durable memory:\n{memory}")
        wiki = self.store.get_wiki(agent.id).content.strip()
        if wiki:
            parts.append(f"Persistent conversation wiki:\n{wiki}")
        if include_chat_history:
            chat_history = self._build_chat_context_text(agent.id, current_task_id)
            if chat_history:
                parts.append(f"Recent chat history:\n{chat_history}")
            parts.append(
                "This is a persistent chat session. Use prior chat history and the wiki to answer with continuity."
            )
            LOGGER.info(
                "memory_context agent=%s task=%s wiki_chars=%s chat_chars=%s",
                agent.id,
                current_task_id or "-",
                len(wiki),
                len(chat_history),
            )
        return "\n\n".join(parts).strip()

    @staticmethod
    def _build_user_prompt(task: TaskRecord) -> str:
        description = task.description.strip() or task.title.strip()
        if task.channel == "chat":
            return description
        return f"Task: {task.title}\n\n{description}\n\nReturn a concise result."

    def _build_chat_messages(self, agent_id: str, current_task_id: str) -> list[dict[str, Any]]:
        history = self.store.load_agent_chat_messages(agent_id, limit_turns=8, exclude_task_id=current_task_id)
        LOGGER.info(
            "memory_context agent=%s task=%s wiki_chars=%s chat_messages=%s",
            agent_id,
            current_task_id or "-",
            len(self.store.get_wiki(agent_id).content.strip()),
            len(history),
        )
        messages: list[dict[str, Any]] = []
        for message in history:
            messages.append(
                {
                    "role": message.role,
                    "content": self._truncate(message.content, 1500),
                }
            )
        return messages

    def _build_chat_context_text(self, agent_id: str, current_task_id: str) -> str:
        history = self.store.load_agent_chat_messages(agent_id, limit_turns=8, exclude_task_id=current_task_id)
        if not history:
            return ""
        lines = []
        for message in history:
            label = {"user": "User", "assistant": "Assistant", "system": "System"}.get(message.role, message.role)
            lines.append(f"{label}: {self._truncate(message.content, 500)}")
        return "\n".join(lines)

    @staticmethod
    def _task_message_text(task: TaskRecord) -> str:
        return (task.description or task.title or "").strip()

    @staticmethod
    def _truncate(value: str, max_length: int) -> str:
        text = str(value or "")
        if len(text) <= max_length:
            return text
        return text[: max_length - 1].rstrip() + "…"

    @staticmethod
    def _provider_endpoint(base_url: str, default: str, suffix: str) -> str:
        value = base_url.strip().rstrip("/")
        if not value:
            return default
        if value.endswith(suffix):
            return value
        return f"{value}{suffix}"

    @staticmethod
    def _openai_response_text(response: dict[str, Any]) -> str:
        chunks = []
        for item in response.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    chunks.append(content.get("text", ""))
        return "\n".join(chunks)

    @staticmethod
    def _openai_response_sources(response: dict[str, Any]) -> list[dict[str, str]]:
        sources: dict[str, dict[str, str]] = {}
        for item in response.get("output", []):
            if item.get("type") == "web_search_call":
                for source in item.get("action", {}).get("sources", []) or []:
                    url = str(source.get("url", "")).strip()
                    if url:
                        sources[url] = {"url": url, "title": str(source.get("title") or url)}
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                for annotation in content.get("annotations", []) or []:
                    if annotation.get("type") != "url_citation":
                        continue
                    url = str(annotation.get("url", "")).strip()
                    if url:
                        sources[url] = {"url": url, "title": str(annotation.get("title") or url)}
        return list(sources.values())

    @staticmethod
    def _chat_endpoint(base_url: str) -> str:
        base_url = base_url.strip().rstrip("/")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("OpenAI-compatible base URL must be an absolute HTTP(S) URL")
        if base_url.endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"

    @staticmethod
    def _post_json(
        endpoint: str,
        payload: dict[str, Any],
        api_key: Optional[str],
        extra_headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if extra_headers:
            headers.update(extra_headers)
        request = Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers)
        try:
            with urlopen(request, timeout=90) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            detail = ModelExecutor._provider_error_detail(body)
            reason = str(error.reason or error.msg or "").strip() or "HTTP error"
            if error.code in {401, 403}:
                message = (
                    f"Provider authentication failed (HTTP {error.code} {reason}). "
                    "Check the API key saved for this agent/project and make sure the selected provider matches that key."
                )
            else:
                message = f"Provider request failed (HTTP {error.code} {reason})."
            if detail:
                message = f"{message} Provider response: {detail}"
            raise RuntimeError(message) from error
        except URLError as error:
            reason = getattr(error, "reason", error)
            raise RuntimeError(f"Provider request failed: {reason}") from error

    @staticmethod
    def _provider_error_detail(body: str) -> str:
        text = str(body or "").strip()
        if not text:
            return ""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return ModelExecutor._truncate(" ".join(text.split()), 800)
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message") or error.get("code") or error.get("type")
                if message:
                    return ModelExecutor._truncate(" ".join(str(message).split()), 800)
            detail = payload.get("detail") or payload.get("message")
            if detail:
                return ModelExecutor._truncate(" ".join(str(detail).split()), 800)
        return ModelExecutor._truncate(" ".join(text.split()), 800)
