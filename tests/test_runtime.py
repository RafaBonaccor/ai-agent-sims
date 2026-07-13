import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from agent_runtime.engine import AgentRuntime
from agent_runtime.models import (
    AgentDefinition,
    ApprovalPolicy,
    MemoryUpdate,
    MessageEnvelope,
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
        self.assertEqual({"supervisor", "analyst"}, set(self.runtime.agents))
        loaded = self.runtime.store.load_agents()
        self.assertEqual({"supervisor", "analyst"}, {agent.id for agent in loaded})

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
