from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.parse import quote
from urllib.request import Request, urlopen

from .browser_control import BrowserControl, BrowserControlError
from .knowledge import KnowledgeWiki
from .models import AgentChatMessage, AgentSnapshot, MemoryRecord, RuntimeEvent, TaskRecord
from .storage import RuntimeStore
from .secrets import SecretStore


EventSink = Callable[[RuntimeEvent], Awaitable[None]]
LOGGER = logging.getLogger("agent_lab.models")
BRANCH_PATTERN = re.compile(r"\b(?:work(?:ing)?\s+on|use)\s+(?:the\s+)?branch\s+([a-zA-Z0-9._/-]+)", re.IGNORECASE)
WORKING_BRANCH_PATTERN = re.compile(r"\bwe(?:'re|\s+are)?\s+working\s+on\s+([a-zA-Z0-9._/-]+)", re.IGNORECASE)
NAME_PATTERN = re.compile(r"\bmy\s+name\s+is\s+([A-Za-z][A-Za-z0-9' -]{1,50})", re.IGNORECASE)


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
        "shared_wiki_search": ToolDefinition(
            name="shared_wiki_search",
            description="Search the shared project wiki for reviewed canonical knowledge.",
            toolset="memory",
            risk="read",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 1000},
                    "limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        "shared_wiki_get_page": ToolDefinition(
            name="shared_wiki_get_page",
            description="Read a shared wiki page or journal by name.",
            toolset="memory",
            risk="read",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string", "maxLength": 300}},
                "required": ["name"],
                "additionalProperties": False,
            },
        ),
        "wiki_proposals_list": ToolDefinition(
            name="wiki_proposals_list",
            description="List pending wiki proposals that need Memory Core review.",
            toolset="memory",
            risk="read",
            parameters={
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50}},
                "additionalProperties": False,
            },
        ),
        "wiki_proposal_resolve": ToolDefinition(
            name="wiki_proposal_resolve",
            description="Approve or reject a pending wiki proposal as the Memory Core agent.",
            toolset="memory",
            risk="memory-write",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "maxLength": 300},
                    "status": {"type": "string", "enum": ["approved", "rejected"]},
                    "reason": {"type": "string", "maxLength": 2000},
                },
                "required": ["name", "status"],
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

    def __init__(
        self,
        store: RuntimeStore,
        browser_control: Optional[BrowserControl] = None,
        wiki: Optional[KnowledgeWiki] = None,
    ):
        self.store = store
        self.browser_control = browser_control
        self.wiki = wiki

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
        if name == "shared_wiki_search":
            if self.wiki is None:
                raise ValueError("Shared wiki is not configured")
            query = str(arguments.get("query", "")).strip()
            if not query:
                raise ValueError("shared_wiki_search requires non-empty query")
            limit = max(1, min(int(arguments.get("limit", 5) or 5), 20))
            return self.wiki.search(query, limit=limit)
        if name == "shared_wiki_get_page":
            if self.wiki is None:
                raise ValueError("Shared wiki is not configured")
            page_name = str(arguments.get("name", "")).strip()
            if not page_name:
                raise ValueError("shared_wiki_get_page requires non-empty name")
            return self.wiki.get_page(page_name)
        if name == "wiki_proposals_list":
            if self.wiki is None:
                raise ValueError("Shared wiki is not configured")
            limit = max(1, min(int(arguments.get("limit", 10) or 10), 50))
            return {"proposals": self.wiki.pending_proposals(limit=limit)}
        if name == "wiki_proposal_resolve":
            if self.wiki is None:
                raise ValueError("Shared wiki is not configured")
            proposal_name = str(arguments.get("name", "")).strip()
            status = str(arguments.get("status", "")).strip()
            reason = str(arguments.get("reason", "")).strip()
            if not proposal_name or status not in {"approved", "rejected"}:
                raise ValueError("wiki_proposal_resolve requires name and valid status")
            resolved = self.wiki.resolve_proposal(
                name=proposal_name,
                status=status,
                reviewer=agent.id,
                reason=reason or f"Resolved by {agent.id}.",
            )
            return {"resolved": True, "name": resolved.name, "status": status, "reviewer": agent.id}
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
        workspace_root: Optional[Path] = None,
        wiki: Optional[KnowledgeWiki] = None,
    ):
        self.store = store
        self.secrets = secrets
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.wiki = wiki or KnowledgeWiki(self.workspace_root / "data" / "wiki")
        self.tools = ToolRegistry(store, browser_control, self.wiki)

    async def run(
        self,
        agent: AgentSnapshot,
        task: TaskRecord,
        emit: EventSink,
        memory_briefing: str = "",
    ) -> dict[str, Any]:
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
            result = await self._run_openai_compatible(agent, task, emit, memory_briefing=memory_briefing)
        elif agent.model.provider in {"openai", "anthropic", "gemini", "ollama"}:
            result = await asyncio.to_thread(self._run_native_provider, agent, task, memory_briefing)
        else:
            raise ValueError(f"Unsupported provider: {agent.model.provider}")
        self._update_memory_artifacts(agent, task, result)
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

    def _update_memory_artifacts(self, agent: AgentSnapshot, task: TaskRecord, result: dict[str, Any]) -> None:
        for fact in self._extract_private_memory_facts(task, result):
            self._append_private_memory_fact(agent.id, fact)
        journal_content = self._task_journal_content(task, result)
        if journal_content:
            self.wiki.append_journal_entry(
                page=f"agent-{agent.id}-journal",
                heading=task.title.strip()[:120] or "Task update",
                content=journal_content,
                agent_id=agent.id,
                source=task.id,
            )
        self._create_shared_wiki_proposal(agent, task, result)

    def _extract_private_memory_facts(self, task: TaskRecord, result: dict[str, Any]) -> list[str]:
        if task.channel != "chat":
            return []
        text = "\n".join(
            value for value in (
                str(task.title or "").strip(),
                str(task.description or "").strip(),
                str(result.get("summary", "") or "").strip(),
            )
            if value
        )
        lowered = text.lower()
        facts: list[str] = []
        if any(needle in lowered for needle in ("everything in english", "all in english", "in english please", "answer in english")):
            facts.append("User preference: respond in English.")
        if any(needle in lowered for needle in ("in italian", "in italiano", "answer in italian", "rispondi in italiano")):
            facts.append("User preference: respond in Italian.")
        branch_match = BRANCH_PATTERN.search(text) or WORKING_BRANCH_PATTERN.search(text)
        if branch_match:
            facts.append(f"Current working branch: {branch_match.group(1).strip()}.")
        name_match = NAME_PATTERN.search(text)
        if name_match:
            facts.append(f"User name: {name_match.group(1).strip()}.")
        if "always update readme" in lowered:
            facts.append("Workflow preference: keep the README updated.")
        if "always update the video script" in lowered or "update the video script each time" in lowered:
            facts.append("Workflow preference: keep the video script log updated.")
        deduped: list[str] = []
        seen: set[str] = set()
        for fact in facts:
            key = fact.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(fact)
        return deduped

    def _append_private_memory_fact(self, agent_id: str, fact: str) -> None:
        addition = str(fact or "").strip()
        if not addition:
            return
        memory = self.store.get_memory(agent_id)
        existing_lines = [line.strip() for line in memory.content.splitlines() if line.strip()]
        if addition in existing_lines:
            return
        memory.content = ("\n".join(existing_lines + [addition])).strip()[-8_000:]
        self.store.save_memory(memory)

    def _task_journal_content(self, task: TaskRecord, result: dict[str, Any]) -> str:
        summary = str(result.get("summary", "") or "").strip()
        if not summary:
            return ""
        parts = [
            f"Task: {task.title.strip() or 'Untitled task'}",
            f"Request: {self._truncate((task.description or task.title or '').strip(), 800)}",
            f"Outcome: {self._truncate(summary, 1_500)}",
        ]
        sources = [
            str(item.get("url", "") or "").strip()
            for item in (result.get("sources") or [])
            if isinstance(item, dict) and str(item.get("url", "") or "").strip()
        ]
        if sources:
            parts.append("Sources:\n" + "\n".join(f"- {url}" for url in sources[:8]))
        return "\n\n".join(part for part in parts if part)

    def _create_shared_wiki_proposal(
        self, agent: AgentSnapshot, task: TaskRecord, result: dict[str, Any]
    ) -> None:
        if task.channel == "chat":
            return
        if result.get("simulated"):
            return
        summary = str(result.get("summary", "") or "").strip()
        if not summary:
            return
        details = str(result.get("details", "") or "").strip()
        sources = [
            str(item.get("url", "") or "").strip()
            for item in (result.get("sources") or [])
            if isinstance(item, dict) and str(item.get("url", "") or "").strip()
        ]
        if len(summary) < 120 and not details and not sources:
            return
        title = f"{agent.name}: {task.title.strip() or 'Task insight'}"
        sections = [
            "## Context",
            f"- Agent: {agent.name} ({agent.id})",
            f"- Role: {agent.role}",
            f"- Task: {task.title.strip() or 'Untitled task'}",
            f"- Capability: {task.capability or 'general'}",
            "",
            "## User request",
            self._truncate((task.description or task.title or "").strip(), 1_000),
            "",
            "## Proposed durable knowledge",
            self._truncate(summary, 2_500),
        ]
        if details:
            sections.extend(["", "## Supporting details", self._truncate(details, 2_500)])
        if sources:
            sections.extend(["", "## Sources", *[f"- {url}" for url in sources[:10]]])
        self.wiki.propose(
            agent_id=agent.id,
            title=title,
            content="\n".join(section for section in sections if section is not None).strip(),
            source=task.id,
            target_page=f"knowledge-{task.capability or agent.role or 'general'}",
        )

    async def _run_openai_compatible(
        self, agent: AgentSnapshot, task: TaskRecord, emit: EventSink, memory_briefing: str = ""
    ) -> dict[str, Any]:
        endpoint = self._chat_endpoint(agent.model.base_url)
        api_key = self._resolve_api_key(agent)
        system_prompt = self._build_system_prompt(
            agent,
            task=task,
            include_chat_history=False,
            memory_briefing=memory_briefing,
        )
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
                if not api_key:
                    api_key = self.secrets.get_project()
            else:
                api_key = self.secrets.get_project()
        if not api_key and agent.model.api_key_env:
            api_key = os.environ.get(agent.model.api_key_env)
        if not api_key:
            if agent.model.api_key_scope == "agent":
                raise RuntimeError("No API key configured for agent scope and no project fallback is available")
            raise RuntimeError("No API key configured for project scope")
        return api_key

    def _run_native_provider(self, agent: AgentSnapshot, task: TaskRecord, memory_briefing: str = "") -> dict[str, Any]:
        provider = agent.model.provider
        api_key = self._resolve_api_key(agent)
        system = self._build_system_prompt(
            agent,
            task=task,
            include_chat_history=task.channel == "chat",
            current_task_id=task.id,
            memory_briefing=memory_briefing,
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
        task: Optional[TaskRecord] = None,
        include_chat_history: bool = False,
        current_task_id: str = "",
        memory_briefing: str = "",
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
        if memory_briefing.strip():
            parts.append("Memory Core briefing:\n" + memory_briefing.strip())
        if task and task.consultation_notes.strip():
            parts.append(
                "Specialist consultation notes:\n"
                + task.consultation_notes.strip()
                + "\n\nUse these specialist inputs to synthesize the final answer for the user."
            )
        if include_chat_history:
            chat_history = self._build_chat_context_text(agent.id, current_task_id)
            if chat_history:
                parts.append(f"Recent chat history:\n{chat_history}")
            parts.append(
                "This is a persistent chat session. Use prior chat history and the wiki to answer with continuity."
            )
            LOGGER.info(
                "memory_context agent=%s task=%s wiki_chars=%s memory_briefing_chars=%s chat_chars=%s",
                agent.id,
                current_task_id or "-",
                len(wiki),
                len(memory_briefing),
                len(chat_history),
            )
        return "\n\n".join(parts).strip()

    @staticmethod
    def _build_user_prompt(task: TaskRecord) -> str:
        description = task.description.strip() or task.title.strip()
        if task.channel == "chat":
            if task.route_mode == "consult" and task.consult_agent_ids:
                consulted = ", ".join(task.consult_agent_ids)
                return (
                    f"{description}\n\n"
                    "You are the main user-facing agent. "
                    f"You have already consulted these specialists internally: {consulted}. "
                    "Read the specialist consultation notes and produce one final answer for the user. "
                    "Do not tell the user to talk to another agent. "
                    "Synthesize, resolve conflicts when possible, cite useful sources, and speak with one coherent voice."
                )
            if task.route_mode == "clarify" and task.clarification_question.strip():
                return (
                    f"{description}\n\n"
                    "Before continuing, ask the following clarification question exactly once:\n"
                    f"{task.clarification_question.strip()}"
                )
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

    def route_chat_with_reasoning(
        self,
        task: TaskRecord,
        current_agent: AgentSnapshot,
        agents: dict[str, AgentSnapshot],
    ) -> Optional[dict[str, Any]]:
        for router_agent in self._routing_candidates(current_agent, agents):
            try:
                decision = self._route_chat_via_provider(router_agent, task, current_agent, agents)
            except Exception as error:
                LOGGER.info(
                    "routing_llm_unavailable router=%s provider=%s error=%s",
                    router_agent.id,
                    router_agent.model.provider,
                    error,
                )
                continue
            if decision is not None:
                return decision
        return None

    def decide_council_policy_with_reasoning(
        self,
        task: TaskRecord,
        source_agent: AgentSnapshot,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
        agents: dict[str, AgentSnapshot],
    ) -> Optional[dict[str, Any]]:
        for router_agent in self._routing_candidates(source_agent, agents):
            try:
                decision = self._decide_council_policy_via_provider(
                    router_agent,
                    task,
                    source_agent,
                    consulted_rounds,
                )
            except Exception as error:
                LOGGER.info(
                    "council_llm_unavailable router=%s provider=%s error=%s",
                    router_agent.id,
                    router_agent.model.provider,
                    error,
                )
                continue
            if decision is not None:
                return decision
        return None

    def decide_consult_followup_with_reasoning(
        self,
        task: TaskRecord,
        source_agent: AgentSnapshot,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
        agents: dict[str, AgentSnapshot],
    ) -> Optional[dict[str, Any]]:
        for router_agent in self._routing_candidates(source_agent, agents):
            try:
                decision = self._decide_consult_followup_via_provider(
                    router_agent,
                    task,
                    source_agent,
                    consulted_rounds,
                    agents,
                )
            except Exception as error:
                LOGGER.info(
                    "followup_llm_unavailable router=%s provider=%s error=%s",
                    router_agent.id,
                    router_agent.model.provider,
                    error,
                )
                continue
            if decision is not None:
                return decision
        return None

    def decide_peer_escalation_with_reasoning(
        self,
        task: TaskRecord,
        specialist_agent: AgentSnapshot,
        specialist_summary: str,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
        agents: dict[str, AgentSnapshot],
        source_agent: AgentSnapshot,
    ) -> Optional[dict[str, Any]]:
        for router_agent in self._routing_candidates(specialist_agent, agents):
            try:
                decision = self._decide_peer_escalation_via_provider(
                    router_agent,
                    task,
                    specialist_agent,
                    specialist_summary,
                    consulted_rounds,
                    agents,
                    source_agent,
                )
            except Exception as error:
                LOGGER.info(
                    "peer_escalation_llm_unavailable router=%s provider=%s error=%s",
                    router_agent.id,
                    router_agent.model.provider,
                    error,
                )
                continue
            if decision is not None:
                return decision
        return None

    def _routing_candidates(
        self,
        current_agent: AgentSnapshot,
        agents: dict[str, AgentSnapshot],
    ) -> list[AgentSnapshot]:
        ordered_ids = []
        for candidate_id in (
            current_agent.id,
            "orchestrator",
            "memory",
            "ai-news-navigator",
            *agents.keys(),
        ):
            if candidate_id not in agents or candidate_id in ordered_ids:
                continue
            ordered_ids.append(candidate_id)
        candidates = []
        for candidate_id in ordered_ids:
            agent = agents[candidate_id]
            if agent.model.provider == "simulated":
                continue
            if agent.model.provider != "ollama":
                try:
                    self._resolve_api_key(agent)
                except Exception:
                    continue
            candidates.append(agent)
        return candidates

    def _route_chat_via_provider(
        self,
        router_agent: AgentSnapshot,
        task: TaskRecord,
        current_agent: AgentSnapshot,
        agents: dict[str, AgentSnapshot],
    ) -> Optional[dict[str, Any]]:
        provider = router_agent.model.provider
        api_key = None if provider == "ollama" else self._resolve_api_key(router_agent)
        system = self._routing_system_prompt()
        user = self._routing_user_prompt(task, current_agent, agents)

        if provider == "openai":
            endpoint = self._provider_endpoint(router_agent.model.base_url, "https://api.openai.com/v1/responses", "/responses")
            response = self._post_json(
                endpoint,
                {
                    "model": router_agent.model.model,
                    "instructions": system,
                    "input": user,
                },
                api_key,
            )
            text = self._openai_response_text(response)
        elif provider == "openai-compatible":
            endpoint = self._chat_endpoint(router_agent.model.base_url)
            response = self._post_json(
                endpoint,
                {
                    "model": router_agent.model.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0,
                },
                api_key,
            )
            text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        elif provider == "anthropic":
            endpoint = self._provider_endpoint(router_agent.model.base_url, "https://api.anthropic.com/v1/messages", "/v1/messages")
            response = self._post_json(
                endpoint,
                {
                    "model": router_agent.model.model,
                    "max_tokens": 500,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                None,
                {"x-api-key": api_key or "", "anthropic-version": "2023-06-01"},
            )
            text = "\n".join(item.get("text", "") for item in response.get("content", []) if item.get("type") == "text")
        elif provider == "gemini":
            base = router_agent.model.base_url.strip().rstrip("/") or "https://generativelanguage.googleapis.com/v1beta"
            endpoint = f"{base}/models/{quote(router_agent.model.model, safe='')}:generateContent"
            response = self._post_json(
                endpoint,
                {
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                },
                None,
                {"x-goog-api-key": api_key or ""},
            )
            candidates = response.get("candidates", [])
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            text = "\n".join(part.get("text", "") for part in parts)
        elif provider == "ollama":
            endpoint = self._provider_endpoint(router_agent.model.base_url, "http://127.0.0.1:11434/api/chat", "/api/chat")
            response = self._post_json(
                endpoint,
                {
                    "model": router_agent.model.model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                None,
            )
            text = response.get("message", {}).get("content", "")
        else:
            return None
        return self._parse_routing_decision(text, current_agent, agents)

    def _decide_council_policy_via_provider(
        self,
        router_agent: AgentSnapshot,
        task: TaskRecord,
        source_agent: AgentSnapshot,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
    ) -> Optional[dict[str, Any]]:
        provider = router_agent.model.provider
        api_key = None if provider == "ollama" else self._resolve_api_key(router_agent)
        system = self._council_policy_system_prompt()
        user = self._council_policy_user_prompt(task, source_agent, consulted_rounds)

        if provider == "openai":
            endpoint = self._provider_endpoint(router_agent.model.base_url, "https://api.openai.com/v1/responses", "/responses")
            response = self._post_json(
                endpoint,
                {
                    "model": router_agent.model.model,
                    "instructions": system,
                    "input": user,
                },
                api_key,
            )
            text = self._openai_response_text(response)
        elif provider == "openai-compatible":
            endpoint = self._chat_endpoint(router_agent.model.base_url)
            response = self._post_json(
                endpoint,
                {
                    "model": router_agent.model.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0,
                },
                api_key,
            )
            text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        elif provider == "anthropic":
            endpoint = self._provider_endpoint(router_agent.model.base_url, "https://api.anthropic.com/v1/messages", "/v1/messages")
            response = self._post_json(
                endpoint,
                {
                    "model": router_agent.model.model,
                    "max_tokens": 500,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                None,
                {"x-api-key": api_key or "", "anthropic-version": "2023-06-01"},
            )
            text = "\n".join(item.get("text", "") for item in response.get("content", []) if item.get("type") == "text")
        elif provider == "gemini":
            base = router_agent.model.base_url.strip().rstrip("/") or "https://generativelanguage.googleapis.com/v1beta"
            endpoint = f"{base}/models/{quote(router_agent.model.model, safe='')}:generateContent"
            response = self._post_json(
                endpoint,
                {
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                },
                None,
                {"x-goog-api-key": api_key or ""},
            )
            candidates = response.get("candidates", [])
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            text = "\n".join(part.get("text", "") for part in parts)
        elif provider == "ollama":
            endpoint = self._provider_endpoint(router_agent.model.base_url, "http://127.0.0.1:11434/api/chat", "/api/chat")
            response = self._post_json(
                endpoint,
                {
                    "model": router_agent.model.model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                None,
            )
            text = response.get("message", {}).get("content", "")
        else:
            return None
        return self._parse_council_policy_decision(text, consulted_rounds)

    def _decide_consult_followup_via_provider(
        self,
        router_agent: AgentSnapshot,
        task: TaskRecord,
        source_agent: AgentSnapshot,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
        agents: dict[str, AgentSnapshot],
    ) -> Optional[dict[str, Any]]:
        provider = router_agent.model.provider
        api_key = None if provider == "ollama" else self._resolve_api_key(router_agent)
        system = self._consult_followup_system_prompt()
        user = self._consult_followup_user_prompt(task, source_agent, consulted_rounds, agents)

        if provider == "openai":
            endpoint = self._provider_endpoint(router_agent.model.base_url, "https://api.openai.com/v1/responses", "/responses")
            response = self._post_json(
                endpoint,
                {
                    "model": router_agent.model.model,
                    "instructions": system,
                    "input": user,
                },
                api_key,
            )
            text = self._openai_response_text(response)
        elif provider == "openai-compatible":
            endpoint = self._chat_endpoint(router_agent.model.base_url)
            response = self._post_json(
                endpoint,
                {
                    "model": router_agent.model.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0,
                },
                api_key,
            )
            text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        elif provider == "anthropic":
            endpoint = self._provider_endpoint(router_agent.model.base_url, "https://api.anthropic.com/v1/messages", "/v1/messages")
            response = self._post_json(
                endpoint,
                {
                    "model": router_agent.model.model,
                    "max_tokens": 500,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                None,
                {"x-api-key": api_key or "", "anthropic-version": "2023-06-01"},
            )
            text = "\n".join(item.get("text", "") for item in response.get("content", []) if item.get("type") == "text")
        elif provider == "gemini":
            base = router_agent.model.base_url.strip().rstrip("/") or "https://generativelanguage.googleapis.com/v1beta"
            endpoint = f"{base}/models/{quote(router_agent.model.model, safe='')}:generateContent"
            response = self._post_json(
                endpoint,
                {
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                },
                None,
                {"x-goog-api-key": api_key or ""},
            )
            candidates = response.get("candidates", [])
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            text = "\n".join(part.get("text", "") for part in parts)
        elif provider == "ollama":
            endpoint = self._provider_endpoint(router_agent.model.base_url, "http://127.0.0.1:11434/api/chat", "/api/chat")
            response = self._post_json(
                endpoint,
                {
                    "model": router_agent.model.model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                None,
            )
            text = response.get("message", {}).get("content", "")
        else:
            return None
        return self._parse_consult_followup_decision(text, consulted_rounds, agents, source_agent)

    def _decide_peer_escalation_via_provider(
        self,
        router_agent: AgentSnapshot,
        task: TaskRecord,
        specialist_agent: AgentSnapshot,
        specialist_summary: str,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
        agents: dict[str, AgentSnapshot],
        source_agent: AgentSnapshot,
    ) -> Optional[dict[str, Any]]:
        provider = router_agent.model.provider
        api_key = None if provider == "ollama" else self._resolve_api_key(router_agent)
        system = self._peer_escalation_system_prompt()
        user = self._peer_escalation_user_prompt(
            task,
            specialist_agent,
            specialist_summary,
            consulted_rounds,
            agents,
            source_agent,
        )

        if provider == "openai":
            endpoint = self._provider_endpoint(router_agent.model.base_url, "https://api.openai.com/v1/responses", "/responses")
            response = self._post_json(
                endpoint,
                {
                    "model": router_agent.model.model,
                    "instructions": system,
                    "input": user,
                },
                api_key,
            )
            text = self._openai_response_text(response)
        elif provider == "openai-compatible":
            endpoint = self._chat_endpoint(router_agent.model.base_url)
            response = self._post_json(
                endpoint,
                {
                    "model": router_agent.model.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0,
                },
                api_key,
            )
            text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        elif provider == "anthropic":
            endpoint = self._provider_endpoint(router_agent.model.base_url, "https://api.anthropic.com/v1/messages", "/v1/messages")
            response = self._post_json(
                endpoint,
                {
                    "model": router_agent.model.model,
                    "max_tokens": 500,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                None,
                {"x-api-key": api_key or "", "anthropic-version": "2023-06-01"},
            )
            text = "\n".join(item.get("text", "") for item in response.get("content", []) if item.get("type") == "text")
        elif provider == "gemini":
            base = router_agent.model.base_url.strip().rstrip("/") or "https://generativelanguage.googleapis.com/v1beta"
            endpoint = f"{base}/models/{quote(router_agent.model.model, safe='')}:generateContent"
            response = self._post_json(
                endpoint,
                {
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                },
                None,
                {"x-goog-api-key": api_key or ""},
            )
            candidates = response.get("candidates", [])
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            text = "\n".join(part.get("text", "") for part in parts)
        elif provider == "ollama":
            endpoint = self._provider_endpoint(router_agent.model.base_url, "http://127.0.0.1:11434/api/chat", "/api/chat")
            response = self._post_json(
                endpoint,
                {
                    "model": router_agent.model.model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                None,
            )
            text = response.get("message", {}).get("content", "")
        else:
            return None
        return self._parse_peer_escalation_decision(text, consulted_rounds, agents, specialist_agent, source_agent)

    @staticmethod
    def _routing_system_prompt() -> str:
        return (
            "You are a conversation router for a multi-agent system. "
            "Choose whether the user's latest message should stay with the current agent or be handed to a better specialist. "
            "Use the agent list, roles, capabilities, and the actual user message. "
            "Use route_mode='route' when the user wants to directly switch and talk to another agent. "
            "Use route_mode='consult' when the current agent should ask another specialist and then relay the answer back. "
            "Prefer consult when the current agent is a coordinator, orchestrator, or memory/context agent. "
            "Route when the request clearly fits another specialist better, even if the user did not name that agent. "
            "Return JSON only with this schema: "
            '{"route": boolean, "route_mode": "stay|route|consult", "target_agent_id": string, "reason": string, "confidence": number}. '
            "If the conversation should stay with the current agent, set route to false, route_mode to 'stay', and target_agent_id to the current agent id."
        )

    @staticmethod
    def _council_policy_system_prompt() -> str:
        return (
            "You decide whether a multi-agent task needs an internal specialist council before final synthesis. "
            "Use the user request plus the specialist summaries already collected. "
            "Enable council only when cross-specialist challenge, reconciliation, or extension would materially improve the result. "
            "Prefer a small turn budget. "
            "Return JSON only with this schema: "
            '{"enabled": boolean, "reason": string, "participant_ids": string[], "max_turns": number}.'
        )

    @staticmethod
    def _consult_followup_system_prompt() -> str:
        return (
            "You decide the next bounded orchestration step after initial specialist consultation. "
            "Choose exactly one action: synthesize, memory, or consult. "
            "Use synthesize when the source agent can now answer. "
            "Use memory when Memory Core context would materially improve the answer. "
            "Use consult when exactly one additional unconsulted specialist would materially improve the answer. "
            "Return JSON only with this schema: "
            '{"action": "synthesize|memory|consult", "reason": string, "target_agent_id": string}.'
        )

    @staticmethod
    def _peer_escalation_system_prompt() -> str:
        return (
            "You decide whether a specialist should explicitly request another step before final synthesis. "
            "Choose exactly one action: none or request. "
            "A request may target another unconsulted specialist, Memory Core, or a council turn. "
            "Return JSON only with this schema: "
            '{"action": "none|request", "reason": string, "target_kind": "specialist|memory|council", "target_agent_id": string}.'
        )

    def _routing_user_prompt(
        self,
        task: TaskRecord,
        current_agent: AgentSnapshot,
        agents: dict[str, AgentSnapshot],
    ) -> str:
        agent_lines = []
        for agent in agents.values():
            agent_lines.append(
                f"- id={agent.id}; name={agent.name}; role={agent.role}; capabilities={', '.join(agent.capabilities or [])}; "
                f"instructions={self._truncate(agent.instructions or '', 220)}"
            )
        return "\n".join(
            [
                f"Current agent: {current_agent.id}",
                f"Task title: {task.title}",
                f"User message: {(task.description or task.title or '').strip()}",
                "Available agents:",
                *agent_lines,
            ]
        )

    def _council_policy_user_prompt(
        self,
        task: TaskRecord,
        source_agent: AgentSnapshot,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
    ) -> str:
        round_lines = []
        for agent, summary, sources in consulted_rounds[:3]:
            round_lines.append(
                f"- id={agent.id}; name={agent.name}; role={agent.role}; "
                f"summary={self._truncate(summary, 400)}; sources={len(sources)}"
            )
        return "\n".join(
            [
                f"Source agent: {source_agent.id}",
                f"Task title: {task.title}",
                f"User message: {(task.description or task.title or '').strip()}",
                "Consulted specialists:",
                *round_lines,
            ]
        )

    def _consult_followup_user_prompt(
        self,
        task: TaskRecord,
        source_agent: AgentSnapshot,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
        agents: dict[str, AgentSnapshot],
    ) -> str:
        consulted_ids = {agent.id for agent, _summary, _sources in consulted_rounds}
        round_lines = []
        for agent, summary, sources in consulted_rounds[:4]:
            round_lines.append(
                f"- id={agent.id}; name={agent.name}; role={agent.role}; "
                f"summary={self._truncate(summary, 400)}; sources={len(sources)}"
            )
        candidate_lines = []
        for agent in agents.values():
            if agent.id == source_agent.id or agent.id in consulted_ids or agent.role == "supervisor":
                continue
            candidate_lines.append(
                f"- id={agent.id}; name={agent.name}; role={agent.role}; capabilities={', '.join(agent.capabilities or [])}"
            )
        return "\n".join(
            [
                f"Source agent: {source_agent.id}",
                f"Task title: {task.title}",
                f"User message: {(task.description or task.title or '').strip()}",
                "Consulted specialists:",
                *(round_lines or ["- none"]),
                "Available unconsulted specialists:",
                *(candidate_lines or ["- none"]),
            ]
        )

    def _peer_escalation_user_prompt(
        self,
        task: TaskRecord,
        specialist_agent: AgentSnapshot,
        specialist_summary: str,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
        agents: dict[str, AgentSnapshot],
        source_agent: AgentSnapshot,
    ) -> str:
        consulted_ids = {agent.id for agent, _summary, _sources in consulted_rounds}
        candidate_lines = []
        for agent in agents.values():
            if agent.id in consulted_ids or agent.id in {specialist_agent.id, source_agent.id} or agent.role == "supervisor":
                continue
            candidate_lines.append(
                f"- id={agent.id}; name={agent.name}; role={agent.role}; capabilities={', '.join(agent.capabilities or [])}"
            )
        return "\n".join(
            [
                f"Source agent: {source_agent.id}",
                f"Current specialist: {specialist_agent.id}",
                f"Task title: {task.title}",
                f"User message: {(task.description or task.title or '').strip()}",
                f"Current specialist summary: {self._truncate(specialist_summary, 500)}",
                "Available non-specialist escalation kinds: memory, council",
                "Available unconsulted specialists:",
                *(candidate_lines or ["- none"]),
            ]
        )

    @staticmethod
    def _parse_routing_decision(
        text: str,
        current_agent: AgentSnapshot,
        agents: dict[str, AgentSnapshot],
    ) -> Optional[dict[str, Any]]:
        payload = None
        cleaned = str(text or "").strip()
        if not cleaned:
            return None
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                try:
                    payload = json.loads(match.group(0))
                except json.JSONDecodeError:
                    payload = None
        if not isinstance(payload, dict):
            return None
        target_agent_id = str(payload.get("target_agent_id") or current_agent.id).strip().lower()
        if target_agent_id not in agents:
            return None
        route = bool(payload.get("route"))
        route_mode = str(payload.get("route_mode") or ("route" if route else "stay")).strip().lower()
        if route_mode not in {"stay", "route", "consult"}:
            route_mode = "route" if route else "stay"
        if not route or target_agent_id == current_agent.id:
            return {
                "should_route": False,
                "target_agent_id": current_agent.id,
                "reason": str(payload.get("reason") or "LLM router kept the current agent.").strip(),
                "route_mode": "stay",
                "confidence": float(payload.get("confidence") or 0),
            }
        confidence = payload.get("confidence", 0)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.0
        return {
            "should_route": True,
            "target_agent_id": target_agent_id,
            "reason": str(payload.get("reason") or f"LLM router selected {target_agent_id}.").strip(),
            "route_mode": route_mode,
            "confidence": confidence,
        }

    @staticmethod
    def _parse_council_policy_decision(
        text: str,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
    ) -> Optional[dict[str, Any]]:
        payload = None
        cleaned = str(text or "").strip()
        if not cleaned:
            return None
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                try:
                    payload = json.loads(match.group(0))
                except json.JSONDecodeError:
                    payload = None
        if not isinstance(payload, dict):
            return None
        valid_ids = [agent.id for agent, _summary, _sources in consulted_rounds[:3]]
        participant_ids = [
            str(value).strip().lower()
            for value in (payload.get("participant_ids") or [])
            if str(value).strip().lower() in valid_ids
        ]
        if not participant_ids:
            participant_ids = valid_ids[:]
        try:
            max_turns = max(0, min(2, int(payload.get("max_turns") or 0)))
        except (TypeError, ValueError):
            max_turns = 0
        enabled = bool(payload.get("enabled")) and len(participant_ids) >= 2 and max_turns > 0
        return {
            "enabled": enabled,
            "reason": str(payload.get("reason") or "LLM council policy decision.").strip(),
            "participant_ids": participant_ids,
            "max_turns": max_turns if enabled else 0,
            "decision_mode": "llm",
        }

    @staticmethod
    def _parse_consult_followup_decision(
        text: str,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
        agents: dict[str, AgentSnapshot],
        source_agent: AgentSnapshot,
    ) -> Optional[dict[str, Any]]:
        payload = None
        cleaned = str(text or "").strip()
        if not cleaned:
            return None
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                try:
                    payload = json.loads(match.group(0))
                except json.JSONDecodeError:
                    payload = None
        if not isinstance(payload, dict):
            return None
        action = str(payload.get("action") or "synthesize").strip().lower()
        if action not in {"synthesize", "memory", "consult"}:
            action = "synthesize"
        consulted_ids = {agent.id for agent, _summary, _sources in consulted_rounds}
        target_agent_id = str(payload.get("target_agent_id") or "").strip().lower()
        if action == "consult":
            if (
                not target_agent_id
                or target_agent_id not in agents
                or target_agent_id in consulted_ids
                or target_agent_id == source_agent.id
            ):
                return None
        return {
            "action": action,
            "reason": str(payload.get("reason") or "LLM follow-up decision.").strip(),
            "target_agent_id": target_agent_id if action == "consult" else "",
            "decision_mode": "llm",
        }

    @staticmethod
    def _parse_peer_escalation_decision(
        text: str,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
        agents: dict[str, AgentSnapshot],
        specialist_agent: AgentSnapshot,
        source_agent: AgentSnapshot,
    ) -> Optional[dict[str, Any]]:
        payload = None
        cleaned = str(text or "").strip()
        if not cleaned:
            return None
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                try:
                    payload = json.loads(match.group(0))
                except json.JSONDecodeError:
                    payload = None
        if not isinstance(payload, dict):
            return None
        action = str(payload.get("action") or "none").strip().lower()
        if action not in {"none", "request"}:
            action = "none"
        target_kind = str(payload.get("target_kind") or "specialist").strip().lower()
        if target_kind not in {"specialist", "memory", "council"}:
            target_kind = "specialist"
        consulted_ids = {agent.id for agent, _summary, _sources in consulted_rounds}
        target_agent_id = str(payload.get("target_agent_id") or "").strip().lower()
        if action == "request" and target_kind == "specialist":
            if (
                not target_agent_id
                or target_agent_id not in agents
                or target_agent_id in consulted_ids
                or target_agent_id in {specialist_agent.id, source_agent.id}
            ):
                return None
        return {
            "action": action,
            "reason": str(payload.get("reason") or "LLM peer escalation decision.").strip(),
            "target_kind": target_kind if action == "request" else "",
            "target_agent_id": target_agent_id if action == "request" and target_kind == "specialist" else ("memory" if action == "request" and target_kind == "memory" else ""),
            "decision_mode": "llm",
        }

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
