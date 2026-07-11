from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Optional

from .models import (
    AgentChatMessage,
    AgentSnapshot,
    MemoryRecord,
    ProjectJobPreset,
    RuntimeEvent,
    TaskRecord,
    WikiRecord,
    utc_now,
)


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
                CREATE TABLE IF NOT EXISTS wikis (
                    agent_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_job_presets (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    document TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_created_at_idx ON events(created_at DESC);
                CREATE INDEX IF NOT EXISTS project_job_presets_project_idx
                    ON project_job_presets(project_id, created_at DESC);
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

    def get_wiki(self, agent_id: str) -> WikiRecord:
        with self.lock:
            row = self.connection.execute(
                "SELECT content, updated_at FROM wikis WHERE agent_id = ?", (agent_id,)
            ).fetchone()
        if row is None:
            return WikiRecord(agent_id=agent_id, content="")
        return WikiRecord(agent_id=agent_id, content=row["content"], updated_at=row["updated_at"])

    def save_wiki(self, wiki: WikiRecord) -> None:
        wiki.updated_at = utc_now()
        with self.lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO wikis(agent_id, content, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    content=excluded.content,
                    updated_at=excluded.updated_at
                """,
                (wiki.agent_id, wiki.content, wiki.updated_at.isoformat()),
            )

    def bootstrap_wiki_from_chat(self, agent_id: str, limit_turns: int = 40) -> WikiRecord:
        with self.lock:
            existing = self.connection.execute(
                "SELECT content, updated_at FROM wikis WHERE agent_id = ?", (agent_id,)
            ).fetchone()
        if existing is not None:
            return WikiRecord(
                agent_id=agent_id,
                content=existing["content"],
                updated_at=existing["updated_at"],
            )

        history = self.load_agent_chat_messages(agent_id, limit_turns=limit_turns)
        lines = []
        for message in history:
            label = "user" if message.role == "user" else message.role
            content = " ".join(message.content.split())
            lines.append(f"- {message.created_at.isoformat(timespec='seconds')} | {label}: {content[:500]}")
        wiki = WikiRecord(agent_id=agent_id, content="\n".join(lines)[-8_000:])
        self.save_wiki(wiki)
        return wiki

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

    def save_project_job_preset(self, preset: ProjectJobPreset) -> None:
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO project_job_presets(id, project_id, document, created_at) VALUES (?, ?, ?, ?)",
                (preset.id, preset.project_id, preset.model_dump_json(), preset.created_at.isoformat()),
            )

    def load_project_job_presets(self, project_id: Optional[str] = None) -> list[ProjectJobPreset]:
        with self.lock:
            if project_id:
                rows = self.connection.execute(
                    "SELECT document FROM project_job_presets WHERE project_id = ? ORDER BY created_at DESC",
                    (project_id,),
                ).fetchall()
            else:
                rows = self.connection.execute(
                    "SELECT document FROM project_job_presets ORDER BY created_at DESC"
                ).fetchall()
        return [ProjectJobPreset.model_validate_json(row["document"]) for row in rows]

    def delete_project_job_preset(self, preset_id: str) -> bool:
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "DELETE FROM project_job_presets WHERE id = ?", (preset_id,)
            )
        return cursor.rowcount > 0

    def recent_events(self, limit: int = 100) -> list[RuntimeEvent]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT document FROM events ORDER BY sequence DESC LIMIT ?", (limit,)
            ).fetchall()
        return [RuntimeEvent.model_validate_json(row["document"]) for row in reversed(rows)]

    def load_agent_chat_messages(
        self, agent_id: str, limit_turns: int = 12, exclude_task_id: str = ""
    ) -> list[AgentChatMessage]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT document FROM tasks ORDER BY updated_at DESC, rowid DESC"
            ).fetchall()
        turns: list[list[AgentChatMessage]] = []
        for row in rows:
            task = TaskRecord.model_validate_json(row["document"])
            legacy_chat = (
                task.channel == "task"
                and task.requested_agent_id == agent_id
                and task.capability is None
                and task.title == task.description
            )
            if task.id == exclude_task_id or (
                task.requested_agent_id != agent_id or (task.channel != "chat" and not legacy_chat)
            ):
                continue
            turn = [
                AgentChatMessage(
                    id=f"{task.id}-user",
                    task_id=task.id,
                    role="user",
                    content=task.description or task.title,
                    created_at=task.created_at,
                )
            ]
            if task.result:
                turn.append(
                    AgentChatMessage(
                        id=f"{task.id}-assistant",
                        task_id=task.id,
                        role="assistant",
                        content=self._chat_assistant_content(task),
                        sources=task.result.get("sources", []),
                        created_at=task.updated_at,
                    )
                )
            elif task.error:
                turn.append(
                    AgentChatMessage(
                        id=f"{task.id}-error",
                        task_id=task.id,
                        role="system",
                        content=self._chat_error_content(task),
                        created_at=task.updated_at,
                    )
                )
            turns.append(turn)
            if len(turns) >= limit_turns:
                break
        # Select the newest turns first, then expose them chronologically.
        return [message for turn in reversed(turns) for message in turn]

    @staticmethod
    def _chat_assistant_content(task: TaskRecord) -> str:
        if not task.result:
            return "Task completato."
        summary = str(task.result.get("summary", "Task completato."))
        if (
            task.channel == "chat"
            and task.result.get("provider") == "simulated"
            and task.result.get("details") == "Executed by the native deterministic provider."
            and task.result.get("model") == "native-simulator"
        ):
            user_text = " ".join((task.description or task.title or "").split())
            if len(user_text) > 500:
                user_text = user_text[:499].rstrip() + "…"
            return (
                "Risposta storica simulata locale: questo messaggio non è stato generato da Codex "
                f"o da una API LLM. Il runtime aveva ricevuto: “{user_text}”."
            )
        return summary

    @staticmethod
    def _chat_error_content(task: TaskRecord) -> str:
        error = str(task.error or "Task fallito.")
        if error.startswith("HTTP Error 401") or error.startswith("HTTP Error 403"):
            return (
                "Provider authentication failed. Controlla la API key salvata per questo agente/progetto "
                "e verifica che provider e scope della key siano corretti."
            )
        return error

    def close(self) -> None:
        with self.lock:
            self.connection.close()
