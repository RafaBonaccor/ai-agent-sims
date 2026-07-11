# Architectural decisions

## Markdown wiki plus SQLite conversations

Use SQLite for exact chronological chat and runtime records. Use Markdown for curated shared knowledge. Chat history is evidence, not automatically project truth.

## Controlled writeback

All agents may search the wiki and propose durable changes. Only Memory, supervisor, or explicitly `shared-memory` capable agents may replace canonical wiki pages. Proposed updates retain the originating task as provenance.

## Bounded context

Provider prompts use a recent conversation window and relevance-ranked wiki pages. The complete database and wiki are never injected blindly into every request.

## Immutable retry history

Retries create new child tasks rather than resetting failed task state. This preserves observability, makes evaluation reproducible, and lets the orchestrator compare agents and attempts.

## Runtime-owned orchestration

Models propose plans and produce task outputs, but the native runtime validates dependencies, chooses eligible agents, enforces concurrency and retry limits, advances state, and decides when learning artifacts may be written.

## Stable prompt tiers

Identity, tool guidance, and skill indexes form the stable prefix. Project files and wiki retrieval form contextual grounding. Private memory, session summary, provider, and time remain volatile. Task text stays in the user-message layer so normal turns do not unnecessarily invalidate the stable prefix.

## Session lineage over destructive truncation

When context pressure crosses the configured threshold, close the current session, create a child session, retain the first exchange and recent tail, and carry a structured middle-history summary. Never silently delete the only persisted copy of earlier messages.
