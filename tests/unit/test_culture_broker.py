"""Culture/camera broker regressions; in-process HTTP and synthetic catalog only."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest
from fastapi.testclient import TestClient

from service import catalog
from service.main import create_app


AUTH = {"Authorization": "Bearer culture-test-worker"}
LOCATION = {"lat": 37.579, "lng": 126.973, "origin": "selected"}
PUBLIC_FIELDS = {"place_id", "name", "name_en", "kind", "lat", "lng", "source_id", "catalog_version"}


def place(place_id, kind, offset=0):
    return {"place_id": place_id, "name": f"Fixture {place_id}", "kind": kind,
            "lat": 37.579 + offset, "lng": 126.973, "distance_m": round(offset * 111000, 1),
            "source_id": f"source-{place_id}", "catalog_version": "culture-fixture-v1"}


@pytest.fixture
def broker(tmp_path, monkeypatch):
    # No production data files or external catalog/model calls are used.
    places = [place("restaurant-a", "restaurant"), place("heritage-a", "heritage", .001),
              place("heritage-unsearched", "heritage", .002)]
    calls = []

    def get_place(place_id):
        for entry in places:
            if entry["place_id"] == place_id:
                return {k: v for k, v in entry.items() if k != "distance_m"}
        return None

    def search(food_id, shop_id, location, radius_m, kind=None):
        calls.append((food_id, shop_id, deepcopy(location), radius_m, kind))
        selected = [p for p in places[:2] if kind is None or p["kind"] == kind]
        if shop_id is not None:
            selected = [p for p in selected if p["place_id"] == shop_id]
        return {"places": deepcopy(selected), "catalog_count": len(places), "scope_label": "Synthetic test catalog"}

    monkeypatch.setenv("GUIDE_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("GUIDE_COOKIE_SECURE", "false")
    monkeypatch.setattr(catalog, "get_place", get_place)
    monkeypatch.setattr(catalog, "valid_food_ids", lambda: {"fixture-food"})
    monkeypatch.setattr(catalog, "evidence_for_mode", lambda mode: [])
    monkeypatch.setattr(catalog, "search_places", search)
    app = create_app(tmp_path / "runtime", worker_token="culture-test-worker")
    with TestClient(app) as client:
        response = client.post("/api/sessions", json={})
        assert response.status_code == 200
        yield client, app.state.store, response.json()["session_id"], places, calls


def body(sid, **changes):
    return {"schema_version": 1, "session_id": sid, "question": "Explain this cultural place",
            "photo_id": None, "dataset_mode": "real_place", "response_language": "en",
            "location": deepcopy(LOCATION), "radius_m": 1000, "confirmed_food_id": None,
            "confirmed_shop_id": None, "confirmed_place_id": None, "interaction_mode": "ask", **changes}


def enqueue(broker, **changes):
    client, _, sid, _, _ = broker
    response = client.post("/api/requests", json=body(sid, **changes))
    assert response.status_code == 202, response.text
    return response.json()["request_id"]


def claim(broker, rid):
    response = broker[0].get("/worker/jobs/next", headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.json()["request_id"] == rid
    return response.json()


def result(sid, rid, **changes):
    return {"schema_version": 1, "session_id": sid, "request_id": rid,
            "captured_at": datetime.now(timezone.utc).isoformat(), "dataset_mode": "real_place",
            "status": "need_confirmation", "speech_text": "Please confirm the place.", "response_language": "en",
            "scene": {"food_candidates": [], "confirmed_food_id": None, "confirmed_shop_id": None,
                      "place_candidates": [], "confirmed_place_id": None},
            "places": [], "menus": [], "claims": [], "evidence": [], "conflicts": [], "itinerary": [],
            "order_ko": None, "unknowns": [], "next_question": "Which place is this?", "error_code": None, **changes}


def save(broker, rid, **changes):
    client, _, sid, _, _ = broker
    return client.post("/worker/results", headers=AUTH,
                       json={"session_id": sid, "request_id": rid, "result": result(sid, rid, **changes)})


def search(broker, rid, kind):
    client, _, sid, _, _ = broker
    response = client.post("/worker/search", headers=AUTH,
                           json={"session_id": sid, "request_id": rid, "food_id": None,
                                 "shop_id": None, "radius_m": 1000, "kind": kind})
    assert response.status_code == 200, response.text
    return response.json()["places"]


@pytest.mark.parametrize("state", ["queued", "running"])
def test_observe_cannot_supersede_manual_job(broker, state):
    client, store, sid, _, _ = broker
    rid = enqueue(broker)
    if state == "running":
        claim(broker, rid)
    before = set(store.jobs)
    rejected = client.post("/api/requests", json=body(sid, interaction_mode="observe"))
    assert rejected.status_code == 409
    assert rejected.json()["error_code"] == "JOB_BUSY"
    assert set(store.jobs) == before
    assert store.jobs[rid]["session"].active_request_id == rid
    assert client.get(f"/api/requests/{rid}").json()["status"] == state
    if state == "queued":
        claim(broker, rid)
    assert save(broker, rid).status_code == 200


@pytest.mark.parametrize("state", ["queued", "running"])
def test_manual_request_supersedes_observe_job(broker, state):
    client, store, _, _, _ = broker
    observed = enqueue(broker, interaction_mode="observe")
    if state == "running":
        claim(broker, observed)
    manual = enqueue(broker, question="My manual question takes priority")
    assert client.get(f"/api/requests/{observed}").json()["status"] == "superseded"
    stale = save(broker, observed)
    assert stale.status_code == 409 and stale.json()["error_code"] == "STALE_REQUEST"
    assert not (store.output / observed).exists()
    claim(broker, manual)
    assert save(broker, manual).status_code == 200


def test_completed_observations_preserve_full_manual_history(broker):
    expected = []
    for index in range(3):
        question, answer = f"Manual need {index}", f"Manual answer {index}"
        rid = enqueue(broker, question=question)
        claim(broker, rid)
        assert save(broker, rid, speech_text=answer).status_code == 200
        expected.extend([{"role": "user", "content": question}, {"role": "assistant", "content": answer}])
    for index in range(4):
        rid = enqueue(broker, interaction_mode="observe", question=f"Automatic scene {index}")
        assert claim(broker, rid)["history"] == expected
        assert save(broker, rid, speech_text=f"Automatic answer {index}").status_code == 200
        assert broker[1].jobs[rid]["session"].history == expected
        assert broker[0].get(f"/api/results/{rid}/download?format=json").status_code == 200
    manual = enqueue(broker, question="Keep my original needs")
    assert claim(broker, manual)["history"] == expected


@pytest.mark.parametrize("changes,code", [
    ({"confirmed_place_id": "unknown-place"}, "UNKNOWN_PLACE"),
    ({"confirmed_shop_id": "unknown-place"}, "UNKNOWN_PLACE"),
    ({"confirmed_place_id": "heritage-a", "confirmed_shop_id": "restaurant-a"}, "PLACE_CONFIRMATION_MISMATCH"),
])
def test_invalid_request_confirmation_does_not_replace_active_job(broker, changes, code):
    client, store, sid, _, _ = broker
    rid = enqueue(broker)
    response = client.post("/api/requests", json=body(sid, **changes))
    assert response.status_code == 422
    assert response.json()["error_code"] == code
    assert list(store.jobs) == [rid]
    assert store.jobs[rid]["session"].active_request_id == rid
    assert client.get(f"/api/requests/{rid}").json()["status"] == "queued"


@pytest.mark.parametrize("changes", [
    {"confirmed_place_id": "heritage-a"},
    {"confirmed_shop_id": "restaurant-a"},
    {"confirmed_place_id": "heritage-a", "confirmed_shop_id": "heritage-a"},
])
def test_valid_new_and_legacy_confirmations_remain_accepted(broker, changes):
    rid = enqueue(broker, **changes)
    assigned = claim(broker, rid)
    for key, value in changes.items():
        assert assigned["request"][key] == value
    scene = result(broker[2], rid)["scene"]
    scene.update(changes)
    assert save(broker, rid, scene=scene).status_code == 200


@pytest.mark.parametrize("confirmed,proposed", [(None, "heritage-a"), ("heritage-a", "restaurant-a"), ("heritage-a", None)])
def test_scene_cannot_invent_change_or_remove_place_confirmation(broker, confirmed, proposed):
    rid = enqueue(broker, confirmed_place_id=confirmed)
    claim(broker, rid)
    scene = result(broker[2], rid)["scene"]
    scene["confirmed_place_id"] = proposed
    response = save(broker, rid, scene=scene)
    assert response.status_code == 422
    assert response.json()["error_code"] == "PLACE_CONFIRMATION_MISMATCH"
    assert not (broker[1].output / rid).exists()
    scene["confirmed_place_id"] = confirmed
    assert save(broker, rid, scene=scene).status_code == 200


def test_scene_cannot_forge_legacy_shop_confirmation(broker):
    rid = enqueue(broker)
    claim(broker, rid)
    scene = result(broker[2], rid)["scene"]
    scene["confirmed_shop_id"] = "heritage-a"
    response = save(broker, rid, scene=scene)
    assert response.status_code == 422, "Unconfirmed legacy shop ID must not be accepted as user confirmation"
    assert not (broker[1].output / rid).exists()


def test_unknown_scene_candidate_is_rejected_but_known_unconfirmed_candidate_is_allowed(broker):
    rid = enqueue(broker)
    claim(broker, rid)
    scene = result(broker[2], rid)["scene"]
    scene["place_candidates"] = [{"id": "unknown-place", "name_ko": "Unknown", "name_en": "Unknown"}]
    response = save(broker, rid, scene=scene)
    assert response.status_code == 422 and response.json()["error_code"] == "UNKNOWN_PLACE"
    assert not (broker[1].output / rid).exists()
    scene["place_candidates"][0]["id"] = "heritage-a"
    assert save(broker, rid, scene=scene).status_code == 200


@pytest.mark.parametrize("kinds", [("restaurant", "heritage"), ("heritage", "restaurant")])
def test_both_searches_are_accumulated_and_saved(broker, kinds):
    client, store, _, _, calls = broker
    rid = enqueue(broker)
    claim(broker, rid)
    found = search(broker, rid, kinds[0]) + search(broker, rid, kinds[1])
    assert {p["kind"] for p in found} == {"restaurant", "heritage"}
    assert calls == [(None, None, LOCATION, 1000, kind) for kind in kinds]
    assert save(broker, rid, places=found).status_code == 200
    card = json.loads((store.output / rid / "travel-card.json").read_text(encoding="utf-8"))
    assert card["places"] == found
    assert client.get(f"/api/results/{rid}/download?format=json").json()["places"] == found


@pytest.mark.parametrize("tamper", ["unsearched", "latitude", "longitude", "restaurant-kind", "heritage-kind"])
def test_unsearched_or_tampered_places_cannot_be_saved(broker, tamper):
    rid = enqueue(broker)
    claim(broker, rid)
    found = search(broker, rid, "restaurant") + search(broker, rid, "heritage")
    altered = deepcopy(found)
    if tamper == "unsearched":
        altered.append(deepcopy(broker[3][2]))  # Known catalog ID, absent from this job's searches.
    elif tamper == "latitude":
        altered[0]["lat"] += .001
    elif tamper == "longitude":
        altered[0]["lng"] += .001
    elif tamper == "restaurant-kind":
        altered[0]["kind"] = "heritage"
    else:
        altered[1]["kind"] = "restaurant"
    response = save(broker, rid, places=altered)
    assert response.status_code == 422 and response.json()["error_code"] == "INVALID_PLACE"
    assert not (broker[1].output / rid).exists()
    assert broker[0].get(f"/api/requests/{rid}").json()["status"] == "running"
    assert save(broker, rid, places=found).status_code == 200


def test_public_catalog_response_uses_only_public_fields(broker, monkeypatch):
    # Exercise the real serializer over synthetic raw data; do not stub public_catalog.
    assert callable(getattr(catalog, "public_catalog", None)), "The public catalog contract must be implemented"
    private = "fixture-private-metadata-not-for-browser"
    raw_places = [{**p, "name_en": p["name"], "food_ids": [], "private_notes": private,
                   "api_key": private, "internal_path": private, "evidence_text": private}
                  for p in broker[3][:2]]
    raw = {"catalog_version": "culture-fixture-v1", "scope_label": "Synthetic test catalog",
           "places": raw_places, "foods": [], "worker_token": private}

    def load(name):
        assert name == "catalog.json"
        return deepcopy(raw)

    monkeypatch.setattr(catalog, "_load", load)
    monkeypatch.setenv("NVIDIA_API_KEY", "fixture-model-secret")
    monkeypatch.setenv("WORKER_TOKEN", "fixture-worker-secret")
    response = broker[0].get("/api/catalog")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"catalog_count", "scope_label", "catalog_version", "places"}
    assert payload["catalog_count"] == len(payload["places"]) == 2
    assert {entry["kind"] for entry in payload["places"]} == {"restaurant", "heritage"}
    assert all(set(entry) == PUBLIC_FIELDS for entry in payload["places"])
    for forbidden in (private, "fixture-model-secret", "fixture-worker-secret", "culture-test-worker"):
        assert forbidden not in response.text


def test_cross_mode_observe_preserves_manual_history_and_mode(broker):
    manual = enqueue(broker, question="Keep my real-place visit requirements")
    claim(broker, manual)
    assert save(broker, manual, speech_text="Saved real-place visit context").status_code == 200
    session = broker[1].jobs[manual]["session"]
    expected = [{"role": "user", "content": "Keep my real-place visit requirements"},
                {"role": "assistant", "content": "Saved real-place visit context"}]
    assert session.history == expected
    assert session.history_mode == "real_place"

    observed = enqueue(broker, interaction_mode="observe", dataset_mode="fictional_task",
                       question="Observe this fictional practice scene", location=None)
    assert session.history == expected
    assert session.history_mode == "real_place"
    assigned = claim(broker, observed)
    assert assigned["request"]["dataset_mode"] == "fictional_task"
    assert assigned["history"] == []
    assert session.history == expected
    assert session.history_mode == "real_place"

    saved = save(broker, observed, dataset_mode="fictional_task", speech_text="Fictional scene observation")
    assert saved.status_code == 200, saved.text
    assert session.history == expected
    assert session.history_mode == "real_place"
    resumed = enqueue(broker, question="Continue my real-place visit")
    assert claim(broker, resumed)["history"] == expected
