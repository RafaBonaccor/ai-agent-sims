from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock

from .models import AgentSnapshot, MemoryRecord, RuntimeEvent, TaskRecord, utc_now


class RuntimeStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = RLock()
        self._create_schema()

    def _create_schema(self) -> None:
        with self.lock, self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    document TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    document TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL,
                    entity_id TEXT,
                    document TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memories (
                    agent_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_created_at_idx ON events(created_at DESC);
                """
            )

    def save_agent(self, agent: AgentSnapshot) -> None:
        document = agent.model_dump_json()
        with self.lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO agents(id, document) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET document=excluded.document, updated_at=CURRENT_TIMESTAMP
                """,
                (agent.id, document),
            )

    def load_agents(self) -> list[AgentSnapshot]:
        with self.lock:
            rows = self.connection.execute("SELECT document FROM agents ORDER BY id").fetchall()
        return [AgentSnapshot.model_validate_json(row["document"]) for row in rows]

    def save_task(self, task: TaskRecord) -> None:
        document = task.model_dump_json()
        with self.lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO tasks(id, document) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET document=excluded.document, updated_at=CURRENT_TIMESTAMP
                """,
                (task.id, document),
            )

    def load_tasks(self) -> list[TaskRecord]:
        with self.lock:
            rows = self.connection.execute("SELECT document FROM tasks ORDER BY updated_at DESC").fetchall()
        return [TaskRecord.model_validate_json(row["document"]) for row in rows]

    def get_memory(self, agent_id: str) -> MemoryRecord:
        with self.lock:
            row = self.connection.execute(
                "SELECT content, updated_at FROM memories WHERE agent_id = ?", (agent_id,)
            ).fetchone()
        if row is None:
            return MemoryRecord(agent_id=agent_id, content="")
        return MemoryRecord(agent_id=agent_id, content=row["content"], updated_at=row["updated_at"])

    def save_memory(self, memory: MemoryRecord) -> None:
        memory.updated_at = utc_now()
        with self.lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO memories(agent_id, content, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    content=excluded.content,
                    updated_at=excluded.updated_at
                """,
                (memory.agent_id, memory.content, memory.updated_at.isoformat()),
            )

    def append_event(self, event: RuntimeEvent) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO events(id, type, entity_id, document, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.type,
                    event.entity_id,
                    event.model_dump_json(),
                    event.created_at.isoformat(),
                ),
            )

    def recent_events(self, limit: int = 100) -> list[RuntimeEvent]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT document FROM events ORDER BY sequence DESC LIMIT ?", (limit,)
            ).fetchall()
        return [RuntimeEvent.model_validate_json(row["document"]) for row in reversed(rows)]

    def close(self) -> None:
        with self.lock:
            self.connection.close()
