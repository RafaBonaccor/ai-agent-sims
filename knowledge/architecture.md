# Runtime architecture

The system has three layers:

1. `agent_runtime/` provides FastAPI, SQLite persistence, typed protocols, task execution, tools, provider adapters, conversation context, and the shared knowledge wiki.
2. `app.mjs` and `src/` render and control the Three.js world and consume REST/WebSocket runtime events.
3. `knowledge/` contains the shared, durable project context maintained through controlled agent tools.

SQLite stores exact operational history such as agents, tasks, events, private memories, and conversation messages. Markdown stores curated project truth that should remain readable and versionable.

Context assembly is bounded. It combines agent identity, instructions, private memory, recent dialogue, relevant wiki pages, the active task, and tool policy. This creates persistent continuity without pretending to enlarge the model's native token window.

Tool-facing project modules should prefer one shared data contract across interfaces. When a workflow exists in both GUI and CLI, the GUI should write a stable manifest that the CLI can consume unchanged rather than inventing a second private format.

## Marketplace deal validation

The deal-monitor detail pass is the semantic boundary for accepting a listing.
Numeric thresholds alone are insufficient: the requested catalog id must be
present in the listing breadcrumb ids and the search term must match exact
tokens or controlled aliases in the listing title/category path. Description
text is intentionally excluded to prevent incidental words from becoming false
matches. Breadcrumb metadata is collected in the existing detail-page DOM read
and cached in SQLite, so validation adds no browser round trip and preserves the
five-second monitoring cadence. Legacy cache entries without this evidence are
refreshed once and then become reusable.

## Visual sourcing boundary

AliExpress visual sourcing is owned by `sourcing-agent`, not by
`vinted-employee`. The Project Gateway starts `aliexpress.image_search` as an
independent process with its own browser lifecycle and SQLite database
(`data/aliexpress_sourcing.db`). No Vinted scheduler, login marker, offer state,
or live monitor/browser state is imported into this workflow. A user may pass an
explicit immutable manifest of selected marketplace rows; only their IDs, links,
titles and already-extracted image references cross the boundary.

The data path is:

`reference image/folder/selected-items manifest -> local image cache -> DOM file upload -> verified visual-result transition -> card extraction -> normalization -> per-source ranking -> SQLite history -> agent-readable job output`

The result transition must change the AliExpress URL/result set before cards are
accepted. This prevents ordinary homepage recommendations from being stored as
visual matches. Each input image is identified by SHA-256 content hash; recent
results can be reused without opening a browser, and folder-watch mode processes
new images in later cycles. Candidate rows include product link/image, price,
rating, visible sold count, rank, and the originating image hash.

The GUI batch launcher owns a third process handle, separate from the normal
scrape/monitor process and the offer process. Consequently a long-running
marketplace monitor can remain active while selected images are searched. The
`aliexpress_source_items` relation preserves source listing provenance without
writing into the marketplace database.

The boundary is epistemic as well as operational: visual results are candidates,
not proof of product identity, material, authenticity, supplier reliability,
margin, or compliance. Cross-agent use is an explicit typed handoff of an image
or candidate rather than shared mutable state.

## Autonomous workflow loop

Autonomous objectives are persisted as a workflow plus an immutable task tree. The supervisor produces a dependency graph, specialist agents execute child tasks, outputs move through typed handoffs, failed attempts create retry tasks, reviewer output becomes an evaluation gate, and the supervisor synthesizes the final result. Successful trajectories create or refine reusable Markdown skills under `knowledge/skills/`; failures become reviewable wiki proposals.

## Session and prompt foundation

Direct and delegated conversations use normalized SQLite sessions and messages with FTS5 search, WAL mode, token/tool/API counters, and parent-child lineage. Prompt assembly is split into stable identity/tool/skill guidance, project context, volatile memory/session metadata, and canonical conversation messages. Threshold-based compression replaces middle history with a structured summary while retaining the first exchange and a configurable recent tail.

Provider selection is registry-based. Built-in and project JSON profiles resolve API mode, endpoint and credential environment; per-agent fallback chains preserve task and session identity across provider failure.

