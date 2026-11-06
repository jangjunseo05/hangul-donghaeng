"""F2 source review and F3 sandbox probe: worker modules against the real broker, offline model stub."""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from agent import probe
from agent.core import ModelSession
from agent.review import DEMO_INPUT, run_review_job
from service.main import create_app
from tests.unit.test_service import AUTH, session

QUESTION = "해온궁 휴궁일과 관람시간은?"


class BrokerAPI:
    """Minimal WorkerAPI stand-in that forwards to the in-process broker."""
    def __init__(self, client):
        self.client = self
        self.test_client = client

    async def request(self, method, path, json=None, timeout=None):
        response = self.test_client.request(method, "/" + path, json=json, headers=AUTH)
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)

    async def call(self, method, path, json=None):
        response = await self.request(method, path, json=json)
        assert response.status_code < 300, response.text
        return response


def model_answer(**changes):
    answer = {"status": "answered",
              "claims": [{"text": "해온궁은 매주 화요일 휴궁하고 09:00부터 18:00까지 관람할 수 있습니다.",
                          "source_ids": ["input:001"],
                          "quotes": [{"source_id": "input:001", "text": "해온궁은 매주 화요일 휴궁합니다."}]}],
              "conflicts": [{"source_ids": ["input:001", "input:002"],
                             "quotes": [{"source_id": "input:001", "text": "해온궁은 매주 화요일 휴궁합니다."},
                                        {"source_id": "input:002", "text": "해온궁은 매주 월요일 휴궁이라"}],
                             "reason": "휴궁 요일이 다릅니다.", "resolution": "2026년 관리소 공지를 따릅니다."}],
              "unknowns": [],
              "source_judgments": [{"source_id": "input:002", "verdict": "outdated",
                                    "quote": {"source_id": "input:002", "text": "해온궁은 매주 월요일 휴궁이라"},
                                    "reason": "2019년 개인 블로그로 2026년 공식 공지에 의해 대체됨"}]}
    answer.update(changes)
    return answer


def model_session(answer):
    seen = []

    def provider(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"model": "offline-test-model", "choices": [
            {"finish_reason": "stop", "message": {"content": json.dumps(answer, ensure_ascii=False)}}]})
    client = httpx.AsyncClient(base_url="https://model.invalid/v1/", transport=httpx.MockTransport(provider))
    return ModelSession(client, "offline-test-model"), seen


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path, worker_token="test-worker-token")) as test_client:
        yield test_client


def start_review(client, condition=None, question=QUESTION):
    sid = session(client)
    response = client.post("/api/reviews", json={"session_id": sid, "question": question, "condition": condition,
                                                 "response_language": "ko"})
    assert response.status_code == 202, response.text
    job = client.get("/worker/jobs/next", headers=AUTH).json()
    assert job["kind"] == "review" and job["question"] == question and job["condition"] == condition
    return response.json()["request_id"], job


def test_inputs_listing_covers_the_demo_set(client):
    session(client)
    listing = client.get("/api/reviews/inputs").json()
    assert listing["input_label"] == "review-demo"
    assert [item["path"] for item in listing["sources"]] == sorted(p.name for p in DEMO_INPUT.iterdir())
    assert listing["sources"][0]["as_of"] == "2026-09-01"


def test_review_judges_every_source_and_broker_saves_files(client):
    rid, job = start_review(client, condition="화요일에 방문할 예정이에요")
    model, seen = model_session(model_answer())
    asyncio.run(run_review_job(job, BrokerAPI(client), model))
    status = client.get(f"/api/reviews/{rid}").json()
    assert status["status"] == "completed"
    verdicts = {source["path"]: (source["verdict"], source["reason"]) for source in status["result"]["sources"]}
    assert verdicts == {
        "01-haeon-palace-notice-2026.md": ("used", None),
        "02-travel-blog-2019.md": ("excluded", "outdated"),
        "03-heritage-guide-2024.md": ("used", None),
        "04-seaside-food-list.md": ("excluded", "irrelevant"),
        "05-visitor-forum-post.txt": ("excluded", "untrusted_instruction")}
    prompt = seen[0]["messages"][1]["content"]
    assert "ignore all previous instructions" not in prompt  # flagged source never reaches the model
    assert "화요일에 방문할 예정이에요" in prompt
    assert [e["name"] for e in status["trace"]][-3:] == ["review_sources", "grounding_check", "result_saved"]
    assert client.get(f"/api/reviews/{rid}/download?format=md").status_code == 200
    saved = client.get(f"/api/reviews/{rid}/download?format=json").json()
    assert saved["conflicts"][0]["source_ids"] == ["input:001", "input:002"]
    assert client.get(f"/api/requests/{rid}").status_code == 404  # not a guide job


