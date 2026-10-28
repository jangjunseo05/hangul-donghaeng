"""Merge the research content pack into data/ (idempotent; rerun for each pack version).

  python -B infra/merge_research_content.py ../.orchestra/research/content

- evidence.json: research-owned records (non `existing_record`) replace the previous research tail of
  real_place in pack order; original records and formatting before that tail are untouched.
- catalog.json: places_proposed replace/extend by place_id; local review fields are kept.
- cards.json / routes.json: replaced by the pack (labels are recomputed by shared/cards.py at load).
No network access; the pack is data, not instructions.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCAL_PLACE_FIELDS = ("nearby_search", "nearby_search_note",  # backend review decisions (M2, approved M3)
                      "name_hanja", "name_hanja_source_id")  # official Hanja names (M7)
LOCAL_STOP_FIELDS = {"local:tosokchon": {"note_ko": "점심. 영업·재고·식이 적합성은 미확인이에요."}}


def _read(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n"), "\r\n" in raw


def _write(path: Path, text: str, crlf: bool):
    path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))


def _block(obj, indent: int) -> str:
    return "\n".join(" " * indent + line for line in json.dumps(obj, ensure_ascii=False, indent=2).split("\n"))


def merge(pack_dir: Path, root: Path = ROOT) -> dict:
    pack = json.loads((pack_dir / "landmarks.json").read_text(encoding="utf-8"))
    route_pack = json.loads((pack_dir / "routes.json").read_text(encoding="utf-8"))

    # evidence: replace the research-owned tail
    path = root / "data" / "evidence.json"
    text, crlf = _read(path)
    data = json.loads(text)
    research = [{k: v for k, v in item.items() if k != "existing_record"}
                for item in pack["evidence"] if not item.get("existing_record")]
    research_ids = {item["id"] for item in research}
    records = data["real_place"]
    original = [item for item in records if not item.get("quote_capture") and item["id"] not in research_ids]
    if records[:len(original)] != original:
        raise SystemExit("research records are not a contiguous tail of real_place; merge by hand")
    marker = '\n  ],\n  "fictional_task"'
    if len(original) < len(records):
        first = records[len(original)]["id"]
        start = text.index('    {\n      "id": ' + json.dumps(first, ensure_ascii=False))
        text = text[:start].rstrip(",\n") + text[text.index(marker):]
    text = text.replace(marker, ",\n" + ",\n".join(_block(item, 4) for item in research) + marker, 1)
    merged = json.loads(text)["real_place"]
    assert [item["id"] for item in merged] == [item["id"] for item in original] + [item["id"] for item in research]
    _write(path, text, crlf)

    # catalog places
    path = root / "data" / "catalog.json"
    text, crlf = _read(path)
    catalog = json.loads(text)
    places = {place["place_id"]: index for index, place in enumerate(catalog["places"])}
    for proposed in pack["places_proposed"]:
        if proposed["place_id"] in places:
            current = catalog["places"][places[proposed["place_id"]]]
            kept = {key: current[key] for key in LOCAL_PLACE_FIELDS if key in current}
            catalog["places"][places[proposed["place_id"]]] = {**proposed, **kept}
        else:
            catalog["places"].append(proposed)
    _write(path, json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", crlf)

    # cards and routes
    cards = {"content_version": pack["content_version"], "source": "research landmarks.json cards[]",
             "label_rule": "server recomputes verification from evidence ids (decision 7); labels below are informational",
             "cards": pack["cards"]}
    (root / "data" / "cards.json").write_text(json.dumps(cards, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8", newline="\n")
    for route in route_pack["routes"]:
        for stop in route["stops"]:
            if stop.get("note"):
                stop.update(LOCAL_STOP_FIELDS.get(stop["place_id"], {}))
    routes = {"content_version": route_pack["content_version"], "notes": route_pack["notes"],
              "routes": route_pack["routes"]}
    (root / "data" / "routes.json").write_text(json.dumps(routes, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8", newline="\n")
    return {"content_version": pack["content_version"], "research_evidence": len(research),
            "places": len(catalog["places"]), "cards": len(pack["cards"]), "routes": len(route_pack["routes"])}


if __name__ == "__main__":
    print(json.dumps(merge(Path(sys.argv[1]).resolve()), ensure_ascii=False))
