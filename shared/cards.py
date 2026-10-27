"""Landmark card assembly shared by the broker (validation) and the worker (drafting).

Verification labels are recomputed from the cited evidence (decision 7), never
trusted from authored files or a model:
  any public-source record (wikipedia:/wikidata:/osm:) -> at least public_source
  only catalog records -> catalog; no evidence -> model_unverified
The card label is the weakest block. Quoted source text stays in data/ and is not served.
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from shared.models import VERIFICATION_ORDER, LandmarkCard

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PUBLIC_PREFIXES = ("wikipedia:", "wikidata:", "osm:")
BLOCKS = ("what_it_is", "why_it_matters", "what_to_look_for", "fun_fact")
PUBLISHERS = (("visitseoul.net", "Visit Seoul"), ("visitkorea.or.kr", "Korea Tourism Organization"),
              ("seoul.go.kr", "Seoul Metropolitan Government"), ("korea.net", "Korea.net"))


def evidence_label(evidence_id: str) -> str:
    return "public_source" if evidence_id.startswith(PUBLIC_PREFIXES) else "catalog"


def relabel_block(block: dict | None, known: dict[str, dict], *, dated: bool = False) -> dict | None:
    """Drop unknown ids and recompute the label; an uncited block becomes model_unverified.

    dated=True (visit notes): attach the reference date, the block's own as_of or else the
    newest as_of of its cited records. Story blocks carry none: as_of is not an event date.
    """
    if block is None:
        return None
    ids = [item for item in dict.fromkeys(block.get("evidence_ids", [])) if item in known]
    labels = [known[item].get("verification") or evidence_label(item) for item in ids]
    label = max(labels, key=VERIFICATION_ORDER.index) if labels else "model_unverified"
    dates = [known[item]["as_of"] for item in ids if isinstance(known[item].get("as_of"), str)]
    as_of = (block.get("as_of") or max(dates, default=None)) if dated else None
    return {"text": block["text"], "evidence_ids": ids, "verification": label,
            "analogy": bool(block.get("analogy", False)), "as_of": as_of}


def source_title(url: str) -> str | None:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if host.endswith("wikipedia.org") and parts.path.startswith("/wiki/"):
        return unquote(parts.path[len("/wiki/"):]).replace("_", " ")
    return next((label for suffix, label in PUBLISHERS if host == suffix or host.endswith("." + suffix)), None)


def build_card(place_id: str | None, name: str, lang: str, blocks: dict, visit_note: dict | None,
               known: dict[str, dict]) -> dict:
    """known maps evidence id -> record with source and optional title/license/verification."""
    relabeled = {key: relabel_block(blocks.get(key), known) for key in BLOCKS}
    note = relabel_block(visit_note, known, dated=True)
    if note is not None and note["verification"] == "model_unverified":
        note = None  # Operation facts are never written from model knowledge.
    present = [block for block in (*relabeled.values(), note) if block is not None]
    ids = sorted({item for block in present for item in block["evidence_ids"]})
    card = {"schema_version": 1, "place_id": place_id, "name": name, "lang": lang, "blocks": relabeled,
            "visit_note": note, "evidence_ids": ids,
            "verification": max((block["verification"] for block in present), key=VERIFICATION_ORDER.index),
            "sources": [{"id": item, "url": known[item]["source"],
                         "title": known[item].get("title") or source_title(known[item]["source"]),
                         "license": known[item].get("license"),
                         "verification": known[item].get("verification") or evidence_label(item)} for item in ids]}
    return LandmarkCard.model_validate(card).model_dump(mode="json")


def _load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _authored() -> dict:
    places = {place["place_id"]: place for place in _load("catalog.json")["places"]}
    evidence = {record["id"]: record for record in _load("evidence.json")["real_place"]}
    cards = {}
    for item in _load("cards.json")["cards"]:
        place = places[item["place_id"]]
        name = place.get("name_ko", place["name"]) if item["lang"] == "ko" else place.get("name_en", place["name"])
        cards[(item["place_id"], item["lang"])] = build_card(
            item["place_id"], name, item["lang"], item["blocks"], item.get("visit_note"), evidence)
    return cards


def catalog_card(place_id: str, lang: str) -> dict | None:
    """Pre-authored card for a catalog place; no model call (research guide §3)."""
    card = _authored().get((place_id, lang))
    return json.loads(json.dumps(card)) if card else None


def has_catalog_card(place_id: str) -> bool:
    return any(key[0] == place_id for key in _authored())
