"""Broker-observed agent trace and stored OpenShell deployment evidence in health."""
import json

import pytest
from fastapi.testclient import TestClient

from service.main import create_app
from tests.unit.test_service import AUTH, new_job, result, save, session


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path, worker_token="test-worker-token")


def trace(client, rid):
    return client.get(f"/api/requests/{rid}").json()["trace"]


def test_trace_records_worker_steps_seen_at_the_broker(app):
    with TestClient(app) as client:
        sid = session(client)
        rid = new_job(client, sid)
        assert [e["name"] for e in trace(client, rid)] == ["request_accepted"]
        assert client.get("/worker/jobs/next", headers=AUTH).status_code == 200
        assert client.post("/worker/progress", headers=AUTH,
                           json={"session_id": sid, "request_id": rid, "stage": "matching"}).status_code == 200
        searched = client.post("/worker/search", headers=AUTH, json={
            "session_id": sid, "request_id": rid, "food_id": "samgyetang", "shop_id": None, "radius_m": 1000})
        assert searched.status_code == 200, searched.text
        assert save(client, sid, rid).status_code == 200
        events = trace(client, rid)
        assert [(e["kind"], e["name"], e["ok"]) for e in events] == [
            ("broker", "request_accepted", True), ("sandbox", "job_claimed", True),
            ("stage", "matching", True), ("tool", "catalog_search", True),
            ("check", "grounding_check", True), ("broker", "result_saved", True)]
        assert all(isinstance(e["t_ms"], int) and e["t_ms"] >= 0 for e in events)
        assert "result" in events[3]["detail"]


def test_trace_records_broker_rejections(app):
    with TestClient(app) as client:
        sid = session(client)
        rid = new_job(client, sid)
        client.get("/worker/jobs/next", headers=AUTH)
        bad = {"id": "invented", "source": "https://example.com", "as_of": None, "type": "document",
               "dataset_id": "invented"}
        assert save(client, sid, rid, evidence=[bad]).status_code == 422
        last = trace(client, rid)[-1]
        assert (last["kind"], last["name"], last["ok"], last["detail"]) == (
            "check", "grounding_check", False, "INVALID_EVIDENCE")
        radius = client.post("/worker/search", headers=AUTH, json={
            "session_id": sid, "request_id": rid, "food_id": "samgyetang", "shop_id": None, "radius_m": 3000})
        assert radius.status_code == 422
        assert trace(client, rid)[-1]["detail"] == "RADIUS_MISMATCH"


def test_health_exposes_stored_evidence_without_claiming_live_verification(app):
    with TestClient(app) as client:
        health = client.get("/api/health").json()
    assert health["sandbox_verified"] is False
    evidence = health["sandbox_evidence"]
    assert evidence["runtime"] == "OpenShell 0.1.2"
    assert evidence["boundary_verdict"] == "PASS"
    assert evidence["boundary_checks_passed"] == evidence["boundary_checks_total"] == 11
    assert evidence["policy_loaded"] is True
    assert evidence["worker"] == "hangul-worker-12"
    assert evidence["boundary_sandbox"] == "hangul-matrix-01"
    assert evidence["policy_read_write"] == ["/tmp", "/dev/null"]
    assert "POST :8001/v1/chat/completions" in evidence["policy_network_allow"]
    assert "POST :8000/worker/results" in evidence["policy_network_allow"]
    assert len(evidence["policy_hash"]) == 64
    assert evidence["scope"] == "stored_deployment_evidence"


def test_rejection_flood_cannot_hide_the_final_check(app):
    with TestClient(app) as client:
        sid = session(client)
        rid = new_job(client, sid)
        client.get("/worker/jobs/next", headers=AUTH)
        bad = {"session_id": sid, "request_id": rid, "food_id": "samgyetang", "shop_id": None, "radius_m": 3000}
        for _ in range(60):
            client.post("/worker/search", headers=AUTH, json=bad)
        assert save(client, sid, rid).status_code == 200
        events = trace(client, rid)
        assert len(events) <= 40
        assert [e["name"] for e in events].count("trace_truncated") == 1
        assert [e["name"] for e in events[-2:]] == ["grounding_check", "result_saved"]


def test_health_evidence_is_null_when_files_are_missing(tmp_path, monkeypatch):
    from service import main
    monkeypatch.setattr(main, "EVIDENCE_DIR", tmp_path / "missing")
    with TestClient(create_app(tmp_path, worker_token="test-worker-token")) as client:
        assert client.get("/api/health").json()["sandbox_evidence"] is None


def test_repeated_progress_does_not_flood_the_trace(app):
    with TestClient(app) as client:
        sid = session(client)
        rid = new_job(client, sid)
        client.get("/worker/jobs/next", headers=AUTH)
        for _ in range(50):
            client.post("/worker/progress", headers=AUTH, json={"session_id": sid, "request_id": rid, "stage": "writing"})
        assert [e["name"] for e in trace(client, rid)].count("writing") == 1
