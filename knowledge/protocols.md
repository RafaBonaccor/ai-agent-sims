# Knowledge protocol

1. Retrieve relevant canonical pages before reasoning about existing project decisions.
2. Treat raw conversation as chronological evidence, not verified shared truth.
3. Store agent-specific preferences and observations in private memory.
4. Submit durable project discoveries through `wiki_propose` with a clear title and source task.
5. Memory or supervisor agents validate proposals for correctness, duplication, freshness, and conflicts.
6. Validated knowledge is written to a focused canonical page with `wiki_update`.
7. Prefer updating an existing page over creating overlapping knowledge.

## Delegation protocol

1. A supervisor creates a dependency-safe plan and emits `plan.created`.
2. Work begins with `delegation.request`; the selected specialist responds through `delegation.accepted`.
3. Completed dependency outputs move through `delegation.handoff` before downstream execution.
4. Results return through `delegation.result`; transient failures emit `delegation.retry` and create a new task attempt.
5. Reviewer evidence is recorded in `evaluation.result` before final synthesis.
6. Successful trajectories are compiled into reusable skills; failures are proposed as lessons for Memory review.
