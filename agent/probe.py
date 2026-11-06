"""Sandbox probe job (F3): attempt four out-of-policy actions and report what happened.

Each attempt is harmless: read a directory listing, create-then-delete an empty file, open one
HTTPS connection, POST an empty body. Only errno names / HTTP status codes are reported.
Outside OpenShell these attempts are expected to be ALLOWED, and that is reported as is.
"""
from __future__ import annotations

from datetime import datetime, timezone
import errno
import os
from pathlib import Path
import uuid

import httpx

CODE_DIR = Path(__file__).resolve().parents[1]  # /app in the worker image
READ_PATH = Path(os.getenv("PROBE_READ_PATH", "/home"))
EGRESS_URL = os.getenv("PROBE_EGRESS_URL", "https://example.com/")


def _os_error(exc: OSError) -> tuple[str, str]:
    name = errno.errorcode.get(exc.errno or 0, type(exc).__name__)
    return ("denied" if exc.errno in {errno.EACCES, errno.EPERM, errno.EROFS} else "error"), name


def read_outside_allowlist() -> tuple[str, str | None]:
    try:
        os.listdir(READ_PATH)
        return "allowed", None
    except OSError as exc:
        return _os_error(exc)


def write_code_dir() -> tuple[str, str | None]:
    target = CODE_DIR / f".sandbox-probe-{uuid.uuid4().hex[:12]}"
    try:
        with target.open("x"):
            pass
    except OSError as exc:
        return _os_error(exc)
    try:
        target.unlink(missing_ok=True)
    except OSError:
        pass
    return "allowed", None


async def egress_unlisted_host(run_context: str = "") -> tuple[str, str | None]:
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=4.0) as client:
            response = await client.get(EGRESS_URL)
    except (httpx.ConnectError, httpx.ProxyError) as exc:
        # OpenShell's destination denial surfaced as ConnectError in the recorded boundary test
        # (docs/runtime/evidence/boundary-matrix-01.log). Outside the sandbox the same error just means
        # offline/DNS/firewall, which is not evidence of a policy denial.
        return ("denied" if run_context == "openshell" else "error"), type(exc).__name__
    except httpx.HTTPError as exc:
        return "error", type(exc).__name__
    return ("denied", "403") if response.status_code == 403 else ("allowed", str(response.status_code))


async def broker_unlisted_path(api) -> tuple[str, str | None]:
    try:
        response = await api.client.request("POST", "worker/canary", json={}, timeout=5.0)
    except httpx.HTTPError as exc:
        return "error", type(exc).__name__
    if response.status_code < 300:
        return "allowed", str(response.status_code)
    # Only the policy's L7 rejection (403) is a denial; 401/404/5xx are errors, not sandbox evidence.
    return ("denied" if response.status_code == 403 else "error"), str(response.status_code)


async def run_probe_job(job: dict, api, run_context: str) -> None:
    attempts = []
    for attempt_id, action in (("read_outside_allowlist", read_outside_allowlist), ("write_code_dir", write_code_dir)):
        observed, detail = action()
        attempts.append({"id": attempt_id, "expected": "denied", "observed": observed, "detail": detail})
    for attempt_id, observed_detail in (("egress_unlisted_host", await egress_unlisted_host(run_context)),
                                        ("broker_unlisted_path", await broker_unlisted_path(api))):
        attempts.append({"id": attempt_id, "expected": "denied", "observed": observed_detail[0],
                         "detail": observed_detail[1]})
    context = "".join(char for char in (run_context or "").lower() if char.isascii() and (char.isalnum() or char in "_.-"))
    result = {"run_context": context[:40] or "unknown", "finished_at": datetime.now(timezone.utc).isoformat(),
              "attempts": attempts}
    receipt = (await api.call("POST", "worker/probe-results", json={
        "session_id": job["session_id"], "request_id": job["request_id"], "result": result})).json()
    if receipt.get("saved") is not True:
        raise RuntimeError("save_not_confirmed")
