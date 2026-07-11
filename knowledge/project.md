# Agent Protocol Lab 3D

Agent Protocol Lab is a local-first multi-agent control room presented as a Three.js simulation. The Python runtime is the source of truth for agents, tasks, protocols, conversations, tools, provider execution, and persistence. The browser visualizes that runtime and provides configuration and direct chat controls.

## Product principles

- Agents have explicit identities, capabilities, protocols, tools, limits, approvals, and providers.
- Direct conversations must retain continuity across restarts.
- Shared knowledge is durable, inspectable Markdown rather than hidden model state.
- Provider adapters may use Codex CLI, OpenAI Responses, compatible APIs, or the deterministic simulator.
- API keys stay in environment variables and are never written to agent configuration.
