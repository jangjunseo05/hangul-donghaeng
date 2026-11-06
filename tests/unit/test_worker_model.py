"""Opt-in thinking-off for hosted reasoning models, honest model-echo logging, worker_model in health."""
import contextlib
import io
import json
import os
import time
import unittest
from unittest import mock

import httpx
from fastapi.testclient import TestClient

from agent.core import ModelSession
from agent.worker import Config, broker_headers
from service.main import create_app
from test_agent import Harness, decision, draft

AUTH = {"Authorization": "Bearer test-worker-token"}


async def one_call(disable_thinking, response_model="stub-test-model"):
    sent, captured = [], io.StringIO()

    def model(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"model": response_model, "choices": [
            {"message": {"content": json.dumps({"ok": True})}, "finish_reason": "stop"}]})

    from pydantic import BaseModel

    class Ok(BaseModel):
        ok: bool

    async with httpx.AsyncClient(base_url="https://model/v1/", transport=httpx.MockTransport(model)) as client:
        with contextlib.redirect_stderr(captured):
            await ModelSession(client, "stub-test-model", disable_thinking).structured(
                [{"role": "user", "content": "x"}], Ok)
    return sent[0], json.loads(captured.getvalue().splitlines()[0])


class ThinkingTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_request_is_unchanged(self):
        body, event = await one_call(False)
        self.assertNotIn("chat_template_kwargs", body)
        self.assertNotIn("thinking_disabled", event)
        self.assertEqual(set(body), {"model", "messages", "temperature", "max_tokens", "stream"})

    async def test_opt_in_disables_thinking_and_says_so_in_the_log(self):
        body, event = await one_call(True)
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})
        self.assertIs(event["thinking_disabled"], True)

    async def test_alias_echo_is_recorded_as_mismatch_without_logging_the_alias(self):
        harness = Harness([decision(), draft()])
        original = harness.model

        def model(request):
            payload = original(request).json()
            payload["model"] = "private/ALIAS_NAME"
            return httpx.Response(200, json=payload)

        harness.model = model
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            self.assertEqual(await harness.run(), "saved")  # a mismatch is recorded, not a failure
        events = [json.loads(line) for line in captured.getvalue().splitlines()]
        self.assertTrue(events)
        for event in events:
            self.assertEqual(event["configured_model"], "stub-test-model")
            self.assertIs(event["response_model_match"], False)
        self.assertNotIn("ALIAS_NAME", captured.getvalue())

    def test_env_flag_is_off_unless_exactly_true(self):
        base = {"WORKER_TOKEN": "t", "NVIDIA_API_KEY": "k", "GUIDE_SERVER_URL": "http://127.0.0.1:8000"}
        for value, expected in (("", False), ("1", False), ("yes", False), ("true", True), ("TRUE", True)):
            with mock.patch.dict(os.environ, {**base, "NVIDIA_DISABLE_THINKING": value}, clear=True):
                self.assertIs(Config.from_env().disable_thinking, expected)


class BrokerHeaderTests(unittest.TestCase):
    def test_worker_sends_its_labels_and_omits_an_unusable_model_id(self):
        config = Config("http://127.0.0.1:8000", "tok", "key", model="nvidia/some-model", run_context="local-dev")
        config.disable_thinking = True
        self.assertEqual(broker_headers(config), {"Authorization": "Bearer tok", "X-Worker-Model": "nvidia/some-model",
                                                  "X-Worker-Thinking": "disabled", "X-Worker-Context": "local-dev"})
        config.model = "bad model<id>"
        self.assertNotIn("X-Worker-Model", broker_headers(config))
        self.assertNotIn("key", json.dumps(broker_headers(config)))  # the model key never goes to the broker

    def test_challenge_runner_reads_the_same_flag(self):
        from agent.challenge import _config
        for value, expected in (("", False), ("true", True)):
            with mock.patch.dict(os.environ, {"NVIDIA_DISABLE_THINKING": value}, clear=True):
                self.assertIs(_config().disable_thinking, expected)


class HealthWorkerModelTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(__import__("pathlib").Path(self.tmp.name), worker_token="test-worker-token")

    def tearDown(self):
        self.tmp.cleanup()

    def test_health_reports_what_the_authenticated_worker_says_it_calls(self):
        with TestClient(self.app) as client:
            self.assertIsNone(client.get("/api/health").json()["worker_model"])
            client.get("/worker/jobs/next", headers={**AUTH, "X-Worker-Model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
                                                     "X-Worker-Thinking": "disabled", "X-Worker-Context": "local-dev"})
            self.assertEqual(client.get("/api/health").json()["worker_model"],
                             {"id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", "thinking": "disabled",
                              "run_context": "local-dev"})
            self.assertIs(client.get("/api/health").json()["sandbox_verified"], False)
            # Older worker without the header: back to unknown, never a stale or invented name.
            client.get("/worker/jobs/next", headers=AUTH)
            self.assertIsNone(client.get("/api/health").json()["worker_model"])

    def test_label_is_hidden_once_the_worker_is_no_longer_connected(self):
        with TestClient(self.app) as client:
            client.get("/worker/jobs/next", headers={**AUTH, "X-Worker-Model": "m-1", "X-Worker-Context": "local-dev"})
            self.assertEqual(client.get("/api/health").json()["worker_model"]["id"], "m-1")
            with mock.patch("service.main.time.monotonic", return_value=time.monotonic() + 10_000):
                health = client.get("/api/health").json()
            self.assertIs(health["worker_connected"], False)
            self.assertIsNone(health["worker_model"])

    def test_unauthenticated_or_malformed_reports_are_ignored(self):
        with TestClient(self.app) as client:
            client.get("/worker/jobs/next", headers={"X-Worker-Model": "evil/model"})
            self.assertIsNone(client.get("/api/health").json()["worker_model"])
            client.get("/worker/jobs/next", headers={**AUTH, "X-Worker-Model": "<script>", "X-Worker-Thinking": "weird"})
            self.assertIsNone(client.get("/api/health").json()["worker_model"])
            client.get("/worker/jobs/next", headers={**AUTH, "X-Worker-Model": "m-1", "X-Worker-Thinking": "weird",
                                                     "X-Worker-Context": "sandboxed"})
            self.assertEqual(client.get("/api/health").json()["worker_model"],
                             {"id": "m-1", "thinking": "default", "run_context": "unknown"})
            # Self-reported "openshell" is a label only: it never turns sandbox_verified on.
            client.get("/worker/jobs/next", headers={**AUTH, "X-Worker-Model": "m-1", "X-Worker-Context": "openshell"})
            health = client.get("/api/health").json()
            self.assertEqual(health["worker_model"]["run_context"], "openshell")
            self.assertIs(health["sandbox_verified"], False)


if __name__ == "__main__":
    unittest.main()
