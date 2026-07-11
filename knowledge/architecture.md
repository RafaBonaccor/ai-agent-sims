# Runtime architecture

The system has three layers:

1. `agent_runtime/` provides FastAPI, SQLite persistence, typed protocols, task execution, tools, provider adapters, conversation context, and the shared knowledge wiki.
2. `app.mjs` and `src/` render and control the Three.js world and consume REST/WebSocket runtime events.
3. `knowledge/` contains the shared, durable project context maintained through controlled agent tools.

SQLite stores exact operational history such as agents, tasks, events, private memories, and conversation messages. Markdown stores curated project truth that should remain readable and versionable.

Context assembly is bounded. It combines agent identity, instructions, private memory, recent dialogue, relevant wiki pages, the active task, and tool policy. This creates persistent continuity without pretending to enlarge the model's native token window.

## Autonomous workflow loop

Autonomous objectives are persisted as a workflow plus an immutable task tree. The supervisor produces a dependency graph, specialist agents execute child tasks, outputs move through typed handoffs, failed attempts create retry tasks, reviewer output becomes an evaluation gate, and the supervisor synthesizes the final result. Successful trajectories create or refine reusable Markdown skills under `knowledge/skills/`; failures become reviewable wiki proposals.

## Session and prompt foundation

Direct and delegated conversations use normalized SQLite sessions and messages with FTS5 search, WAL mode, token/tool/API counters, and parent-child lineage. Prompt assembly is split into stable identity/tool/skill guidance, project context, volatile memory/session metadata, and canonical conversation messages. Threshold-based compression replaces middle history with a structured summary while retaining the first exchange and a configurable recent tail.

Provider selection is registry-based. Built-in and project JSON profiles resolve API mode, endpoint and credential environment; per-agent fallback chains preserve task and session identity across provider failure.
