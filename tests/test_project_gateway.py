import json
import tempfile
import unittest
from pathlib import Path

from agent_runtime.project_gateway import ProjectGateway, ProjectJobCreate


class ProjectGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        (root / "config").mkdir()
        (root / "integrations" / "demo").mkdir(parents=True)
        (root / "projects" / "demo").mkdir(parents=True)
        (root / "config" / "projects.json").write_text(
            json.dumps(
                {
                    "projects": [
                        {
                            "id": "demo",
                            "name": "Demo",
                            "root": "projects/demo",
                            "integration": "integrations/demo/adapter.json",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (root / "integrations" / "demo" / "adapter.json").write_text(
            json.dumps(
                {
                    "runtime": {"entrypoint": "main.py", "venvCandidates": []},
                    "actions": {
                        "read": {
                            "label": "Read demo",
                            "arguments": ["status"],
                            "parameters": ["query"],
                        },
                        "write": {"arguments": ["submit"], "requiresApproval": True},
                    },
                }
            ),
            encoding="utf-8",
        )

        async def emit(_event):
            return None

        self.gateway = ProjectGateway(root, emit)

    async def asyncTearDown(self):
        await self.gateway.shutdown()
        self.temporary_directory.cleanup()

    async def test_rejects_parameters_outside_action_allowlist(self):
        with self.assertRaisesRegex(ValueError, "Unsupported parameters"):
            await self.gateway.create_job(
                ProjectJobCreate(project_id="demo", action="read", parameters={"shell": "whoami"})
            )

    async def test_exposes_human_action_labels(self):
        projects = self.gateway.list_projects()
        self.assertEqual("Read demo", projects[0]["actions"][0]["label"])

    async def test_requires_explicit_approval_for_external_action(self):
        with self.assertRaisesRegex(PermissionError, "requires explicit approval"):
            await self.gateway.create_job(ProjectJobCreate(project_id="demo", action="write"))


if __name__ == "__main__":
    unittest.main()
