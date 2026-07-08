import tempfile
import unittest
from pathlib import Path

from agent_runtime.execution import ModelExecutor
from agent_runtime.models import AgentSnapshot, ModelSettings
from agent_runtime.secrets import SecretStore
from agent_runtime.storage import RuntimeStore


@unittest.skipUnless(__import__("os").name == "nt", "DPAPI is Windows-specific")
class SecretStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.secrets = SecretStore(self.root / "secrets.json")
        self.database = RuntimeStore(self.root / "runtime.db")

    def tearDown(self):
        self.database.close()
        self.temporary_directory.cleanup()

    def test_encrypts_and_recovers_project_and_agent_keys(self):
        self.secrets.set_project("project-secret-key")
        self.secrets.set_agent("analyst", "agent-secret-key")

        self.assertEqual("project-secret-key", self.secrets.get_project())
        self.assertEqual("agent-secret-key", self.secrets.get_agent("analyst"))
        stored = (self.root / "secrets.json").read_text(encoding="utf-8")
        self.assertNotIn("project-secret-key", stored)
        self.assertNotIn("agent-secret-key", stored)

    def test_executor_resolves_selected_key_scope(self):
        self.secrets.set_project("project-secret-key")
        self.secrets.set_agent("analyst", "agent-secret-key")
        executor = ModelExecutor(self.database, self.secrets)

        project_agent = AgentSnapshot(
            id="project-agent",
            name="Project Agent",
            role="analyst",
            model=ModelSettings(api_key_scope="project"),
        )
        private_agent = AgentSnapshot(
            id="analyst",
            name="Private Agent",
            role="analyst",
            model=ModelSettings(api_key_scope="agent"),
        )

        self.assertEqual("project-secret-key", executor._resolve_api_key(project_agent))
        self.assertEqual("agent-secret-key", executor._resolve_api_key(private_agent))


if __name__ == "__main__":
    unittest.main()
