# Current status

- Native Python runtime and Three.js UI are connected through REST and WebSocket events.
- Agents can be created and configured from the interface.
- Direct messages are executed by the provider configured on the selected agent.
- Per-agent conversations persist in SQLite and are restored in the UI.
- Provider prompts receive recent conversation, private memory, and relevant shared wiki pages.
- Shared-wiki search, proposal, and restricted update tools are available.
- Autonomous workflows support model-generated or deterministic planning, dependency-aware delegation, bounded parallel execution, typed handoffs, immutable retries, quality evaluation, final synthesis, and reusable skill learning.
- Sessions now provide normalized messages, FTS5 search, WAL persistence, lineage compression, token/tool/API counters, canonical prompt history, registry-based provider resolution, provider fallback, and task cancellation.
