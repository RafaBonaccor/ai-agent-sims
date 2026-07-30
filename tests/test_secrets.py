import unittest
import tempfile
import os
from pathlib import Path

from agent_runtime.execution import ModelExecutor
from agent_runtime.models import AgentSnapshot, ModelSettings
from agent_runtime.secrets import SecretStore
from agent_runtime.storage import RuntimeStore


class SecretStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.secrets = SecretStore(self.root / "secrets.json", backend="local-test")
        self.database = RuntimeStore(self.root / "runtime.db")

    def tearDown(self):
        self.database.close()
        self.temporary_directory.cleanup()

    def test_encrypts_and_recovers_project_and_agent_keys(self):
        self.secrets.set_project("project-secret-key")
        self.secrets.set_agent("analyst", "agent-secret-key")
        self.secrets.set_discord_bot_token("discord-bot-token-1234567890")

        self.assertEqual("project-secret-key", self.secrets.get_project())
        self.assertEqual("agent-secret-key", self.secrets.get_agent("analyst"))
        self.assertEqual("discord-bot-token-1234567890", self.secrets.get_discord_bot_token())
        stored = (self.root / "secrets.json").read_text(encoding="utf-8")
        self.assertNotIn("project-secret-key", stored)
        self.assertNotIn("agent-secret-key", stored)
        self.assertNotIn("discord-bot-token-1234567890", stored)
        self.assertIn("local-test", stored)

    def test_status_reports_discord_bot_token(self):
        self.assertFalse(self.secrets.status().get("discord_bot_configured"))
        self.secrets.set_discord_bot_token("discord-bot-token-1234567890")
        self.assertTrue(self.secrets.status().get("discord_bot_configured"))

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

    def test_executor_falls_back_to_project_key_when_agent_key_is_missing(self):
        self.secrets.set_project("project-secret-key")
        executor = ModelExecutor(self.database, self.secrets)

        private_agent = AgentSnapshot(
            id="analyst",
            name="Private Agent",
            role="analyst",
            model=ModelSettings(api_key_scope="agent"),
        )

        self.assertEqual("project-secret-key", executor._resolve_api_key(private_agent))

    def test_executor_falls_back_to_project_env_when_agent_env_is_missing(self):
        previous_project = os.environ.get("OPENAI_API_KEY")
        previous_agent = os.environ.get("AGENT_ANALYST_KEY")
        try:
            os.environ["OPENAI_API_KEY"] = "env-project-secret-key"
            os.environ.pop("AGENT_ANALYST_KEY", None)
            executor = ModelExecutor(self.database, self.secrets)
            private_agent = AgentSnapshot(
                id="analyst",
                name="Private Agent",
                role="analyst",
                model=ModelSettings(api_key_scope="agent", api_key_env="OPENAI_API_KEY"),
            )
            self.assertEqual("env-project-secret-key", executor._resolve_api_key(private_agent))
        finally:
            if previous_project is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_project
            if previous_agent is None:
                os.environ.pop("AGENT_ANALYST_KEY", None)
            else:
                os.environ["AGENT_ANALYST_KEY"] = previous_agent


if __name__ == "__main__":
    unittest.main()