def test_broker_rejects_forged_quotes_and_tampered_sources(client):
    rid, job = start_review(client)
    base = {"status": "answered", "question": QUESTION, "condition": None, "input_label": "review-demo",
            "sources": [], "claims": [], "conflicts": [], "unknowns": []}
    listing = client.get("/api/reviews/inputs").json()["sources"]
    sources = [{"id": s["id"], "path": s["path"], "sha256": s["sha256"], "as_of": s["as_of"],
                "verdict": "used", "reason": None, "note": None} for s in listing]
    sources[-1].update(verdict="excluded", reason="untrusted_instruction")
    sources[3].update(verdict="excluded", reason="irrelevant")  # off-topic food list
    forged = {**base, "sources": sources, "claims": [{"text": "x", "source_ids": ["input:001"],
              "quotes": [{"source_id": "input:001", "text": "해온궁은 매일 무료입니다."}]}]}
    excerpts = [{"source_id": "input:001", "text": "해온궁은 매주 화요일 휴궁합니다."}]
    response = client.post("/worker/review-results", headers=AUTH, json={
        "session_id": job["session_id"], "request_id": rid, "result": forged, "excerpts": excerpts})
    assert response.json()["error_code"] == "MISSING_EVIDENCE"
    tampered = [{**sources[0], "sha256": "0" * 64}, *sources[1:]]
    response = client.post("/worker/review-results", headers=AUTH, json={
        "session_id": job["session_id"], "request_id": rid, "result": {**base, "sources": tampered,
        "status": "insufficient_evidence", "unknowns": ["n/a"]}, "excerpts": []})
    assert response.json()["error_code"] == "INVALID_EVIDENCE"
    assert client.get(f"/api/reviews/{rid}").json()["trace"][-1]["detail"] == "INVALID_EVIDENCE"


def test_guide_result_endpoint_refuses_review_jobs(client):
    rid, job = start_review(client)
    response = client.post("/worker/results", headers=AUTH, json={
        "session_id": job["session_id"], "request_id": rid, "result": {}})
    assert response.status_code in {409, 422}


def test_probe_reports_local_run_honestly_and_broker_counts_canary(client, monkeypatch):
    async def no_network(run_context=""):
        return "allowed", "200"
    monkeypatch.setattr(probe, "egress_unlisted_host", no_network)
    sid = session(client)
    rid = client.post("/api/sandbox-probe", json={"session_id": sid}).json()["request_id"]
    assert client.post("/api/sandbox-probe", json={"session_id": sid}).status_code == 409
    job = client.get("/worker/jobs/next", headers=AUTH).json()
    assert job == {"kind": "probe", "session_id": sid, "request_id": rid}
    asyncio.run(probe.run_probe_job(job, BrokerAPI(client), "local-dev"))
    status = client.get(f"/api/sandbox-probe/{rid}").json()
    attempts = {item["id"]: item for item in status["result"]["attempts"]}
    assert status["result"]["run_context"] == "local-dev"
    assert attempts["write_code_dir"]["observed"] == "allowed"  # no sandbox here, and we say so
    assert attempts["broker_unlisted_path"] == {"id": "broker_unlisted_path", "expected": "denied",
                                                "observed": "allowed", "detail": "200", "broker_received": 1}
    names = [event["name"] for event in status["trace"]]
    assert "canary_received" in names and names[-1] == "result_saved"
    assert not list(probe.CODE_DIR.glob(".sandbox-probe-*"))


