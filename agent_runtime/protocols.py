from __future__ import annotations

from dataclasses import dataclass

from .models import MessageEnvelope, TaskState


@dataclass(frozen=True)
class ProtocolDefinition:
    id: str
    message_types: frozenset[str]


PROTOCOLS = {
    "agent-lifecycle": ProtocolDefinition(
        id="agent-lifecycle",
        message_types=frozenset(
            {"agent.registered", "agent.ready", "agent.state", "agent.stopped", "agent.failed"}
        ),
    ),
    "task-contract": ProtocolDefinition(
        id="task-contract",
        message_types=frozenset(
            {
                "task.announce",
                "task.propose",
                "task.award",
                "task.accept",
                "task.progress",
                "task.result",
                "task.reject",
                "task.cancel",
                "task.fail",
            }
        ),
    ),
    "quality-review": ProtocolDefinition(
        id="quality-review",
        message_types=frozenset(
            {"review.request", "review.finding", "review.revision", "review.approved"}
        ),
    ),
    "memory-learning": ProtocolDefinition(
        id="memory-learning",
        message_types=frozenset(
            {"memory.recall", "memory.propose", "memory.approve", "memory.commit"}
        ),
    ),
    "tool-execution": ProtocolDefinition(
        id="tool-execution",
        message_types=frozenset(
            {"tool.request", "tool.approval", "tool.approved", "tool.denied", "tool.result"}
        ),
    ),
}


TASK_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.CREATED: frozenset({TaskState.ANNOUNCED, TaskState.CANCELLED}),
    TaskState.ANNOUNCED: frozenset({TaskState.AWARDED, TaskState.FAILED, TaskState.CANCELLED}),
    TaskState.AWARDED: frozenset({TaskState.ACCEPTED, TaskState.FAILED, TaskState.CANCELLED}),
    TaskState.ACCEPTED: frozenset({TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED}),
    TaskState.RUNNING: frozenset({TaskState.VERIFYING, TaskState.FAILED, TaskState.CANCELLED}),
    TaskState.VERIFYING: frozenset({TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}),
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}


def validate_message(message: MessageEnvelope) -> None:
    protocol = PROTOCOLS.get(message.protocol)
    if protocol is None:
        raise ValueError(f"Unknown protocol: {message.protocol}")
    if message.type not in protocol.message_types:
        raise ValueError(f"Message {message.type} is not valid for {message.protocol}")


def validate_task_transition(current: TaskState, target: TaskState) -> None:
    if target not in TASK_TRANSITIONS[current]:
        raise ValueError(f"Invalid task transition: {current.value} -> {target.value}")