## Conversation orchestration model

Chat handling now follows a Hermes-inspired orchestration flow rather than a flat "send message to current agent" model.

There are four conversational outcomes:

1. `stay`: the current agent keeps the conversation.
2. `route`: the user is directly moved to a better matching agent.
3. `consult`: the current agent stays as the user-facing front agent, consults one or more specialists, and then synthesizes the final answer.
4. `clarify`: the runtime detects an ambiguous target choice and asks the user to disambiguate before routing.

Routing is hybrid:

- first pass: LLM-first router when a real provider plus valid API key is available;
- fallback: deterministic multilingual routing using agent aliases, role/capability matching, and intent keywords.

The runtime distinguishes between:

- explicit transfer requests such as "let me talk to the researcher";
- consult requests such as "ask the researcher";
- implicit specialist needs inferred from the content of the message.

### Internal conversation protocols

The conversation-routing protocol now includes:

- `chat.route`
- `chat.consult`
- `chat.strategy`
- `chat.peer-brief`
- `chat.peer-request`
- `chat.accept`
- `chat.reply`
- `chat.strategy-update`

This means inter-agent chat is a real runtime protocol with persistence and visual playback in the game.

### Consult-many behavior

`consult` is no longer limited to a single specialist. The runtime can select multiple specialists when the request spans distinct capability clusters, for example planning plus implementation.

The task record persists:

- `source_agent_id`
- `consult_agent_id`
- `consult_agent_ids`
- `route_mode`
- `consultation_notes`

Each specialist reply is appended into `consultation_notes`, and those notes are injected into the source agent prompt under `Specialist consultation notes`. This allows the source agent to synthesize a final user-facing answer from multiple internal consults.

The source agent user prompt also changes in consult mode: it explicitly states that the current agent remains the main user-facing interface, must synthesize the specialist inputs, and must not send the user away to talk to another agent.

For simulated source agents, the runtime performs a deterministic aggregate synthesis instead of surfacing only the last consulted specialist. For provider-backed agents, the model still writes the final response, but the runtime augments the result with merged specialist sources and explicit `consulted_agents` metadata so the consultation path remains structurally visible.

Routing arbitration is now asymmetric by design: explicit deterministic route requests still override weak model hesitation, and strong fallback implicit-consult evidence can also override a low-confidence LLM `stay` decision. This keeps provider-backed routing from suppressing obvious specialist handoffs.

The consultation path now carries an explicit delegation brief. Before a specialist answers, the source agent sends a `chat.plan` message containing the user goal, the routing reason, the specialist question, the expected output, the consultation position, and the synthesis goal. This makes the internal reasoning legible both to the specialist and to the frontend visualization layer.

Each chat task now also gets a first-class `strategy` thread entry before execution proceeds. This task-level artifact records the selected route mode (`stay`, `route`, `consult`, or `clarify`), the decision mode that produced it, the user-facing agent, the execution agent, the consulted specialists, the clarification question when relevant, and the concrete orchestration steps. That closes a visibility gap between high-level routing choice and per-specialist plan packets.

Strategy is no longer static. When execution changes course — for example when a weak specialist answer triggers a revision request, when a post-consult council step is enabled or skipped, or when the source agent moves into final synthesis — the runtime appends a `strategy-update` entry. This makes plan adaptation inspectable instead of hiding it inside control flow.

Those strategy artifacts now also travel through the runtime as real `chat.strategy` and `chat.strategy-update` protocol messages. That means the frontend can render strategy choice and strategy adaptation as explicit agent-to-agent traffic instead of only as local thread annotations.

The consultation path is now allowed a bounded mid-run deliberation loop before synthesis. After the initial specialist rounds, the source agent can make follow-up decisions — LLM-first when available, heuristic otherwise — to do one of three things: continue to synthesis, request an extra Memory Core recall with a more focused query built from the consultation state, or consult one additional unconsulted specialist. The loop is intentionally capped, and repeated memory follow-up is prevented, so this is still bounded rather than fully open-ended, but it moves orchestration closer to Hermes-style adaptive reasoning instead of a fixed linear consult flow.