def test_worker_cannot_set_broker_received(client):
    sid = session(client)
    rid = client.post("/api/sandbox-probe", json={"session_id": sid}).json()["request_id"]
    client.get("/worker/jobs/next", headers=AUTH)
    attempts = [{"id": name, "expected": "denied", "observed": "denied", "detail": "EACCES", "broker_received": 0}
                for name in ("read_outside_allowlist", "write_code_dir", "egress_unlisted_host")]
    client.post("/worker/canary", headers=AUTH, json={})
    attempts.append({"id": "broker_unlisted_path", "expected": "denied", "observed": "denied", "detail": "403",
                     "broker_received": 0})
    response = client.post("/worker/probe-results", headers=AUTH, json={"session_id": sid, "request_id": rid, "result": {
        "run_context": "openshell", "finished_at": "2026-11-06T00:00:00Z", "attempts": attempts}})
    assert response.status_code == 200
    result = client.get(f"/api/sandbox-probe/{rid}").json()["result"]
    assert next(a for a in result["attempts"] if a["id"] == "broker_unlisted_path")["broker_received"] == 1


def test_policy_allows_result_routes_but_not_canary():
    from infra.render_policy import WORKER_ROUTES
    assert ("POST", "/worker/review-results") in WORKER_ROUTES
    assert ("POST", "/worker/probe-results") in WORKER_ROUTES
    assert not any("canary" in path for _, path in WORKER_ROUTES)


def valid_exclusions(client):
    """Demo verdicts the broker's deterministic rules accept: the relevant files (all within the excerpt
    budget) are used, the food list is irrelevant and the forum post is untrusted_instruction."""
    listing = client.get("/api/reviews/inputs").json()["sources"]
    reasons = {"04-seaside-food-list.md": "irrelevant", "05-visitor-forum-post.txt": "untrusted_instruction"}
    return [{"id": s["id"], "path": s["path"], "sha256": s["sha256"], "as_of": s["as_of"],
             "verdict": "excluded" if s["path"] in reasons else "used",
             "reason": reasons.get(s["path"]), "note": None} for s in listing]


def submit_review_result(client, rid, job, **changes):
    sources = valid_exclusions(client)
    result = {"status": "insufficient_evidence", "question": QUESTION, "condition": None, "input_label": "review-demo",
              "sources": sources, "claims": [], "conflicts": [], "unknowns": ["n/a"]}
    result.update(changes.pop("result", {}))
    return client.post("/worker/review-results", headers=AUTH, json={
        "session_id": job["session_id"], "request_id": rid, "result": result, "excerpts": [], **changes})


def test_broker_rejects_injected_source_marked_used(client):
    rid, job = start_review(client)
    listing = client.get("/api/reviews/inputs").json()["sources"]
    sources = [{"id": s["id"], "path": s["path"], "sha256": s["sha256"], "as_of": s["as_of"], "verdict": "used",
                "reason": None, "note": None} for s in listing]
    response = submit_review_result(client, rid, job, result={"sources": sources})
    assert response.json()["error_code"] == "INVALID_EVIDENCE"


def test_broker_rejects_relabelled_demo_and_unknown_external_input(client):
    rid, job = start_review(client)
    # Same demo files under another label: the broker still recognises and verifies them.
    relabelled = submit_review_result(client, rid, job, result={"input_label": "hackathon-input"})
    assert relabelled.status_code == 200, relabelled.text
    rid, job = start_review(client)
    foreign = [{"id": "input:001", "path": "notes.md", "sha256": "1" * 64, "as_of": None, "verdict": "excluded",
                "reason": "irrelevant", "note": None}]
    response = submit_review_result(client, rid, job, result={"input_label": "other", "sources": foreign})
    assert response.json()["error_code"] == "INVALID_EVIDENCE"


