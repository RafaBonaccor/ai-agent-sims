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
from .models import (
    AgentDefinition,
    AgentChatMessage,
    AgentSnapshot,
    AgentState,
    MessageEnvelope,
    MemoryRecord,
    MemoryUpdate,
    RuntimeEvent,
    TaskCreate,
    TaskRecord,
    TaskState,
    WikiRecord,
    WikiUpdate,
    utc_now,
)
from .protocols import validate_message, validate_task_transition
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
        project_root = (seed_path.parent.parent if seed_path else Path(__file__).resolve().parent.parent).resolve()
        self.browser_control = browser_control or BrowserControl(project_root)
        self.executor = ModelExecutor(self.store, secrets, browser_control=self.browser_control)
        if not self.agents:
            self._seed_agents()
        for agent_id in self.agents:
            self.store.bootstrap_wiki_from_chat(agent_id)
        self._recover_interrupted_state()

    def _seed_agents(self) -> None:
        if self.seed_path is None or not self.seed_path.exists():
            return
        definitions = json.loads(self.seed_path.read_text(encoding="utf-8"))
        for item in definitions:
            agent = AgentSnapshot(**AgentDefinition.model_validate(item).model_dump())
            self.agents[agent.id] = agent
            self.store.save_agent(agent)

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

    def get_agent_chat(self, agent_id: str) -> list[AgentChatMessage]:
        if agent_id not in self.agents:
            raise KeyError(agent_id)
        return self.store.load_agent_chat_messages(agent_id)

    async def add_agent(self, definition: AgentDefinition) -> AgentSnapshot:
        if definition.id in self.agents:
            raise ValueError(f"Agent already exists: {definition.id}")
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

            task.result = await asyncio.wait_for(
                self.executor.run(agent, task, self.publish),
                timeout=agent.limits.timeout_seconds,
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