Each chat task now also carries a persistent `discussion_log`. The runtime appends normalized thread entries for internal plan packets, specialist acceptance, specialist replies, memory recalls, and final handoff responses, and publishes a `chat.thread.updated` event each time the thread changes. This is the first step toward Hermes-style inspectable internal reasoning instead of only ephemeral speech bubbles.

The runtime now also makes synthesis explicit inside the same thread. Before the source agent writes the user-facing answer, it appends a `synthesis` entry describing that it is reconciling specialist input, and after the final answer is ready it appends a `synthesis-result` entry. That makes the final reasoning jump inspectable instead of hidden behind the last model call.

Consultation is no longer strictly single-pass. If a specialist reply is too weak for its role — for example too short, ungrounded, or missing structure — the source agent can autonomously emit a `chat.revise` follow-up turn, ask for a better answer, and store both the revision request and the revised reply in the same discussion thread. This is the first true multi-turn internal discussion loop in the runtime.

When multiple specialists are consulted, later specialists no longer work in isolation. The source agent can still pass forward brief summaries from earlier specialists as a `council-brief` context block, but the runtime now also emits a direct `chat.peer-brief` message from the previous specialist to the next one. That means the frontend can show an actual specialist-to-specialist handoff instead of only a source-mediated plan packet.

Specialists can now also originate bounded escalation. After a consult round, a specialist can emit a `chat.peer-request` asking the source agent to either bring in one more specialist, query Memory Core again, or force a council turn. The request carries a target kind plus an optional target agent id, so the runtime can distinguish “ask planner”, “pull more memory”, and “run council now” as separate control paths while still surfacing one consistent protocol primitive in the frontend.

When the bounded deliberation loop honors a specialist-originated `chat.peer-request`, the follow-up path remains visible instead of collapsing into hidden control flow. Specialist follow-ups still produce the next `chat.peer-brief` handoff, Memory Core follow-ups emit the same memory traffic used by source-originated recall, and council requests append an explicit `council-policy` entry with `specialist-request` provenance before the council turn begins. This keeps the causal chain from “specialist asked for help” to “runtime changed the plan” inspectable in both protocol traffic and thread history.

Those escalation artifacts now carry typed metadata rather than only generic prose. `chat.peer-request` and the mirrored discussion entries record the requested target kind (`specialist`, `memory`, or `council`), the resolved target label, the requesting specialist, and the decision mode. The follow-up `strategy-update` entries also preserve who requested the extra step and what kind of step was honored. That gives the frontend enough structure to render “Researcher asked for Memory Core”, “Researcher asked for Planner”, and “Researcher forced a council step” as distinct visible reasoning moves instead of flattening them into the same generic escalation bubble.

Specialist output is now surfaced as a first-class reasoning artifact rather than only as a plain summary. After a specialist reply or council reaction, the runtime emits a `chat.reasoning` protocol message and appends a `reasoning` discussion entry that records the specialist focus, the distilled conclusion, any detected concern, the suggested next step, and the council counterpart when relevant. The frontend can therefore show not only that an agent answered, but what line of reasoning it is advancing and what uncertainty or follow-up it is signaling.

The runtime now also supports a bounded council-turn phase after multi-specialist consults. Council is policy-driven rather than unconditional: the runtime first attempts an LLM council-policy decision when a provider-backed router is available, and falls back to heuristics otherwise. It then appends a `council-policy` thread entry explaining whether council was enabled, which specialists were included, the chosen turn budget, and whether the decision came from `llm` or `heuristic` mode. Only when the task looks multi-perspective enough do up to three consulted specialists exchange short follow-up reactions through `chat.council` turns. Those council notes are appended back into `consultation_notes` so the final synthesis step can incorporate cross-specialist challenge/extension rather than only raw first-pass summaries.

### Marketplace category trend scout

`vinted.brand_trend_scout` is an independent long-running Project Gateway job.
It does not share scheduling state with continuous monitoring, profile tracking,
or the deal hunter. Its comma-separated broad categories are persisted as
independent cohorts; `gioielli` is an umbrella benchmark and leaf categories are
the comparable segments. Catalog observations are persisted in dedicated cohort
tables; explicit sold markers are checked in bounded batches.

