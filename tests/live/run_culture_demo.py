"""Real broker culture acceptance. Root must declare READY before:
  .venv/Scripts/python.exe -B tests/live/run_culture_demo.py --run-live --root-ready
Without --run-live: no HTTP, uploads, model calls, or runtime artifacts.
Offline: --check-helpers. File uploads do NOT prove camera, microphone or TTS.
Sequential requests do NOT prove single-flight, manual priority or auto-frame control.
Only structured citation/identity checks are automatic; historical truth and
uncited narrative still require human review of the retained redacted results.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("culture_qa_base", Path(__file__).with_name("run_demo.py"))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
require = base.require
CheckError = base.CheckError
CONFIRMATIONS = ("confirmed_food_id", "confirmed_shop_id", "confirmed_place_id")
SAMPLES = {
    "heritage": ("heritage-demo.jpg", "heritage-license.json"),
    "food": ("samgyetang-960.jpg", "license-manifest.json"),
}
HISTORY = re.compile(r"역사|조선|건립|창건|복원|왕세자|홍예|정문|\\b(?:1[0-9]{3}|20[0-9]{2})년")


# Fixed terminal codes declared by agent/core.py and agent/worker.py.
# Do not import the worker or accept arbitrary identifier-shaped server text.
SAFE_WORKER_ERROR_CODES = frozenset({
    "model_timeout", "invalid_model_output", "model_http_error",
    "model_transport_error", "model_call_limit", "job_timeout",
    "invalid_job_or_result", "service_http_error", "service_transport_error",
    "superseded", "invalid_photo_reference", "invalid_photo_type",
    "search_call_limit", "save_not_confirmed", "photo_too_large",
    "job_identity_mismatch", "invalid_assignment", "evidence_unavailable",
    "unknown_food_id", "unknown_shop_id", "unknown_place_id",
    "conflicting_place_confirmation", "unknown_dataset_mode", "unapproved_evidence",
})


def safe_worker_error_code(value):
    return value if isinstance(value, str) and value in SAFE_WORKER_ERROR_CODES else "unknown"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sample_bytes():
    """Validate both licensed files before any network, retaining checked bytes."""
    checked = {}
    for key, (filename, manifest_name) in SAMPLES.items():
        photo = ROOT / "data/samples" / filename
        manifest = photo.parent / manifest_name
        require(photo.is_file() and manifest.is_file(), "sample_or_manifest_missing")
        info = read_json(manifest)
        require(info.get("license") == "CC0-1.0"
                and str(info.get("status", "")).startswith("license_verified")
                and info.get("source_page")
                and (info.get("license_verification") or info.get("source_verification"))
                and info.get("local_file") == photo.relative_to(ROOT).as_posix(),
                "sample_license_unverified")
        content = photo.read_bytes()
        sha = base.hashlib.sha256(content).hexdigest()
        require(sha == info.get("sha256"), "sample_sha_mismatch")
        require(content.startswith(b"\xff\xd8") and 0 < len(content) <= 8 * 1024 * 1024,
                "invalid_sample_jpeg")
        checked[key] = (filename, content, {"sha256": sha, "license": "CC0-1.0",
                                          "manifest_sha256": base.digest(manifest)})
    return checked


SCENARIO_NAMES = ("culture_observe", "heritage_to_restaurant", "food_to_heritage")


def selected_scenarios(names=None):
    wanted = set(SCENARIO_NAMES if names is None else names)
    require(bool(wanted) and wanted <= set(SCENARIO_NAMES), "invalid_scenario_selection")
    return [name for name in SCENARIO_NAMES if name in wanted]


def selected_complete(records, names):
    return (bool(names) and [r["scenario"] for r in records] == list(names)
            and all(r["outcome"] == "completed_useful"
                    or (r["scenario"] == "culture_observe"
                        and r["outcome"] == "completed_clarification") for r in records))


def cases(catalog):
    anchors = {p["place_id"]: p for p in catalog["places"]}
    require("local:gwanghwamun" in anchors, "gwanghwamun_catalog_missing")
    gate = anchors["local:gwanghwamun"]
    location = {"lat": gate["lat"], "lng": gate["lng"], "origin": "selected"}
    return [
        ("culture_observe", "heritage", "observe", None, None, None,
         "이 장면의 문화장소를 관찰해 주세요. 광화문이나 궁궐인지 확신할 수 없으면 후보로 남기고 맥락 확인 질문을 해 주세요. 역사 설명은 승인된 문화 근거를 인용해 주세요."),
        ("heritage_to_restaurant", "heritage", "ask", location, None, "local:gwanghwamun",
         "제가 광화문으로 확인했고 카탈로그의 광화문 지점을 선택했습니다. 광화문의 역사를 근거와 함께 설명하고 선택 지점 1000m 안의 수록된 식당을 찾아 식사를 이어가게 도와주세요."),
        ("food_to_heritage", "food", "ask", dict(base.NEAR), "samgyetang", None,
         "사진의 음식은 제가 삼계탕으로 확인했습니다. 선택한 서촌 지점 1000m 안에서 식사 후 볼 문화유적을 찾아 역사와 문화 연결을 근거와 함께 설명해 주세요."),
    ]


def confirmation_check(raw, payload):
    scene = raw.get("scene")
    require(isinstance(scene, dict), "missing_raw_scene")
    for field in CONFIRMATIONS:
        require(field in scene and scene[field] == payload[field],
                "confirmation_not_preserved")


def culture_check(claims, approved):
    culture_ids = {e["id"] for e in approved["real_place"]
                   if "culture" in e.get("claim_scopes", []) or e.get("scope") == "culture"}
    cited = set()
    for claim in claims:
        if HISTORY.search(claim["text"]):
            require(claim["scope"] == "culture", "history_claim_wrong_scope")
        if claim["scope"] == "culture":
            ids = set(claim["evidence_ids"])
            require(bool(ids) and ids <= culture_ids, "culture_claim_missing_culture_evidence")
            cited.update(ids)
    return cited


def require_case_status(status, name):
    require(status in {"ready", "need_confirmation"}, "result_not_ready")
    require(name == "culture_observe" or status == "ready", "bidirectional_result_not_ready")


def check_download_headers(response, suffix, media_type):
    require(response.status_code == 200, "download_http_error")
    require(media_type in response.headers.get("content-type", "").lower(),
            "download_content_type_mismatch")
    disposition = response.headers.get("content-disposition", "").lower()
    require(disposition.startswith("attachment") and ("." + suffix) in disposition,
            "download_attachment_header_missing")


def check_result(raw, result, payload, name, approved, catalog):
    require_case_status(result["status"], name)
    confirmation_check(raw, payload)  # Raw keys, before schema defaults can hide omissions.
    metrics = base.check_result(result, payload, name, approved, catalog)
    canonical = {p["place_id"]: p for p in catalog["places"]}
    candidates = result["scene"]["place_candidates"]
    for candidate in candidates:
        require(candidate["id"] in canonical, "unknown_place_candidate")
    for place in result["places"]:
        require(place["kind"] == canonical[place["place_id"]].get("kind", "restaurant"),
                "place_kind_mismatch")
    cited = culture_check(result["claims"], approved)
    heritage_ids = {eid for place in canonical.values() if place.get("kind") == "heritage"
                    for eid in place.get("culture_evidence_ids", [])}
    culture_cited = cited & heritage_ids
    if name == "culture_observe":
        uncertain_candidate = any(canonical[c["id"]].get("kind") == "heritage" for c in candidates)
        clarification = bool((result["next_question"] or "").strip())
        require(uncertain_candidate or clarification or culture_cited, "observe_no_cultural_response")
    else:
        kind = "restaurant" if name == "heritage_to_restaurant" else "heritage"
        require(any(p["kind"] == kind for p in result["places"]), "required_place_kind_missing")
        if name == "heritage_to_restaurant":
            require(bool(cited & set(canonical["local:gwanghwamun"]["culture_evidence_ids"])),
                    "confirmed_heritage_culture_missing")
        else:
            returned_ids = {eid for p in result["places"] if p["kind"] == "heritage"
                            for eid in canonical[p["place_id"]].get("culture_evidence_ids", [])}
            require(bool(cited & returned_ids), "returned_heritage_culture_missing")
    metrics.update(culture_evidence_count=len(cited), confirmation_fields_preserved=True,
                   historical_truth_and_narrative_grounding="human_review_required",
                   search_provenance="broker_validated_result_not_independent_trace")
    return metrics


async def live(args, report, output, secrets):
    import httpx
    from pydantic import ValidationError
    from shared.models import GuideRequest, GuideResult

    samples = sample_bytes()
    catalog = read_json(ROOT / "data/catalog.json")
    approved = read_json(ROOT / "data/evidence.json")
    selected = [case for case in cases(catalog) if case[0] in args.selected_scenarios]
    report["samples"] = {k: v[2] for k, v in samples.items()}
    report["input_sha256"] = {p: base.digest(ROOT / p) for p in
                            ("shared/api-contract.md", "shared/models.py", "data/catalog.json",
                             "data/evidence.json", "tests/live/run_demo.py")}
    async with httpx.AsyncClient(base_url=args.base_url, timeout=5.0,
                                 follow_redirects=False, trust_env=False) as client:
        health = await base.json_call(client, "GET", "/api/health")
        require(health.get("status") == "ok" and health.get("worker_connected") is True,
                "service_not_ready")
        public = await base.json_call(client, "GET", "/api/catalog")
        expected = {p["place_id"]: p for p in catalog["places"]}
        require(public.get("catalog_version") == catalog["catalog_version"],
                "served_catalog_version_mismatch")
        actual = public.get("places", [])
        require(len(actual) == len(expected), "served_catalog_count_mismatch")
        require({p["place_id"] for p in actual} == set(expected), "served_catalog_ids_mismatch")
        for p in actual:
            require(all(p[k] == expected[p["place_id"]][k] for k in
                        ("name", "lat", "lng", "kind", "source_id")), "served_catalog_mismatch")
        session = await base.json_call(client, "POST", "/api/sessions", json={})
        sid = session.get("session_id")
        require(isinstance(sid, str) and bool(sid), "missing_session")
        secrets.append(sid)
        require(bool(client.cookies), "missing_session_cookie")
        secrets.extend(c.value for c in client.cookies.jar)
        uploaded_ids = {}
        for name, sample, mode, location, food, place, question in selected:
            record = {"scenario": name, "outcome": "not_started", "polls": 0}
            report["scenarios"].append(record)
            started = time.monotonic()
            try:
                if sample not in uploaded_ids:
                    filename, content, _ = samples[sample]
                    uploaded = await base.json_call(client, "POST", "/api/photos",
                                                    files={"file": (filename, content, "image/jpeg")})
                    pid = uploaded.get("photo_id")
                    require(isinstance(pid, str) and bool(pid), "missing_photo_id")
                    secrets.append(pid)
                    require(all(type(uploaded.get(k)) is int and 0 < uploaded[k] <= 1280
                                for k in ("width", "height")), "invalid_photo_dimensions")
                    uploaded_ids[sample] = pid
                payload = {"schema_version": 1, "session_id": sid, "question": question,
                           "photo_id": uploaded_ids[sample], "dataset_mode": "real_place",
                           "response_language": "ko", "location": location, "radius_m": 1000,
                           "confirmed_food_id": food, "confirmed_shop_id": None,
                           "confirmed_place_id": place, "interaction_mode": mode}
                GuideRequest.model_validate(payload)
                submitted = time.monotonic()
                rid, raw = await asyncio.wait_for(base.submit_poll(client, payload, record), 70.0)
                record["submit_to_terminal_ms"] = round((time.monotonic() - submitted) * 1000)
                secrets.append(rid)
                result = GuideResult.model_validate(raw).model_dump(mode="json")
                require(result["request_id"] == rid, "result_id_mismatch")
                secrets.extend(c.value for c in client.cookies.jar)
                base.write_json(output / f"{name}.result.json", result, secrets)
                base.write_json(output / "final-result.json", result, secrets)
                response = await client.get(f"/api/results/{rid}/download?format=json")
                check_download_headers(response, "json", "application/json")
                downloaded = response.json()
                require(downloaded == raw, "download_raw_result_mismatch")
                card = GuideResult.model_validate(downloaded).model_dump(mode="json")
                require(card == result, "download_result_mismatch")
                base.write_json(output / f"{name}.downloaded-card.json", card, secrets)
                record["download_matches_result"] = True
                record["json_download_headers_valid"] = True
                html = await client.get(f"/api/results/{rid}/download?format=html")
                check_download_headers(html, "html", "text/html")
                require(bool(html.content.strip()) and b"<html" in html.content.lower(),
                        "html_card_missing")
                record["html_download_headers_valid"] = True
                record["html_card_sha256"] = base.hashlib.sha256(html.content).hexdigest()
                record["html_semantic_match"] = "human_review_required"
                record.update(check_result(raw, result, payload, name, approved, catalog))
                record["outcome"] = ("completed_clarification" if result["status"] == "need_confirmation"
                                     else "completed_useful")
                record["result_status"] = result["status"]
            except asyncio.TimeoutError:
                record.update(outcome="timeout", diagnostic="submit_poll_exceeded_70s")
            except CheckError as exc:
                code = str(exc)
                record.update(outcome="not_ready" if code in
                              {"job_failed", "job_superseded", "result_not_ready"} else "failed",
                              diagnostic=code)
            except httpx.HTTPError:
                record.update(outcome="failed", diagnostic="http_transport_error")
            except (ValidationError, ValueError, TypeError, KeyError):
                record.update(outcome="failed", diagnostic="response_contract_invalid")
            finally:
                # Preserve known causes; never persist arbitrary worker-supplied text.
                if ("worker_error_code" in record
                        or record.get("last_job_state") in {"failed", "superseded"}):
                    record["worker_error_code"] = safe_worker_error_code(record.get("worker_error_code"))
                secrets.extend(c.value for c in client.cookies.jar)
                record["scenario_elapsed_ms"] = round((time.monotonic() - started) * 1000)
                base.write_json(output / "metrics.json", report, secrets)
            if record["outcome"] not in {"completed_useful", "completed_clarification"}:
                return  # Never queue another paid/model job after failure.


def check_helpers():
    base.check_helpers()
    catalog = read_json(ROOT / "data/catalog.json")
    approved = read_json(ROOT / "data/evidence.json")
    sample_bytes()
    assert [case[0] for case in cases(catalog)] == list(SCENARIO_NAMES)
    assert selected_scenarios() == list(SCENARIO_NAMES)
    assert selected_scenarios(["food_to_heritage"]) == ["food_to_heritage"]
    assert selected_scenarios(["food_to_heritage", "heritage_to_restaurant",
                               "food_to_heritage"]) == list(SCENARIO_NAMES[1:])
    subset = list(SCENARIO_NAMES[1:])
    successful = [{"scenario": name, "outcome": "completed_useful"} for name in subset]
    assert selected_complete(successful, subset)
    assert not selected_complete(successful[:1], subset)
    assert not selected_complete(successful, list(SCENARIO_NAMES))
    assert not selected_complete([{"scenario": subset[0], "outcome": "completed_clarification"}],
                                 subset[:1])
    assert selected_complete([{"scenario": "culture_observe",
                               "outcome": "completed_clarification"}], ["culture_observe"])
    for invalid in ([], ["unknown"]):
        try:
            selected_scenarios(invalid)
        except CheckError as exc:
            assert str(exc) == "invalid_scenario_selection"
        else:
            raise AssertionError("invalid selection accepted")
    require_case_status("need_confirmation", "culture_observe")
    for name in ("heritage_to_restaurant", "food_to_heritage"):
        require_case_status("ready", name)
        try:
            require_case_status("need_confirmation", name)
        except CheckError as exc:
            assert str(exc) == "bidirectional_result_not_ready"
        else:
            raise AssertionError("bidirectional clarification incorrectly passed")
    for code in SAFE_WORKER_ERROR_CODES:
        assert safe_worker_error_code(code) == code
    for unknown in (None, "", "model_timeout extra", "nvapi-private-value",
                    "Bearer private", "MODEL_TIMEOUT", 7, [], {}):
        assert safe_worker_error_code(unknown) == "unknown"
    assert base.redact({"worker_error_code": safe_worker_error_code("model_timeout")}) == {
        "worker_error_code": "model_timeout"}
    payload = dict.fromkeys(CONFIRMATIONS)
    confirmation_check({"scene": dict(payload)}, payload)
    good = {"scope": "culture", "text": "광화문의 역사", "evidence_ids":
            catalog["places"][-1]["culture_evidence_ids"]}
    assert culture_check([good], approved)
    for fn, code in (
        (lambda: confirmation_check({"scene": {}}, payload), "confirmation_not_preserved"),
        (lambda: confirmation_check({"scene": {**payload, "confirmed_place_id": "local:gwanghwamun"}},
                                    payload), "confirmation_not_preserved"),
        (lambda: culture_check([{**good, "evidence_ids": ["visitkorea:tosokchon-menu"]}], approved),
         "culture_claim_missing_culture_evidence"),
        (lambda: culture_check([{**good, "scope": "operation"}], approved), "history_claim_wrong_scope"),
    ):
        try:
            fn()
        except CheckError as exc:
            assert str(exc) == code
        else:
            raise AssertionError("negative helper case accepted")
    print("CULTURE_HELPERS_PASS: offline only; samples verified; no service/model/camera evidence")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    gates = parser.add_mutually_exclusive_group()
    gates.add_argument("--run-live", action="store_true")
    gates.add_argument("--check-helpers", action="store_true")
    parser.add_argument("--root-ready", action="store_true",
                        help="Operator attests root has declared this service deployment READY.")
    parser.add_argument("--base-url", type=base.base_url, default="http://127.0.0.1:8000")
    parser.add_argument("--scenario", action="append", choices=SCENARIO_NAMES,
                        help="Repeat to select a subset; deduplicated in canonical order. Default: all three.")
    args = parser.parse_args()
    args.selected_scenarios = selected_scenarios(args.scenario)
    if args.check_helpers:
        check_helpers()
        return 0
    if not args.run_live or not args.root_ready:
        print("NOT_RUN: --run-live AND --root-ready required after root declares READY; no HTTP/files.")
        return 2
    require(".runtime/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines(),
            "runtime_ignore_missing")
    output = ROOT / ".runtime/culture-qa" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "status": "INCOMPLETE",
              "root_ready_operator_attested": True, "selected_scenarios": args.selected_scenarios,
              "budget_seconds": 240, "poll_limit_seconds": 70,
              "latency_kind": "client_wall_clock_including_queue_tools_and_model",
              "model_provider": "unverifiable_from_browser_api", "model_latency_ms": None,
              "openshell": "independent_proof_required", "camera_microphone_tts": "not_tested",
              "singleflight_manual_priority_auto_frames": "not_tested",
              "historical_truth_and_narrative_grounding": "human_review_required", "scenarios": []}
    secrets = []
    started = time.monotonic()
    code = 1
    try:
        asyncio.run(asyncio.wait_for(live(args, report, output, secrets), 240.0))
        records = report["scenarios"]
        if selected_complete(records, args.selected_scenarios):
            report["status"] = ("COMPLETED_WITH_CLARIFICATION"
                                if any(c["outcome"] == "completed_clarification" for c in records)
                                else "COMPLETED_USEFUL")
            code = 0
    except asyncio.TimeoutError:
        report.update(status="TIMEOUT", diagnostic="overall_240s_budget_exceeded")
    except CheckError as exc:
        report.update(status="NOT_READY" if str(exc) == "service_not_ready" else "FAILED",
                      diagnostic=str(exc))
    except KeyboardInterrupt:
        report.update(status="INTERRUPTED", diagnostic="operator_interrupted")
    except Exception:
        report.update(status="FAILED", diagnostic="preflight_or_runtime_error")
    finally:
        report["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        base.write_json(output / "metrics.json", report, secrets)
    print(report["status"])
    for record in report["scenarios"]:
        print(record["scenario"], record["outcome"], record.get("diagnostic", ""))
    print("Evidence:", output.relative_to(ROOT))
    print("Historical meaning needs review; model/provider/OpenShell unverified; camera/mic/TTS untested.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
