import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from agent_runtime.engine import AgentRuntime
from agent_runtime.knowledge import KnowledgeWiki
from agent_runtime.models import (
    AgentDefinition,
    AgentChatMessage,
    ApprovalPolicy,
    MemoryUpdate,
    MessageEnvelope,
    ModelSettings,
    SystemSettings,
    SystemUiSettings,
    TaskCreate,
    TaskRecord,
    TaskState,
)
from agent_runtime.protocols import validate_message


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        database = Path(self.temporary_directory.name) / "runtime.db"
        self.runtime = AgentRuntime(database, simulation_delay=0)
        self.runtime.executor.workspace_root = Path(self.temporary_directory.name)
        self.runtime.knowledge_wiki = KnowledgeWiki(Path(self.temporary_directory.name) / "data" / "wiki")
        self.runtime.executor.wiki = self.runtime.knowledge_wiki
        self.runtime.executor.tools.wiki = self.runtime.knowledge_wiki
        await self.runtime.add_agent(
            AgentDefinition(
                id="supervisor",
                name="Supervisor",
                role="supervisor",
                capabilities=["routing"],
            )
        )
        await self.runtime.add_agent(
            AgentDefinition(
                id="analyst",
                name="Analyst",
                role="specialist",
                capabilities=["analysis"],
            )
        )
        await self.runtime.add_agent(
            AgentDefinition(
                id="researcher",
                name="Researcher",
                role="specialist",
                capabilities=["research"],
            )
        )

    async def asyncTearDown(self):
        await self.runtime.shutdown()
        self.temporary_directory.cleanup()

    async def test_task_runs_through_valid_lifecycle(self):
        task = await self.runtime.create_task(
            TaskCreate(title="Analyze runtime events", capability="analysis")
        )
        await asyncio.gather(*tuple(self.runtime.running_jobs))

        completed = self.runtime.tasks[task.id]
        self.assertEqual(TaskState.COMPLETED, completed.state)
        self.assertEqual("analyst", completed.assigned_agent_id)
        self.assertEqual("simulated", completed.result["provider"])
        self.assertEqual("native-simulator", completed.result["model"])

        event_types = [event.type for event in self.runtime.store.recent_events(100)]
        self.assertIn("protocol.message", event_types)
        self.assertIn("agent.state.changed", event_types)
        self.assertIn("task.state.changed", event_types)

    async def test_agents_are_persisted(self):
        self.assertEqual({"supervisor", "analyst", "researcher"}, set(self.runtime.agents))
        loaded = self.runtime.store.load_agents()
        self.assertEqual({"supervisor", "analyst", "researcher"}, {agent.id for agent in loaded})

    async def test_system_settings_apply_to_existing_and_new_agents(self):
        settings = await self.runtime.update_system_settings(
            SystemSettings(
                configured=True,
                model=ModelSettings(
                    provider="openai",
                    model="gpt-5.5",
                    base_url="https://api.openai.com/v1",
                    api_key_env="OPENAI_API_KEY",
                    api_key_scope="project",
                    temperature=0.4,
                ),
                ui=SystemUiSettings(theme="light", auto_agents=False, simulation_speed=2),
            )
        )

        self.assertTrue(settings.configured)
        self.assertEqual("openai", self.runtime.agents["analyst"].model.provider)
        self.assertEqual("gpt-5.5", self.runtime.agents["researcher"].model.model)
        persisted = self.runtime.store.load_system_settings()
        self.assertEqual("light", persisted.ui.theme)
        self.assertFalse(persisted.ui.auto_agents)

        created = await self.runtime.add_agent(
            AgentDefinition(
                id="planner",
                name="Planner",
                role="planner",
                capabilities=["planning"],
            )
        )
        self.assertEqual("openai", created.model.provider)
        self.assertEqual("OPENAI_API_KEY", created.model.api_key_env)

    async def test_missing_seed_agents_are_added_without_overwriting_existing_agents(self):
        seed_path = Path(self.temporary_directory.name) / "agents.json"
        seed_path.write_text(
            json.dumps(
                [
                    {
                        "id": "analyst",
                        "name": "Seed Analyst",
                        "role": "specialist",
                        "instructions": "Do not overwrite existing analyst.",
                    },
                    {
                        "id": "ai-news-navigator",
                        "name": "AI News Navigator",
                        "role": "web-navigator",
                        "capabilities": ["news"],
                    },
                ]
            ),
            encoding="utf-8",
        )

        await self.runtime.shutdown()
        database = Path(self.temporary_directory.name) / "runtime.db"
        self.runtime = AgentRuntime(database, seed_path=seed_path, simulation_delay=0)

        self.assertIn("ai-news-navigator", self.runtime.agents)
        self.assertEqual("Analyst", self.runtime.agents["analyst"].name)

    async def test_chat_history_is_scoped_to_requested_agent(self):
        task = await self.runtime.create_task(
            TaskCreate(
                title="Explain the result",
                description="Explain the result",
                requested_agent_id="analyst",
                channel="chat",
            )
        )
        await asyncio.gather(*tuple(self.runtime.running_jobs))

        history = self.runtime.get_agent_chat("analyst")
        self.assertEqual(["user", "assistant"], [message.role for message in history])
        self.assertEqual(task.id, history[0].task_id)
        self.assertEqual("Explain the result", history[0].content)
        self.assertIn("modalità simulata locale", history[1].content)
        self.assertIn("Explain the result", history[1].content)
        self.assertEqual([], self.runtime.get_agent_chat("supervisor"))
        completed = self.runtime.tasks[task.id]
        strategy = next((entry for entry in completed.discussion_log if entry.get("kind") == "strategy"), None)
        self.assertIsNotNone(strategy)
        self.assertEqual("stay", strategy.get("extra", {}).get("route_mode"))
        self.assertEqual("stay", strategy.get("extra", {}).get("decision_mode"))

    async def test_chat_is_routed_to_named_agent_in_italian(self):
        task = await self.runtime.create_task(
            TaskCreate(
                title="Need research",
                description="Devi parlare con il researcher e chiedergli di cercare trend AI in Europa.",
                requested_agent_id="analyst",
                channel="chat",
            )
        )
        await asyncio.gather(*tuple(self.runtime.running_jobs))

        routed = self.runtime.tasks[task.id]
        self.assertEqual("analyst", routed.source_agent_id)
        self.assertEqual("researcher", routed.consult_agent_id)
        self.assertEqual("analyst", routed.requested_agent_id)
        self.assertEqual("analyst", routed.assigned_agent_id)
        self.assertEqual("consult", routed.route_mode)
        self.assertEqual("research", routed.capability)
        self.assertTrue(routed.route_reason)
        strategy = next((entry for entry in routed.discussion_log if entry.get("kind") == "strategy"), None)
        self.assertIsNotNone(strategy)
        self.assertEqual("consult", strategy.get("extra", {}).get("route_mode"))
        self.assertIn("researcher", strategy.get("extra", {}).get("consult_agent_ids", []))

        recent_events = self.runtime.store.recent_events(80)
        self.assertTrue(any(event.type == "chat.routed" for event in recent_events))
        self.assertTrue(
            any(
                event.type == "protocol.message"
                and event.data.get("message", {}).get("type") == "chat.consult"
                for event in recent_events
            )
        )
        self.assertTrue(
            any(
                event.type == "protocol.message"
                and event.data.get("message", {}).get("type") == "chat.plan"
                and event.data.get("message", {}).get("payload", {}).get("specialist_question")
                for event in recent_events
            )
        )
        self.assertTrue(
            any(
                event.type == "protocol.message"
                and event.data.get("message", {}).get("type") == "chat.strategy"
                for event in recent_events
            )
        )

        analyst_history = self.runtime.get_agent_chat("analyst")
        self.assertTrue(any("Routing this conversation to Researcher." in message.content for message in analyst_history))
        researcher_history = self.runtime.get_agent_chat("researcher")
        self.assertTrue(any("consult requested by Analyst" in message.content for message in researcher_history))

    async def test_chat_is_implicitly_routed_to_best_agent_from_capability_intent(self):
        task = await self.runtime.create_task(
            TaskCreate(
                title="Help me",
                description="Mi serve una ricerca con fonti affidabili sugli ultimi trend AI in Europa.",
                requested_agent_id="analyst",
                channel="chat",
            )
        )
        await asyncio.gather(*tuple(self.runtime.running_jobs))

        routed = self.runtime.tasks[task.id]
        self.assertEqual("analyst", routed.source_agent_id)
        self.assertEqual("researcher", routed.consult_agent_id)
        self.assertEqual("analyst", routed.requested_agent_id)
        self.assertEqual("analyst", routed.assigned_agent_id)
        self.assertEqual("consult", routed.route_mode)
        self.assertIn("better suited", routed.route_reason)
        self.assertIn("Consulted specialist: Researcher", routed.consultation_notes)

    async def test_chat_can_directly_route_user_to_target_agent(self):
        task = await self.runtime.create_task(
            TaskCreate(
                title="Switch chat",
                description="Fammi parlare con il researcher.",
                requested_agent_id="analyst",
                channel="chat",
            )
        )
        await asyncio.gather(*tuple(self.runtime.running_jobs))

        routed = self.runtime.tasks[task.id]
        self.assertEqual("route", routed.route_mode)
        self.assertEqual("researcher", routed.requested_agent_id)
        self.assertEqual("researcher", routed.assigned_agent_id)

    async def test_routed_chat_returns_reply_to_source_agent_history(self):
        task = await self.runtime.create_task(
            TaskCreate(
                title="Need research",
                description="Parla con il researcher e chiedigli una ricerca sulle startup AI europee.",
                requested_agent_id="analyst",
                channel="chat",
            )
        )
        await asyncio.gather(*tuple(self.runtime.running_jobs))

        analyst_history = self.runtime.get_agent_chat("analyst")
        returned = [message for message in analyst_history if message.id in {f"{task.id}-handoff-return", f"{task.id}-consult-note"}]
        self.assertEqual(1, len(returned))
        self.assertTrue(returned[0].content)

        events = self.runtime.store.recent_events(80)
        self.assertTrue(any(event.type in {"chat.returned", "chat.consulted"} for event in events))
        self.assertTrue(
            any(
                event.type == "protocol.message"
                and event.data.get("message", {}).get("type") in {"chat.reply", "chat.consult", "chat.plan"}
                for event in events
            )
        )

    async def test_chat_can_consult_multiple_specialists(self):
        await self.runtime.add_agent(
            AgentDefinition(
                id="planner",
                name="Planner",
                role="planner",
                capabilities=["planning", "decomposition"],
            )
        )
        await self.runtime.add_agent(
            AgentDefinition(
                id="builder",
                name="Builder",
                role="builder",
                capabilities=["implementation", "integration"],
            )
        )
        task = await self.runtime.create_task(
            TaskCreate(
                title="Ship feature",
                description="Organizza i prossimi step e poi implementa la modifica nel progetto.",
                requested_agent_id="analyst",
                channel="chat",
            )
        )
        await asyncio.gather(*tuple(self.runtime.running_jobs))

        routed = self.runtime.tasks[task.id]
        self.assertEqual("consult", routed.route_mode)
        self.assertGreaterEqual(len(routed.consult_agent_ids), 2)
        self.assertTrue({"planner", "builder"}.issubset(set(routed.consult_agent_ids)))
        self.assertIn("Consulted specialist: Planner", routed.consultation_notes)
        self.assertIn("Consulted specialist: Builder", routed.consultation_notes)
        self.assertIn("I consulted the relevant specialists.", routed.result["summary"])
        self.assertIn("consulted_agents", routed.result)
        self.assertIn("Planner", routed.result["consulted_agents"])
        self.assertIn("Builder", routed.result["consulted_agents"])
        self.assertTrue(any(entry.get("kind") == "council-policy" for entry in routed.discussion_log))
        council_policy = next(entry for entry in routed.discussion_log if entry.get("kind") == "council-policy")
        self.assertTrue(council_policy.get("extra", {}).get("enabled"))
        self.assertGreaterEqual(int(council_policy.get("extra", {}).get("max_turns", 0)), 1)
        self.assertTrue(any(
            entry.get("kind") == "strategy-update"
            and entry.get("extra", {}).get("phase") == "council"
            for entry in routed.discussion_log
        ))
        self.assertTrue(any(entry.get("kind") == "peer-brief" for entry in routed.discussion_log))
        self.assertTrue(any(entry.get("kind") == "council-brief" for entry in routed.discussion_log))
        self.assertTrue(any(entry.get("kind") == "council-turn-request" for entry in routed.discussion_log))
        self.assertTrue(any(entry.get("kind") == "council-turn" for entry in routed.discussion_log))
        recent_events = self.runtime.store.recent_events(120)
        plan_messages = [
            event.data.get("message", {})
            for event in recent_events
            if event.type == "protocol.message"
            and event.data.get("message", {}).get("type") == "chat.plan"
        ]
        self.assertGreaterEqual(len(plan_messages), 2)
        self.assertTrue(any(message.get("payload", {}).get("consult_position") == "1/2" for message in plan_messages))
        self.assertTrue(any(message.get("payload", {}).get("consult_position") == "2/2" for message in plan_messages))
        self.assertTrue(
            any(
                event.type == "protocol.message"
                and event.data.get("message", {}).get("type") == "chat.peer-brief"
                for event in recent_events
            )
        )
        self.assertTrue(
            any(
                event.type == "protocol.message"
                and event.data.get("message", {}).get("type") == "chat.council"
                for event in recent_events
            )
        )

    async def test_llm_council_policy_can_override_heuristic_selection(self):
        await self.runtime.add_agent(
            AgentDefinition(
                id="planner",
                name="Planner",
                role="planner",
                capabilities=["planning", "decomposition"],
            )
        )
        await self.runtime.add_agent(
            AgentDefinition(
                id="builder",
                name="Builder",
                role="builder",
                capabilities=["implementation", "integration"],
            )
        )
        original = self.runtime.executor.decide_council_policy_with_reasoning
        self.runtime.executor.decide_council_policy_with_reasoning = lambda *args, **kwargs: {
            "enabled": True,
            "reason": "LLM selected a narrow council.",
            "participant_ids": ["planner", "builder"],
            "max_turns": 1,
            "decision_mode": "llm",
        }
        try:
            task = await self.runtime.create_task(
                TaskCreate(
                    title="Ship feature",
                    description="Organizza i prossimi step e poi implementa la modifica nel progetto.",
                    requested_agent_id="analyst",
                    channel="chat",
                )
            )
            await asyncio.gather(*tuple(self.runtime.running_jobs))
        finally:
            self.runtime.executor.decide_council_policy_with_reasoning = original

        routed = self.runtime.tasks[task.id]
        policy = next(entry for entry in routed.discussion_log if entry.get("kind") == "council-policy")
        self.assertEqual("llm", policy.get("extra", {}).get("decision_mode"))
        self.assertEqual(1, int(policy.get("extra", {}).get("max_turns", 0)))
        self.assertEqual(["planner", "builder"], policy.get("extra", {}).get("participants"))

    async def test_followup_decision_can_add_one_more_specialist_before_synthesis(self):
        await self.runtime.add_agent(
            AgentDefinition(
                id="planner",
                name="Planner",
                role="planner",
                capabilities=["planning", "decomposition"],
            )
        )
        original = self.runtime.executor.decide_consult_followup_with_reasoning
        self.runtime.executor.decide_consult_followup_with_reasoning = lambda *args, **kwargs: {
            "action": "consult",
            "reason": "Add the planner before synthesis.",
            "target_agent_id": "planner",
            "decision_mode": "llm",
        }
        try:
            task = await self.runtime.create_task(
                TaskCreate(
                    title="Need research",
                    description="Parla con il researcher e chiedigli una ricerca sulle startup AI europee.",
                    requested_agent_id="analyst",
                    channel="chat",
                )
            )
            await asyncio.gather(*tuple(self.runtime.running_jobs))
        finally:
            self.runtime.executor.decide_consult_followup_with_reasoning = original

        routed = self.runtime.tasks[task.id]
        self.assertIn("planner", routed.consult_agent_ids)
        self.assertIn("Consulted specialist: Planner", routed.consultation_notes)
        self.assertTrue(any(
            entry.get("kind") == "strategy-update"
            and entry.get("extra", {}).get("phase") == "followup-consult"
            for entry in routed.discussion_log
        ))
        self.assertTrue(any(entry.get("kind") == "peer-brief" for entry in routed.discussion_log))
        recent_events = self.runtime.store.recent_events(160)
        self.assertTrue(
            any(
                event.type == "protocol.message"
                and event.data.get("message", {}).get("type") == "chat.plan"
                and event.data.get("message", {}).get("recipient") == "planner"
                for event in recent_events
            )
        )
        self.assertTrue(
            any(
                event.type == "protocol.message"
                and event.data.get("message", {}).get("type") == "chat.peer-brief"
                and event.data.get("message", {}).get("recipient") == "planner"
                for event in recent_events
            )
        )

    async def test_specialist_can_request_peer_escalation_before_synthesis(self):
        await self.runtime.add_agent(
            AgentDefinition(
                id="planner",
                name="Planner",
                role="planner",
                capabilities=["planning", "decomposition"],
            )
        )
        original_peer = self.runtime.executor.decide_peer_escalation_with_reasoning
        original_followup = self.runtime.executor.decide_consult_followup_with_reasoning
        self.runtime.executor.decide_peer_escalation_with_reasoning = lambda *args, **kwargs: {
            "action": "request",
            "reason": "A planner should structure the next steps from this research.",
            "target_agent_id": "planner",
            "decision_mode": "llm",
        }
        self.runtime.executor.decide_consult_followup_with_reasoning = lambda *args, **kwargs: {
            "action": "synthesize",
            "reason": "No extra source-level follow-up needed.",
            "target_agent_id": "",
            "decision_mode": "llm",
        }
        try:
            task = await self.runtime.create_task(
                TaskCreate(
                    title="Need research",
                    description="Parla con il researcher e chiedigli una ricerca sulle startup AI europee.",
                    requested_agent_id="analyst",
                    channel="chat",
                )
            )
            await asyncio.gather(*tuple(self.runtime.running_jobs))
        finally:
            self.runtime.executor.decide_peer_escalation_with_reasoning = original_peer
            self.runtime.executor.decide_consult_followup_with_reasoning = original_followup

        routed = self.runtime.tasks[task.id]
        self.assertIn("planner", routed.consult_agent_ids)
        peer_request_entry = next(entry for entry in routed.discussion_log if entry.get("kind") == "peer-request")
        self.assertEqual("specialist", peer_request_entry.get("extra", {}).get("target_kind"))
        self.assertEqual("planner", peer_request_entry.get("extra", {}).get("target_agent_id"))
        self.assertEqual("Planner", peer_request_entry.get("extra", {}).get("target_label"))
        self.assertEqual("researcher", peer_request_entry.get("extra", {}).get("requested_by_agent_id"))
        recent_events = self.runtime.store.recent_events(200)
        self.assertTrue(
            any(
                event.type == "protocol.message"
                and event.data.get("message", {}).get("type") == "chat.peer-request"
                and event.data.get("message", {}).get("sender") == "researcher"
                and event.data.get("message", {}).get("recipient") == "analyst"
                and event.data.get("message", {}).get("payload", {}).get("target_label") == "Planner"
                for event in recent_events
            )
        )

    async def test_specialist_can_request_memory_before_synthesis(self):
        await self.runtime.add_agent(
            AgentDefinition(
                id="memory",
                name="Memory Core",
                role="memory",
                capabilities=["memory", "recall"],
                toolsets=["memory"],
            )
        )
        wiki_root = Path(self.temporary_directory.name) / "data" / "wiki"
        wiki_root.mkdir(parents=True, exist_ok=True)
        (wiki_root / "peer-memory.md").write_text(
            "# Memory\n\n## Shared context\nMemory Core knows the prior project context.\n",
            encoding="utf-8",
        )
        original_peer = self.runtime.executor.decide_peer_escalation_with_reasoning
        original_followup = self.runtime.executor.decide_consult_followup_with_reasoning
        self.runtime.executor.decide_peer_escalation_with_reasoning = lambda *args, **kwargs: {
            "action": "request",
            "reason": "Need Memory Core context before synthesis.",
            "target_kind": "memory",
            "target_agent_id": "memory",
            "decision_mode": "llm",
        }
        self.runtime.executor.decide_consult_followup_with_reasoning = lambda *args, **kwargs: {
            "action": "synthesize",
            "reason": "No extra source-level follow-up needed.",
            "target_agent_id": "",
            "decision_mode": "llm",
        }
        try:
            task = await self.runtime.create_task(
                TaskCreate(
                    title="Need research",
                    description="Parla con il researcher e ricordati del contesto del progetto.",
                    requested_agent_id="analyst",
                    channel="chat",
                )
            )
            await asyncio.gather(*tuple(self.runtime.running_jobs))
        finally:
            self.runtime.executor.decide_peer_escalation_with_reasoning = original_peer
            self.runtime.executor.decide_consult_followup_with_reasoning = original_followup

        routed = self.runtime.tasks[task.id]
        self.assertIn("Memory Core follow-up context:", routed.consultation_notes)
        peer_request_entry = next(entry for entry in routed.discussion_log if entry.get("kind") == "peer-request")
        self.assertEqual("memory", peer_request_entry.get("extra", {}).get("target_kind"))
        self.assertEqual("Memory Core", peer_request_entry.get("extra", {}).get("target_label"))
        self.assertEqual("researcher", peer_request_entry.get("extra", {}).get("requested_by_agent_id"))
        strategy_update = next(
            entry
            for entry in routed.discussion_log
            if entry.get("kind") == "strategy-update" and entry.get("extra", {}).get("phase") == "memory-followup"
        )
        self.assertEqual("memory", strategy_update.get("extra", {}).get("followup_target_kind"))
        self.assertEqual("Memory Core", strategy_update.get("extra", {}).get("followup_target_label"))
        self.assertEqual("researcher", strategy_update.get("extra", {}).get("followup_requested_by_agent_id"))
        recent_events = self.runtime.store.recent_events(220)
        self.assertTrue(
            any(
                event.type == "protocol.message"
                and event.data.get("message", {}).get("type") == "chat.peer-request"
                and event.data.get("message", {}).get("payload", {}).get("target_kind") == "memory"
                and event.data.get("message", {}).get("payload", {}).get("target_label") == "Memory Core"
                for event in recent_events
            )
        )

    async def test_specialist_can_request_council_before_synthesis(self):
        await self.runtime.add_agent(
            AgentDefinition(
                id="planner",
                name="Planner",
                role="planner",
                capabilities=["planning", "decomposition"],
            )
        )
        original_peer = self.runtime.executor.decide_peer_escalation_with_reasoning
        original_followup = self.runtime.executor.decide_consult_followup_with_reasoning
        self.runtime.executor.decide_peer_escalation_with_reasoning = lambda *args, **kwargs: {
            "action": "request",
            "reason": "Run a council before synthesis.",
            "target_kind": "council",
            "target_agent_id": "",
            "decision_mode": "llm",
        }
        self.runtime.executor.decide_consult_followup_with_reasoning = lambda *args, **kwargs: {
            "action": "consult",
            "reason": "Also consult the planner.",
            "target_agent_id": "planner",
            "decision_mode": "llm",
        }
        try:
            task = await self.runtime.create_task(
                TaskCreate(
                    title="Need research and plan",
                    description="Parla con il researcher, poi organizza i prossimi step.",
                    requested_agent_id="analyst",
                    channel="chat",
                )
            )
            await asyncio.gather(*tuple(self.runtime.running_jobs))
        finally:
            self.runtime.executor.decide_peer_escalation_with_reasoning = original_peer
            self.runtime.executor.decide_consult_followup_with_reasoning = original_followup

        routed = self.runtime.tasks[task.id]
        policy = next(entry for entry in routed.discussion_log if entry.get("kind") == "council-policy")
        self.assertEqual("specialist-request", policy.get("extra", {}).get("decision_mode"))
        self.assertEqual("researcher", policy.get("extra", {}).get("requested_by_agent_id"))
        peer_request_entry = next(entry for entry in routed.discussion_log if entry.get("kind") == "peer-request")
        self.assertEqual("council", peer_request_entry.get("extra", {}).get("target_kind"))
        self.assertEqual("Council", peer_request_entry.get("extra", {}).get("target_label"))
        self.assertEqual("researcher", peer_request_entry.get("extra", {}).get("requested_by_agent_id"))
        strategy_update = next(
            entry
            for entry in routed.discussion_log
            if entry.get("kind") == "strategy-update" and entry.get("extra", {}).get("phase") == "council-request"
        )
        self.assertEqual("council", strategy_update.get("extra", {}).get("followup_target_kind"))
        self.assertEqual("Council", strategy_update.get("extra", {}).get("followup_target_label"))
        self.assertEqual("researcher", strategy_update.get("extra", {}).get("followup_requested_by_agent_id"))
        recent_events = self.runtime.store.recent_events(260)
        self.assertTrue(
            any(
                event.type == "protocol.message"
                and event.data.get("message", {}).get("type") == "chat.peer-request"
                and event.data.get("message", {}).get("payload", {}).get("target_kind") == "council"
                and event.data.get("message", {}).get("payload", {}).get("target_label") == "Council"
                for event in recent_events
            )
        )

    async def test_followup_decision_can_request_extra_memory_before_synthesis(self):
        await self.runtime.add_agent(
            AgentDefinition(
                id="memory",
                name="Memory Core",
                role="memory",
                capabilities=["memory", "recall"],
                toolsets=["memory"],
            )
        )
        wiki_root = Path(self.temporary_directory.name) / "data" / "wiki"
        wiki_root.mkdir(parents=True, exist_ok=True)
        (wiki_root / "memory-followup.md").write_text(
            "# Retrieval\n\n## Prior context\nThe project already uses Memory Core as the shared context broker.\n",
            encoding="utf-8",
        )
        original = self.runtime.executor.decide_consult_followup_with_reasoning
        self.runtime.executor.decide_consult_followup_with_reasoning = lambda *args, **kwargs: {
            "action": "memory",
            "reason": "Ask Memory Core for deeper project context before synthesis.",
            "target_agent_id": "",
            "decision_mode": "llm",
        }
        try:
            task = await self.runtime.create_task(
                TaskCreate(
                    title="Need research",
                    description="Parla con il researcher e chiedigli una ricerca sulle startup AI europee.",
                    requested_agent_id="analyst",
                    channel="chat",
                )
            )
            await asyncio.gather(*tuple(self.runtime.running_jobs))
        finally:
            self.runtime.executor.decide_consult_followup_with_reasoning = original

        routed = self.runtime.tasks[task.id]
        self.assertIn("Memory Core follow-up context:", routed.consultation_notes)
        self.assertTrue(any(
            entry.get("kind") == "strategy-update"
            and entry.get("extra", {}).get("phase") == "memory-followup"
            for entry in routed.discussion_log
        ))
        memory_entries = [entry for entry in routed.discussion_log if entry.get("kind") == "memory"]
        self.assertGreaterEqual(len(memory_entries), 2)

    async def test_consult_flow_persists_internal_discussion_thread(self):
        task = await self.runtime.create_task(
            TaskCreate(
                title="Need research",
                description="Parla con il researcher e chiedigli una ricerca sulle startup AI europee.",
                requested_agent_id="analyst",
                channel="chat",
            )
        )
        await asyncio.gather(*tuple(self.runtime.running_jobs))

        routed = self.runtime.tasks[task.id]
        self.assertTrue(routed.discussion_log)
        self.assertTrue(any(entry.get("kind") == "strategy" for entry in routed.discussion_log))
        self.assertTrue(any(
            entry.get("kind") == "strategy-update"
            and entry.get("extra", {}).get("phase") in {"post-consult", "synthesis"}
            for entry in routed.discussion_log
        ))
        self.assertTrue(any(entry.get("kind") == "plan" for entry in routed.discussion_log))
        self.assertTrue(any(entry.get("kind") == "accept" for entry in routed.discussion_log))
        self.assertTrue(any(entry.get("kind") == "reply" for entry in routed.discussion_log))
        reasoning_entry = next(entry for entry in routed.discussion_log if entry.get("kind") == "reasoning")
        self.assertEqual("consult", reasoning_entry.get("extra", {}).get("reasoning_type"))
        self.assertTrue(reasoning_entry.get("extra", {}).get("focus"))
        self.assertTrue(reasoning_entry.get("extra", {}).get("next_step"))
        self.assertTrue(any(entry.get("kind") == "council-policy" for entry in routed.discussion_log))
        council_policy = next(entry for entry in routed.discussion_log if entry.get("kind") == "council-policy")
        self.assertFalse(council_policy.get("extra", {}).get("enabled"))
        self.assertEqual(0, int(council_policy.get("extra", {}).get("max_turns", 0)))
        self.assertTrue(any(entry.get("kind") == "synthesis" for entry in routed.discussion_log))
        self.assertTrue(any(entry.get("kind") == "synthesis-result" for entry in routed.discussion_log))

        events = self.runtime.store.recent_events(120)
        thread_updates = [
            event for event in events
            if event.type == "chat.thread.updated"
            and event.task_id == task.id
        ]
        self.assertTrue(thread_updates)
        self.assertTrue(any(event.data.get("entry", {}).get("kind") == "reply" for event in thread_updates))
        self.assertTrue(any(event.data.get("entry", {}).get("kind") == "reasoning" for event in thread_updates))
        self.assertTrue(
            any(
                event.type == "protocol.message"
                and event.data.get("message", {}).get("type") == "chat.reasoning"
                and event.task_id == task.id
                for event in events
            )
        )

    async def test_weak_specialist_reply_triggers_autonomous_revision_turn(self):
        original_run = self.runtime.executor.run
        calls = {"researcher": 0}

        async def fake_run(agent, task, emit, memory_briefing=""):
            if agent.id == "researcher":
                calls["researcher"] += 1
                if calls["researcher"] == 1:
                    return {
                        "summary": "Very short answer.",
                        "provider": "simulated",
                        "model": agent.model.model,
                        "tool_calls": 0,
                        "sources": [],
                    }
                return {
                    "summary": "Expanded answer with concrete detail and a source-backed revision for the source agent to use.",
                    "provider": "simulated",
                    "model": agent.model.model,
                    "tool_calls": 0,
                    "sources": [{"url": "https://example.test/revised", "title": "Revised source"}],
                }
            return await original_run(agent, task, emit, memory_briefing=memory_briefing)

        self.runtime.executor.run = fake_run
        try:
            task = await self.runtime.create_task(
                TaskCreate(
                    title="Need research",
                    description="Parla con il researcher e chiedigli una ricerca sulle startup AI europee.",
                    requested_agent_id="analyst",
                    channel="chat",
                )
            )
            await asyncio.gather(*tuple(self.runtime.running_jobs))
        finally:
            self.runtime.executor.run = original_run

        routed = self.runtime.tasks[task.id]
        self.assertGreaterEqual(calls["researcher"], 2)
        self.assertTrue(any(entry.get("kind") == "revise" for entry in routed.discussion_log))
        self.assertTrue(any(entry.get("kind") == "revision-result" for entry in routed.discussion_log))
        self.assertTrue(any(
            entry.get("kind") == "strategy-update"
            and entry.get("extra", {}).get("phase") == "revision"
            for entry in routed.discussion_log
        ))

        events = self.runtime.store.recent_events(160)
        self.assertTrue(
            any(
                event.type == "protocol.message"
                and event.data.get("message", {}).get("type") == "chat.revise"
                for event in events
            )
        )
        self.assertTrue(
            any(
                event.type == "protocol.message"
                and event.data.get("message", {}).get("type") == "chat.strategy-update"
                for event in events
            )
        )

    async def test_consult_prompt_explicitly_requires_final_synthesis(self):
        task = TaskRecord(
            title="Need research synthesis",
            description="Explain the market situation.",
            requested_agent_id="analyst",
            channel="chat",
            route_mode="consult",
            consult_agent_ids=["researcher"],
        )

        prompt = self.runtime.executor._build_user_prompt(task)
        self.assertIn("You are the main user-facing agent.", prompt)
        self.assertIn("Do not tell the user to talk to another agent.", prompt)
        self.assertIn("researcher", prompt)

    async def test_consultation_source_merge_keeps_all_specialist_sources(self):
        task = TaskRecord(
            title="Need synthesis",
            description="Need synthesis",
            requested_agent_id="analyst",
            channel="chat",
            route_mode="consult",
            consult_agent_ids=["researcher", "analyst"],
            consultation_notes=(
                "Consulted specialist: Researcher (researcher)\n"
                "Specialist summary: First source.\n"
                "Specialist sources: https://example.test/a, https://example.test/b\n\n"
                "Consulted specialist: Analyst (analyst)\n"
                "Specialist summary: Second source.\n"
                "Specialist sources: https://example.test/c"
            ),
        )

        merged = self.runtime._merge_consultation_sources(
            task,
            {"sources": [{"url": "https://example.test/final", "title": "Final"}]},
            {"sources": [{"url": "https://example.test/d", "title": "D"}]},
        )
        self.assertEqual(
            {
                "https://example.test/a",
                "https://example.test/b",
                "https://example.test/c",
                "https://example.test/d",
                "https://example.test/final",
            },
            {item["url"] for item in merged},
        )

    async def test_router_does_not_implicitly_route_plain_questions(self):
        decision = self.runtime.router.route_chat(
            TaskRecord(
                title="Question",
                description="Can you research AI trends in Europe?",
                requested_agent_id="analyst",
                channel="chat",
            ),
            self.runtime.agents,
        )
        self.assertFalse(decision.should_route)

    def test_conversation_routing_protocol_accepts_chat_plan(self):
        validate_message(
            MessageEnvelope(
                type="chat.plan",
                protocol="conversation-routing",
                sender="analyst",
                recipient="researcher",
                correlation_id="corr-1",
                payload={"specialist_question": "Research this topic."},
            )
        )

    def test_conversation_routing_protocol_accepts_chat_strategy(self):
        validate_message(
            MessageEnvelope(
                type="chat.strategy",
                protocol="conversation-routing",
                sender="analyst",
                recipient="researcher",
                correlation_id="corr-strategy",
                payload={"strategy_summary": "Consult the researcher, then synthesize."},
            )
        )

    def test_conversation_routing_protocol_accepts_chat_peer_brief(self):
        validate_message(
            MessageEnvelope(
                type="chat.peer-brief",
                protocol="conversation-routing",
                sender="researcher",
                recipient="planner",
                correlation_id="corr-peer-brief",
                payload={"previous_specialist": "Researcher", "previous_summary": "Use this prior finding."},
            )
        )

    def test_conversation_routing_protocol_accepts_chat_peer_request(self):
        validate_message(
            MessageEnvelope(
                type="chat.peer-request",
                protocol="conversation-routing",
                sender="researcher",
                recipient="analyst",
                correlation_id="corr-peer-request",
                payload={"target_specialist": "Planner", "target_agent_id": "planner", "reason": "Need planning next."},
            )
        )

    def test_conversation_routing_protocol_accepts_chat_reasoning(self):
        validate_message(
            MessageEnvelope(
                type="chat.reasoning",
                protocol="conversation-routing",
                sender="researcher",
                recipient="analyst",
                correlation_id="corr-reasoning",
                payload={
                    "focus": "Find the strongest source-backed AI startup trends in Europe.",
                    "conclusion": "Applied AI infrastructure is where funding is concentrating.",
                    "concern": "Need one more primary source for 2026.",
                    "next_step": "Use this to guide final synthesis.",
                },
            )
        )

    def test_conversation_routing_protocol_accepts_chat_revise(self):
        validate_message(
            MessageEnvelope(
                type="chat.revise",
                protocol="conversation-routing",
                sender="analyst",
                recipient="researcher",
                correlation_id="corr-2",
                payload={"followup_question": "Add more detail."},
            )
        )

    def test_conversation_routing_protocol_accepts_chat_strategy_update(self):
        validate_message(
            MessageEnvelope(
                type="chat.strategy-update",
                protocol="conversation-routing",
                sender="analyst",
                recipient="researcher",
                correlation_id="corr-strategy-update",
                payload={"summary": "Escalate to revision.", "phase": "revision"},
            )
        )

    def test_conversation_routing_protocol_accepts_chat_council(self):
        validate_message(
            MessageEnvelope(
                type="chat.council",
                protocol="conversation-routing",
                sender="planner",
                recipient="builder",
                correlation_id="corr-3",
                payload={"other_specialist": "Planner"},
            )
        )

    async def test_fallback_implicit_consult_survives_weak_llm_stay_decision(self):
        original = self.runtime.executor.route_chat_with_reasoning
        self.runtime.executor.route_chat_with_reasoning = lambda *args, **kwargs: {
            "should_route": False,
            "target_agent_id": "analyst",
            "route_mode": "stay",
            "reason": "weak stay",
            "confidence": 0.1,
        }
        try:
            task = await self.runtime.create_task(
                TaskCreate(
                    title="Need research",
                    description="Mi serve una ricerca con fonti affidabili sugli ultimi trend AI in Europa.",
                    requested_agent_id="analyst",
                    channel="chat",
                )
            )
            await asyncio.gather(*tuple(self.runtime.running_jobs))
        finally:
            self.runtime.executor.route_chat_with_reasoning = original

        routed = self.runtime.tasks[task.id]
        self.assertEqual("consult", routed.route_mode)
        self.assertEqual("researcher", routed.consult_agent_id)

    async def test_ambiguous_routing_requests_clarification(self):
        await self.runtime.add_agent(
            AgentDefinition(
                id="planner",
                name="Planner",
                role="planner",
                capabilities=["planning"],
            )
        )
        task = await self.runtime.create_task(
            TaskCreate(
                title="Ambiguous handoff",
                description="Fammi parlare con il planner o con il researcher.",
                requested_agent_id="analyst",
                channel="chat",
            )
        )
        await asyncio.gather(*tuple(self.runtime.running_jobs))

        routed = self.runtime.tasks[task.id]
        self.assertEqual("clarify", routed.route_mode)
        self.assertTrue(routed.clarification_question)
        self.assertIn("Planner or Researcher", routed.result["summary"])

    async def test_chat_prompts_include_persistent_wiki_and_previous_messages(self):
        first = await self.runtime.create_task(
            TaskCreate(
                title="Remember the project name",
                description="Remember the project name",
                requested_agent_id="analyst",
                channel="chat",
            )
        )
        await asyncio.gather(*tuple(self.runtime.running_jobs))

        wiki = self.runtime.get_wiki("analyst")
        self.assertIn("modalità simulata locale", wiki.content)
        self.assertIn("Remember the project name", wiki.content)

        analyst = self.runtime.agents["analyst"]
        prompt = self.runtime.executor._build_system_prompt(
            analyst,
            include_chat_history=True,
            current_task_id="task-followup",
        )
        self.assertIn("Persistent conversation wiki", prompt)
        self.assertIn("Remember the project name", prompt)
        self.assertIn("Assistant: Analyst è in modalità simulata locale", prompt)

    async def test_chat_prompts_include_saved_project_job_outputs(self):
        self.runtime.store.save_agent_chat_message(
            "analyst",
            AgentChatMessage(
                id="job-123-project-output",
                task_id="job-123",
                role="assistant",
                content=(
                    "Project job completed.\n"
                    "Project: main-scraper\n"
                    "Action: vinted.search\n"
                    "Rows: 2\n"
                    "Search: charm\n"
                    "\n"
                    "Row preview:\n"
                    "1. Pandora charm | 12,00 EUR | 2 hours ago | hot listing"
                ),
                sources=[{"title": "Pandora charm", "url": "https://example.test/items/1"}],
                created_at=self.runtime.tasks.get("job-123", TaskRecord(title="stub", requested_agent_id="analyst")).created_at,
            ),
        )

        analyst = self.runtime.agents["analyst"]
        prompt = self.runtime.executor._build_system_prompt(
            analyst,
            include_chat_history=True,
            current_task_id="task-followup",
        )
        self.assertIn("Project job completed.", prompt)
        self.assertIn("Pandora charm", prompt)

    async def test_chat_updates_private_memory_for_explicit_preferences(self):
        await self.runtime.create_task(
            TaskCreate(
                title="Keep working conventions",
                description="Please answer in English. We are working on branch dev. Always update README.",
                requested_agent_id="analyst",
                channel="chat",
            )
        )
        await asyncio.gather(*tuple(self.runtime.running_jobs))

        memory = self.runtime.get_memory("analyst").content
        self.assertIn("User preference: respond in English.", memory)
        self.assertIn("Current working branch: dev.", memory)
        self.assertIn("Workflow preference: keep the README updated.", memory)

    async def test_completed_tasks_are_journaled_into_shared_wiki(self):
        await self.runtime.create_task(
            TaskCreate(
                title="Analyze runtime events",
                description="Capture a concise outcome.",
                requested_agent_id="analyst",
            )
        )
        await asyncio.gather(*tuple(self.runtime.running_jobs))

        journal = Path(self.temporary_directory.name) / "data" / "wiki" / "agent-analyst-journal.md"
        self.assertTrue(journal.exists())
        content = journal.read_text(encoding="utf-8")
        self.assertIn("Analyze runtime events", content)
        self.assertIn("Outcome:", content)

    async def test_completed_tasks_create_reviewable_shared_wiki_proposals(self):
        analyst = self.runtime.agents["analyst"]
        self.runtime.executor._create_shared_wiki_proposal(
            analyst,
            TaskRecord(
                title="Capture architecture guidance",
                description="Summarize the memory architecture and retrieval flow.",
                requested_agent_id="analyst",
                capability="analysis",
            ),
            {
                "summary": (
                    "The runtime now injects relevant shared wiki sections into the system prompt, "
                    "stores durable user preferences in private memory, and journals completed tasks "
                    "for later retrieval."
                ),
                "details": "This should be reviewed before becoming shared team knowledge.",
                "sources": [{"url": "https://example.test/architecture", "title": "Architecture"}],
            },
        )

        proposals = self.runtime.list_wiki_proposals()
        self.assertEqual(1, len(proposals))
        self.assertIn("Capture architecture guidance", proposals[0].content)
        self.assertIn("target_page: knowledge-analysis", proposals[0].content)
        self.assertIn("## Proposed durable knowledge", proposals[0].content)

    async def test_simulated_task_results_do_not_create_shared_wiki_proposals(self):
        analyst = self.runtime.agents["analyst"]
        self.runtime.executor._create_shared_wiki_proposal(
            analyst,
            TaskRecord(title="Synthetic result", requested_agent_id="analyst", capability="analysis"),
            {
                "summary": "Analyst completed Synthetic result with a deterministic simulated output.",
                "details": "Executed by the native deterministic provider.",
                "simulated": True,
            },
        )

        self.assertEqual([], self.runtime.list_wiki_proposals())

    async def test_wiki_proposals_can_be_resolved(self):
        path = self.runtime.knowledge_wiki.propose(
            agent_id="analyst",
            title="Architecture note",
            content="Useful runtime guidance.",
            source="task-test",
        )

        resolved = await self.runtime.resolve_wiki_proposal(
            path.name,
            status="approved",
            reviewer="Rafael",
            reason="Matches the intended architecture.",
        )

        self.assertTrue(resolved.name.startswith("approved-"))
        self.assertIn("Matches the intended architecture.", resolved.content)
        self.assertEqual([], self.runtime.list_wiki_proposals())
        canonical = Path(self.temporary_directory.name) / "data" / "wiki" / "shared-knowledge.md"
        self.assertTrue(canonical.exists())
        self.assertIn("Useful runtime guidance.", canonical.read_text(encoding="utf-8"))

    async def test_approved_task_proposals_become_retrievable_shared_wiki(self):
        analyst = self.runtime.agents["analyst"]
        self.runtime.executor._create_shared_wiki_proposal(
            analyst,
            TaskRecord(
                title="Record retrieval architecture",
                description="Durable notes about section retrieval.",
                requested_agent_id="analyst",
                capability="analysis",
            ),
            {
                "summary": (
                    "Section retrieval ranks markdown headings and injects the most relevant "
                    "wiki excerpts into agent system prompts. Approved wiki proposals become "
                    "canonical markdown pages so future agents can reuse reviewed knowledge."
                )
            },
        )
        proposal = self.runtime.list_wiki_proposals()[0]

        await self.runtime.resolve_wiki_proposal(
            proposal.name,
            status="approved",
            reviewer="Rafael",
            reason="Correct.",
        )

        matches = self.runtime.knowledge_wiki.retrieve("section retrieval system prompts", limit=2)
        self.assertTrue(any("Section retrieval ranks markdown headings" in content for _, content in matches))
        canonical = Path(self.temporary_directory.name) / "data" / "wiki" / "knowledge-analysis.md"
        self.assertTrue(canonical.exists())

    async def test_system_prompt_includes_relevant_shared_wiki_sections(self):
        wiki_root = Path(self.temporary_directory.name) / "data" / "wiki"
        wiki_root.mkdir(parents=True, exist_ok=True)
        (wiki_root / "runtime-guidelines.md").write_text(
            "# Runtime guidelines\n\n## Branch policy\nWork on branch dev for active integration changes.\n",
            encoding="utf-8",
        )

        analyst = self.runtime.agents["analyst"]
        prompt = self.runtime.executor._build_system_prompt(
            analyst,
            task=TaskRecord(title="Update branch policy", description="Keep working on branch dev."),
            include_chat_history=False,
            memory_briefing="## runtime-guidelines.md :: Branch policy\nWork on branch dev for active integration changes.",
        )
        self.assertIn("Memory Core briefing", prompt)
        self.assertIn("Branch policy", prompt)
        self.assertIn("Work on branch dev", prompt)

    async def test_memory_core_briefing_is_delivered_as_protocol_message(self):
        wiki_root = Path(self.temporary_directory.name) / "data" / "wiki"
        wiki_root.mkdir(parents=True, exist_ok=True)
        (wiki_root / "runtime-guidelines.md").write_text(
            "# Runtime guidelines\n\n## Branch policy\nWork on branch dev for active integration changes.\n",
            encoding="utf-8",
        )
        await self.runtime.add_agent(
            AgentDefinition(
                id="memory",
                name="Memory Core",
                role="memory",
                capabilities=["memory", "recall"],
                toolsets=["memory"],
            )
        )
        analyst = self.runtime.agents["analyst"]
        briefing = await self.runtime._memory_core_briefing(
            analyst,
            TaskRecord(title="Update branch policy", description="Keep working on branch dev."),
            sender="supervisor",
        )
        self.assertIn("Branch policy", briefing)
        events = self.runtime.store.recent_events(20)
        self.assertTrue(any(event.type == "protocol.message" and event.data.get("message", {}).get("type") == "memory.recall" for event in events))

    async def test_shared_wiki_ranking_uses_relevance_not_file_order(self):
        wiki_root = Path(self.temporary_directory.name) / "data" / "wiki"
        wiki_root.mkdir(parents=True, exist_ok=True)
        (wiki_root / "aaa-unrelated.md").write_text(
            "# Unrelated\n\n## Browser\nBrowser pages and scraper sessions.\n",
            encoding="utf-8",
        )
        (wiki_root / "zzz-memory.md").write_text(
            "# Memory\n\n## Retrieval\nSemantic retrieval ranks wiki sections for system prompts.\n",
            encoding="utf-8",
        )

        matches = self.runtime.knowledge_wiki.retrieve("semantic retrieval prompts", limit=1)

        self.assertEqual("zzz-memory.md :: Retrieval", matches[0][0])

    async def test_wiki_proposal_records_conflict_and_confidence_metadata(self):
        self.runtime.knowledge_wiki.update_page(
            "knowledge-analysis",
            "# Analysis\n\n## Offer policy\nAgents must use the base price when calculating offers.",
            agent_id="analyst",
            source="seed",
        )

        proposal = self.runtime.knowledge_wiki.propose(
            agent_id="analyst",
            title="Conflicting offer policy",
            content="Agents must not use the base price when calculating offers.",
            source="task-conflict",
            target_page="knowledge-analysis",
            confidence=0.42,
        )
        content = proposal.read_text(encoding="utf-8")

        self.assertIn("confidence: 0.42", content)
        self.assertIn("conflict: true", content)
        self.assertIn("conflicts:", content)
        self.assertIn("## Conflict warnings", content)

    async def test_conflicting_wiki_proposal_approval_requires_override_reason(self):
        self.runtime.knowledge_wiki.update_page(
            "knowledge-analysis",
            "# Analysis\n\n## Offer policy\nAgents must use the base price when calculating offers.",
            agent_id="analyst",
            source="seed",
        )
        proposal = self.runtime.knowledge_wiki.propose(
            agent_id="analyst",
            title="Conflicting offer policy",
            content="Agents must not use the base price when calculating offers.",
            source="task-conflict",
            target_page="knowledge-analysis",
        )

        with self.assertRaises(ValueError):
            await self.runtime.resolve_wiki_proposal(
                proposal.name,
                status="approved",
                reviewer="Rafael",
                reason="Reviewed.",
            )

        resolved = await self.runtime.resolve_wiki_proposal(
            proposal.name,
            status="approved",
            reviewer="Rafael",
            reason="Reviewed, override conflict.",
        )
        self.assertTrue(resolved.name.startswith("approved-"))
        canonical = (Path(self.temporary_directory.name) / "data" / "wiki" / "knowledge-analysis.md").read_text(encoding="utf-8")
        self.assertIn("Agents must not use the base price", canonical)
        self.assertNotIn("Conflict warnings", canonical)

    async def test_wiki_maintenance_consolidates_duplicate_sections_and_indexes_pages(self):
        wiki_root = Path(self.temporary_directory.name) / "data" / "wiki"
        wiki_root.mkdir(parents=True, exist_ok=True)
        (wiki_root / "knowledge-analysis.md").write_text(
            "# Analysis\n\n## Duplicate A\nSame durable fact.\n\n## Duplicate B\nSame durable fact.\n",
            encoding="utf-8",
        )

        result = await self.runtime.run_wiki_maintenance()

        self.assertEqual(1, result.duplicate_sections_removed)
        self.assertGreaterEqual(result.pages_updated, 1)
        self.assertTrue((wiki_root / "index.md").exists())
        content = (wiki_root / "knowledge-analysis.md").read_text(encoding="utf-8")
        self.assertIn("Same durable fact.", content)
        self.assertNotIn("Duplicate B", content)

    async def test_nested_wiki_pages_keep_relative_identity(self):
        wiki_root = Path(self.temporary_directory.name) / "data" / "wiki"
        nested = wiki_root / "providers" / "openai.md"
        nested.parent.mkdir(parents=True, exist_ok=True)
        nested.write_text("# OpenAI\n\n## Runtime\nUse Responses API for hosted web search.\n", encoding="utf-8")

        pages = self.runtime.list_wiki_pages()
        self.assertIn("providers/openai.md", [page.name for page in pages])
        page = self.runtime.get_wiki_page("providers/openai.md")
        self.assertEqual("providers/openai.md", page.name)
        self.assertIn("Responses API", page.content)

        with self.assertRaises(ValueError):
            self.runtime.get_wiki_page("../secrets.json")

    async def test_nested_wiki_proposal_targets_are_not_flattened(self):
        proposal = self.runtime.knowledge_wiki.propose(
            agent_id="architect",
            title="Provider runtime",
            content="Provider runtime settings belong under the provider-specific page.",
            source="architecture-review",
            target_page="providers/openai",
        )

        await self.runtime.resolve_wiki_proposal(
            proposal.name,
            status="approved",
            reviewer="test",
            reason="Reviewed.",
        )

        wiki_root = Path(self.temporary_directory.name) / "data" / "wiki"
        self.assertTrue((wiki_root / "providers" / "openai.md").exists())
        self.assertFalse((wiki_root / "providers-openai.md").exists())
        page = self.runtime.get_wiki_page("providers/openai.md")
        self.assertEqual("providers/openai.md", page.name)
        self.assertIn("provider-specific page", page.content)

    async def test_shared_wiki_trimming_preserves_recent_complete_sections(self):
        self.runtime.knowledge_wiki.append_journal_entry(
            page="knowledge-analysis",
            heading="Older section",
            content="Old content " * 80,
            agent_id="analyst",
            source="old",
            max_characters=900,
        )
        self.runtime.knowledge_wiki.append_journal_entry(
            page="knowledge-analysis",
            heading="Recent section",
            content="Recent durable knowledge.",
            agent_id="analyst",
            source="new",
            max_characters=900,
        )

        content = (Path(self.temporary_directory.name) / "data" / "wiki" / "knowledge-analysis.md").read_text(encoding="utf-8")
        self.assertIn("## Recent section", content)
        self.assertIn("Recent durable knowledge.", content)

    async def test_chat_history_limit_keeps_latest_turns_in_order(self):
        for index in range(14):
            self.runtime.store.save_task(
                TaskRecord(
                    title=f"message {index}",
                    description=f"message {index}",
                    requested_agent_id="analyst",
                    channel="chat",
                    result={"summary": f"reply {index}"},
                )
            )

        history = self.runtime.store.load_agent_chat_messages("analyst", limit_turns=3)
        self.assertEqual(
            ["message 11", "reply 11", "message 12", "reply 12", "message 13", "reply 13"],
            [message.content for message in history],
        )

    async def test_legacy_simulated_chat_history_is_labeled(self):
        self.runtime.store.save_task(
            TaskRecord(
                title="ciao come va",
                description="ciao come va",
                requested_agent_id="analyst",
                channel="chat",
                result={
                    "summary": "Analyst completed ciao come va",
                    "details": "Executed by the native deterministic provider.",
                    "provider": "simulated",
                    "model": "native-simulator",
                },
            )
        )

        history = self.runtime.store.load_agent_chat_messages("analyst")
        self.assertIn("Risposta storica simulata locale", history[1].content)
        self.assertNotIn("Analyst completed", history[1].content)

    async def test_legacy_provider_auth_error_is_labeled(self):
        self.runtime.store.save_task(
            TaskRecord(
                title="ciao come va",
                description="ciao come va",
                requested_agent_id="analyst",
                channel="chat",
                error="HTTP Error 401: Unauthorized",
            )
        )

        history = self.runtime.store.load_agent_chat_messages("analyst")
        self.assertIn("Provider authentication failed", history[1].content)
        self.assertNotIn("HTTP Error 401", history[1].content)

    async def test_wiki_bootstrap_preserves_existing_chat(self):
        task = TaskRecord(
            title="Remember blueprints",
            description="Remember blueprints",
            requested_agent_id="archival-agent",
            channel="chat",
            result={"summary": "I will remember blueprints"},
        )
        self.runtime.store.save_task(task)
        wiki = self.runtime.store.bootstrap_wiki_from_chat("archival-agent")
        self.assertIn("user: Remember blueprints", wiki.content)
        self.assertIn("assistant: I will remember blueprints", wiki.content)

    async def test_agent_settings_and_private_memory_are_editable(self):
        analyst = self.runtime.agents["analyst"]
        definition = AgentDefinition(
            **{
                **analyst.model_dump(
                    exclude={"state", "active_task_id", "load", "created_at"}
                ),
                "instructions": "Prefer structured evidence.",
                "toolsets": ["memory", "tasks"],
            }
        )
        updated = await self.runtime.update_agent("analyst", definition)
        self.assertEqual("Prefer structured evidence.", updated.instructions)
        self.assertEqual(["memory", "tasks"], updated.toolsets)

        memory = await self.runtime.update_memory(
            "analyst", MemoryUpdate(content="The project uses typed runtime events.")
        )
        self.assertEqual(memory.content, self.runtime.get_memory("analyst").content)

    async def test_tools_respect_agent_toolsets_and_approval_policy(self):
        analyst = self.runtime.agents["analyst"]
        enabled = AgentDefinition(
            **{
                **analyst.model_dump(
                    exclude={"state", "active_task_id", "load", "created_at"}
                ),
                "toolsets": ["memory"],
            }
        )
        analyst = await self.runtime.update_agent("analyst", enabled)
        task = TaskRecord(title="Remember architecture")
        output = await self.runtime.executor.tools.execute(
            "memory_append", {"content": "Events are persisted."}, analyst, task
        )
        self.assertTrue(output["saved"])
        self.assertIn("Events are persisted.", self.runtime.get_memory("analyst").content)
        proposal = self.runtime.knowledge_wiki.propose(
            agent_id="analyst",
            title="Memory proposal",
            content="Use Memory Core for recall and wiki review.",
            source="task-memory",
        )
        proposals_output = await self.runtime.executor.tools.execute(
            "wiki_proposals_list", {"limit": 5}, analyst, task
        )
        self.assertEqual(proposal.name, proposals_output["proposals"][0]["name"])
        search_output = await self.runtime.executor.tools.execute(
            "shared_wiki_search", {"query": "memory core recall", "limit": 2}, analyst, task
        )
        self.assertEqual("memory core recall", search_output["query"])

        blocked_definition = AgentDefinition(
            **{
                **enabled.model_dump(),
                "approvals": ApprovalPolicy(required_for=["memory-write"]),
            }
        )
        blocked = await self.runtime.update_agent("analyst", blocked_definition)
        with self.assertRaises(PermissionError):
            await self.runtime.executor.tools.execute(
                "memory_append", {"content": "Blocked fact"}, blocked, task
            )

    def test_protocol_rejects_unknown_message_type(self):
        message = MessageEnvelope(
            type="task.impossible",
            protocol="task-contract",
            sender="supervisor",
            recipient="analyst",
            correlation_id="test-run",
        )
        with self.assertRaises(ValueError):
            validate_message(message)


if __name__ == "__main__":
    unittest.main()