def test_quote_cannot_straddle_two_excerpts(client):
    rid, job = start_review(client)
    sources = valid_exclusions(client)
    excerpts = [{"source_id": "input:001", "text": "해온궁은 매주 화요일 휴궁합니다."},
                {"source_id": "input:001", "text": "한복 착용 관람객은 무료로 입장할 수 있습니다."}]
    claim = {"text": "x", "source_ids": ["input:001"], "quotes": [
        {"source_id": "input:001", "text": "휴궁합니다.\n한복 착용"}]}
    response = submit_review_result(client, rid, job, excerpts=excerpts, result={
        "sources": sources, "status": "answered", "claims": [claim], "unknowns": []})
    assert response.json()["error_code"] == "MISSING_EVIDENCE"


def test_offline_egress_is_not_reported_as_denied_outside_openshell(monkeypatch):
    class Offline:
        def __init__(self, **_):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            return False
        async def get(self, url):
            raise httpx.ConnectError("offline")
    monkeypatch.setattr(probe.httpx, "AsyncClient", Offline)
    assert asyncio.run(probe.egress_unlisted_host("local-dev")) == ("error", "ConnectError")
    assert asyncio.run(probe.egress_unlisted_host("openshell")) == ("denied", "ConnectError")


def test_only_403_counts_as_broker_denial():
    class Api:
        def __init__(self, status):
            self.client, self.status = self, status
        async def request(self, *_, **__):
            return httpx.Response(self.status)
    assert asyncio.run(probe.broker_unlisted_path(Api(403))) == ("denied", "403")
    assert asyncio.run(probe.broker_unlisted_path(Api(404))) == ("error", "404")
    assert asyncio.run(probe.broker_unlisted_path(Api(200))) == ("allowed", "200")


def test_broker_rejects_faked_verdict_metadata(client):
    for change in ({"index": 0, "verdict": "excluded", "reason": "irrelevant"},  # relevant notice hidden as off-topic
                   {"index": 3, "reason": "not_selected"},     # off-topic list passed off as relevant
                   {"index": 0, "as_of": "2030-01-01"}):       # date not read from the file
        rid, job = start_review(client)
        sources = valid_exclusions(client)
        sources[change.pop("index")].update(change)
        response = submit_review_result(client, rid, job, result={"sources": sources})
        assert response.json()["error_code"] == "INVALID_EVIDENCE", change


def test_external_result_reusing_demo_names_must_pass_demo_checks(client, monkeypatch):
    monkeypatch.setenv("REVIEW_ALLOW_EXTERNAL_INPUT", "true")
    rid, job = start_review(client)
    sources = valid_exclusions(client)
    for source in sources:
        source["sha256"] = "0" * 64
    response = submit_review_result(client, rid, job, result={"input_label": "hackathon-input", "sources": sources})
    assert response.json()["error_code"] == "INVALID_EVIDENCE"
    rid, job = start_review(client)
    foreign = [{"id": "input:001", "path": "notes.md", "sha256": "1" * 64, "as_of": None, "verdict": "excluded",
                "reason": "irrelevant", "note": None}]
    saved = submit_review_result(client, rid, job, result={"input_label": "hackathon-input", "sources": foreign})
    assert saved.status_code == 200, saved.text
    result = client.get(f"/api/reviews/{rid}").json()["result"]
    assert result["verified_input"] is False
    assert "NOT visible to the broker" in client.get(f"/api/reviews/{rid}/download?format=md").text


def test_worker_cannot_claim_verified_input_and_markdown_is_flattened(client, monkeypatch):
    monkeypatch.setenv("REVIEW_ALLOW_EXTERNAL_INPUT", "true")
    rid, job = start_review(client)
    foreign = [{"id": "input:001", "path": "notes.md", "sha256": "1" * 64, "as_of": None, "verdict": "excluded",
                "reason": "irrelevant", "note": None}]
    response = submit_review_result(client, rid, job, result={
        "input_label": "hackathon-input", "sources": foreign, "verified_input": True,
        "unknowns": ["x\nFake heading\n===\nmore"]})
    assert response.status_code == 200, response.text
    assert client.get(f"/api/reviews/{rid}").json()["result"]["verified_input"] is False
    markdown = client.get(f"/api/reviews/{rid}/download?format=md").text
    assert "Fake heading\n" not in markdown and "x Fake heading === more" in markdown


