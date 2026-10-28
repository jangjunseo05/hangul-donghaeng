"""Evaluation runner with an HTTP-stub model: candidate building, decisions and metrics; no network."""
import asyncio
import io
import json

import httpx
from PIL import Image

from infra import eval_landmarks as runner

GATE_GPS = {"lat": 37.5760179589004, "lng": 126.976788008924}


def sample(sample_id, expected, split="positive", condition="gps_correct", gps=GATE_GPS):
    return {"sample_id": sample_id, "image": f"commons:File:{sample_id}.jpg", "split": split,
            "gps_condition": condition, "gps": gps, "expected_place_id": expected}


def test_candidates_follow_gps_condition():
    assert runner.candidates_for(sample("a", "local:gwanghwamun", condition="gps_none", gps=None)) == []
    near = [item["id"] for item in runner.candidates_for(sample("a", "local:gwanghwamun"))]
    assert near[0] == "local:gwanghwamun" and "local:geunjeongjeon" in near
    assert runner.candidates_for(sample("a", "local:gwanghwamun"))[0]["part_of"] == "Gyeongbokgung Palace"
    namsan = {"lat": 37.5512, "lng": 126.9882}
    assert runner.candidates_for(sample("b", "local:gwanghwamun", condition="gps_wrong", gps=namsan)) == []


def test_run_records_choices_and_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "SECOND_LOOK", True)
    image = io.BytesIO()
    Image.new("RGB", (8, 8)).save(image, "JPEG")
    samples = [sample("gate-1", "local:gwanghwamun"), sample("gate-2", "local:gwanghwamun"),
               sample("tower-1", None, split="easy_negative"),
               sample("free-1", "local:gwanghwamun", condition="gps_none", gps=None),
               sample("missing", "local:bukchon")]
    for item in samples[:4]:
        (tmp_path / f"{item['sample_id']}.jpg").write_bytes(image.getvalue())
    replies = [
        {"visual_basis": "Three arches.", "visual_cues": ["arches"], "scene_kind": "landmark",
         "place_id": "local:gwanghwamun", "confidence": "high", "landmark_name": None},
        {"name_board_text": "광화문", "unique_cue": "name board", "verdict": "yes"},
        {"visual_basis": "Dark.", "visual_cues": [], "scene_kind": "other", "place_id": "unknown",
         "confidence": "low", "landmark_name": None},
        {"visual_basis": "Gate.", "visual_cues": [], "scene_kind": "landmark", "place_id": "local:gwanghwamun",
         "confidence": "medium", "landmark_name": None},
        {"visual_basis": "Gate.", "visible_text": None, "scene_kind": "landmark",
         "is_cultural_landmark": True, "landmark_name": "광화문", "identification_supported": True},
    ]
    prompts = []

    def model(request):
        prompts.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(replies.pop(0))}}]})

    results = asyncio.run(runner.run(samples, tmp_path, "http://model/v1", "stub", False,
                                     transport=httpx.MockTransport(model)))
    predicted = {item["sample_id"]: item["predicted_place_id"] for item in results}
    # tower-1 chose a candidate without any distinctive cue -> not suggested (M5 1a);
    # free-1 named a landmark freely -> kept as a model name, never a catalog id (M5 1c).
    assert predicted == {"gate-1": "local:gwanghwamun", "gate-2": "unknown", "tower-1": "unknown",
                         "free-1": "unknown", "missing": "unknown"}
    assert results[2]["raw_choice"] == "local:gwanghwamun" and results[3]["free_name"] == "광화문"
    assert results[0]["verify_verdict"] == "yes" and "verify_verdict" not in results[2]
    assert results[-1]["error_code"] == "image_missing"
    assert all(len(item["parsed_output_sha256"]) == 64 for item in results[:4])
    assert "local:gwanghwamun" in prompts[0]["messages"][-1]["content"][0]["text"]
    summary = runner.metrics(results)
    assert summary["top1_accuracy"] == 0.5 and summary["abstain_rate"] == 0.5
    assert summary["false_accept_rate"] == 0.0  # negatives only
    assert summary["free_recognition_named_rate"] == 1.0
    assert summary["confidence_calibration"]["high"] == {"n": 1, "precision": 1.0}
    assert summary["errors"] == {"image_missing": 1}


def test_samples_file_validation(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text(json.dumps(sample("ok-1", "local:bukchon")) + "\n\n"
                    + json.dumps({**sample("drop-1", "local:bukchon"), "review_status": "drop"}) + "\n"
                    + json.dumps({**sample("keep-1", "local:bukchon"), "review_status": "keep"}) + "\n", encoding="utf-8")
    assert [item["sample_id"] for item in runner.load_samples(path)] == ["ok-1", "keep-1"]
    path.write_text(json.dumps({**sample("../x", "local:bukchon")}) + "\n", encoding="utf-8")
    try:
        runner.load_samples(path)
    except ValueError as exc:
        assert "unsafe" in str(exc)
    else:
        raise AssertionError("unsafe sample id accepted")


def test_rows_sharing_an_image_use_one_file(tmp_path):
    first = {**sample("gate-02__gps_correct", "local:gwanghwamun"), "image_id": "gate-02"}
    second = {**sample("gate-02__gps_none", "local:gwanghwamun", condition="gps_none", gps=None), "image_id": "gate-02"}
    assert runner.image_path(tmp_path, first) == runner.image_path(tmp_path, second) == tmp_path / "gate-02.jpg"


def test_metric_definitions_split_negatives_and_location_override():
    rows = [
        {"split": "hard_negative", "gps_condition": "gps_complex", "predicted_place_id": "local:gwanghwamun", "confidence": "high", "latency_ms": 1},
        {"split": "hard_negative", "gps_condition": "gps_none", "predicted_place_id": "unknown", "free_name": "Injeongjeon", "confidence": None, "latency_ms": 1},
        {"split": "easy_negative", "gps_condition": "gps_complex", "predicted_place_id": "unknown", "confidence": "low", "latency_ms": 1},
        {"split": "positive", "gps_condition": "gps_wrong", "expected_place_id": "local:gwanghwamun", "predicted_place_id": "unknown", "free_name": "Gwanghwamun", "confidence": None, "latency_ms": 1},
        {"split": "positive", "gps_condition": "gps_wrong", "expected_place_id": "local:bukchon", "predicted_place_id": "unknown", "confidence": None, "latency_ms": 1},
    ]
    summary = runner.metrics(rows)
    # Naming the lookalike correctly ("Injeongjeon") is not a false accept; a catalog choice is.
    assert summary["false_accept_rate"] == round(1 / 3, 4)
    assert summary["negative_any_suggestion_rate"] == round(2 / 3, 4)
    assert summary["false_accept_by_condition"]["gps_none"] == {"n": 1, "rate": 0.0, "any_suggestion_rate": 1.0}
    rows[1]["free_name"] = "Gyeongbokgung Palace"
    assert runner.metrics(rows)["false_accept_rate"] == round(2 / 3, 4)
    assert summary["location_override_rate"] == 0.5


def test_legacy_results_are_rescored_without_name_mapping():
    legacy = [{"split": "positive", "gps_condition": "gps_none", "candidates": [], "free_name": "Gwanghwamun Gate",
               "expected_place_id": "local:gwanghwamun", "predicted_place_id": "local:gwanghwamun"}]
    assert runner.rescore_legacy(legacy)[0]["predicted_place_id"] == "unknown"
