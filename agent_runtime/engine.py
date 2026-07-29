from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from .browser_control import BrowserControl
from .execution import ModelExecutor
from .knowledge import KnowledgeWiki
from .models import (
    AgentDefinition,
    AgentChatMessage,
    AgentSnapshot,
    AgentState,
    MessageEnvelope,
    MemoryRecord,
    MemoryUpdate,
    RuntimeEvent,
    SystemSettings,
    TaskCreate,
    TaskRecord,
    TaskState,
    WikiMaintenanceResult,
    WikiPageContent,
    WikiPageRecord,
    WikiRecord,
    WikiProposalRecord,
    WikiSearchResult,
    WikiUpdate,
    utc_now,
)
from .protocols import validate_message, validate_task_transition
from .router import ConversationRouter
from .storage import RuntimeStore
from .secrets import SecretStore


LOGGER = logging.getLogger("agent_lab.runtime")


class AgentRuntime:
    def __init__(
        self,
        database_path: Path,
        seed_path: Optional[Path] = None,
        simulation_delay: float = 1.0,
        secrets: Optional[SecretStore] = None,
        browser_control: Optional[BrowserControl] = None,
    ):
        self.store = RuntimeStore(database_path)
        self.seed_path = seed_path
        self.simulation_delay = max(0, simulation_delay)
        self.agents: dict[str, AgentSnapshot] = {agent.id: agent for agent in self.store.load_agents()}
        self.tasks: dict[str, TaskRecord] = {task.id: task for task in self.store.load_tasks()}
        self.subscribers: set[asyncio.Queue[RuntimeEvent]] = set()
        self.running_jobs: set[asyncio.Task[None]] = set()
        self.router = ConversationRouter()
        self.system_settings = self.store.load_system_settings()
        project_root = (seed_path.parent.parent if seed_path else Path(__file__).resolve().parent.parent).resolve()
        self.browser_control = browser_control or BrowserControl(project_root)
        self.knowledge_wiki = KnowledgeWiki(project_root / "data" / "wiki")
        self.executor = ModelExecutor(
            self.store,
            secrets,
            browser_control=self.browser_control,
            workspace_root=project_root,
            wiki=self.knowledge_wiki,
        )
        if not self.agents:
            self._seed_agents()
        else:
            self._seed_missing_agents()
        for agent_id in self.agents:
            self.store.bootstrap_wiki_from_chat(agent_id)
        self._recover_interrupted_state()

    def _seed_agents(self) -> None:
        if self.seed_path is None or not self.seed_path.exists():
            return
        definitions = json.loads(self.seed_path.read_text(encoding="utf-8"))
        for item in definitions:
            definition = self._apply_system_model_defaults(AgentDefinition.model_validate(item))
            agent = AgentSnapshot(**definition.model_dump())
            self.agents[agent.id] = agent
            self.store.save_agent(agent)

    def _seed_missing_agents(self) -> None:
        if self.seed_path is None or not self.seed_path.exists():
            return
        definitions = json.loads(self.seed_path.read_text(encoding="utf-8"))
        for item in definitions:
            definition = self._apply_system_model_defaults(AgentDefinition.model_validate(item))
            if definition.id in self.agents:
                continue
            agent = AgentSnapshot(**definition.model_dump())
            self.agents[agent.id] = agent
            self.store.save_agent(agent)
            self.store.append_event(
                RuntimeEvent(
                    type="agent.seeded",
                    entity_id=agent.id,
                    agent_id=agent.id,
                    summary=f"Seeded missing agent {agent.name}.",
                    data={"agent": agent.model_dump(mode="json")},
                )
            )

    def _recover_interrupted_state(self) -> None:
        recovered_tasks = 0
        terminal_states = {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}
        for task in self.tasks.values():
            if task.state not in terminal_states:
                task.state = TaskState.FAILED
                task.error = "Runtime stopped before the task completed"
                task.updated_at = utc_now()
                self.store.save_task(task)
                recovered_tasks += 1
        for agent in self.agents.values():
            if agent.state != AgentState.IDLE or agent.active_task_id:
                agent.state = AgentState.IDLE
                agent.active_task_id = None
                agent.load = 0.08
                self.store.save_agent(agent)
        if recovered_tasks:
            self.store.append_event(
                RuntimeEvent(
                    type="runtime.recovered",
                    summary=f"Recovered {recovered_tasks} interrupted task(s).",
                    data={"tasks": recovered_tasks},
                )
            )

    def list_agents(self) -> list[AgentSnapshot]:
        return sorted(self.agents.values(), key=lambda agent: (agent.role != "supervisor", agent.name))

    def list_tasks(self) -> list[TaskRecord]:
        return sorted(self.tasks.values(), key=lambda task: task.updated_at, reverse=True)

    def get_system_settings(self) -> SystemSettings:
        return self.system_settings

    def get_agent_chat(self, agent_id: str) -> list[AgentChatMessage]:
        if agent_id not in self.agents:
            raise KeyError(agent_id)
        return self.store.load_agent_chat_messages(agent_id)

    async def add_agent(self, definition: AgentDefinition) -> AgentSnapshot:
        if definition.id in self.agents:
            raise ValueError(f"Agent already exists: {definition.id}")
        definition = self._apply_system_model_defaults(definition)
        agent = AgentSnapshot(**definition.model_dump())
        self.agents[agent.id] = agent
        self.store.save_agent(agent)
        await self.publish(
            RuntimeEvent(
                type="agent.created",
                entity_id=agent.id,
                agent_id=agent.id,
                summary=f"{agent.name} joined as {agent.role}.",
                data={"agent": agent.model_dump(mode="json")},
            )
        )
        return agent

    async def update_agent(self, agent_id: str, definition: AgentDefinition) -> AgentSnapshot:
        current = self.agents.get(agent_id)
        if current is None:
            raise KeyError(agent_id)
        if definition.id != agent_id:
            raise ValueError("Agent id cannot be changed")
        updated = AgentSnapshot(
            **definition.model_dump(),
            state=current.state,
            active_task_id=current.active_task_id,
            load=current.load,
            created_at=current.created_at,
        )
        self.agents[agent_id] = updated
        self.store.save_agent(updated)
        await self.publish(
            RuntimeEvent(
                type="agent.updated",
                entity_id=agent_id,
                agent_id=agent_id,
                summary=f"Updated settings for {updated.name}.",
                data={"agent": updated.model_dump(mode="json")},
            )
        )
        return updated

    async def update_system_settings(self, settings: SystemSettings) -> SystemSettings:
        normalized = SystemSettings.model_validate(settings.model_dump())
        normalized.configured = True
        self.system_settings = normalized
        self.store.save_system_settings(normalized)
        for agent_id, current in list(self.agents.items()):
            payload = current.model_dump()
            payload["model"] = normalized.model.model_copy(deep=True)
            updated = AgentSnapshot(**payload)
            self.agents[agent_id] = updated
            self.store.save_agent(updated)
        await self.publish(
            RuntimeEvent(
                type="system.settings.updated",
                entity_id="system-settings",
                summary="Updated global system settings and applied them to all agents.",
                data={"settings": normalized.model_dump(mode="json")},
            )
        )
        return normalized

    def _apply_system_model_defaults(self, definition: AgentDefinition) -> AgentDefinition:
        if not self.system_settings.configured:
            return definition
        payload = definition.model_dump()
        payload["model"] = self.system_settings.model.model_copy(deep=True)
        return AgentDefinition(**payload)

    def get_memory(self, agent_id: str) -> MemoryRecord:
        if agent_id not in self.agents:
            raise KeyError(agent_id)
        return self.store.get_memory(agent_id)

    async def update_memory(self, agent_id: str, update: MemoryUpdate) -> MemoryRecord:
        if agent_id not in self.agents:
            raise KeyError(agent_id)
        memory = MemoryRecord(agent_id=agent_id, content=update.content)
        self.store.save_memory(memory)
        await self.publish(
            RuntimeEvent(
                type="memory.updated",
                entity_id=agent_id,
                agent_id=agent_id,
                summary=f"Updated private memory for {self.agents[agent_id].name}.",
                data={"characters": len(memory.content)},
            )
        )
        return memory

    def get_wiki(self, agent_id: str) -> WikiRecord:
        if agent_id not in self.agents:
            raise KeyError(agent_id)
        return self.store.get_wiki(agent_id)

    def list_wiki_proposals(self, limit: int = 20) -> list[WikiProposalRecord]:
        return [
            WikiProposalRecord(**item)
            for item in self.knowledge_wiki.pending_proposals(limit=limit)
        ]

    def list_wiki_pages(self) -> list[WikiPageRecord]:
        return [WikiPageRecord(**item) for item in self.knowledge_wiki.list_pages()]

    def get_wiki_page(self, name: str) -> WikiPageContent:
        return WikiPageContent(**self.knowledge_wiki.get_page(name))

    def search_wiki(self, query: str, limit: int = 8) -> WikiSearchResult:
        return WikiSearchResult(**self.knowledge_wiki.search(query=query, limit=limit))

    async def run_wiki_maintenance(self) -> WikiMaintenanceResult:
        result = WikiMaintenanceResult(**self.knowledge_wiki.maintain())
        await self.publish(
            RuntimeEvent(
                type="wiki.maintenance.completed",
                entity_id="wiki-maintenance",
                summary=(
                    f"Wiki maintenance scanned {result.pages_scanned} page(s), "
                    f"updated {result.pages_updated}."
                ),
                data=result.model_dump(mode="json"),
            )
        )
        return result

    async def resolve_wiki_proposal(
        self, name: str, status: str, reviewer: str, reason: str
    ) -> WikiProposalRecord:
        resolved = self.knowledge_wiki.resolve_proposal(
            name=name,
            status=status,
            reviewer=reviewer,
            reason=reason,
        )
        content = resolved.read_text(encoding="utf-8")
        await self.publish(
            RuntimeEvent(
                type="wiki.proposal.resolved",
                entity_id=resolved.name,
                summary=f"Wiki proposal {name} marked as {status}.",
                data={
                    "name": name,
                    "status": status,
                    "reviewer": reviewer,
                    "reason": reason,
                    "reviewed_file": resolved.name,
                },
            )
        )
        return WikiProposalRecord(name=resolved.name, content=content)

    async def update_wiki(self, agent_id: str, update: WikiUpdate) -> WikiRecord:
        if agent_id not in self.agents:
            raise KeyError(agent_id)
        wiki = WikiRecord(agent_id=agent_id, content=update.content)
        self.store.save_wiki(wiki)
        await self.publish(
            RuntimeEvent(
                type="wiki.updated",
                entity_id=agent_id,
                agent_id=agent_id,
                summary=f"Updated wiki for {self.agents[agent_id].name}.",
                data={"characters": len(wiki.content)},
            )
        )
        return wiki

    async def create_task(self, task_input: TaskCreate) -> TaskRecord:
        task = TaskRecord(**task_input.model_dump())
        await self._apply_chat_routing(task)
        await self._ensure_chat_strategy(task)
        LOGGER.info(
            "task_created id=%s requested_agent=%s capability=%s",
            task.id,
            task.requested_agent_id or "auto",
            task.capability or "-",
        )
        self.tasks[task.id] = task
        self.store.save_task(task)
        await self.publish(
            RuntimeEvent(
                type="task.created",
                entity_id=task.id,
                task_id=task.id,
                summary=f"New task: {task.title}",
                data={"task": task.model_dump(mode="json")},
            )
        )
        job = asyncio.create_task(self._run_simulated_task(task.id), name=f"runtime-{task.id}")
        self.running_jobs.add(job)
        job.add_done_callback(self.running_jobs.discard)
        return task

    async def _apply_chat_routing(self, task: TaskRecord) -> None:
        if not task.requested_agent_id or task.requested_agent_id not in self.agents:
            return
        current_agent = self.agents[task.requested_agent_id]
        llm_decision = await asyncio.to_thread(
            self.executor.route_chat_with_reasoning,
            task,
            current_agent,
            self.agents,
        )
        fallback_decision = self.router.route_chat(task, self.agents)
        decision = None
        llm_confidence = 0.0
        if isinstance(llm_decision, dict):
            try:
                llm_confidence = max(0.0, min(1.0, float(llm_decision.get("confidence") or 0)))
            except (TypeError, ValueError):
                llm_confidence = 0.0
        if isinstance(llm_decision, dict) and llm_decision.get("should_route"):
            decision = llm_decision
        elif fallback_decision.route_mode == "clarify":
            decision = {
                "should_route": False,
                "target_agent_id": task.requested_agent_id,
                "route_mode": "clarify",
                "reason": fallback_decision.reason,
                "language": fallback_decision.language,
                "clarification_question": fallback_decision.clarification_question,
                "confidence": fallback_decision.confidence,
            }
        elif fallback_decision.should_route and fallback_decision.reason.startswith("Detected routing request"):
            decision = {
                "should_route": True,
                "target_agent_id": fallback_decision.target_agent_id,
                "route_mode": fallback_decision.route_mode,
                "reason": fallback_decision.reason,
                "language": fallback_decision.language,
                "forwarded_message": fallback_decision.forwarded_message,
                "confidence": fallback_decision.confidence,
            }
        elif fallback_decision.should_route and (
            llm_decision is None
            or not llm_decision.get("should_route")
            or llm_confidence < fallback_decision.confidence
        ):
            decision = {
                "should_route": True,
                "target_agent_id": fallback_decision.target_agent_id,
                "route_mode": fallback_decision.route_mode,
                "reason": fallback_decision.reason,
                "language": fallback_decision.language,
                "forwarded_message": fallback_decision.forwarded_message,
                "confidence": fallback_decision.confidence,
            }
        if not decision:
            return
        if str(decision.get("route_mode", "")).strip() == "clarify":
            task.route_mode = "clarify"
            task.route_reason = str(decision.get("reason", "")).strip()
            task.route_language = str(decision.get("language") or self.router.detect_language(task.description or task.title or "")).strip()
            task.clarification_question = str(decision.get("clarification_question", "")).strip()
            return
        source_agent = self.agents.get(task.requested_agent_id)
        target_agent = self.agents.get(str(decision.get("target_agent_id", "")).strip())
        if source_agent is None or target_agent is None:
            return
        original_message = (task.description or task.title or "").strip()
        task.source_agent_id = source_agent.id
        task.route_mode = str(decision.get("route_mode", "route")).strip() or "route"
        task.consult_agent_ids = [target_agent.id] if task.route_mode == "consult" else []
        if task.route_mode == "consult":
            task.consult_agent_ids.extend(
                agent.id for agent in self._select_additional_consult_agents(
                    original_message,
                    source_agent,
                    exclude_ids={target_agent.id},
                )
            )
        task.consult_agent_ids = list(dict.fromkeys(task.consult_agent_ids))
        task.consult_agent_id = task.consult_agent_ids[0] if task.consult_agent_ids else None
        task.requested_agent_id = source_agent.id if task.route_mode == "consult" else target_agent.id
        task.route_reason = str(decision.get("reason", "")).strip()
        task.route_language = str(decision.get("language") or fallback_decision.language or self.router.detect_language(original_message)).strip()
        decision_mode = "llm" if isinstance(llm_decision, dict) and llm_decision.get("should_route") else "fallback"
        forwarded_message = str(decision.get("forwarded_message") or "").strip()
        if not forwarded_message:
            forwarded_message = self.router._forwarded_message(
                original_message,
                source_agent,
                target_agent,
                task.route_language,
                task.route_mode,
            )
        task.description = (
            original_message
            if task.route_mode == "consult"
            else str(forwarded_message or fallback_decision.forwarded_message or original_message).strip()
        )
        if not task.capability and target_agent.capabilities:
            task.capability = target_agent.capabilities[0]

        created_at = utc_now()
        strategy = self._build_task_strategy(
            task,
            source_agent=source_agent,
            primary_target=target_agent,
            decision_mode=decision_mode,
        )
        initial_plan = self._build_delegation_packet(
            task,
            source_agent,
            target_agent,
            consult_index=0,
            total_consults=max(1, len(task.consult_agent_ids) if task.route_mode == "consult" else 1),
        )
        self.store.save_agent_chat_message(
            source_agent.id,
            AgentChatMessage(
                id=f"{task.id}-route-source",
                task_id=task.id,
                role="system",
                content=(
                    f"Routing this conversation to {target_agent.name}.\n"
                    f"Plan: {initial_plan.get('plan_summary', '')}"
                ).strip(),
                created_at=created_at,
            ),
        )
        self.store.save_agent_chat_message(
            target_agent.id,
            AgentChatMessage(
                id=f"{task.id}-route-target",
                task_id=task.id,
                role="system",
                content=(
                    f"Conversation {'consult requested by' if task.route_mode == 'consult' else 'routed from'} {source_agent.name}. "
                    f"Original user message: {original_message}\n"
                    f"Plan: {initial_plan.get('plan_summary', '')}"
                ),
                created_at=created_at,
            ),
        )
        await self.send_message(
            MessageEnvelope(
                type="chat.consult" if task.route_mode == "consult" else "chat.route",
                protocol="conversation-routing",
                sender=source_agent.id,
                recipient=target_agent.id,
                task_id=task.id,
                correlation_id=task.id,
                payload={
                    "title": task.title,
                    "original_message": original_message,
                    "reason": str(decision.get("reason", "")).strip(),
                    "language": str(decision.get("language", "")).strip(),
                    "plan_summary": initial_plan.get("plan_summary", ""),
                },
                priority=max(2, task.priority),
            )
        )
        await self.send_message(
            MessageEnvelope(
                type="chat.plan",
                protocol="conversation-routing",
                sender=source_agent.id,
                recipient=target_agent.id,
                task_id=task.id,
                correlation_id=task.id,
                payload=initial_plan,
                priority=max(2, task.priority),
            )
        )
        await self._append_discussion_entry(
            task,
            sender=source_agent.id,
            recipient=target_agent.id,
            kind="plan",
            content=initial_plan.get("plan_summary", "") or f"Delegation plan sent to {target_agent.name}.",
            extra=initial_plan,
        )
        if task.route_mode != "consult":
            await self.send_message(
                MessageEnvelope(
                    type="chat.accept",
                    protocol="conversation-routing",
                    sender=target_agent.id,
                    recipient=source_agent.id,
                    task_id=task.id,
                    correlation_id=task.id,
                    payload={
                        "title": task.title,
                        "reason": "Conversation accepted by the requested agent.",
                    },
                    priority=max(2, task.priority),
                )
            )
        await self.publish(
            RuntimeEvent(
                type="chat.routed",
                entity_id=task.id,
                task_id=task.id,
                agent_id=target_agent.id,
                summary=f"Conversation routed from {source_agent.name} to {target_agent.name}.",
                data={
                    "task": task.model_dump(mode="json"),
                    "from_agent_id": source_agent.id,
                    "to_agent_id": target_agent.id,
                    "reason": str(decision.get("reason", "")).strip(),
                    "language": str(decision.get("language", "")).strip(),
                    "confidence": float(decision.get("confidence", 0) or 0),
                    "routing_mode": decision_mode,
                    "route_mode": task.route_mode,
                    "strategy": strategy,
                },
            )
        )
        await self._send_strategy_message(
            task=task,
            sender=source_agent.id,
            recipient=target_agent.id,
            strategy=strategy,
            message_type="chat.strategy",
            summary=strategy.get("strategy_summary", "") or f"Execution strategy chosen: {task.route_mode or 'route'}.",
        )
        await self._append_discussion_entry(
            task,
            sender=source_agent.id,
            recipient=target_agent.id,
            kind="strategy",
            content=strategy.get("strategy_summary", "") or f"Execution strategy chosen: {task.route_mode or 'route'}.",
            extra=strategy,
        )

    async def _ensure_chat_strategy(self, task: TaskRecord) -> None:
        if task.channel != "chat":
            return
        if any(str(entry.get("kind") or "").strip() == "strategy" for entry in task.discussion_log):
            return
        agent = self.agents.get(task.requested_agent_id or "")
        if agent is None:
            return
        if task.route_mode == "clarify":
            strategy = self._build_task_strategy(
                task,
                source_agent=agent,
                primary_target=agent,
                decision_mode="clarify",
            )
            await self._send_strategy_message(
                task=task,
                sender=agent.id,
                recipient=agent.id,
                strategy=strategy,
                message_type="chat.strategy",
                summary=strategy.get("strategy_summary", "") or "Clarification required before routing.",
            )
            await self._append_discussion_entry(
                task,
                sender=agent.id,
                recipient=agent.id,
                kind="strategy",
                content=strategy.get("strategy_summary", "") or "Clarification required before routing.",
                extra=strategy,
            )
            return
        if task.route_mode:
            return
        strategy = self._build_task_strategy(
            task,
            source_agent=agent,
            primary_target=agent,
            decision_mode="stay",
        )
        await self._send_strategy_message(
            task=task,
            sender=agent.id,
            recipient=agent.id,
            strategy=strategy,
            message_type="chat.strategy",
            summary=strategy.get("strategy_summary", "") or f"{agent.name} will handle this conversation directly.",
        )
        await self._append_discussion_entry(
            task,
            sender=agent.id,
            recipient=agent.id,
            kind="strategy",
            content=strategy.get("strategy_summary", "") or f"{agent.name} will handle this conversation directly.",
            extra=strategy,
        )

    def _build_task_strategy(
        self,
        task: TaskRecord,
        source_agent: AgentSnapshot,
        primary_target: AgentSnapshot,
        decision_mode: str,
    ) -> dict[str, Any]:
        route_mode = str(task.route_mode or "stay").strip() or "stay"
        consulted_ids = list(task.consult_agent_ids or ([task.consult_agent_id] if task.consult_agent_id else []))
        consulted_ids = [agent_id for agent_id in consulted_ids if agent_id]
        steps: list[str]
        user_facing_agent_id = source_agent.id
        execution_agent_id = primary_target.id
        if route_mode == "consult":
            consulted_names = ", ".join(
                self.agents.get(agent_id).name if self.agents.get(agent_id) else agent_id
                for agent_id in consulted_ids
            )
            strategy_summary = (
                f"{source_agent.name} stays user-facing, consults {consulted_names or primary_target.name}, "
                "then synthesizes one final reply."
            )
            steps = [
                f"{source_agent.name} keeps the user conversation.",
                f"Consult specialists in order: {consulted_names or primary_target.name}.",
                "Run a bounded council step only if the task needs reconciliation across specialists.",
                f"{source_agent.name} synthesizes one final user-facing answer.",
            ]
        elif route_mode == "route":
            user_facing_agent_id = primary_target.id
            strategy_summary = f"Transfer the conversation from {source_agent.name} to {primary_target.name} for direct handling."
            steps = [
                f"Route the conversation from {source_agent.name} to {primary_target.name}.",
                f"{primary_target.name} answers the user directly.",
            ]
        elif route_mode == "clarify":
            strategy_summary = (
                f"Pause delegation and ask the user to clarify the target agent before continuing."
            )
            steps = [
                "Do not route yet.",
                "Ask exactly one clarification question.",
                "Resume routing only after the user disambiguates the target.",
            ]
        else:
            strategy_summary = f"{source_agent.name} handles the conversation directly without delegation."
            steps = [
                f"{source_agent.name} keeps the conversation.",
                f"{source_agent.name} answers directly unless new routing evidence appears.",
            ]
        return {
            "title": task.title,
            "route_mode": route_mode,
            "decision_mode": str(decision_mode or "heuristic").strip(),
            "reason": task.route_reason or "",
            "language": task.route_language or "",
            "user_goal": (task.description or task.title or "").strip(),
            "source_agent_id": source_agent.id,
            "user_facing_agent_id": user_facing_agent_id,
            "execution_agent_id": execution_agent_id,
            "primary_target_agent_id": primary_target.id,
            "consult_agent_ids": consulted_ids,
            "clarification_question": task.clarification_question or "",
            "strategy_summary": strategy_summary,
            "steps": steps,
        }

    async def _append_strategy_update(
        self,
        task: TaskRecord,
        sender: str,
        recipient: str,
        summary: str,
        *,
        phase: str,
        updates: Optional[dict[str, Any]] = None,
    ) -> None:
        latest_strategy = next(
            (
                entry for entry in reversed(task.discussion_log)
                if str(entry.get("kind") or "").strip() in {"strategy", "strategy-update"}
            ),
            None,
        )
        previous_extra = latest_strategy.get("extra", {}) if isinstance(latest_strategy, dict) else {}
        merged_extra = dict(previous_extra if isinstance(previous_extra, dict) else {})
        merged_extra.update(dict(updates or {}))
        merged_extra["phase"] = str(phase or "").strip()
        await self._send_strategy_message(
            task=task,
            sender=sender,
            recipient=recipient,
            strategy=merged_extra,
            message_type="chat.strategy-update",
            summary=str(summary or "").strip(),
        )
        await self._append_discussion_entry(
            task,
            sender=sender,
            recipient=recipient,
            kind="strategy-update",
            content=str(summary or "").strip(),
            extra=merged_extra,
        )

    async def _send_strategy_message(
        self,
        *,
        task: TaskRecord,
        sender: str,
        recipient: str,
        strategy: dict[str, Any],
        message_type: str,
        summary: str,
    ) -> None:
        await self.send_message(
            MessageEnvelope(
                type=message_type,
                protocol="conversation-routing",
                sender=sender,
                recipient=recipient,
                task_id=task.id,
                correlation_id=task.id,
                payload={
                    **dict(strategy or {}),
                    "summary": str(summary or "").strip(),
                },
                priority=max(2, task.priority),
            )
        )

    async def _pause(self, seconds: float) -> None:
        await asyncio.sleep(seconds * self.simulation_delay)

    def choose_agent(self, task: TaskRecord) -> Optional[AgentSnapshot]:
        if task.requested_agent_id:
            return self.agents.get(task.requested_agent_id)
        candidates = [agent for agent in self.agents.values() if agent.role != "supervisor"]
        available = [agent for agent in candidates if agent.active_task_id is None]
        if available:
            candidates = available
        if task.capability:
            candidates = [agent for agent in candidates if task.capability in agent.capabilities]
        if not candidates:
            candidates = [agent for agent in self.agents.values() if agent.role != "supervisor"]
        if not candidates:
            candidates = list(self.agents.values())
        return min(candidates, key=lambda agent: (agent.load, agent.name)) if candidates else None

    async def _run_simulated_task(self, task_id: str) -> None:
        task = self.tasks[task_id]
        supervisor = next((agent for agent in self.agents.values() if agent.role == "supervisor"), None)
        try:
            await self._transition_task(task, TaskState.ANNOUNCED)
            agent = self.choose_agent(task)
            if agent is None:
                raise RuntimeError("No agent is available")

            agent.active_task_id = task.id
            agent.load = max(agent.load, 0.15)
            self.store.save_agent(agent)

            sender = supervisor.id if supervisor else "runtime"
            await self.send_message(
                MessageEnvelope(
                    type="task.announce",
                    protocol="task-contract",
                    sender=sender,
                    recipient=agent.id,
                    task_id=task.id,
                    correlation_id=task.id,
                    payload={"title": task.title, "capability": task.capability},
                    priority=task.priority,
                )
            )
            await self._pause(0.45)
            task.assigned_agent_id = agent.id
            await self._transition_task(task, TaskState.AWARDED, agent)
            await self._set_agent_state(agent, AgentState.RECEIVING, task)
            await self.send_message(
                MessageEnvelope(
                    type="task.award",
                    protocol="task-contract",
                    sender=sender,
                    recipient=agent.id,
                    task_id=task.id,
                    correlation_id=task.id,
                    payload={"title": task.title},
                    priority=task.priority,
                )
            )

            await self._pause(0.5)
            await self._transition_task(task, TaskState.ACCEPTED, agent)
            await self._set_agent_state(agent, AgentState.PLANNING, task, load=0.35)
            await self._pause(0.8)
            await self._transition_task(task, TaskState.RUNNING, agent)
            await self._set_agent_state(agent, AgentState.EXECUTING, task, load=0.7)

            for progress in (25, 55, 80):
                await self._pause(0.75)
                await self.send_message(
                    MessageEnvelope(
                        type="task.progress",
                        protocol="task-contract",
                        sender=agent.id,
                        recipient=sender,
                        task_id=task.id,
                        correlation_id=task.id,
                        payload={"progress": progress},
                        priority=task.priority,
                    )
                )

            consulted_result = await self._run_chat_consultation(task, agent, sender=sender)
            memory_briefing = await self._memory_core_briefing(agent, task, sender=sender)
            if task.channel == "chat" and task.route_mode == "clarify" and task.clarification_question:
                task.result = {
                    "summary": task.clarification_question,
                    "details": "Routing clarification requested before delegation.",
                    "provider": "runtime-clarifier",
                    "model": "routing-clarifier",
                    "tool_calls": 0,
                    "sources": [],
                }
            else:
                if task.channel == "chat" and task.route_mode == "consult" and consulted_result:
                    await self._append_strategy_update(
                        task,
                        sender=agent.id,
                        recipient=task.source_agent_id or agent.id,
                        summary=(
                            f"{agent.name} is moving from specialist consultation to final synthesis."
                        ),
                        phase="synthesis",
                        updates={
                            "current_stage": "synthesis",
                            "consulted_agents": self._consulted_agent_names(task),
                        },
                    )
                    await self._append_discussion_entry(
                        task,
                        sender=agent.id,
                        recipient=task.source_agent_id or agent.id,
                        kind="synthesis",
                        content=(
                            f"{agent.name} is synthesizing specialist input from "
                            f"{', '.join(self._consulted_agent_names(task))} into one user-facing answer."
                        ),
                        extra={"consulted_agents": self._consulted_agent_names(task)},
                    )
                task.result = await asyncio.wait_for(
                    self.executor.run(agent, task, self.publish, memory_briefing=memory_briefing),
                    timeout=agent.limits.timeout_seconds,
                )
                if task.channel == "chat" and task.route_mode == "consult" and consulted_result:
                    merged_sources = self._merge_consultation_sources(task, task.result, consulted_result)
                    consulted_agents = self._consulted_agent_names(task)
                    if agent.model.provider == "simulated":
                        task.result = {
                            "summary": self._synthesize_consultation_summary(task, consulted_result),
                            "details": f"Consultation synthesized via {', '.join(consulted_agents)}.",
                            "provider": agent.model.provider,
                            "model": agent.model.model,
                            "tool_calls": 0,
                            "sources": merged_sources,
                            "consulted_agents": consulted_agents,
                        }
                    else:
                        existing_details = str(task.result.get("details") or "").strip()
                        consultation_details = f"Consultation synthesized via {', '.join(consulted_agents)}."
                        task.result["details"] = (
                            f"{existing_details}\n\n{consultation_details}".strip()
                            if existing_details
                            else consultation_details
                        )
                        task.result["sources"] = merged_sources
                        task.result["consulted_agents"] = consulted_agents
                    await self._append_discussion_entry(
                        task,
                        sender=agent.id,
                        recipient=task.source_agent_id or agent.id,
                        kind="synthesis-result",
                        content=str(task.result.get("summary") or "").strip() or "Final synthesis ready.",
                        sources=task.result.get("sources") if isinstance(task.result.get("sources"), list) else [],
                        extra={"consulted_agents": consulted_agents},
                    )
            await self._transition_task(task, TaskState.VERIFYING, agent)
            await self._set_agent_state(agent, AgentState.VERIFYING, task, load=0.45)
            await self._pause(0.8)
            await self.send_message(
                MessageEnvelope(
                    type="task.result",
                    protocol="task-contract",
                    sender=agent.id,
                    recipient=sender,
                    task_id=task.id,
                    correlation_id=task.id,
                    payload=task.result,
                    priority=task.priority,
                )
            )
            await self._complete_chat_handoff(task, agent)
            await self._transition_task(task, TaskState.COMPLETED, agent)
            await self._set_agent_state(agent, AgentState.IDLE, None, load=0.08)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            LOGGER.exception("task_failed id=%s error=%s", task.id, error)
            task.error = str(error)
            if task.state not in {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}:
                await self._transition_task(task, TaskState.FAILED)
            if task.assigned_agent_id and task.assigned_agent_id in self.agents:
                await self._set_agent_state(
                    self.agents[task.assigned_agent_id], AgentState.FAILED, task, load=0.1
                )

    async def _memory_core_briefing(
        self,
        agent: AgentSnapshot,
        task: TaskRecord,
        sender: str,
        query_override: str = "",
    ) -> str:
        memory_agent = self.agents.get("memory")
        if memory_agent is None or agent.id == memory_agent.id:
            return ""
        query = str(query_override or "").strip() or "\n".join(
            part for part in (
                task.title,
                task.description,
                agent.role,
                " ".join(agent.capabilities),
            )
            if str(part or "").strip()
        ).strip()
        if not query:
            return ""
        matches = self.knowledge_wiki.retrieve(query, limit=4, max_characters=10_000)
        if not matches:
            return ""
        briefing = "\n\n".join(f"## {name}\n{content}" for name, content in matches)
        await self.send_message(
            MessageEnvelope(
                type="memory.recall",
                protocol="memory-learning",
                sender=memory_agent.id,
                recipient=agent.id,
                task_id=task.id,
                correlation_id=task.id,
                payload={
                    "query": query,
                    "matches": [{"name": name, "content": content} for name, content in matches],
                },
                priority=max(1, min(task.priority, 5)),
            )
        )
        await self.publish(
            RuntimeEvent(
                type="memory.recall.delivered",
                entity_id=task.id,
                agent_id=agent.id,
                task_id=task.id,
                summary=f"Memory Core sent recall to {agent.name}.",
                data={
                    "sender": memory_agent.id,
                    "recipient": agent.id,
                    "query": query,
                    "matches": len(matches),
                },
            )
        )
        await self._append_discussion_entry(
            task,
            sender=memory_agent.id,
            recipient=agent.id,
            kind="memory",
            content=f"Memory recall sent with {len(matches)} relevant knowledge match(es) for this task.",
            extra={"query": query, "matches": len(matches)},
        )
        return briefing

    async def _append_discussion_entry(
        self,
        task: TaskRecord,
        sender: str,
        recipient: str,
        kind: str,
        content: str,
        sources: Optional[list[dict[str, str]]] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        entry = {
            "id": f"{task.id}-thread-{uuid4().hex[:10]}",
            "task_id": task.id,
            "sender": sender,
            "recipient": recipient,
            "kind": kind,
            "content": str(content or "").strip(),
            "sources": list(sources or []),
            "created_at": utc_now().isoformat(),
            "extra": dict(extra or {}),
        }
        if not entry["content"]:
            return
        task.discussion_log = [*task.discussion_log, entry][-120:]
        self.store.save_task(task)
        await self.publish(
            RuntimeEvent(
                type="chat.thread.updated",
                entity_id=task.id,
                task_id=task.id,
                agent_id=sender,
                summary=f"{sender} updated the internal discussion thread.",
                data={"task": task.model_dump(mode="json"), "entry": entry},
            )
        )

    @staticmethod
    def _peer_request_target_label(
        target_kind: str,
        target_agent: Optional[AgentSnapshot] = None,
    ) -> str:
        normalized = str(target_kind or "specialist").strip()
        if normalized == "memory":
            return "Memory Core"
        if normalized == "council":
            return "Council"
        if target_agent is not None:
            return target_agent.name
        return "another specialist"

    def _peer_request_default_content(
        self,
        requester: AgentSnapshot,
        target_kind: str,
        target_agent: Optional[AgentSnapshot] = None,
    ) -> str:
        normalized = str(target_kind or "specialist").strip()
        if normalized == "memory":
            return f"{requester.name} requested Memory Core context before synthesis."
        if normalized == "council":
            return f"{requester.name} requested a council step before synthesis."
        target_label = self._peer_request_target_label(normalized, target_agent)
        return f"{requester.name} requested {target_label} before synthesis."

    @staticmethod
    def _reasoning_excerpt(text: str, *, limit: int = 220) -> str:
        normalized = " ".join(str(text or "").split()).strip()
        if len(normalized) <= limit:
            return normalized
        return normalized[: max(0, limit - 1)].rstrip() + "…"

    def _build_reasoning_snapshot(
        self,
        *,
        focus: str,
        summary: str,
        sources: list[dict[str, str]],
        reasoning_type: str,
        reacting_to: str = "",
    ) -> dict[str, str]:
        focus_text = self._reasoning_excerpt(focus, limit=160)
        conclusion = self._reasoning_excerpt(summary, limit=220)
        lowered = str(summary or "").lower()
        concern = ""
        for marker in ("however", "but", "risk", "uncertain", "unknown", "missing", "conflict"):
            if marker in lowered:
                concern = f"Potential concern mentioned around: {marker}."
                break
        if not concern and not sources:
            concern = "No supporting sources were attached yet."
        next_step = "Ready for source-agent synthesis."
        if reasoning_type == "council":
            next_step = "Use this council note to refine the final synthesis."
        elif not sources:
            next_step = "Consider another verification or memory lookup before synthesis."
        return {
            "focus": focus_text or "Specialist task context",
            "conclusion": conclusion or "No specialist conclusion was returned.",
            "concern": concern,
            "next_step": next_step,
            "reasoning_type": reasoning_type,
            "reacting_to": reacting_to.strip(),
        }

    async def _emit_reasoning_note(
        self,
        task: TaskRecord,
        *,
        sender: AgentSnapshot,
        recipient: AgentSnapshot,
        focus: str,
        summary: str,
        sources: list[dict[str, str]],
        reasoning_type: str,
        reacting_to: str = "",
    ) -> None:
        reasoning = self._build_reasoning_snapshot(
            focus=focus,
            summary=summary,
            sources=sources,
            reasoning_type=reasoning_type,
            reacting_to=reacting_to,
        )
        await self.send_message(
            MessageEnvelope(
                type="chat.reasoning",
                protocol="conversation-routing",
                sender=sender.id,
                recipient=recipient.id,
                task_id=task.id,
                correlation_id=task.id,
                payload={
                    "title": task.title,
                    **reasoning,
                },
                priority=max(2, task.priority),
            )
        )
        await self._append_discussion_entry(
            task,
            sender=sender.id,
            recipient=recipient.id,
            kind="reasoning",
            content=reasoning["conclusion"],
            sources=sources,
            extra=reasoning,
        )

    async def _emit_specialist_peer_request(
        self,
        task: TaskRecord,
        source_agent: AgentSnapshot,
        requester: AgentSnapshot,
        peer_request: dict[str, Any],
        pending_peer_requests: list[dict[str, Any]],
    ) -> None:
        target_kind = str(peer_request.get("target_kind") or "specialist").strip()
        target_agent_id = str(peer_request.get("target_agent_id") or "").strip()
        target_agent = self.agents.get(target_agent_id)
        if target_kind == "specialist" and target_agent is None:
            return
        target_label = self._peer_request_target_label(target_kind, target_agent)
        reason = str(peer_request.get("reason") or "").strip()
        decision_mode = str(peer_request.get("decision_mode") or "heuristic").strip()
        await self.send_message(
            MessageEnvelope(
                type="chat.peer-request",
                protocol="conversation-routing",
                sender=requester.id,
                recipient=source_agent.id,
                task_id=task.id,
                correlation_id=task.id,
                payload={
                    "title": task.title,
                    "target_kind": target_kind,
                    "target_specialist": target_label,
                    "target_label": target_label,
                    "target_agent_id": "memory" if target_kind == "memory" else (target_agent.id if target_agent else ""),
                    "reason": reason,
                    "decision_mode": decision_mode,
                    "requested_by_agent_id": requester.id,
                    "requested_by_agent_name": requester.name,
                },
                priority=max(2, task.priority),
            )
        )
        await self._append_discussion_entry(
            task,
            sender=requester.id,
            recipient=source_agent.id,
            kind="peer-request",
            content=(reason or self._peer_request_default_content(requester, target_kind, target_agent)),
            extra={
                "target_kind": target_kind,
                "target_agent_id": "memory" if target_kind == "memory" else (target_agent.id if target_agent else ""),
                "target_label": target_label,
                "decision_mode": decision_mode,
                "requested_by_agent_id": requester.id,
            },
        )
        pending_peer_requests.append(
            {
                "target_kind": target_kind,
                "target_agent_id": "memory" if target_kind == "memory" else (target_agent.id if target_agent else ""),
                "target_label": target_label,
                "reason": reason,
                "decision_mode": decision_mode,
                "sender_agent_id": requester.id,
            }
        )

    @staticmethod
    def _synthesize_consultation_summary(task: TaskRecord, consulted_result: dict[str, Any]) -> str:
        notes = str(task.consultation_notes or "").strip()
        if not notes:
            return str(consulted_result.get("summary") or "").strip() or "Consultation completed."
        specialist_lines = []
        current_name = ""
        current_summary = ""
        for line in notes.splitlines():
            stripped = line.strip()
            if stripped.startswith("Consulted specialist: "):
                if current_name and current_summary:
                    specialist_lines.append(f"- {current_name}: {current_summary}")
                current_name = stripped.removeprefix("Consulted specialist: ").split(" (", 1)[0].strip()
                current_summary = ""
            elif stripped.startswith("Specialist summary: "):
                current_summary = stripped.removeprefix("Specialist summary: ").strip()
        if current_name and current_summary:
            specialist_lines.append(f"- {current_name}: {current_summary}")
        if not specialist_lines:
            return str(consulted_result.get("summary") or "").strip() or "Consultation completed."
        return "I consulted the relevant specialists.\n" + "\n".join(specialist_lines)

    @staticmethod
    def _merge_consultation_sources(
        task: TaskRecord,
        primary_result: Optional[dict[str, Any]],
        consulted_result: dict[str, Any],
    ) -> list[dict[str, str]]:
        merged: dict[str, dict[str, str]] = {}
        notes = str(task.consultation_notes or "").strip()
        for line in notes.splitlines():
            stripped = line.strip()
            if not stripped.startswith("Specialist sources: "):
                continue
            raw_sources = stripped.removeprefix("Specialist sources: ").strip()
            for candidate in raw_sources.split(","):
                url = candidate.strip()
                if url:
                    merged[url] = {"url": url, "title": url}
        for item in (primary_result or {}).get("sources") or []:
            if isinstance(item, dict):
                url = str(item.get("url", "") or "").strip()
                if url:
                    merged[url] = {"url": url, "title": str(item.get("title") or url)}
        for item in consulted_result.get("sources") or []:
            if isinstance(item, dict):
                url = str(item.get("url", "") or "").strip()
                if url:
                    merged[url] = {"url": url, "title": str(item.get("title") or url)}
        return list(merged.values())

    def _consulted_agent_names(self, task: TaskRecord) -> list[str]:
        names: list[str] = []
        for agent_id in task.consult_agent_ids or ([task.consult_agent_id] if task.consult_agent_id else []):
            agent = self.agents.get(agent_id)
            names.append(agent.name if agent else agent_id)
        return names

    async def _consult_followup_decision(
        self,
        task: TaskRecord,
        source_agent: AgentSnapshot,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
    ) -> dict[str, Any]:
        request = (task.description or task.title or "").strip().lower()
        consulted_ids = {agent.id for agent, _summary, _sources in consulted_rounds}
        llm_decision = await asyncio.to_thread(
            self.executor.decide_consult_followup_with_reasoning,
            task,
            source_agent,
            consulted_rounds,
            self.agents,
        )
        if isinstance(llm_decision, dict) and str(llm_decision.get("action") or "").strip() in {"synthesize", "memory", "consult"}:
            target_agent_id = str(llm_decision.get("target_agent_id") or "").strip()
            if llm_decision.get("action") != "consult" or (target_agent_id and target_agent_id not in consulted_ids and target_agent_id in self.agents):
                return llm_decision
        extra_candidates = self._select_additional_consult_agents(
            task.description or task.title or "",
            source_agent,
            exclude_ids=consulted_ids,
        )
        if len(consulted_rounds) < 3 and extra_candidates:
            if any(keyword in request for keyword in ("plan", "planning", "organizza", "implement", "implementation", "review", "risk", "critic", "compare", "tradeoff", "trade-off")):
                return {
                    "action": "consult",
                    "reason": f"One more specialist should contribute before synthesis: {extra_candidates[0].name}.",
                    "target_agent_id": extra_candidates[0].id,
                    "decision_mode": "heuristic",
                }
            if any(len(str(summary or "").strip()) < 140 for _agent, summary, _sources in consulted_rounds):
                return {
                    "action": "consult",
                    "reason": f"The current specialist output is still thin; add {extra_candidates[0].name} before synthesis.",
                    "target_agent_id": extra_candidates[0].id,
                    "decision_mode": "heuristic",
                }
        if any(keyword in request for keyword in ("memory", "context", "remember", "wiki", "history", "prior")):
            return {
                "action": "memory",
                "reason": "Memory Core context could improve the final synthesis.",
                "target_agent_id": "",
                "decision_mode": "heuristic",
            }
        return {
            "action": "synthesize",
            "reason": "The source agent can proceed to synthesis with the current specialist context.",
            "target_agent_id": "",
            "decision_mode": "heuristic",
        }

    async def _specialist_peer_request_decision(
        self,
        task: TaskRecord,
        source_agent: AgentSnapshot,
        specialist_agent: AgentSnapshot,
        specialist_summary: str,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
    ) -> Optional[dict[str, Any]]:
        llm_decision = await asyncio.to_thread(
            self.executor.decide_peer_escalation_with_reasoning,
            task,
            specialist_agent,
            specialist_summary,
            consulted_rounds,
            self.agents,
            source_agent,
        )
        if isinstance(llm_decision, dict) and str(llm_decision.get("action") or "").strip() == "request":
            target_kind = str(llm_decision.get("target_kind") or "specialist").strip()
            target_agent_id = str(llm_decision.get("target_agent_id") or "").strip()
            known_ids = {agent.id for agent, _summary, _sources in consulted_rounds}
            if target_kind in {"memory", "council"}:
                return llm_decision
            if target_agent_id and target_agent_id not in known_ids and target_agent_id in self.agents:
                return llm_decision
        request = (task.description or task.title or "").strip().lower()
        known_ids = {agent.id for agent, _summary, _sources in consulted_rounds}
        if ("research" in set(specialist_agent.capabilities or []) or specialist_agent.id == "researcher"):
            if any(keyword in request for keyword in ("context", "history", "memory", "wiki", "prior")):
                return {
                    "action": "request",
                    "reason": "Research needs deeper project context from Memory Core before synthesis.",
                    "target_kind": "memory",
                    "target_agent_id": "memory" if "memory" in self.agents else "",
                    "decision_mode": "heuristic",
                }
            if any(keyword in request for keyword in ("plan", "planning", "organizza", "steps", "roadmap")) and "planner" in self.agents and "planner" not in known_ids:
                return {
                    "action": "request",
                    "reason": "Research is done; a planner should turn the findings into steps.",
                    "target_kind": "specialist",
                    "target_agent_id": "planner",
                    "decision_mode": "heuristic",
                }
            if any(keyword in request for keyword in ("implement", "implementation", "code", "build", "modifica")) and "builder" in self.agents and "builder" not in known_ids:
                return {
                    "action": "request",
                    "reason": "Research is done; a builder should turn the findings into implementation details.",
                    "target_kind": "specialist",
                    "target_agent_id": "builder",
                    "decision_mode": "heuristic",
                }
        if ("planning" in set(specialist_agent.capabilities or []) or specialist_agent.id == "planner"):
            if any(keyword in request for keyword in ("implement", "implementation", "code", "build", "modifica")) and "builder" in self.agents and "builder" not in known_ids:
                return {
                    "action": "request",
                    "reason": "The plan is ready; a builder should detail implementation next.",
                    "target_kind": "specialist",
                    "target_agent_id": "builder",
                    "decision_mode": "heuristic",
                }
        if ("implementation" in set(specialist_agent.capabilities or []) or specialist_agent.id == "builder"):
            if any(keyword in request for keyword in ("review", "risk", "critic", "tradeoff", "trade-off")) and "critic" in self.agents and "critic" not in known_ids:
                return {
                    "action": "request",
                    "reason": "Implementation needs a critic review before synthesis.",
                    "target_kind": "specialist",
                    "target_agent_id": "critic",
                    "decision_mode": "heuristic",
                }
            if any(keyword in request for keyword in ("review", "risk", "tradeoff", "trade-off", "compare", "conflict")):
                return {
                    "action": "request",
                    "reason": "Implementation should go through a council step before synthesis.",
                    "target_kind": "council",
                    "target_agent_id": "",
                    "decision_mode": "heuristic",
                }
        return None

    @staticmethod
    def _memory_followup_query(
        task: TaskRecord,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
    ) -> str:
        specialist_summaries = "\n".join(
            f"{agent.name}: {str(summary or '').strip()}"
            for agent, summary, _sources in consulted_rounds[:3]
            if str(summary or "").strip()
        )
        return "\n".join(
            part for part in (
                task.title,
                task.description,
                "Need additional project memory and prior context for final synthesis.",
                specialist_summaries,
            )
            if str(part or "").strip()
        ).strip()

    def _select_additional_consult_agents(
        self,
        user_message: str,
        source_agent: AgentSnapshot,
        exclude_ids: set[str],
    ) -> list[AgentSnapshot]:
        normalized = self.router.normalize_text(user_message)
        candidates: list[tuple[int, AgentSnapshot]] = []
        for agent in self.agents.values():
            if (
                agent.id == source_agent.id
                or agent.id in exclude_ids
                or agent.role == "supervisor"
            ):
                continue
            score = self.router._capability_score(normalized, agent)
            if score < 2:
                continue
            candidates.append((score, agent))
        candidates.sort(key=lambda item: (-item[0], item[1].load, item[1].name))
        selected: list[AgentSnapshot] = []
        covered_capabilities: set[str] = set()
        for score, agent in candidates:
            capabilities = set(agent.capabilities or [])
            if capabilities and capabilities.issubset(covered_capabilities):
                continue
            selected.append(agent)
            covered_capabilities.update(capabilities)
            if len(selected) >= 2:
                break
        return selected

    @staticmethod
    def _specialist_expected_output(target_agent: AgentSnapshot) -> str:
        capabilities = ", ".join(target_agent.capabilities[:3]) if target_agent.capabilities else target_agent.role
        return f"Provide a concise specialist answer focused on {capabilities}."

    def _specialist_question(
        self,
        task: TaskRecord,
        source_agent: AgentSnapshot,
        target_agent: AgentSnapshot,
    ) -> str:
        request = (task.description or task.title or "").strip()
        if target_agent.id == "researcher" or "research" in (target_agent.capabilities or []):
            return f"Research the user request, gather reliable context, and return the most relevant findings for: {request}"
        if target_agent.id == "planner" or "planning" in (target_agent.capabilities or []):
            return f"Break this request into the next actionable steps and identify dependencies: {request}"
        if target_agent.id == "builder" or "implementation" in (target_agent.capabilities or []):
            return f"Explain the concrete implementation approach for this request and likely code changes: {request}"
        if target_agent.id == "critic" or "review" in (target_agent.capabilities or []):
            return f"Review this request for risks, edge cases, and verification needs: {request}"
        if target_agent.id == "memory" or "memory" in (target_agent.capabilities or []):
            return f"Recover the most relevant prior context and durable knowledge for: {request}"
        return (
            f"{source_agent.name} needs your specialist input. "
            f"Answer the part of this request that best matches your role ({target_agent.role}): {request}"
        )

    def _build_delegation_packet(
        self,
        task: TaskRecord,
        source_agent: AgentSnapshot,
        target_agent: AgentSnapshot,
        consult_index: int,
        total_consults: int,
    ) -> dict[str, Any]:
        user_goal = (task.description or task.title or "").strip()
        specialist_question = self._specialist_question(task, source_agent, target_agent)
        expected_output = self._specialist_expected_output(target_agent)
        synthesis_goal = "Return your answer to the source agent so they can synthesize one final user-facing reply."
        consult_position = (
            f"{consult_index + 1}/{total_consults}"
            if total_consults > 1
            else "1/1"
        )
        plan_summary = (
            f"{source_agent.name} -> {target_agent.name}: "
            f"{specialist_question[:180].rstrip()}"
            + ("…" if len(specialist_question) > 180 else "")
        )
        return {
            "title": task.title,
            "route_mode": task.route_mode or "route",
            "user_goal": user_goal,
            "reason": task.route_reason or "",
            "specialist_question": specialist_question,
            "expected_output": expected_output,
            "synthesis_goal": synthesis_goal,
            "consult_position": consult_position,
            "plan_summary": plan_summary,
        }

    @staticmethod
    def _should_request_specialist_followup(
        consulted_agent: AgentSnapshot,
        summary: str,
        sources: list[dict[str, str]],
    ) -> bool:
        normalized_summary = str(summary or "").strip()
        if len(normalized_summary) < 80:
            return True
        capability_set = set(consulted_agent.capabilities or [])
        if ("research" in capability_set or consulted_agent.id == "researcher") and not sources:
            return True
        if ("planning" in capability_set or consulted_agent.id == "planner") and normalized_summary.count("\n") < 1:
            return True
        return False

    @staticmethod
    def _followup_question(
        consulted_agent: AgentSnapshot,
        delegation_packet: dict[str, Any],
        summary: str,
        sources: list[dict[str, str]],
    ) -> str:
        if ("research" in set(consulted_agent.capabilities or []) or consulted_agent.id == "researcher") and not sources:
            return "Please add grounded evidence or sources and make the findings more concrete."
        if len(str(summary or "").strip()) < 80:
            return "Please expand this answer with more concrete detail, not just a brief acknowledgement."
        if "planning" in set(consulted_agent.capabilities or []) or consulted_agent.id == "planner":
            return "Please structure the answer into explicit steps and dependencies."
        return (
            f"Please revise your answer so it better satisfies the expected output: "
            f"{delegation_packet.get('expected_output', '').strip()}"
        ).strip()

    @staticmethod
    def _build_council_prompt(
        task: TaskRecord,
        speaker: AgentSnapshot,
        listener: AgentSnapshot,
        speaker_summary: str,
        listener_summary: str,
    ) -> str:
        request = (task.description or task.title or "").strip()
        return (
            f"You are {speaker.name}. Another specialist, {listener.name}, produced this summary:\n"
            f"{listener_summary}\n\n"
            f"Your own current summary is:\n{speaker_summary}\n\n"
            f"User request:\n{request}\n\n"
            "Return one short council note that refines, challenges, or extends the other specialist's reasoning."
        ).strip()

    @staticmethod
    def _council_policy_decision(
        task: TaskRecord,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
    ) -> dict[str, Any]:
        participants = consulted_rounds[:3]
        if len(participants) < 2:
            return {
                "enabled": False,
                "reason": "Council skipped because fewer than two specialist rounds were available.",
                "participant_ids": [agent.id for agent, _summary, _sources in participants],
                "max_turns": 0,
                "decision_mode": "heuristic",
            }
        request = (task.description or task.title or "").strip().lower()
        if any(keyword in request for keyword in ("compare", "conflict", "tradeoff", "trade-off", "decide", "choose", "organizza", "implementa", "review", "risk", "vs ")):
            return {
                "enabled": True,
                "reason": "Council enabled because the task mixes multiple specialist perspectives or explicit tradeoffs.",
                "participant_ids": [agent.id for agent, _summary, _sources in participants],
                "max_turns": min(2, len(participants) - 1),
                "decision_mode": "heuristic",
            }
        if len(task.consult_agent_ids) >= 3:
            return {
                "enabled": True,
                "reason": "Council enabled because three or more specialists were consulted.",
                "participant_ids": [agent.id for agent, _summary, _sources in participants],
                "max_turns": min(2, len(participants) - 1),
                "decision_mode": "heuristic",
            }
        summary_lengths = [len(str(summary or "").strip()) for _agent, summary, _sources in participants]
        if summary_lengths and max(summary_lengths) - min(summary_lengths) >= 120:
            return {
                "enabled": True,
                "reason": "Council enabled because specialist summaries had uneven depth and may need reconciliation.",
                "participant_ids": [agent.id for agent, _summary, _sources in participants],
                "max_turns": 1,
                "decision_mode": "heuristic",
            }
        return {
            "enabled": False,
            "reason": "Council skipped because the specialist outputs looked straightforward enough for direct synthesis.",
            "participant_ids": [agent.id for agent, _summary, _sources in participants],
            "max_turns": 0,
            "decision_mode": "heuristic",
        }

    async def _run_council_phase(
        self,
        task: TaskRecord,
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
        source_agent: AgentSnapshot,
    ) -> None:
        participants = consulted_rounds[:3]
        llm_policy = await asyncio.to_thread(
            self.executor.decide_council_policy_with_reasoning,
            task,
            source_agent,
            consulted_rounds,
            self.agents,
        )
        policy = llm_policy if isinstance(llm_policy, dict) else self._council_policy_decision(task, consulted_rounds)
        enabled = bool(policy.get("enabled"))
        reason = str(policy.get("reason") or "").strip()
        max_turns = max(0, int(policy.get("max_turns") or 0))
        participant_map = {agent.id: (agent, summary, sources) for agent, summary, sources in participants}
        requested_ids = [str(agent_id).strip() for agent_id in (policy.get("participant_ids") or []) if str(agent_id).strip()]
        participant_ids = [agent_id for agent_id in requested_ids if agent_id in participant_map] or [agent.id for agent, _summary, _sources in participants]
        selected_participants = [participant_map[agent_id] for agent_id in participant_ids if agent_id in participant_map]
        await self._append_discussion_entry(
            task,
            sender=source_agent.id,
            recipient=source_agent.id,
            kind="council-policy",
            content=reason,
            extra={
                "enabled": enabled,
                "participants": participant_ids,
                "max_turns": max_turns,
                "decision_mode": str(policy.get("decision_mode") or "heuristic"),
            },
        )
        await self._append_strategy_update(
            task,
            sender=source_agent.id,
            recipient=source_agent.id,
            summary=(
                reason
                if enabled
                else "Council was skipped and the source agent will continue directly to synthesis."
            ),
            phase="council" if enabled else "post-consult",
            updates={
                "current_stage": "council" if enabled else "post-consult",
                "council_enabled": enabled,
                "council_participants": participant_ids,
                "council_turn_budget": max_turns,
                "council_decision_mode": str(policy.get("decision_mode") or "heuristic"),
            },
        )
        if not enabled:
            return
        for index in range(1, min(len(selected_participants), max_turns + 1)):
            speaker, speaker_summary, _speaker_sources = selected_participants[index]
            listener, listener_summary, _listener_sources = selected_participants[index - 1]
            council_prompt = self._build_council_prompt(
                task,
                speaker=speaker,
                listener=listener,
                speaker_summary=speaker_summary,
                listener_summary=listener_summary,
            )
            await self.send_message(
                MessageEnvelope(
                    type="chat.council",
                    protocol="conversation-routing",
                    sender=listener.id,
                    recipient=speaker.id,
                    task_id=task.id,
                    correlation_id=task.id,
                    payload={
                        "title": task.title,
                        "other_specialist": listener.name,
                        "other_summary": listener_summary,
                    },
                    priority=max(2, task.priority),
                )
            )
            await self._append_discussion_entry(
                task,
                sender=listener.id,
                recipient=speaker.id,
                kind="council-turn-request",
                content=f"{listener.name} asked {speaker.name} for a council reaction.",
                extra={"other_summary": listener_summary},
            )
            council_task = TaskRecord(
                title=f"Council turn · {task.title}",
                description=council_prompt,
                capability=task.capability,
                priority=task.priority,
                requested_agent_id=speaker.id,
                source_agent_id=source_agent.id,
                route_mode="consult-child",
                channel="chat",
            )
            council_memory_briefing = await self._memory_core_briefing(
                speaker,
                council_task,
                sender=source_agent.id,
            )
            result = await asyncio.wait_for(
                self.executor.run(
                    speaker,
                    council_task,
                    self.publish,
                    memory_briefing=council_memory_briefing,
                ),
                timeout=speaker.limits.timeout_seconds,
            )
            council_summary = str(result.get("summary") or "").strip()
            council_sources = result.get("sources") or []
            await self._append_discussion_entry(
                task,
                sender=speaker.id,
                recipient=source_agent.id,
                kind="council-turn",
                content=council_summary or f"{speaker.name} returned a council note.",
                sources=council_sources if isinstance(council_sources, list) else [],
                extra={"reacting_to": listener.name},
            )
            await self._emit_reasoning_note(
                task,
                sender=speaker,
                recipient=source_agent,
                focus=f"Council reaction to {listener.name}",
                summary=council_summary,
                sources=council_sources if isinstance(council_sources, list) else [],
                reasoning_type="council",
                reacting_to=listener.name,
            )
            council_note = "\n".join(
                part for part in (
                    f"Council note from {speaker.name} reacting to {listener.name}:",
                    council_summary,
                )
                if str(part or "").strip()
            ).strip()
            if council_note:
                existing = str(task.consultation_notes or "").strip()
                task.consultation_notes = (
                    f"{existing}\n\n{council_note}".strip() if existing else council_note
                )[-12_000:]

    async def _run_consult_round(
        self,
        task: TaskRecord,
        source_agent: AgentSnapshot,
        consulted_agent: AgentSnapshot,
        consult_index: int,
        total_consults: int,
        prior_specialist_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]],
        prior_specialist_briefs: list[str],
        *,
        acceptance_reason: str = "Consultation accepted by the specialist.",
    ) -> tuple[dict[str, Any], str, list[dict[str, str]], dict[str, Any]]:
        delegation_packet = self._build_delegation_packet(
            task,
            source_agent,
            consulted_agent,
            consult_index=consult_index,
            total_consults=total_consults,
        )
        consult_prompt = self.router._forwarded_message(
            (task.description or task.title or "").strip(),
            source_agent,
            consulted_agent,
            task.route_language,
            "consult",
        )
        consult_prompt = (
            f"{consult_prompt}\n\n"
            f"Specialist question: {delegation_packet['specialist_question']}\n"
            f"Expected output: {delegation_packet['expected_output']}\n"
            f"Synthesis goal: {delegation_packet['synthesis_goal']}"
        ).strip()
        if prior_specialist_briefs:
            if prior_specialist_rounds:
                previous_agent, previous_summary, _previous_sources = prior_specialist_rounds[-1]
                await self.send_message(
                    MessageEnvelope(
                        type="chat.peer-brief",
                        protocol="conversation-routing",
                        sender=previous_agent.id,
                        recipient=consulted_agent.id,
                        task_id=task.id,
                        correlation_id=task.id,
                        payload={
                            "title": task.title,
                            "previous_specialist": previous_agent.name,
                            "previous_summary": previous_summary,
                        },
                        priority=max(2, task.priority),
                    )
                )
                await self._append_discussion_entry(
                    task,
                    sender=previous_agent.id,
                    recipient=consulted_agent.id,
                    kind="peer-brief",
                    content=(
                        f"{previous_agent.name} briefed {consulted_agent.name} before the next specialist round."
                    ),
                    extra={"previous_summary": previous_summary},
                )
            consult_prompt = (
                f"{consult_prompt}\n\n"
                "Prior specialist context:\n"
                + "\n".join(f"- {brief}" for brief in prior_specialist_briefs[-2:])
            ).strip()
            await self._append_discussion_entry(
                task,
                sender=source_agent.id,
                recipient=consulted_agent.id,
                kind="council-brief",
                content=f"Passing prior specialist context to {consulted_agent.name}.",
                extra={"prior_specialists": prior_specialist_briefs[-2:]},
            )
        consult_task = TaskRecord(
            title=f"Consultation {consult_index + 1} · {task.title}",
            description=consult_prompt,
            capability=task.capability,
            priority=task.priority,
            requested_agent_id=consulted_agent.id,
            source_agent_id=source_agent.id,
            route_mode="consult-child",
            channel="chat",
        )
        await self._set_agent_state(consulted_agent, AgentState.RECEIVING, consult_task, load=0.28)
        await self.send_message(
            MessageEnvelope(
                type="chat.plan",
                protocol="conversation-routing",
                sender=source_agent.id,
                recipient=consulted_agent.id,
                task_id=task.id,
                correlation_id=task.id,
                payload=delegation_packet,
                priority=max(2, task.priority),
            )
        )
        await self._append_discussion_entry(
            task,
            sender=source_agent.id,
            recipient=consulted_agent.id,
            kind="plan",
            content=delegation_packet["plan_summary"],
            extra=delegation_packet,
        )
        await self.send_message(
            MessageEnvelope(
                type="chat.accept",
                protocol="conversation-routing",
                sender=consulted_agent.id,
                recipient=source_agent.id,
                task_id=task.id,
                correlation_id=task.id,
                payload={"title": task.title, "reason": acceptance_reason},
                priority=max(2, task.priority),
            )
        )
        await self._append_discussion_entry(
            task,
            sender=consulted_agent.id,
            recipient=source_agent.id,
            kind="accept",
            content=f"{consulted_agent.name} accepted the specialist request.",
            extra={"consult_position": delegation_packet["consult_position"]},
        )
        await self._set_agent_state(consulted_agent, AgentState.EXECUTING, consult_task, load=0.64)
        consult_memory_briefing = await self._memory_core_briefing(consulted_agent, consult_task, sender=source_agent.id)
        result = await asyncio.wait_for(
            self.executor.run(consulted_agent, consult_task, self.publish, memory_briefing=consult_memory_briefing),
            timeout=consulted_agent.limits.timeout_seconds,
        )
        summary = str(result.get("summary") or "").strip()
        raw_sources = result.get("sources") or []
        sources = raw_sources if isinstance(raw_sources, list) else []
        if self._should_request_specialist_followup(consulted_agent, summary, sources):
            followup_question = self._followup_question(
                consulted_agent,
                delegation_packet,
                summary,
                sources,
            )
            await self.send_message(
                MessageEnvelope(
                    type="chat.revise",
                    protocol="conversation-routing",
                    sender=source_agent.id,
                    recipient=consulted_agent.id,
                    task_id=task.id,
                    correlation_id=task.id,
                    payload={
                        "title": task.title,
                        "followup_question": followup_question,
                        "previous_summary": summary,
                    },
                    priority=max(2, task.priority),
                )
            )
            await self._append_discussion_entry(
                task,
                sender=source_agent.id,
                recipient=consulted_agent.id,
                kind="revise",
                content=followup_question,
                extra={"previous_summary": summary},
            )
            await self._append_strategy_update(
                task,
                sender=source_agent.id,
                recipient=consulted_agent.id,
                summary=(
                    f"{source_agent.name} requested a stronger revision from {consulted_agent.name} "
                    "before final synthesis."
                ),
                phase="revision",
                updates={
                    "current_stage": "revision",
                    "revision_target_agent_id": consulted_agent.id,
                    "revision_question": followup_question,
                },
            )
            revised_task = TaskRecord(
                title=f"Consultation revision · {task.title}",
                description=(
                    f"{consult_prompt}\n\n"
                    f"Follow-up question: {followup_question}\n"
                    f"Previous answer to improve: {summary}"
                ).strip(),
                capability=task.capability,
                priority=task.priority,
                requested_agent_id=consulted_agent.id,
                source_agent_id=source_agent.id,
                route_mode="consult-child",
                channel="chat",
            )
            revised_memory_briefing = await self._memory_core_briefing(
                consulted_agent,
                revised_task,
                sender=source_agent.id,
            )
            result = await asyncio.wait_for(
                self.executor.run(
                    consulted_agent,
                    revised_task,
                    self.publish,
                    memory_briefing=revised_memory_briefing,
                ),
                timeout=consulted_agent.limits.timeout_seconds,
            )
            summary = str(result.get("summary") or "").strip()
            raw_sources = result.get("sources") or []
            sources = raw_sources if isinstance(raw_sources, list) else []
            await self._append_discussion_entry(
                task,
                sender=consulted_agent.id,
                recipient=source_agent.id,
                kind="revision-result",
                content=summary or f"{consulted_agent.name} returned a revised specialist reply.",
                sources=sources,
                extra={"followup_question": followup_question},
            )
        await self._set_agent_state(consulted_agent, AgentState.IDLE, None, load=0.08)
        consultation_note = "\n".join(
            part
            for part in (
                f"Consulted specialist: {consulted_agent.name} ({consulted_agent.id})",
                f"Reason: {task.route_reason}" if task.route_reason else "",
                f"Specialist summary: {summary}" if summary else "",
                (
                    "Specialist sources: "
                    + ", ".join(
                        str(item.get("url", "") or "").strip()
                        for item in sources
                        if isinstance(item, dict) and str(item.get("url", "") or "").strip()
                    )
                ) if sources else "",
            )
            if part
        ).strip()
        if consultation_note:
            existing = str(task.consultation_notes or "").strip()
            task.consultation_notes = (
                f"{existing}\n\n{consultation_note}".strip() if existing else consultation_note
            )[-12_000:]
        created_at = utc_now()
        self.store.save_agent_chat_message(
            source_agent.id,
            AgentChatMessage(
                id=f"{task.id}-consult-note" if consult_index == 0 else f"{task.id}-consult-note-{consulted_agent.id}",
                task_id=f"{task.id}-consult-note" if consult_index == 0 else f"{task.id}-consult-note-{consulted_agent.id}",
                role="system",
                content=f"Consultation from {consulted_agent.name}: {summary}",
                sources=sources,
                created_at=created_at,
            ),
        )
        await self.send_message(
            MessageEnvelope(
                type="chat.reply",
                protocol="conversation-routing",
                sender=consulted_agent.id,
                recipient=source_agent.id,
                task_id=task.id,
                correlation_id=task.id,
                payload={
                    "title": task.title,
                    "summary": summary,
                    "sources": sources,
                    "route_mode": "consult",
                    "specialist_question": delegation_packet["specialist_question"],
                    "expected_output": delegation_packet["expected_output"],
                },
                priority=max(2, task.priority),
            )
        )
        await self._append_discussion_entry(
            task,
            sender=consulted_agent.id,
            recipient=source_agent.id,
            kind="reply",
            content=summary or f"{consulted_agent.name} returned a specialist reply.",
            sources=sources,
            extra={
                "specialist_question": delegation_packet["specialist_question"],
                "expected_output": delegation_packet["expected_output"],
            },
        )
        await self._emit_reasoning_note(
            task,
            sender=consulted_agent,
            recipient=source_agent,
            focus=delegation_packet["specialist_question"],
            summary=summary,
            sources=sources,
            reasoning_type="consult",
        )
        await self.publish(
            RuntimeEvent(
                type="chat.consulted",
                entity_id=task.id,
                task_id=task.id,
                agent_id=consulted_agent.id,
                summary=f"{source_agent.name} consulted {consulted_agent.name}.",
                data={
                    "task": task.model_dump(mode="json"),
                    "from_agent_id": source_agent.id,
                    "to_agent_id": consulted_agent.id,
                    "summary": summary,
                    "sources": sources,
                    "specialist_question": delegation_packet["specialist_question"],
                    "expected_output": delegation_packet["expected_output"],
                },
            )
        )
        return result, summary, sources, delegation_packet

    async def _run_chat_consultation(
        self,
        task: TaskRecord,
        source_agent: AgentSnapshot,
        sender: str,
    ) -> Optional[dict[str, Any]]:
        if task.channel != "chat" or task.route_mode != "consult" or not task.consult_agent_ids:
            return None
        last_result: Optional[dict[str, Any]] = None
        consulted_rounds: list[tuple[AgentSnapshot, str, list[dict[str, str]]]] = []
        prior_specialist_briefs: list[str] = []
        pending_peer_requests: list[dict[str, Any]] = []
        forced_council_request = False
        for index, consulted_agent_id in enumerate(task.consult_agent_ids):
            consulted_agent = self.agents.get(consulted_agent_id)
            if consulted_agent is None:
                continue
            result, summary, sources, _packet = await self._run_consult_round(
                task,
                source_agent,
                consulted_agent,
                index,
                len(task.consult_agent_ids),
                consulted_rounds,
                prior_specialist_briefs,
            )
            if summary:
                prior_specialist_briefs.append(f"{consulted_agent.name}: {summary}")
                consulted_rounds.append((consulted_agent, summary, sources))
                peer_request = await self._specialist_peer_request_decision(
                    task,
                    source_agent,
                    consulted_agent,
                    summary,
                    consulted_rounds,
                )
                if isinstance(peer_request, dict) and str(peer_request.get("action") or "").strip() == "request":
                    await self._emit_specialist_peer_request(
                        task,
                        source_agent,
                        consulted_agent,
                        peer_request,
                        pending_peer_requests,
                    )
            last_result = result
        max_followup_cycles = 2
        memory_followup_used = False
        for _cycle in range(max_followup_cycles):
            followup: dict[str, Any]
            if pending_peer_requests:
                peer_request = pending_peer_requests.pop(0)
                known_ids = {agent.id for agent, _summary, _sources in consulted_rounds}
                if str(peer_request.get("target_kind") or "specialist").strip() == "specialist" and str(peer_request.get("target_agent_id") or "").strip() in known_ids:
                    continue
                followup = {
                    "action": "consult" if str(peer_request.get("target_kind") or "specialist").strip() == "specialist" else str(peer_request.get("target_kind") or "").strip(),
                    "reason": str(peer_request.get("reason") or "A specialist requested another specialist before synthesis.").strip(),
                    "target_agent_id": str(peer_request.get("target_agent_id") or "").strip(),
                    "target_label": str(peer_request.get("target_label") or "").strip(),
                    "decision_mode": str(peer_request.get("decision_mode") or "specialist-request"),
                    "requested_by_agent_id": str(peer_request.get("sender_agent_id") or "").strip(),
                    "target_kind": str(peer_request.get("target_kind") or "specialist").strip(),
                }
            else:
                followup = await self._consult_followup_decision(task, source_agent, consulted_rounds)
            followup_action = str(followup.get("action") or "synthesize").strip()
            if followup_action == "memory":
                if memory_followup_used:
                    break
                memory_followup_used = True
                await self._append_strategy_update(
                    task,
                    sender=source_agent.id,
                    recipient=source_agent.id,
                    summary=str(followup.get("reason") or "Memory Core was asked for extra context before synthesis.").strip(),
                    phase="memory-followup",
                    updates={
                        "current_stage": "memory-followup",
                        "followup_action": "memory",
                        "followup_target_kind": "memory",
                        "followup_target_label": "Memory Core",
                        "followup_requested_by_agent_id": str(followup.get("requested_by_agent_id") or "").strip(),
                        "followup_decision_mode": str(followup.get("decision_mode") or "heuristic"),
                    },
                )
                extra_memory = await self._memory_core_briefing(
                    source_agent,
                    task,
                    sender=source_agent.id,
                    query_override=self._memory_followup_query(task, consulted_rounds),
                )
                if extra_memory:
                    existing = str(task.consultation_notes or "").strip()
                    memory_note = "Memory Core follow-up context:\n" + extra_memory.strip()
                    task.consultation_notes = (
                        f"{existing}\n\n{memory_note}".strip() if existing else memory_note
                    )[-12_000:]
                continue
            if followup_action == "council":
                forced_council_request = True
                await self._append_strategy_update(
                    task,
                    sender=source_agent.id,
                    recipient=source_agent.id,
                    summary=str(followup.get("reason") or "A specialist requested a council step before synthesis.").strip(),
                    phase="council-request",
                    updates={
                        "current_stage": "council-request",
                        "followup_action": "council",
                        "followup_target_kind": "council",
                        "followup_target_label": "Council",
                        "followup_requested_by_agent_id": str(followup.get("requested_by_agent_id") or "").strip(),
                        "followup_decision_mode": str(followup.get("decision_mode") or "specialist-request"),
                    },
                )
                break
            if followup_action == "consult":
                extra_agent_id = str(followup.get("target_agent_id") or "").strip()
                extra_agent = self.agents.get(extra_agent_id)
                known_ids = {agent.id for agent, _summary, _sources in consulted_rounds}
                if extra_agent is None or extra_agent_id in known_ids:
                    break
                if extra_agent_id not in task.consult_agent_ids:
                    task.consult_agent_ids.append(extra_agent_id)
                await self._append_strategy_update(
                    task,
                    sender=source_agent.id,
                    recipient=extra_agent.id,
                    summary=str(followup.get("reason") or f"{source_agent.name} requested one more specialist before synthesis.").strip(),
                    phase="followup-consult",
                    updates={
                        "current_stage": "followup-consult",
                        "followup_action": "consult",
                        "followup_target_kind": "specialist",
                        "followup_target_agent_id": extra_agent.id,
                        "followup_target_label": extra_agent.name,
                        "followup_requested_by_agent_id": str(followup.get("requested_by_agent_id") or "").strip(),
                        "followup_decision_mode": str(followup.get("decision_mode") or "heuristic"),
                    },
                )
                result, summary, sources, _packet = await self._run_consult_round(
                    task,
                    source_agent,
                    extra_agent,
                    len(consulted_rounds),
                    len(task.consult_agent_ids),
                    consulted_rounds,
                    prior_specialist_briefs,
                    acceptance_reason="Follow-up consultation accepted by the specialist.",
                )
                if summary:
                    prior_specialist_briefs.append(f"{extra_agent.name}: {summary}")
                    consulted_rounds.append((extra_agent, summary, sources))
                    peer_request = await self._specialist_peer_request_decision(
                        task,
                        source_agent,
                        extra_agent,
                        summary,
                        consulted_rounds,
                    )
                    if isinstance(peer_request, dict) and str(peer_request.get("action") or "").strip() == "request":
                        await self._emit_specialist_peer_request(
                            task,
                            source_agent,
                            extra_agent,
                            peer_request,
                            pending_peer_requests,
                        )
                last_result = result
                continue
            break
        if forced_council_request and len(consulted_rounds) >= 2:
            specialist_requester_id = str(followup.get("requested_by_agent_id") or "").strip() if isinstance(followup, dict) else ""
            await self._append_discussion_entry(
                task,
                sender=source_agent.id,
                recipient=source_agent.id,
                kind="council-policy",
                content="Council forced because a specialist explicitly requested it.",
                extra={
                    "enabled": True,
                    "participants": [agent.id for agent, _summary, _sources in consulted_rounds[:3]],
                    "max_turns": min(2, max(0, len(consulted_rounds[:3]) - 1)),
                    "decision_mode": "specialist-request",
                    "requested_by_agent_id": specialist_requester_id,
                },
            )
            await self._append_strategy_update(
                task,
                sender=source_agent.id,
                recipient=source_agent.id,
                summary="Council was explicitly requested by a specialist before synthesis.",
                phase="council",
                updates={
                    "current_stage": "council",
                    "council_enabled": True,
                    "council_participants": [agent.id for agent, _summary, _sources in consulted_rounds[:3]],
                    "council_turn_budget": min(2, max(0, len(consulted_rounds[:3]) - 1)),
                    "council_decision_mode": "specialist-request",
                    "followup_requested_by_agent_id": specialist_requester_id,
                },
            )
            participants = consulted_rounds[:3]
            for index in range(1, min(len(participants), 3)):
                speaker, speaker_summary, _speaker_sources = participants[index]
                listener, listener_summary, _listener_sources = participants[index - 1]
                council_prompt = self._build_council_prompt(
                    task,
                    speaker=speaker,
                    listener=listener,
                    speaker_summary=speaker_summary,
                    listener_summary=listener_summary,
                )
                await self.send_message(
                    MessageEnvelope(
                        type="chat.council",
                        protocol="conversation-routing",
                        sender=listener.id,
                        recipient=speaker.id,
                        task_id=task.id,
                        correlation_id=task.id,
                        payload={
                            "title": task.title,
                            "other_specialist": listener.name,
                            "other_summary": listener_summary,
                        },
                        priority=max(2, task.priority),
                    )
                )
                await self._append_discussion_entry(
                    task,
                    sender=listener.id,
                    recipient=speaker.id,
                    kind="council-turn-request",
                    content=f"{listener.name} asked {speaker.name} for a council reaction.",
                    extra={"other_summary": listener_summary},
                )
                council_task = TaskRecord(
                    title=f"Council turn · {task.title}",
                    description=council_prompt,
                    capability=task.capability,
                    priority=task.priority,
                    requested_agent_id=speaker.id,
                    source_agent_id=source_agent.id,
                    route_mode="consult-child",
                    channel="chat",
                )
                council_memory_briefing = await self._memory_core_briefing(
                    speaker,
                    council_task,
                    sender=source_agent.id,
                )
                result = await asyncio.wait_for(
                    self.executor.run(
                        speaker,
                        council_task,
                        self.publish,
                        memory_briefing=council_memory_briefing,
                    ),
                    timeout=speaker.limits.timeout_seconds,
                )
                council_summary = str(result.get("summary") or "").strip()
                council_sources = result.get("sources") or []
                await self._append_discussion_entry(
                    task,
                    sender=speaker.id,
                    recipient=source_agent.id,
                    kind="council-turn",
                    content=council_summary or f"{speaker.name} returned a council note.",
                    sources=council_sources if isinstance(council_sources, list) else [],
                    extra={"reacting_to": listener.name},
                )
                council_note = "\n".join(
                    part for part in (
                        f"Council note from {speaker.name} reacting to {listener.name}:",
                        council_summary,
                    )
                    if str(part or "").strip()
                ).strip()
                if council_note:
                    existing = str(task.consultation_notes or "").strip()
                    task.consultation_notes = (
                        f"{existing}\n\n{council_note}".strip() if existing else council_note
                    )[-12_000:]
            return last_result
        await self._run_council_phase(task, consulted_rounds, source_agent)
        return last_result

    async def _complete_chat_handoff(self, task: TaskRecord, agent: AgentSnapshot) -> None:
        if (
            task.channel != "chat"
            or not task.source_agent_id
            or task.source_agent_id == agent.id
            or not task.result
            or task.source_agent_id not in self.agents
        ):
            return
        source_agent = self.agents[task.source_agent_id]
        summary = str(task.result.get("summary") or "").strip() or "Reply ready."
        sources = task.result.get("sources") or []
        created_at = utc_now()
        self.store.save_agent_chat_message(
            source_agent.id,
            AgentChatMessage(
                id=f"{task.id}-handoff-return",
                task_id=task.id,
                role="assistant",
                content=summary,
                sources=sources if isinstance(sources, list) else [],
                created_at=created_at,
            ),
        )
        await self._append_discussion_entry(
            task,
            sender=agent.id,
            recipient=source_agent.id,
            kind="handoff",
            content=summary,
            sources=sources if isinstance(sources, list) else [],
            extra={"route_mode": task.route_mode or "route"},
        )
        await self.send_message(
            MessageEnvelope(
                type="chat.reply",
                protocol="conversation-routing",
                sender=agent.id,
                recipient=source_agent.id,
                task_id=task.id,
                correlation_id=task.id,
                payload={
                    "title": task.title,
                    "summary": summary,
                    "sources": sources if isinstance(sources, list) else [],
                    "route_mode": task.route_mode or "route",
                },
                priority=max(2, task.priority),
            )
        )
        await self.publish(
            RuntimeEvent(
                type="chat.returned",
                entity_id=task.id,
                task_id=task.id,
                agent_id=source_agent.id,
                summary=f"{agent.name} returned a routed reply to {source_agent.name}.",
                data={
                    "task": task.model_dump(mode="json"),
                    "from_agent_id": agent.id,
                    "to_agent_id": source_agent.id,
                    "summary": summary,
                    "sources": sources if isinstance(sources, list) else [],
                },
            )
        )

    async def _transition_task(
        self, task: TaskRecord, target: TaskState, agent: Optional[AgentSnapshot] = None
    ) -> None:
        previous = task.state
        validate_task_transition(previous, target)
        LOGGER.info(
            "task_transition id=%s from=%s to=%s agent=%s",
            task.id,
            previous.value,
            target.value,
            agent.id if agent else task.assigned_agent_id or "-",
        )
        task.state = target
        task.updated_at = utc_now()
        self.store.save_task(task)
        await self.publish(
            RuntimeEvent(
                type="task.state.changed",
                entity_id=task.id,
                task_id=task.id,
                agent_id=agent.id if agent else task.assigned_agent_id,
                summary=f"{task.title}: {previous.value} → {target.value}",
                data={"from": previous.value, "to": target.value, "task": task.model_dump(mode="json")},
            )
        )

    async def _set_agent_state(
        self,
        agent: AgentSnapshot,
        target: AgentState,
        task: Optional[TaskRecord],
        load: Optional[float] = None,
    ) -> None:
        previous = agent.state
        agent.state = target
        agent.active_task_id = task.id if task else None
        if load is not None:
            agent.load = load
        self.store.save_agent(agent)
        await self.publish(
            RuntimeEvent(
                type="agent.state.changed",
                entity_id=agent.id,
                agent_id=agent.id,
                task_id=task.id if task else None,
                summary=f"{agent.name}: {previous.value} → {target.value}",
                data={"from": previous.value, "to": target.value, "load": agent.load},
            )
        )

    async def send_message(self, message: MessageEnvelope) -> None:
        validate_message(message)
        await self.publish(
            RuntimeEvent(
                type="protocol.message",
                entity_id=message.id,
                agent_id=message.sender,
                task_id=message.task_id,
                summary=f"{message.sender} → {message.recipient}: {message.type}",
                data={"message": message.model_dump(mode="json")},
            )
        )

    async def publish(self, event: RuntimeEvent) -> None:
        self.store.append_event(event)
        for queue in tuple(self.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self.subscribers.discard(queue)

    def subscribe(self) -> asyncio.Queue[RuntimeEvent]:
        queue: asyncio.Queue[RuntimeEvent] = asyncio.Queue(maxsize=256)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[RuntimeEvent]) -> None:
        self.subscribers.discard(queue)

    async def shutdown(self) -> None:
        for job in tuple(self.running_jobs):
            job.cancel()
        if self.running_jobs:
            await asyncio.gather(*self.running_jobs, return_exceptions=True)
        await self.browser_control.shutdown()
        self.store.close()
