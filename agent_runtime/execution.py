from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlparse
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import AgentSnapshot, MemoryRecord, RuntimeEvent, TaskRecord
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
    }

    def __init__(self, store: RuntimeStore):
        self.store = store

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
        raise ValueError(f"Tool has no executor: {name}")


class ModelExecutor:
    def __init__(self, store: RuntimeStore, secrets: Optional[SecretStore] = None):
        self.store = store
        self.secrets = secrets
        self.tools = ToolRegistry(store)

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
            result = {
                "summary": f"{agent.name} completed {task.title}",
                "details": "Executed by the native deterministic provider.",
                "provider": "simulated",
                "model": agent.model.model,
                "tool_calls": 0,
            }
        elif agent.model.provider == "openai-compatible":
            result = await self._run_openai_compatible(agent, task, emit)
        elif agent.model.provider in {"openai", "anthropic", "gemini", "ollama"}:
            result = await asyncio.to_thread(self._run_native_provider, agent, task)
        else:
            raise ValueError(f"Unsupported provider: {agent.model.provider}")
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

    async def _run_openai_compatible(
        self, agent: AgentSnapshot, task: TaskRecord, emit: EventSink
    ) -> dict[str, Any]:
        endpoint = self._chat_endpoint(agent.model.base_url)
        api_key = self._resolve_api_key(agent)

        memory = self.store.get_memory(agent.id).content
        system_parts = [
            f"You are {agent.name}, role: {agent.role}.",
            agent.instructions or "Complete assigned tasks carefully and return verifiable results.",
        ]
        if memory:
            system_parts.append(f"Private durable memory:\n{memory}")
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "\n\n".join(system_parts)},
            {
                "role": "user",
                "content": f"Task: {task.title}\n\n{task.description}\n\nReturn a concise result.",
            },
        ]
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
        memory = self.store.get_memory(agent.id).content
        system = f"You are {agent.name}, role: {agent.role}.\n{agent.instructions}".strip()
        if memory:
            system += f"\n\nPrivate durable memory:\n{memory}"
        user = f"Task: {task.title}\n\n{task.description}\n\nReturn a concise result."

        if provider == "openai":
            endpoint = self._provider_endpoint(agent.model.base_url, "https://api.openai.com/v1/responses", "/responses")
            payload = {"model": agent.model.model, "instructions": system, "input": user}
            response = self._post_json(endpoint, payload, api_key)
            summary = self._openai_response_text(response)
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
            "tool_calls": 0,
        }

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
        with urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