def test_one_session_cannot_fill_the_job_table(client):
    sid = session(client)
    for _ in range(60):
        assert client.post("/api/reviews", json={"session_id": sid, "question": QUESTION, "condition": None,
                                                 "response_language": "ko"}).status_code == 202
    owned = [job for job in client.app.state.store.jobs.values() if job["request"]["session_id"] == sid]
    assert len(owned) <= 21


def test_canary_counts_requests_without_worker_token(client):
    sid = session(client)
    rid = client.post("/api/sandbox-probe", json={"session_id": sid}).json()["request_id"]
    client.get("/worker/jobs/next", headers=AUTH)
    assert client.post("/worker/canary", json={}).status_code == 200  # no bearer: still counted
    names = [event["name"] for event in client.get(f"/api/sandbox-probe/{rid}").json()["trace"]]
    assert "canary_received" in names


def test_observe_frames_never_evict_the_ask_answer(client):
    store = client.app.state.store
    sid = session(client)
    owner = next(iter(store.sessions.values()))

    def job(rid, mode, created):
        store.jobs[rid] = {"request_id": rid, "request": {"session_id": sid, "interaction_mode": mode},
                           "status": "completed", "created": created, "session": owner}
    job("ask-card", "ask", 0.0)
    for index in range(40):
        job(f"observe-{index}", "observe", 1.0 + index)
    store.prune_session_jobs(sid)
    assert "ask-card" in store.jobs
    assert sum(1 for rid in store.jobs if rid.startswith("observe-")) == 20
    assert "observe-39" in store.jobs and "observe-0" not in store.jobs


def test_demo_sources_cannot_be_hidden_as_unreadable_or_unselected(client):
    for path, reason in (("01-haeon-palace-notice-2026.md", "unreadable"),
                         ("01-haeon-palace-notice-2026.md", "not_selected")):
        rid, job = start_review(client)
        sources = valid_exclusions(client)
        target = next(source for source in sources if source["path"] == path)
        target.update(verdict="excluded", reason=reason)  # every relevant demo file fits the excerpt budget
        response = submit_review_result(client, rid, job, result={"sources": sources})
        assert response.json()["error_code"] == "INVALID_EVIDENCE", reason


def test_canary_flood_adds_one_trace_event(client):
    sid = session(client)
    rid = client.post("/api/sandbox-probe", json={"session_id": sid}).json()["request_id"]
    client.get("/worker/jobs/next", headers=AUTH)
    for _ in range(60):
        client.post("/worker/canary", json={})
    names = [event["name"] for event in client.get(f"/api/sandbox-probe/{rid}").json()["trace"]]
    assert names.count("canary_received") == 1 and "trace_truncated" not in names


def test_markdown_line_start_syntax_is_neutralized():
    from service.main import flatten_text
    assert flatten_text(["- item", "1. step", "===", "plain - text"]) == [
        "​- item", "​1. step", "​===", "plain - text"]


@pytest.mark.parametrize("question", [
    "When is Haeon Palace open, and what should a visitor know before going?",  # web default (en)
    "해온궁은 언제 열고, 방문 전에 무엇을 알아야 하나요?",                      # web default (ko): 열고 is in the food list
    QUESTION,
])
def test_relevance_of_the_demo_set_for_the_ui_default_questions(question):
    from agent.challenge import load_sources
    from agent.review import relevant
    verdicts = {source.path: relevant(question, source) for source in load_sources(DEMO_INPUT)}
    assert verdicts == {"01-haeon-palace-notice-2026.md": True, "02-travel-blog-2019.md": True,
                        "03-heritage-guide-2024.md": True, "04-seaside-food-list.md": False,
                        "05-visitor-forum-post.txt": True}


