"""Landmark recognition evaluation (research §M2-4 JSONL) against the self-hosted VLM.

PLAN ONLY until the orchestrator approves image download and GPU use (L40S via tunnel):
  python -B infra/eval_landmarks.py --samples ../.orchestra/research/eval/landmark-eval.jsonl \
      --images .runtime/eval-images --download            # Commons thumbnails, 1 req/s, ignored dir
  python -B infra/eval_landmarks.py --samples ... --images .runtime/eval-images --run \
      --base-url http://127.0.0.1:8001/v1 --model nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16
Without --download/--run nothing touches the network. Images are never committed.

Each sample runs the product's observe decision directly against the model:
- gps_correct / gps_complex / gps_wrong: closed-set choice among catalog heritage within 1 km of
  the sample gps (plus live OSM landmarks with --osm), same prompt/schema as agent/core.py.
- gps_none: free recognition (product behaviour without location); the tentative name is mapped
  to a catalog id only by exact catalog name, else unknown.
Outputs results-<model>-<date>.jsonl and metrics-<model>-<date>.json next to --out.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import time
from urllib.parse import quote

import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run as a script from any directory
from agent.core import AgentError, ModelSession  # noqa: E402
from agent.visual_observation import (CANDIDATE_PROMPT, CandidateObservation, VISUAL_PROMPT, VISUAL_SYSTEM,
                                      VerifyObservation, VisualObservation, BOARD_BASES, board_choice, verify_prompt)
from service.catalog import catalog_places
from service.content import distance_m

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_RADIUS_M = 1000
SECOND_LOOK = False  # --second-look: M5 decision 3b verification (off in the product by default)
COMPLEX_IDS = {"local:gwanghwamun", "local:geunjeongjeon", "local:gyeonghoeru"}
DEMO_IDS = COMPLEX_IDS  # M6 decision 2: demo shots are Gwanghwamun, Geunjeongjeon, Gyeonghoeru on Gyeongbokgung GPS
# M7 decision 3: images matching the fixed demo shots (Gwanghwamun front with board, Geunjeongjeon front with
# board, Gyeonghoeru across the pond by day). Tagged by eye from thumbnails, 2026-10-28; see demo-shots.md.
DEMO_FIXED_IMAGES = {"gwanghwamun-04", "gwanghwamun-09", "gwanghwamun-r02", "geunjeongjeon-r03", "geunjeongjeon-r04",
                     "gyeonghoeru-03", "gyeonghoeru-09", "gyeonghoeru-r03", "gyeonghoeru-r04"}
THUMB_HOSTS = ("https://upload.wikimedia.org/", "https://thumb.wikimedia.org/")
USER_AGENT = "HangulDonghaeng/0.2 (+https://github.com/jangjunseo05/hangul-donghaeng) eval"


def load_samples(path: Path) -> list[dict]:
    samples = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get("review_status", "keep") != "keep":
            continue  # research review: only keep rows; relabeled rows already carry the new expected id/split
        for key in ("sample_id", "image", "split", "gps_condition"):
            if key not in item:
                raise ValueError(f"line {number}: missing {key}")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", item["sample_id"]):
            raise ValueError(f"line {number}: unsafe sample_id")
        samples.append(item)
    return samples


def _name_key(value: str) -> str:
    return re.sub(r"[\W_]", "", value).casefold()


def catalog_candidates(gps: dict | None) -> list[dict]:
    heritage = [place for place in catalog_places() if place.get("kind") == "heritage"]
    names = {place["place_id"]: place.get("name_en", place["name"]) for place in catalog_places()}
    found = []
    for place in heritage:
        distance = 0.0 if gps is None else distance_m(gps["lat"], gps["lng"], place["lat"], place["lng"])
        if gps is None or distance <= CANDIDATE_RADIUS_M:
            found.append({"id": place["place_id"], "name_ko": place.get("name_ko", place["name"]),
                          "name_en": place.get("name_en", place["name"]), "kind": "heritage",
                          "distance_m": round(distance),
                          **({"part_of": names[place["parent_place_id"]]} if place.get("parent_place_id") else {})})
    return sorted(found, key=lambda item: (item["distance_m"], item["id"]))[:5]


def osm_candidates(gps: dict) -> list[dict]:
    from service.nearby import search_nearby
    found = search_nearby(landmark_name=None, location={**gps, "origin": "selected"},
                          radius_m=CANDIDATE_RADIUS_M, tab="landmark")
    return [{"id": place["place_id"], "name_ko": place["name"], "name_en": place.get("name_en") or place["name"],
             "kind": "landmark", "distance_m": round(place["distance_m"])} for place in found.get("places", [])]


def candidates_for(sample: dict, use_osm: bool = False) -> list[dict]:
    gps = sample.get("gps")
    if sample["gps_condition"] == "gps_none" or not gps:
        return []
    local = catalog_candidates(gps)
    if use_osm:
        names = {_name_key(item["name_ko"]) for item in local} | {_name_key(item["name_en"]) for item in local}
        local += [item for item in osm_candidates(gps)
                  if _name_key(item["name_ko"]) not in names and _name_key(item["name_en"]) not in names]
    return sorted(local, key=lambda item: (item["distance_m"], item["id"]))[:5]


def with_hanja(candidates: list[dict]) -> list[dict]:
    """Official Hanja names come from the catalog by id, as in the product (agent/core.py)."""
    hanja = {place["place_id"]: place.get("name_hanja") for place in catalog_places()}
    return [{**item, "name_hanja": hanja.get(item["id"])} for item in candidates]


def board_others(ids: set[str]) -> list[dict]:
    return [{"name_ko": place.get("name_ko") or place["name"], "name_hanja": place.get("name_hanja")}
            for place in catalog_places() if place["place_id"] not in ids]


def _messages(prompt: str, image: bytes) -> list[dict]:
    return [{"role": "system", "content": VISUAL_SYSTEM},
            {"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {
                "url": "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")}}]}]


async def evaluate(session_factory, sample: dict, image: bytes, candidates: list[dict]) -> dict:
    model = session_factory()
    started = time.perf_counter()
    record = {"sample_id": sample["sample_id"], "split": sample["split"], "gps_condition": sample["gps_condition"],
              "expected_place_id": sample.get("expected_place_id"), "candidates": [item["id"] for item in candidates],
              "predicted_place_id": "unknown", "confidence": None, "error_code": None}
    try:
        if candidates:
            ids = {item["id"] for item in candidates}

            def check(choice):
                if choice.place_id != "unknown" and choice.place_id not in ids:
                    raise ValueError("unknown_candidate")

            shown = [{key: item[key] for key in ("id", "name_en", "name_ko", "kind", "distance_m", "part_of")
                      if key in item} for item in candidates]
            parsed = await model.structured(_messages(
                CANDIDATE_PROMPT + json.dumps(shown, ensure_ascii=False) + "\nReturn the observation in this schema: "
                + json.dumps(CandidateObservation.model_json_schema()), image), CandidateObservation, check)
            # Same acceptance rule as the product (agent/core.py): name board first, else a distinctive cue.
            chosen, basis = board_choice(parsed, with_hanja(candidates), board_others(ids))
            record["predicted_place_id"] = chosen or "unknown"
            record["raw_choice"] = parsed.place_id
            record["board_basis"] = basis
            record["name_board_text"] = parsed.name_board_text
            if basis in BOARD_BASES:
                parsed = parsed.model_copy(update={"landmark_name": None,
                                                   "confidence": "high" if chosen else parsed.confidence})
            if record["predicted_place_id"] != "unknown" and SECOND_LOOK:
                chosen = next(item for item in shown if item["id"] == record["predicted_place_id"])
                verdict = await model.structured(_messages(verify_prompt(chosen) + json.dumps(
                    VerifyObservation.model_json_schema()), image), VerifyObservation)
                record["verify_verdict"] = verdict.verdict
                record["name_board_text"] = verdict.name_board_text
                if verdict.verdict != "yes":
                    record["predicted_place_id"] = "unknown"
            record["visual_cues"] = parsed.visual_cues
            record["confidence"] = parsed.confidence
            if (parsed.place_id == "unknown" and parsed.scene_kind == "landmark" and parsed.landmark_name
                    and record.get("verify_verdict") in (None, "yes")):
                record["free_name"] = parsed.landmark_name
        else:
            parsed = await model.structured(_messages(
                VISUAL_PROMPT + json.dumps(VisualObservation.model_json_schema()), image), VisualObservation)
            # M5 decision 1(c): a free name is a tentative "model" suggestion, never a catalog id.
            if parsed.scene_kind == "landmark" and parsed.is_cultural_landmark and parsed.identification_supported \
                    and parsed.landmark_name:
                record["free_name"] = parsed.landmark_name
        record["parsed_output_sha256"] = hashlib.sha256(parsed.model_dump_json().encode()).hexdigest()
    except AgentError as exc:
        record["error_code"] = exc.code
    record["latency_ms"] = round((time.perf_counter() - started) * 1000)
    return record


def _rate(hits: int, total: int) -> float | None:
    return round(hits / total, 4) if total else None


def suggested(item: dict) -> bool:
    """The product would tell the visitor "This may be X": a catalog choice or a free model name."""
    return item["predicted_place_id"] != "unknown" or bool(item.get("free_name"))


def _catalog_keys() -> set[str]:
    return {_name_key(value) for place in catalog_places()
            for value in (place["name"], place.get("name_en", ""), place.get("name_ko", "")) if value}


def claims_catalog_place(item: dict, keys: set[str] | None = None) -> bool:
    """False accept = presenting one of OUR places: a catalog choice, or a free name that is a catalog
    name (contained either way). Correctly naming a different landmark is not a false accept."""
    if item["predicted_place_id"] != "unknown":
        return True
    name = _name_key(item.get("free_name") or "")
    keys = _catalog_keys() if keys is None else keys
    return len(name) >= 4 and any(key in name or name in key for key in keys if len(key) >= 4)


def metrics(results: list[dict]) -> dict:
    """M5 definitions (research §M4-1): false accept over negatives only; gps_wrong separately."""
    ok = [item for item in results if not item.get("error_code")]
    positive = [item for item in ok if item["split"] == "positive"]
    negative = [item for item in ok if item["split"] != "positive"]
    correct = [item for item in positive if item["gps_condition"] == "gps_correct"]
    complex_rows = [item for item in positive if item["gps_condition"] == "gps_complex"
                    and item.get("expected_place_id") in COMPLEX_IDS]
    wrong = [item for item in positive if item["gps_condition"] == "gps_wrong"]
    free = [item for item in positive if item["gps_condition"] == "gps_none"]
    calibration = {}
    for level in ("high", "medium", "low"):
        rows = [item for item in positive if item["confidence"] == level and item["predicted_place_id"] != "unknown"]
        calibration[level] = {"n": len(rows), "precision": _rate(
            sum(item["predicted_place_id"] == item["expected_place_id"] for item in rows), len(rows))}
    latencies = sorted(item["latency_ms"] for item in results if item.get("latency_ms"))
    confusion = defaultdict(Counter)
    for item in ok:
        confusion[item.get("expected_place_id") or item["split"]][item["predicted_place_id"]] += 1
    keys = _catalog_keys()
    by_condition = {}
    for condition in sorted({item["gps_condition"] for item in negative}):
        rows = [item for item in negative if item["gps_condition"] == condition]
        by_condition[condition] = {"n": len(rows), "rate": _rate(sum(claims_catalog_place(item, keys) for item in rows), len(rows)),
                                    "any_suggestion_rate": _rate(sum(map(suggested, rows)), len(rows))}
    return {
        "samples": len(results), "errors": Counter(item["error_code"] for item in results if item.get("error_code")),
        "top1_accuracy": _rate(sum(item["predicted_place_id"] == item["expected_place_id"] for item in correct), len(correct)),
        "complex_accuracy": _rate(sum(item["predicted_place_id"] == item["expected_place_id"] for item in complex_rows),
                                  len(complex_rows)),
        "false_accept_rate": _rate(sum(claims_catalog_place(item, keys) for item in negative), len(negative)),
        "negative_any_suggestion_rate": _rate(sum(map(suggested, negative)), len(negative)),
        "false_accept_by_condition": by_condition,
        "location_override_rate": _rate(sum(map(suggested, wrong)), len(wrong)),
        "free_recognition_named_rate": _rate(sum(map(suggested, free)), len(free)),
        "abstain_rate": _rate(sum(item["predicted_place_id"] == "unknown" for item in correct), len(correct)),
        "confidence_calibration": calibration,
        "latency_ms": {"p50": statistics.median(latencies) if latencies else None,
                       "p95": latencies[max(0, math.ceil(0.95 * len(latencies)) - 1)] if latencies else None},
        "confusion": {expected: dict(row) for expected, row in confusion.items()},
        "board_basis": dict(Counter(item.get("board_basis", "n/a") for item in ok)),
        "demo_subset": demo_metrics(results),
        "demo_fixed": demo_metrics(results, DEMO_FIXED_IMAGES),
        "targets": {"top1_accuracy": ">=0.80", "complex_accuracy": ">=0.70", "false_accept_rate": "<=0.05",
                    "abstain_rate": "<=0.15", "high_precision": ">=0.95"},
    }


def _image_id(item: dict) -> str:
    return item.get("image_id") or item.get("sample_id", "").split("__")[0]


def demo_metrics(results: list[dict], images: set[str] | None = None) -> dict:
    """M6 decision 2: demo-scope subset. Positives = demo places photographed with Gyeongbokgung GPS
    (gps_correct or the palace centroid gps_complex); negatives = lookalikes on that same GPS (gps_complex).
    With images (M7 demo_fixed), positives are further limited to the fixed demo shots."""
    ok = [item for item in results if not item.get("error_code")]
    positive = [item for item in ok if item["split"] == "positive" and item.get("expected_place_id") in DEMO_IDS
                and item["gps_condition"] in ("gps_correct", "gps_complex")
                and (images is None or _image_id(item) in images)]
    negative = [item for item in ok if item["split"] != "positive" and item["gps_condition"] == "gps_complex"]
    keys = _catalog_keys()
    return {
        "top1_accuracy": _rate(sum(item["predicted_place_id"] == item["expected_place_id"] for item in positive),
                               len(positive)),
        "positives": len(positive),
        "false_accept_rate": _rate(sum(claims_catalog_place(item, keys) for item in negative), len(negative)),
        "negatives": len(negative),
        "board_basis": dict(Counter(item.get("board_basis", "n/a") for item in positive + negative)),
        "targets": {"top1_accuracy": ">=0.90", "false_accept_rate": "<=0.10"},
    }


def rescore_legacy(rows: list[dict]) -> list[dict]:
    """Apply M5 rules to an M4 results file: free names are no longer catalog ids."""
    rescored = []
    for item in rows:
        item = dict(item)
        if item.get("gps_condition") == "gps_none" or not item.get("candidates"):
            if item.get("free_name"):
                item["predicted_place_id"] = "unknown"
        rescored.append(item)
    return rescored


def rescore_board(rows: list[dict]) -> list[dict]:
    """Re-decide recorded closed-set choices with the current name-board rule and catalog (no model call).
    Needs M6+ rows (name_board_text, raw_choice, visual_cues). scene_kind was not recorded: a row whose
    cue-backed choice was not accepted had a non-landmark scene; every other row is treated as a landmark."""
    rescored = []
    for item in rows:
        item = dict(item)
        if "board_basis" in item and item.get("candidates") and not item.get("error_code"):
            ids = set(item["candidates"])
            cues = [cue for cue in item.get("visual_cues") or [] if isinstance(cue, str) and cue.strip()]
            not_landmark = (item["board_basis"] == "cues" and item["predicted_place_id"] == "unknown"
                            and item.get("raw_choice") in ids and bool(cues))
            choice = CandidateObservation(visual_basis="recorded", visual_cues=cues[:5],
                                          scene_kind="other" if not_landmark else "landmark",
                                          place_id=item.get("raw_choice") or "unknown",
                                          confidence=item.get("confidence") or "low",
                                          name_board_text=item.get("name_board_text"))
            by_id = {place["place_id"]: place for place in catalog_places()}
            candidates = with_hanja([{"id": place_id, "name_ko": by_id[place_id].get("name_ko", by_id[place_id]["name"])}
                                     for place_id in item["candidates"] if place_id in by_id])
            chosen, basis = board_choice(choice, candidates, board_others(ids))
            item["m6_board_basis"], item["m6_predicted_place_id"] = item["board_basis"], item["predicted_place_id"]
            item["predicted_place_id"], item["board_basis"] = chosen or "unknown", basis
            if basis in BOARD_BASES:
                item.pop("free_name", None)
                if chosen:
                    item["confidence"] = "high"
        rescored.append(item)
    return rescored


def image_path(images: Path, sample: dict) -> Path:
    # One file per image: several rows (GPS conditions) share an image_id.
    key = sample.get("image_id") or sample["sample_id"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", key):
        raise ValueError("unsafe image_id")
    return images / f"{key}.jpg"


def download(samples: list[dict], images: Path, width: int = 960) -> dict:
    """Commons thumbnails only (no originals), serial, 1 request/second, identifying UA."""
    images.mkdir(parents=True, exist_ok=True)
    failed = {}
    with httpx.Client(timeout=20.0, headers={"User-Agent": USER_AGENT}, follow_redirects=True, trust_env=False) as client:
        for sample in samples:
            target = image_path(images, sample)
            if target.exists() or not sample["image"].startswith("commons:File:"):
                continue
            title = sample["image"][len("commons:"):]
            try:
                info = client.get("https://commons.wikimedia.org/w/api.php", params={
                    "action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url",
                    "iiurlwidth": width, "format": "json"}).json()
                page = next(iter(info["query"]["pages"].values()))
                url = page["imageinfo"][0]["thumburl"]
                if not url.startswith(THUMB_HOSTS):
                    raise ValueError("unexpected thumbnail host")
                time.sleep(1.0)
                response = client.get(url)
                if response.status_code != 200 or not response.headers.get("content-type", "").startswith("image/"):
                    raise ValueError(f"thumbnail http {response.status_code}")
                target.write_bytes(response.content)
            except (httpx.HTTPError, KeyError, IndexError, StopIteration, ValueError) as exc:
                failed[target.stem] = str(exc)[:120]
            time.sleep(1.0)
    return failed


async def run(samples, images: Path, base_url: str, model_id: str, use_osm: bool, transport=None) -> list[dict]:
    headers = {"Authorization": "Bearer " + os.environ["SELF_HOSTED_API_KEY"]} if os.getenv("SELF_HOSTED_API_KEY") else {}
    results = []
    async with httpx.AsyncClient(base_url=base_url.rstrip("/") + "/", headers=headers, transport=transport,
                                 follow_redirects=False, trust_env=False) as client:
        for sample in samples:
            path = image_path(images, sample)
            if not path.exists():
                results.append({"sample_id": sample["sample_id"], "split": sample["split"],
                                "gps_condition": sample["gps_condition"], "error_code": "image_missing",
                                "expected_place_id": sample.get("expected_place_id"),
                                "predicted_place_id": "unknown", "confidence": None, "latency_ms": 0})
                continue
            results.append(await evaluate(lambda: ModelSession(client, model_id), sample, path.read_bytes(),
                                          candidates_for(sample, use_osm)))
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path)
    parser.add_argument("--images", type=Path, default=ROOT / ".runtime" / "eval-images")
    parser.add_argument("--out", type=Path, default=ROOT / ".runtime" / "eval")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--model", default="nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16")
    parser.add_argument("--osm", action="store_true", help="Add live OSM landmark candidates (broker-style lookup).")
    parser.add_argument("--download", action="store_true", help="Fetch Commons thumbnails (approval required).")
    parser.add_argument("--run", action="store_true", help="Call the model (approval required).")
    parser.add_argument("--second-look", action="store_true", help="Add the yes/no verification call (3b).")
    parser.add_argument("--recompute", type=Path, help="Score an existing results-*.jsonl with the current metrics.")
    args = parser.parse_args(argv)
    if args.recompute:
        rows = [json.loads(line) for line in args.recompute.read_text(encoding="utf-8").splitlines() if line.strip()]
        print(json.dumps(metrics(rescore_board(rescore_legacy(rows))), ensure_ascii=False, indent=2))
        return 0
    global SECOND_LOOK
    SECOND_LOOK = args.second_look
    if not args.samples:
        parser.error("--samples is required unless --recompute is given")
    samples = load_samples(args.samples)
    if args.download:
        failed = download(samples, args.images)
        print(json.dumps({"download_failed": failed}, ensure_ascii=False))
    if not args.run:
        counts = Counter((item["split"], item["gps_condition"]) for item in samples)
        missing = sum(not image_path(args.images, item).exists() for item in samples)
        print(json.dumps({"samples": len(samples), "by_split_condition": {f"{a}/{b}": n for (a, b), n in counts.items()},
                          "images_missing": missing}, ensure_ascii=False, indent=2))
        print("NOT_RUN: pass --run after the orchestrator approves GPU use.")
        return 0
    results = asyncio.run(run(samples, args.images, args.base_url, args.model, args.osm))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = re.sub(r"[^A-Za-z0-9_.-]", "_", args.model.split("/")[-1])
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"results-{tag}-{stamp}.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in results), encoding="utf-8")
    summary = metrics(results)
    (args.out / f"metrics-{tag}-{stamp}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
