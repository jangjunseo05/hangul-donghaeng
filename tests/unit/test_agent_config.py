"""Credential isolation tested against captured HTTP requests; no live calls."""
import contextlib
import io
import os
import unittest
from unittest.mock import patch

import httpx

from agent.core import AgentError
from agent.worker import Config, run
from test_agent import Harness, decision, draft


def settings(**changes):
    return {"WORKER_TOKEN": "test-worker", "NVIDIA_API_KEY": "test-nvidia", **changes}


class EndpointTests(unittest.TestCase):
    def config(self, **changes):
        with patch.dict(os.environ, settings(**changes), clear=True):
            return Config.from_env()

    def test_gateway_requires_opt_in_and_exact_hostname(self):
        with self.assertRaises(AgentError):
            self.config(GUIDE_SERVER_URL="http://host.openshell.internal:8000")
        config = self.config(GUIDE_SERVER_URL="http://host.openshell.internal:8000",
                             GUIDE_ALLOW_HTTP_OPENSHELL_GATEWAY="true")
        self.assertEqual(config.server_url, "http://host.openshell.internal:8000")
        for host in ("host.openshell.internal.evil", "host.openshell.internal.", "other.internal"):
            with self.subTest(host=host), self.assertRaises(AgentError):
                self.config(GUIDE_SERVER_URL="http://" + host + ":8000",
                            GUIDE_ALLOW_HTTP_OPENSHELL_GATEWAY="true")

    def test_nvidia_key_cannot_authenticate_self_hosted(self):
        for host in ("model.example", "integrate.api.nvidia.com.evil", "integrate.api.nvidia.com."):
            with self.subTest(host=host), self.assertRaises(AgentError):
                self.config(NVIDIA_BASE_URL="https://" + host + "/v1")

    def test_model_credentials_rejected_over_all_http_transports(self):
        for host in ("localhost", "127.0.0.1", "[::1]", "host.openshell.internal", "model.example"):
            with self.subTest(host=host), self.assertRaises(AgentError) as caught:
                self.config(NVIDIA_BASE_URL="http://" + host + ":8001/v1", SELF_HOSTED_API_KEY="test-self",
                            NVIDIA_ALLOW_UNAUTHENTICATED_LOCAL="true",
                            NVIDIA_ALLOW_UNAUTHENTICATED_SELF_HOSTED="true",
                            NVIDIA_ALLOW_HTTP_SELF_HOSTED="true", GUIDE_ALLOW_HTTP_OPENSHELL_GATEWAY="true")
            self.assertEqual(caught.exception.code, "insecure_model_credentials")

    def test_official_origin_is_https_443_and_stays_authenticated(self):
        for url in ("http://integrate.api.nvidia.com/v1", "https://integrate.api.nvidia.com:8443/v1"):
            with self.subTest(url=url), self.assertRaises(AgentError):
                self.config(NVIDIA_BASE_URL=url, NVIDIA_ALLOW_HTTP_SELF_HOSTED="true")
        with self.assertRaises(AgentError):
            self.config(NVIDIA_API_KEY="", SELF_HOSTED_API_KEY="test-self",
                        NVIDIA_ALLOW_UNAUTHENTICATED_SELF_HOSTED="true")
        self.assertEqual(self.config().model_headers(), {"Authorization": "Bearer test-nvidia"})

    def test_malformed_urls_fail_with_sanitized_error(self):
        urls = ["http://[::1", "https://model.example:abc/v1", "https://model.example:65536/v1",
                "https://model.example:0/v1", "https://model.example/\n/v1",
                "https://@model.example/v1", "https://user:password@model.example/v1",
                "https://model.example\\@integrate.api.nvidia.com/v1", "file:///tmp/model"]
        for url in urls:
            with self.subTest(url=url), self.assertRaises(AgentError) as caught:
                self.config(NVIDIA_BASE_URL=url, NVIDIA_ALLOW_UNAUTHENTICATED_SELF_HOSTED="true")
            self.assertEqual(str(caught.exception), "invalid_endpoint")


class OutboundCredentialTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, env, model_status=200, broker_redirect=False):
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
        harness = Harness([decision(), draft()], model_status=model_status)
        captured = []
        original_client = httpx.AsyncClient

        def handler(request):
            captured.append(request)
            if request.url.path.startswith("/worker/"):
                if broker_redirect and request.url.path == "/worker/jobs/next":
                    return httpx.Response(307, headers={"Location": "https://attacker.example/collect"})
                return harness.service(request)
            if model_status in (301, 302, 307, 308):
                return httpx.Response(model_status, headers={"Location": "https://attacker.example/collect"})
            return harness.model(request)

        def client_factory(**kwargs):
            return original_client(**kwargs, transport=httpx.MockTransport(handler))

        with patch("agent.worker.httpx.AsyncClient", side_effect=client_factory), contextlib.redirect_stdout(io.StringIO()):
            code = await run(config, once=True)
        return code, captured, harness

    async def test_self_hosted_uses_only_separate_key_on_wire(self):
        code, requests, harness = await self.exercise(settings(
            NVIDIA_BASE_URL="https://model.example/v1", SELF_HOSTED_API_KEY="test-self"))
        self.assertEqual(code, 0)
        for request in requests:
            expected = "Bearer test-self" if request.url.host == "model.example" else "Bearer test-worker"
            self.assertEqual(request.headers.get("Authorization"), expected)
            self.assertNotIn("test-nvidia", str(request.headers))
        for payload in harness.model_requests:
            self.assertTrue(payload["messages"][0]["content"].startswith("/no_think\n"))
            self.assertEqual(payload["max_tokens"], 2200)
        for request in requests:
            if request.url.host == "model.example":
                self.assertEqual(request.extensions["timeout"]["read"], 35.0)

    async def test_unauthenticated_modes_never_forward_nvidia_key(self):
        cases = [settings(NVIDIA_BASE_URL="http://127.0.0.1:8001/v1", NVIDIA_ALLOW_UNAUTHENTICATED_LOCAL="true"),
                 settings(NVIDIA_BASE_URL="https://model.example/v1", NVIDIA_ALLOW_UNAUTHENTICATED_SELF_HOSTED="true"),
                 settings(NVIDIA_BASE_URL="http://model.example:8001/v1", NVIDIA_ALLOW_UNAUTHENTICATED_SELF_HOSTED="true",
                          NVIDIA_ALLOW_HTTP_SELF_HOSTED="true")]
        for env in cases:
            code, requests, _ = await self.exercise(env)
            self.assertEqual(code, 0)
            for request in requests:
                if request.url.path == "/v1/chat/completions":
                    self.assertNotIn("Authorization", request.headers)

    async def test_official_and_gateway_tokens_remain_separate(self):
        code, requests, _ = await self.exercise(settings(
            GUIDE_SERVER_URL="http://host.openshell.internal:8000",
            GUIDE_ALLOW_HTTP_OPENSHELL_GATEWAY="true", SELF_HOSTED_API_KEY="test-self"))
        self.assertEqual(code, 0)
        for request in requests:
            expected = "Bearer test-nvidia" if request.url.host == "integrate.api.nvidia.com" else "Bearer test-worker"
            self.assertEqual(request.headers["Authorization"], expected)

    async def test_redirects_do_not_forward_any_credentials(self):
        for status in (301, 302, 307, 308):
            code, requests, _ = await self.exercise(settings(), model_status=status)
            self.assertEqual(code, 1)
            self.assertEqual(sum(r.url.path == "/v1/chat/completions" for r in requests), 1)
            self.assertFalse(any(r.url.host == "attacker.example" for r in requests))
        code, requests, _ = await self.exercise(settings(), broker_redirect=True)
        self.assertEqual(code, 1)
        self.assertEqual(len(requests), 1)


if __name__ == "__main__":
    unittest.main()
