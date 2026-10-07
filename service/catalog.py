"""Approved catalog helpers: no service-framework imports or network access."""
from __future__ import annotations

import json
import math
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_EVIDENCE_FIELDS = ("id", "source", "as_of", "type", "dataset_id")


def _load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def catalog_summary() -> dict:
    data = _load("catalog.json")
    return {"catalog_count": len(data["places"]), "scope_label": data["scope_label"],
            "catalog_version": data["catalog_version"]}


def food_candidates() -> list[dict]:
    return _load("catalog.json")["foods"]


def valid_food_ids() -> set[str]:
    return {food["id"] for food in food_candidates()}


def get_place(place_id: str) -> dict | None:
    data = _load("catalog.json")
    for place in data["places"]:
        if place["place_id"] == place_id:
            return {**{key: place[key] for key in ("place_id", "name", "lat", "lng", "source_id")},
                    "catalog_version": data["catalog_version"]}
    return None


def evidence_for_mode(mode: str) -> list[dict]:
    if mode not in {"real_place", "fictional_task"}:
        raise ValueError("unknown_dataset_mode")
    return [{key: item[key] for key in _EVIDENCE_FIELDS}
            for item in _load("evidence.json")[mode]]


def _distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (lat1, lng1, lat2, lng2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371008.8 * 2 * math.asin(min(1.0, math.sqrt(a)))


def search_places(food_id, shop_id, location, radius_m) -> dict:
    if type(radius_m) is not int or radius_m not in {500, 1000, 2000, 3000}:
        raise ValueError("invalid_radius")
    if food_id is not None and food_id not in valid_food_ids():
        raise ValueError("unknown_food_id")
    if shop_id is not None and get_place(shop_id) is None:
        raise ValueError("unknown_shop_id")
    summary = catalog_summary()
    result = {"places": [], "catalog_count": summary["catalog_count"], "scope_label": summary["scope_label"]}
    if location is None:
        return {**result, "needs_location": True}
    if not isinstance(location, dict) or location.get("origin") not in {"gps", "selected"}:
        raise ValueError("invalid_location")
    lat, lng = location.get("lat"), location.get("lng")
    if (type(lat) not in (int, float) or type(lng) not in (int, float)
            or not math.isfinite(lat) or not math.isfinite(lng)
            or not -90 <= lat <= 90 or not -180 <= lng <= 180):
        raise ValueError("invalid_location")
    for place in _load("catalog.json")["places"]:
        if shop_id is not None and place["place_id"] != shop_id:
            continue
        if food_id is not None and food_id not in place["food_ids"]:
            continue
        distance = _distance_m(lat, lng, place["lat"], place["lng"])
        if distance <= radius_m:
            result["places"].append({**get_place(place["place_id"]), "distance_m": round(distance, 1)})
    result["places"].sort(key=lambda place: place["distance_m"])
    return result
