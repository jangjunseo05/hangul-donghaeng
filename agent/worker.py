"""Run: python -m agent.worker [--once]. Production contains no fixture fallback."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
import json
import os
import re
from pathlib import Path
import sys
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv

from agent.core import AgentError, ModelSession, execute_job

ID = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
NVIDIA_HOST = "integrate.api.nvidia.com"
OPENSHELL_GATEWAY = "host.openshell.internal"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
JOB_TIMEOUT_SECONDS = 30.0


def _endpoint(url: str):
    try:
        if any(ord(char) <= 32 or ord(char) == 127 for char in url) or "\\" in url:
            raise ValueError("unsafe_url")
        parts = urlsplit(url)
        if (not parts.hostname or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment or parts.scheme not in {"http", "https"}):
            raise ValueError("invalid_url")
        if parts.port is not None and not 1 <= parts.port <= 65535:
            raise ValueError("invalid_port")
        return parts
    except ValueError as exc:
        raise AgentError("invalid_endpoint") from exc


@dataclass
class Config:
    server_url: str
    worker_token: str = field(repr=False)
    api_key: str = field(repr=False)
    base_url: str = "https://integrate.api.nvidia.com/v1"
    model: str = "nvidia/nemotron-nano-12b-v2-vl"
    run_context: str = "local-dev"
    self_hosted_api_key: str = field(default="", repr=False)
    allow_http_gateway: bool = False
    allow_unauthenticated_local: bool = False
    allow_unauthenticated_self_hosted: bool = False
    allow_http_self_hosted: bool = False

    @classmethod
    def from_env(cls):
        config = cls(os.getenv("GUIDE_SERVER_URL", "http://127.0.0.1:8000"),
            os.getenv("WORKER_TOKEN", ""), os.getenv("NVIDIA_API_KEY", ""),
            os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            os.getenv("NVIDIA_MODEL", "nvidia/nemotron-nano-12b-v2-vl"),
            os.getenv("RUN_CONTEXT", "local-dev"))
        config.self_hosted_api_key = os.getenv("SELF_HOSTED_API_KEY", "")
        config.allow_http_gateway = os.getenv("GUIDE_ALLOW_HTTP_OPENSHELL_GATEWAY", "").lower() == "true"
        config.allow_unauthenticated_local = os.getenv("NVIDIA_ALLOW_UNAUTHENTICATED_LOCAL", "").lower() == "true"
        config.allow_unauthenticated_self_hosted = os.getenv("NVIDIA_ALLOW_UNAUTHENTICATED_SELF_HOSTED", "").lower() == "true"
        config.allow_http_self_hosted = os.getenv("NVIDIA_ALLOW_HTTP_SELF_HOSTED", "").lower() == "true"
        config.validate()
        return config

    def validate(self):
        if not self.worker_token:
            raise AgentError("missing_worker_token")
        broker = _endpoint(self.server_url)
        if broker.scheme == "http" and broker.hostname not in LOOPBACK_HOSTS and not (
                self.allow_http_gateway and broker.hostname == OPENSHELL_GATEWAY):
            raise AgentError("https_required")
        if self.run_context not in {"local-dev", "openshell"}:
            raise AgentError("invalid_run_context")
        self.model_headers()

    def model_headers(self) -> dict[str, str]:
        """Select a credential for its origin; never reuse the NVIDIA key elsewhere."""
        parts = _endpoint(self.base_url)
        if parts.hostname == NVIDIA_HOST:
            if parts.scheme != "https" or parts.port not in {None, 443}:
                raise AgentError("invalid_nvidia_endpoint")
            if not self.api_key:
                raise AgentError("missing_model_credentials")
            return {"Authorization": "Bearer " + self.api_key}
        key = self.self_hosted_api_key
        local = parts.hostname in LOOPBACK_HOSTS
        allow_unauthenticated = (self.allow_unauthenticated_local if local
                                 else self.allow_unauthenticated_self_hosted)
        if key and parts.scheme != "https":
            raise AgentError("insecure_model_credentials")
        if not key and not allow_unauthenticated:
            raise AgentError("missing_model_credentials")
        if parts.scheme == "http" and not (local or self.allow_http_self_hosted):
            raise AgentError("https_required")
        return {"Authorization": "Bearer " + key} if key else {}


class WorkerAPI:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.search_count = 0

    async def call(self, method: str, path: str, **kwargs):
        try:
            response = await self.client.request(method, path, timeout=5.0, **kwargs)
            if response.status_code == 409:
                raise AgentError("superseded")
            if response.status_code >= 300:
                raise AgentError("service_http_error")
            return response
        except httpx.HTTPError as exc:
            raise AgentError("service_transport_error") from exc

    async def claim(self):
        response = await self.call("GET", "worker/jobs/next")
        if response.status_code == 204:
            return None
        self.search_count = 0
        return response.json()

    async def photo(self, photo_id, request_id):
        if not ID.fullmatch(photo_id) or not ID.fullmatch(request_id):
            raise AgentError("invalid_photo_reference")
        response = await self.call("GET", "worker/photos/" + photo_id, params={"request_id": request_id})
        if not response.headers.get("content-type", "").startswith("image/jpeg"):
            raise AgentError("invalid_photo_type")
        return response.content

    async def search(self, payload):
        if self.search_count >= 2:
            raise AgentError("search_call_limit")
        self.search_count += 1
        return (await self.call("POST", "worker/search", json=payload)).json()

    async def submit(self, job, result):
        return (await self.call("POST", "worker/results", json={
            "session_id": job["session_id"], "request_id": job["request_id"], "result": result})).json()

    async def fail(self, job, code):
        # No exception strings, upstream bodies, raw photo, user text or credentials.
        await self.call("POST", "worker/fail", json={"session_id": job["session_id"],
            "request_id": job["request_id"], "error_code": code, "detail": code})


async def handle_job(job, api, model):
    try:
        async with asyncio.timeout(JOB_TIMEOUT_SECONDS):
            result = await execute_job(job, api, model)
            receipt = await api.submit(job, result)
            if receipt.get("saved") is not True:
                raise AgentError("save_not_confirmed")
        return "saved"
    except TimeoutError:
        code = "job_timeout"
    except AgentError as exc:
        code = exc.code
    except Exception:
        code = "invalid_job_or_result"
    if code != "superseded":
        try:
            await api.fail(job, code)
        except (AgentError, KeyError):
            pass
    return code


async def run(config: Config, once=False):
    config.validate()
    async with httpx.AsyncClient(base_url=config.server_url.rstrip("/") + "/",
            headers={"Authorization": "Bearer " + config.worker_token},
            follow_redirects=False) as service_client, httpx.AsyncClient(
            base_url=config.base_url.rstrip("/") + "/",
            headers=config.model_headers(),
            follow_redirects=False) as model_client:
        api = WorkerAPI(service_client)
        while True:
            try:
                job = await api.claim()
            except (AgentError, ValueError):
                if once:
                    return 1
                print(json.dumps({"event": "poll_failed", "code": "service_unavailable"}), flush=True)
                await asyncio.sleep(2)
                continue
            if job is not None:
                model = ModelSession(model_client, config.model)
                outcome = await handle_job(job, api, model)
                print(json.dumps({"event": "job_finished", "outcome": outcome,
                                  "model_calls": model.calls, "run_context": config.run_context,
                                  "sandbox_verified": False}), flush=True)
                if once:
                    return 0 if outcome == "saved" else 1
            elif once:
                return 0
            await asyncio.sleep(1)


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Claim at most one real server job")
    args = parser.parse_args()
    try:
        return asyncio.run(run(Config.from_env(), args.once))
    except AgentError as exc:
        print(json.dumps({"event": "startup_failed", "code": exc.code}), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
