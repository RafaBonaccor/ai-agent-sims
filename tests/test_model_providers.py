import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from agent_runtime.execution import ModelExecutor
from agent_runtime.models import AgentSnapshot, ModelSettings, TaskRecord
from agent_runtime.storage import RuntimeStore


class ModelProviderTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = RuntimeStore(Path(self.temporary_directory.name) / "runtime.db")
        self.executor = ModelExecutor(self.store)
        self.executor._resolve_api_key = lambda _agent: "test-key"
        self.task = TaskRecord(title="Summarize the project", description="Be concise")

    def tearDown(self):
        self.store.close()
        self.temporary_directory.cleanup()

    def run_provider(self, provider, response, model="test-model", base_url="", toolsets=None):
        captured = {}

        def fake_post(endpoint, payload, api_key, extra_headers=None):
            captured.update(
                endpoint=endpoint,
                payload=payload,
                api_key=api_key,
                extra_headers=extra_headers or {},
            )
            return response

        self.executor._post_json = fake_post
        agent = AgentSnapshot(
            id="analyst",
            name="Analyst",
            role="analyst",
            toolsets=toolsets or [],
            model=ModelSettings(provider=provider, model=model, base_url=base_url),
        )
        result = self.executor._run_native_provider(agent, self.task)
        return result, captured

    def test_openai_responses_adapter(self):
        response = {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Done"}]}]}
        result, request = self.run_provider("openai", response)
        self.assertEqual("https://api.openai.com/v1/responses", request["endpoint"])
        self.assertEqual("Done", result["summary"])
        self.assertNotIn("tools", request["payload"])

    def test_openai_web_search_is_enabled_by_agent_toolset(self):
        response = {
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "sources": [
                            {"url": "https://example.com/news", "title": "Example News"}
                        ]
                    },
                },
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Current answer [1]",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://example.com/news",
                                    "title": "Example News",
                                }
                            ],
                        }
                    ],
                },
            ]
        }
        result, request = self.run_provider("openai", response, toolsets=["web"])
        self.assertEqual("web_search", request["payload"]["tools"][0]["type"])
        self.assertEqual(["web_search_call.action.sources"], request["payload"]["include"])
        self.assertEqual(1, result["tool_calls"])
        self.assertEqual(
            [{"url": "https://example.com/news", "title": "Example News"}],
            result["sources"],
        )

    def test_anthropic_messages_adapter(self):
        result, request = self.run_provider("anthropic", {"content": [{"type": "text", "text": "Done"}]})
        self.assertEqual("https://api.anthropic.com/v1/messages", request["endpoint"])
        self.assertEqual("test-key", request["extra_headers"]["x-api-key"])
        self.assertEqual("Done", result["summary"])

    def test_gemini_generate_content_adapter(self):
        response = {"candidates": [{"content": {"parts": [{"text": "Done"}]}}]}
        result, request = self.run_provider("gemini", response, model="gemini-test")
        self.assertTrue(request["endpoint"].endswith("/models/gemini-test:generateContent"))
        self.assertEqual("test-key", request["extra_headers"]["x-goog-api-key"])
        self.assertEqual("Done", result["summary"])

    def test_ollama_chat_adapter(self):
        self.executor._resolve_api_key = lambda _agent: None
        result, request = self.run_provider("ollama", {"message": {"content": "Done"}})
        self.assertEqual("http://127.0.0.1:11434/api/chat", request["endpoint"])
        self.assertFalse(request["payload"]["stream"])
        self.assertEqual("Done", result["summary"])

    def test_post_json_reports_provider_auth_errors_with_body(self):
        response = BytesIO(b'{"error":{"message":"Incorrect API key provided."}}')
        error = HTTPError("https://api.example.test/v1/responses", 401, "Unauthorized", {}, response)

        with patch("agent_runtime.execution.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "Provider authentication failed.*Incorrect API key"):
                ModelExecutor._post_json(
                    "https://api.example.test/v1/responses",
                    {"model": "test-model", "input": "hello"},
                    "bad-key",
                )


if __name__ == "__main__":
    unittest.main()
