import asyncio
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
        self.assertEqual([], self.runtime.get_agent_chat("supervisor"))

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
