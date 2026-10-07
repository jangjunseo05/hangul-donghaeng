"""Opt-in acceptance of the real running service; no mocks, worker or model startup."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PRIVATE_KEYS = {"session_id", "request_id", "photo_id", "cookie", "authorization",
                "token", "api_key", "password", "headers", "detail"}
NEAR = {"lat": 37.5790, "lng": 126.9730, "origin": "selected"}
FAR = {"lat": 35.1796, "lng": 129.0756, "origin": "selected"}


class CheckError(Exception):
    """Only fixed, non-sensitive diagnostic codes belong in this exception."""


def require(condition, code):
    if not condition:
        raise CheckError(code)


def base_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise argparse.ArgumentTypeError("Use a loopback http(s) origin without credentials.")
    try:
        parsed.port
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Invalid port.") from exc
    return value.rstrip("/")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def redact(value, secrets=()):
    """Save validated result fields only; IDs/cookies stay in memory."""
    if isinstance(value, dict):
        return {k: redact(v, secrets) for k, v in value.items()
                if k.lower() not in PRIVATE_KEYS}
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in sorted((s for s in secrets if s), key=len, reverse=True):
            value = value.replace(secret, "[redacted]")
        value = re.sub(r"(?i)bearer\s+[^\s\"<>]+", "Bearer [redacted]", value)
        value = re.sub(r"\b(?:sk-|nvapi-)[A-Za-z0-9_-]{8,}", "[redacted]", value)
        value = re.sub(r"https?://[^\s<>\"]+", safe_public_url, value)
    return value


def safe_public_url(match):
    parsed = urlsplit(match.group(0))
    host = parsed.hostname or "redacted"
    return f"{parsed.scheme}://{host}{parsed.path}"  # No credentials/query/fragment.


def write_json(path, value, secrets=()):
    path.write_text(json.dumps(redact(value, secrets), ensure_ascii=False,
                               indent=2) + "\n", encoding="utf-8")


def distance(a, b):
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat = lat2 - lat1
    dlng = math.radians(b["lng"] - a["lng"])
    x = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371008.8 * 2 * math.asin(min(1.0, math.sqrt(x)))


def scenarios(optional=False, selected=None):
    cases = [
        ("photo_question", "What might this food be? Please explain its Korean cultural context; ask if uncertain.",
         None, None, "real_place"),
        ("confirmed_near_seochon", "I confirm this is samgyetang. Find a listed restaurant near my selected Seochon point and help me ask about its menu.",
         NEAR, "samgyetang", "real_place"),
        ("dietary_followup", "For that same food and restaurant: I avoid seafood. Do you know the full ingredients and cross-contact? Give me a Korean question for staff; do not guarantee safety.",
         NEAR, "samgyetang", "real_place"),
        ("far_location_zero_results", "My selected location is now Busan. Find samgyetang in the curated catalog within 500 metres here, not near my previous point. Explain an empty catalog result.",
         FAR, "samgyetang", "real_place"),
    ]
    if optional or (selected and "fictional_conflict" in selected):
        cases.append(("fictional_conflict", "Using only the fictional practice documents, plan a half-day route. Reconcile conflicting operation notices, state assumptions and ask about missing visit details. Do not book anything.",
                      None, None, "fictional_task"))
    if selected is not None:
        wanted = set(selected)
        if optional:
            wanted.add("fictional_conflict")
        available = {case[0] for case in cases}
        if not wanted or not wanted <= available:
            raise ValueError("Select at least one known --scenario.")
        if "dietary_followup" in wanted and "confirmed_near_seochon" not in wanted:
            raise ValueError(
                "--scenario dietary_followup requires --scenario confirmed_near_seochon "
                "in the same run to establish prior confirmation; both run in that order.")
        cases = [case for case in cases if case[0] in wanted]
    return cases


def require_korean_order(value):
    require(isinstance(value, str) and bool(value.strip()), "missing_korean_order")
    require(bool(re.search("[가-힣]", value)), "order_not_korean")
    # Hangul presence is a structural check, not semantic/dietary safety proof.


def check_result(result, payload, name, approved, catalog):
    require(result["session_id"] == payload["session_id"], "session_mismatch")
    require(result["dataset_mode"] == payload["dataset_mode"], "mode_mismatch")
    require(result["response_language"] == payload["response_language"], "language_mismatch")
    require(result["status"] in {"ready", "need_confirmation"}, "result_not_ready")
    require(result["error_code"] is None, "result_error")
    require(bool(result["speech_text"].strip()), "empty_speech")
    evidence = {entry["id"]: entry for entry in result["evidence"]}
    require(len(evidence) == len(result["evidence"]), "duplicate_evidence")
    known = {entry["id"]: entry for entry in approved[payload["dataset_mode"]]}
    for key, entry in evidence.items():
        require(key in known, "unapproved_evidence")
        require(all(entry[field] == known[key][field] for field in
                    ("source", "as_of", "type", "dataset_id")), "evidence_metadata_mismatch")
    cited = {p["source_id"] for p in result["places"]}
    for group in ("menus", "claims", "conflicts", "itinerary"):
        for item in result[group]:
            cited.update(item["evidence_ids"])
    require(cited <= evidence.keys(), "dangling_evidence")
    places = {p["place_id"]: p for p in catalog["places"]}
    for item in result["places"]:
        require(item["place_id"] in places, "unknown_place")
        canonical = places[item["place_id"]]
        require(all(item[k] == canonical[k] for k in ("name", "lat", "lng", "source_id")),
                "invented_place")
        require(item["catalog_version"] == catalog["catalog_version"], "catalog_version_mismatch")
        require(payload["location"] is not None, "place_without_location")
        actual = distance(payload["location"], item)
        require(actual <= payload["radius_m"] + 1
                and abs(item["distance_m"] - actual) <= 2, "distance_mismatch")
    if result["status"] == "need_confirmation":
        require(bool((result["next_question"] or "").strip()), "empty_clarification")
    else:
        require(bool(result["places"] or result["menus"] or result["claims"]
                     or result["itinerary"] or result["order_ko"] or result["unknowns"]),
                "empty_ready_result")
    if payload["confirmed_food_id"]:
        require(result["scene"]["confirmed_food_id"] == payload["confirmed_food_id"],
                "lost_food_confirmation")
    if name == "confirmed_near_seochon" and result["status"] == "ready":
        require(bool(result["places"]), "nearby_ready_without_place")
    if name == "dietary_followup":
        require(bool(result["unknowns"]), "missing_dietary_uncertainty")
        require_korean_order(result["order_ko"])
    if name in {"far_location_zero_results", "fictional_conflict"}:
        require(result["places"] == [], "unexpected_places")
    if name == "far_location_zero_results":
        require(bool(result["unknowns"] or result["next_question"]), "unexplained_zero_results")
    if name == "fictional_conflict" and result["status"] == "ready":
        require(bool(result["conflicts"] and result["itinerary"]), "missing_conflict_or_plan")
    return {"evidence_count": len(evidence), "cited_evidence_count": len(cited),
            "place_count": len(result["places"]), "menu_count": len(result["menus"]),
            "claim_count": len(result["claims"]), "conflict_count": len(result["conflicts"]),
            "unknown_count": len(result["unknowns"]),
            "semantic_truth_and_dietary_safety": "human_review_required"}


async def json_call(client, method, path, expected=200, **kwargs):
    response = await client.request(method, path, **kwargs)
    require(response.status_code == expected, f"http_{response.status_code}")
    require("application/json" in response.headers.get("content-type", ""), "not_json")
    try:
        data = response.json()
    except ValueError as exc:
        raise CheckError("invalid_json") from exc
    require(isinstance(data, dict), "json_not_object")
    return data


async def submit_poll(client, payload, record):
    queued = await json_call(client, "POST", "/api/requests", expected=202, json=payload)
    rid = queued.get("request_id")
    require(isinstance(rid, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", rid),
            "invalid_request_id")
    require(queued.get("status") == "queued", "invalid_submission_state")
    path = f"/api/requests/{rid}"
    require(queued.get("poll_url") == path, "unexpected_poll_url")
    # Never follow a server/model-selected host or arbitrary path.
    record["request_ref_sha256"] = hashlib.sha256(rid.encode()).hexdigest()
    while True:
        job = await json_call(client, "GET", path)
        record["polls"] += 1
        require(job.get("request_id") == rid, "poll_id_mismatch")
        state = job.get("status")
        record["last_job_state"] = state if state in {
            "queued", "running", "completed", "failed", "superseded"} else "invalid"
        if state == "completed":
            return rid, job.get("result")
        if state in {"failed", "superseded"}:
            code = job.get("error_code")
            if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", code):
                record["worker_error_code"] = code
            raise CheckError(f"job_{state}")
        require(state in {"queued", "running"}, "unknown_job_state")
        await asyncio.sleep(1.0)


async def live(args, report, output, secrets):
    import httpx
    from pydantic import ValidationError
    from shared.models import GuideRequest, GuideResult

    catalog = json.loads((ROOT / "data/catalog.json").read_text(encoding="utf-8"))
    approved = json.loads((ROOT / "data/evidence.json").read_text(encoding="utf-8"))
    photo = ROOT / "data/samples/samgyetang-960.jpg"
    license_info = json.loads((photo.parent / "license-manifest.json").read_text(encoding="utf-8-sig"))
    require(license_info["license"] == "CC0-1.0", "sample_license_changed")
    require(digest(photo) == license_info["sha256"], "sample_sha_mismatch")
    report["sample_sha256"] = digest(photo)
    report["sample_license"] = "CC0-1.0"
    report["contract_sha256"] = digest(ROOT / "shared/api-contract.md")
    report["catalog_sha256"] = digest(ROOT / "data/catalog.json")
    report["evidence_sha256"] = digest(ROOT / "data/evidence.json")
    async with httpx.AsyncClient(base_url=args.base_url, timeout=5.0,
                                 follow_redirects=False, trust_env=False) as client:
        health = await json_call(client, "GET", "/api/health")
        report["health_reported"] = {k: health.get(k) is True for k in
                                    ("worker_connected", "model_configured", "sandbox_verified")}
        require(health.get("status") == "ok" and health.get("worker_connected") is True,
                "service_not_ready")
        session = await json_call(client, "POST", "/api/sessions", json={})
        sid = session.get("session_id")
        require(isinstance(sid, str) and bool(sid), "missing_session")
        secrets.append(sid)
        require(bool(client.cookies), "missing_session_cookie")
        secrets.extend(cookie.value for cookie in client.cookies.jar)
        with photo.open("rb") as handle:
            uploaded = await json_call(client, "POST", "/api/photos",
                                       files={"file": (photo.name, handle, "image/jpeg")})
        pid = uploaded.get("photo_id")
        require(isinstance(pid, str) and bool(pid), "missing_photo_id")
        secrets.append(pid)
        require(all(type(uploaded.get(k)) is int and 0 < uploaded[k] <= 1280
                    for k in ("width", "height")), "invalid_photo_dimensions")
        report["photo_uploaded"] = True
        for name, question, location, food, mode in args.cases:
            record = {"scenario": name, "outcome": "not_started", "polls": 0,
                      "model_provider": "unverifiable_from_browser_api",
                      "model_latency_ms": None,
                      "openshell": "independent_proof_required"}
            report["scenarios"].append(record)
            started = time.monotonic()
            payload = {"schema_version": 1, "session_id": sid, "question": question,
                       "photo_id": pid if name == "photo_question" else None,
                       "dataset_mode": mode, "response_language": "en", "location": location,
                       "radius_m": 500, "confirmed_food_id": food, "confirmed_shop_id": None}
            try:
                GuideRequest.model_validate(payload)
                rid, raw = await asyncio.wait_for(submit_poll(client, payload, record), 35.0)
                record["submit_to_terminal_ms"] = round((time.monotonic() - started) * 1000)
                secrets.append(rid)
                result = GuideResult.model_validate(raw).model_dump(mode="json")
                require(result["request_id"] == rid, "result_id_mismatch")
                # Retain structurally valid final results even if a later behavioral check fails.
                write_json(output / f"{name}.result.json", result, secrets)
                write_json(output / "final-result.json", result, secrets)
                downloaded = await json_call(
                    client, "GET", f"/api/results/{rid}/download?format=json")
                card = GuideResult.model_validate(downloaded).model_dump(mode="json")
                require(card == result, "download_result_mismatch")
                write_json(output / f"{name}.downloaded-card.json", card, secrets)
                record["download_matches_result"] = True
                record.update(check_result(result, payload, name, approved, catalog))
                record["outcome"] = ("completed_clarification" if result["status"] == "need_confirmation"
                                     else "completed_useful")
                record["result_status"] = result["status"]
            except asyncio.TimeoutError:
                record["outcome"] = "timeout"
                record["diagnostic"] = "submit_poll_exceeded_35s"
            except CheckError as exc:
                record["outcome"] = "not_ready" if str(exc) in {
                    "job_failed", "job_superseded", "result_not_ready"} else "failed"
                record["diagnostic"] = str(exc)
            except (httpx.HTTPError, ValueError, TypeError, KeyError, ValidationError) as exc:
                record["outcome"] = "failed"
                record["diagnostic"] = type(exc).__name__  # Never error bodies or validation input.
            finally:
                record["scenario_elapsed_ms"] = round((time.monotonic() - started) * 1000)
                write_json(output / "metrics.json", report, secrets)
            if record["outcome"] not in {"completed_useful", "completed_clarification"}:
                break  # Do not stack jobs on a stalled worker or spend further model calls.


def check_helpers():
    assert base_url("http://localhost:8000/") == "http://localhost:8000"
    for bad in ("https://example.org", "http://localhost:8000/?token=x",
                "http://u:p@localhost:8000", "http://localhost:8000/worker"):
        try:
            base_url(bad)
        except argparse.ArgumentTypeError:
            pass
        else:
            raise AssertionError("unsafe origin accepted")
    scrubbed = redact({"session_id": "cookie-secret", "speech_text": "cookie-secret",
                       "source": "https://u:p@example.org/path?token=abc#secret",
                       "nested": {"api_key": "private"}}, ["cookie-secret"])
    assert scrubbed == {"speech_text": "[redacted]", "source": "https://example.org/path", "nested": {}}
    assert redact("Bearer abcdef nvapi-123456789") == "Bearer [redacted] [redacted]"
    assert distance(NEAR, NEAR) == 0
    assert distance(NEAR, FAR) > 100_000
    assert [case[0] for case in scenarios()] == [
        "photo_question", "confirmed_near_seochon", "dietary_followup", "far_location_zero_results"]

    assert len(scenarios(optional=True)) == 5
    assert [case[0] for case in scenarios(selected=["fictional_conflict"])] == ["fictional_conflict"]
    assert [case[0] for case in scenarios(selected=[
        "fictional_conflict", "far_location_zero_results", "far_location_zero_results"])] == [
            "far_location_zero_results", "fictional_conflict"]
    assert [case[0] for case in scenarios(selected=[
        "dietary_followup", "confirmed_near_seochon"])] == [
            "confirmed_near_seochon", "dietary_followup"]
    assert [case[0] for case in scenarios(optional=True, selected=["far_location_zero_results"])] == [
        "far_location_zero_results", "fictional_conflict"]
    for invalid in (["dietary_followup"], ["unknown"], []):
        try:
            scenarios(selected=invalid)
        except ValueError as exc:
            if invalid == ["dietary_followup"]:
                assert "--scenario confirmed_near_seochon" in str(exc)
        else:
            raise AssertionError("invalid scenario selection accepted")
    for invalid_order in (None, "", "   ", "Please confirm ingredients with staff."):
        try:
            require_korean_order(invalid_order)
        except CheckError:
            pass
        else:
            raise AssertionError("missing or English-only order_ko accepted")
    require_korean_order("해산물 재료가 들어가나요?")
    print("HELPER_CHECKS_PASS: no network, no model, no output artifacts")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    gates = parser.add_mutually_exclusive_group()
    gates.add_argument("--run-live", action="store_true", help="Root must declare service ready first.")
    gates.add_argument("--check-helpers", action="store_true", help="Offline pure helper checks only.")
    parser.add_argument("--base-url", type=base_url, default="http://127.0.0.1:8000")
    parser.add_argument("--include-fictional", action="store_true",
                        help="Append fictional_conflict to the default or selected cases.")
    parser.add_argument("--scenario", action="append",
                        choices=[case[0] for case in scenarios(optional=True)],
                        help="Repeat to select cases; runs once each in canonical order. "
                             "Dietary requires confirmed_near_seochon in the same selection.")
    args = parser.parse_args()
    try:
        args.cases = scenarios(args.include_fictional, args.scenario)
    except ValueError as exc:
        parser.error(str(exc))
    if args.check_helpers:
        check_helpers()
        return 0
    if not args.run_live:
        print("NOT_RUN: root readiness approval and explicit --run-live required; no network or files.")
        return 2
    require(".runtime/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines(),
            "runtime_ignore_missing")
    output = ROOT / ".runtime/qa" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    report = {"started_at": datetime.now(timezone.utc).isoformat(),
              "status": "incomplete", "budget_seconds": 240, "poll_limit_seconds": 35,
              "latency_kind": "client_wall_clock_including_queue_tools_and_model",
              "model_provider": "unverifiable_from_browser_api", "model_latency_ms": None,
              "openshell": "independent_proof_required",
              "selected_scenarios": [case[0] for case in args.cases], "scenarios": []}
    secrets = []
    started = time.monotonic()
    code = 1
    try:
        asyncio.run(asyncio.wait_for(live(args, report, output, secrets), 240.0))
        cases = report["scenarios"]
        expected = len(args.cases)
        if len(cases) == expected and all(c["outcome"].startswith("completed_") for c in cases):
            report["status"] = ("COMPLETED_WITH_CLARIFICATION"
                                if any(c["outcome"] == "completed_clarification" for c in cases)
                                else "COMPLETED_USEFUL")
            code = 0  # Structural live flow, never semantic safety/provider/OpenShell certification.
        else:
            report["status"] = "INCOMPLETE"
    except asyncio.TimeoutError:
        report["status"] = "TIMEOUT"
        report["diagnostic"] = "overall_240s_budget_exceeded"
    except CheckError as exc:
        report["status"] = "NOT_READY" if str(exc) == "service_not_ready" else "FAILED"
        report["diagnostic"] = str(exc)
    except KeyboardInterrupt:
        report["status"] = "INTERRUPTED"
    except Exception as exc:
        report["status"] = "FAILED"
        report["diagnostic"] = type(exc).__name__
    finally:
        report["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        write_json(output / "metrics.json", report, secrets)
    print(report["status"])
    for case in report["scenarios"]:
        print(f"{case['scenario']}: {case['outcome']}")
    print(f"Evidence: {output.relative_to(ROOT)}")
    print("Model/provider latency UNVERIFIABLE; OpenShell independent proof REQUIRED.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
