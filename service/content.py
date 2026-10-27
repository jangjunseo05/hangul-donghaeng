"""Deterministic route templates around the catalog; no network access or model calls.

Leg distances are haversine between stop coordinates; walking minutes are a
labelled heuristic. Cards come from shared.cards (labels recomputed there).
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from shared.cards import catalog_card, has_catalog_card, relabel_block
from shared.models import RoutesResponse

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ROUTE_NEAR_LIMIT_M = 3000
WALK_DETOUR, WALK_M_PER_MIN = 1.3, 70

card_for = catalog_card
has_card = has_catalog_card


def _load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    a, b, c, d = map(math.radians, (lat1, lng1, lat2, lng2))
    value = math.sin((c - a) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, value))))


def name_key(value: str) -> str:
    return re.sub(r"[\W_]", "", value).casefold()


def routes(lang: str, near: tuple[float, float] | None = None) -> dict:
    places = {place["place_id"]: place for place in _load("catalog.json")["places"]}
    evidence = {record["id"]: record for record in _load("evidence.json")["real_place"]}
    name_key = "name_ko" if lang == "ko" else "name_en"
    result = []
    for template in _load("routes.json")["routes"]:
        stops = sorted(template["stops"], key=lambda stop: stop["order"])
        first = places[stops[0]["place_id"]]
        if near and distance_m(near[0], near[1], first["lat"], first["lng"]) > ROUTE_NEAR_LIMIT_M:
            continue
        notes = {(leg["from"], leg["to"]): leg.get("note") for leg in template["legs"]}
        legs = []
        for start, end in zip(stops, stops[1:]):
            a, b = places[start["place_id"]], places[end["place_id"]]
            meters = round(distance_m(a["lat"], a["lng"], b["lat"], b["lng"]))
            legs.append({"from_place_id": a["place_id"], "to_place_id": b["place_id"], "straight_line_m": meters,
                         "est_walk_min": math.ceil(meters * WALK_DETOUR / WALK_M_PER_MIN), "route_verified": False,
                         "note": notes.get((a["place_id"], b["place_id"])) if lang == "en" else None})
        window = template.get("time_window_note")
        visit_note = relabel_block({"text": window["text_" + lang], "evidence_ids": window["evidence_ids"]},
                                   evidence) if window else None
        result.append({
            "route_id": template["route_id"], "title": template["title_" + lang],
            "summary": template["summary_" + lang],
            "stops": [{"order": index, "place_id": stop["place_id"],
                       "name": places[stop["place_id"]].get(name_key, places[stop["place_id"]]["name"]),
                       "kind": places[stop["place_id"]].get("kind", "restaurant"),
                       "lat": places[stop["place_id"]]["lat"], "lng": places[stop["place_id"]]["lng"],
                       "dwell_min_estimate": stop["dwell_min"],
                       "note": stop.get("note" if lang == "en" else "note_ko"),
                       "has_card": has_catalog_card(stop["place_id"])} for index, stop in enumerate(stops, 1)],
            "legs": legs, "total_straight_line_m": sum(leg["straight_line_m"] for leg in legs),
            "total_dwell_min_estimate": sum(stop["dwell_min"] for stop in stops),
            "distance_basis": "straight_line",
            "ui_note": template["ui_label_" + lang] + (" " + visit_note["text"] if visit_note else ""),
            "evidence_ids": visit_note["evidence_ids"] if visit_note else [],
            "visit_note": visit_note})
    unknowns = (["직선거리 기준이며 출입문·관람시간·접근성은 확인되지 않았어요."] if lang == "ko" else
                ["Straight-line distances only; gates, opening hours and accessibility are not verified."])
    return RoutesResponse.model_validate({"schema_version": 1, "lang": lang, "routes": result[:2],
                                          "unknowns": unknowns}).model_dump(mode="json")