The query state machine is:

`learning -> observing -> active/promising -> paused_low_rotation -> probe`

Separate paths cover `paused_empty` and `cooldown_error`. Evaluation only uses
items old enough to complete the configured window. Explicit unavailable pages
are excluded, while transient browser errors change only the error/cooldown
state. Pauses set a future probe instead of deleting a query or its observations.
The report layer reads these tables without owning scheduler state.

### Clarification policy

When routing evidence is ambiguous between competing specialists, the runtime does not force a handoff. It can switch to `clarify` mode and return a direct disambiguation question to the user. This is the first guardrail toward confidence-aware orchestration rather than unconditional delegation.

### Source agent synthesis

When route mode is `consult`, the current agent remains the main interface. Specialist results are returned through `chat.reply`, stored in the source agent chat history, and then reused during final answer generation. For simulated agents, the runtime can directly surface the specialist result so the consult loop still behaves coherently without an external model.

Source aggregation is now multi-specialist aware: the runtime parses all `Specialist sources:` lines from `consultation_notes`, merges them with any final-result sources, and removes duplicates by URL. This prevents the final answer from silently inheriting only the last consulted specialist’s references.

Question handling is split correctly between raw and normalized text. Normalized text drives alias/capability matching, while the raw user message still controls question-sensitive routing guards, so punctuation-based policies remain effective.

### Visual runtime alignment

Frontend rendering mirrors the orchestration model:

- routed conversations can switch the open quick chat to the target agent;
- consults stay attached to the source agent as the main interface;
- protocol lines and speech bubbles above agents visualize `route`, `consult`, `plan`, `accept`, and `reply` events;
- specialist plan packets and specialist replies can appear as in-world notifications so the user can inspect what agents are asking each other and how they are structuring the handoff;
- quick chat now exposes separate `Chat` and `Discussion` views, so user-facing chat stays distinct from the internal reasoning thread while both remain live.
- the Project Gateway now has a `Threads` panel that can inspect persisted task-level discussion threads globally instead of only through the per-agent popup.
- strategy entries are rendered in both the per-agent `Discussion` popup and the global `Threads` panel with route mode, decision mode, consulted agents, and explicit execution steps.
- `strategy-update`, `revise`, `revision-result`, `council-policy`, `council-turn`, `synthesis`, and `memory` thread entries now also produce in-world speech bubbles and toast notifications, so reasoning-state changes are visible in the game as they happen rather than only after inspection.
- when the bounded follow-up step triggers, the same visible runtime path is reused: extra specialist consults emit `chat.plan`, `chat.accept`, and `chat.reply` traffic, while extra memory requests emit `memory.recall` traffic and strategy-update notifications before synthesis.
- accepted/running runtime tasks and started Project Gateway jobs claim an explicit in-world work assignment. The agent routes to its linked workstation (or role station), suppresses idle wandering while one or more work IDs remain active, then releases back to normal positioning at a terminal state.

### Game layout editor and job notifications

- Room sculpting is a fixed-intent paint/erase stroke: dragging across tiles never toggles a tile twice or unexpectedly switches from adding to erasing. A whole stroke is one undo step.
- Room cells remain cardinally connected and cannot overlap another room; removing a tile that splits the room is rejected. Door/path tiles must start at a room or an existing path, stay outside room interiors, and cannot be removed singly if that strands another segment. A drag erase prunes any segment it disconnects.
- The room editor keeps reversible layout edits in a bounded in-memory history. Room shapes, doors, workstations, and agent/table placement share one undo/redo path; successful edits continue to persist to local storage.
- Undo/redo restores the layout model first, then rebuilds room, door, and workstation visuals so the scene cannot retain deleted custom workstation props.
- Job completion notifications use a persistent local notification state. The initial job-history fetch establishes a baseline; new terminal jobs are deduplicated by job ID and remain unread across reloads until the user opens the notifications history.
- The badge counts both completed and failed jobs, updates its accessible label, and only pulses when unread count increases. In-world toasts deduplicate keyed events and are capped to avoid stacking without bound.
