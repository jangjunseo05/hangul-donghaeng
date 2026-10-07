"""Render downloaded results as escaped text. Never execute model HTML."""
from html import escape


def markdown_card(result: dict) -> str:
    lines = ["# 한글동행 · Travel card", "", result["speech_text"], ""]
    for place in result["places"]:
        lines += [f"## {place['name']}", f"Straight-line distance: {place['distance_m']:.0f} m", ""]
    for menu in result["menus"]:
        lines += [f"### {menu['name_ko']}", menu["description"], " · ".join(menu["unknowns"]), ""]
    for item in result["itinerary"]:
        lines += [f"- {item['time']}: {item['activity']}"]
    if result["order_ko"]:
        lines += ["", "## 현장에서 물어볼 문장", result["order_ko"]]
    lines += ["", "## 확인할 점", *[f"- {s}" for s in result["unknowns"]]]
    lines += ["", "## 출처", *[f"- {e['id']}: {e['source']} (as of: {e['as_of'] or 'unknown'})" for e in result["evidence"]]]
    return "\n".join(lines) + "\n"


def html_card(result: dict) -> str:
    return ("<!doctype html><html lang='ko'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>한글동행 · Travel card</title>"
            "<style>body{max-width:760px;margin:32px auto;padding:24px;font:16px/1.7 system-ui;"
            "color:#20362e;background:#fffdf8}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}</style>"
            f"<body><pre>{escape(markdown_card(result))}</pre></body></html>")