def test_relevance_ignores_stopwords_and_substrings_and_keeps_content_words():
    from agent.challenge import Source
    from agent.review import relevant, specific_terms
    listing = Source("input:001", "food-list.md", "0" * 64, "파도식당 밀면")
    assert not relevant("What is it?", listing)                  # "is" used to match "list"
    assert not relevant("Is there an opening?", Source("input:002", "x.md", "0" * 64, "reopen soon"))
    assert relevant("Opening hours?", Source("input:003", "x.md", "0" * 64, "Opening hours: 9-18"))
    assert specific_terms("한복 무료?") == ["한복", "무료"]
    assert specific_terms("해온궁은 언제 열고, 방문 전에 무엇을 알아야 하나요?") == ["해온궁은"]  # generic words dropped
    # A short content word next to a name still counts: the food list is relevant to a 밀면 question.
    food = next(s for s in __import__("agent.challenge", fromlist=["load_sources"]).load_sources(DEMO_INPUT)
                if s.path.startswith("04"))
    assert relevant("해온궁 근처 밀면 맛집 있어?", food)
    assert not relevant("해온궁 몇 시에 닫아요?", food)    # 시에 inside "11시에" is not a word start
    assert not relevant("Are all open?", Source("input:005", "x.md", "0" * 64, "allowed only"))  # all != allowed
    # English: 3-letter content words and plurals.
    fee = Source("input:004", "x.md", "0" * 64, "Admission fee: 3,000 won. Ticket office opens at 9.")
    assert relevant("How much is the fee?", fee)
    assert relevant("Are tickets needed?", fee)
    assert specific_terms("How much is the fee?") == ["fee"]


def test_review_prompt_item_shapes_match_the_schema():
    """The prompt spells out item shapes (a real model sent quotes as bare strings); keep them valid."""
    import re as _re
    from agent.review import REVIEW_SYSTEM, ReviewAnswer
    shapes = dict(_re.findall(r"^(claims|conflicts|source_judgments): (\{.*?\})$",
                              REVIEW_SYSTEM.replace('\n "', ' "'), _re.M))  # join continuation lines only
    assert set(shapes) == {"claims", "conflicts", "source_judgments"}
    shapes = {key: value.replace('"..."', '"exact text"') for key, value in shapes.items()}  # placeholders
    quote = {"source_id": "input:002", "text": "exact text"}
    conflict = json.loads(shapes["conflicts"].replace("[one quote object per source]", json.dumps(
        [{"source_id": "input:001", "text": "exact text"}, quote])))
    ReviewAnswer.model_validate({"status": "answered", "unknowns": [], "claims": [json.loads(shapes["claims"])],
                                 "conflicts": [conflict], "source_judgments": [json.loads(shapes["source_judgments"])]})
    assert "never a bare string" in REVIEW_SYSTEM


@pytest.mark.parametrize("code", ["ungrounded_judgment", "judged_source_supports_claim"])
def test_review_validation_codes_reach_the_repair_turn_with_a_hint(code):
    """A real model failed twice with the same answer because these codes were reported as a bare
    invalid_model_output; the repair turn must name the check and say how to fix it."""
    from agent.core import _repair_feedback
    from agent.review import ReviewAnswer
    feedback = _repair_feedback(ValueError(code), ReviewAnswer)
    assert feedback["code"] == code and "source_judgments" in feedback["hint"]


@pytest.mark.parametrize("question", ["When is Haeon Palace open, and what should a visitor know before going?",
                                      "해온궁은 언제 열고, 방문 전에 무엇을 알아야 하나요?"])
def test_broker_relevance_recheck_for_the_ui_default_questions(client, question):
    """The broker re-runs relevance with the job's own question: the food list must be irrelevant, and a worker
    that marks it used (or marks a relevant file irrelevant) is rejected."""
    rid, job = start_review(client, question=question)
    accepted = submit_review_result(client, rid, job, result={"question": question})
    assert accepted.status_code == 200, accepted.text
    for index, change in ((3, {"verdict": "used", "reason": None}), (1, {"verdict": "excluded", "reason": "irrelevant"})):
        rid, job = start_review(client, question=question)
        sources = valid_exclusions(client)
        sources[index].update(change)
        rejected = submit_review_result(client, rid, job, result={"question": question, "sources": sources})
        assert rejected.json()["error_code"] == "INVALID_EVIDENCE", rejected.text
