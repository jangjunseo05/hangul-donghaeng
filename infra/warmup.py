"""Warm the demo stack before presenting (M4 decision 7): one vision request and one TTS request.

  python -B infra/warmup.py [--broker http://127.0.0.1:8000]

The first vision request after a vLLM (re)start can exceed the 35 s model-call bound (M3 smoke),
and Magpie builds its first utterance slowly. This sends an observe frame without location
(free recognition, no OSM call) and one short Korean TTS sentence through the running broker.
Exit 0 only when both succeed. No secrets are needed; nothing is stored.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
PHOTO = ROOT / "data" / "samples" / "heritage-demo.jpg"
TERMINAL = {"completed", "failed", "superseded"}


def vision(client: httpx.Client, session_id: str, limit_s: float) -> dict:
    started = time.perf_counter()
    with PHOTO.open("rb") as handle:
        photo = client.post("/api/photos", files={"file": ("warmup.jpg", handle, "image/jpeg")},
                            data={"purpose": "observe"})
    if photo.status_code != 200:
        return {"ok": False, "error_code": photo.json().get("error_code")}
    created = client.post("/api/requests", json={
        "schema_version": 1, "session_id": session_id, "question": "warm-up", "photo_id": photo.json()["photo_id"],
        "dataset_mode": "real_place", "response_language": "en", "location": None, "radius_m": 1000,
        "confirmed_food_id": None, "confirmed_shop_id": None, "interaction_mode": "observe"})
    if created.status_code != 202:
        return {"ok": False, "error_code": created.json().get("error_code")}
    status = {}
    while time.perf_counter() - started < limit_s:
        status = client.get(created.json()["poll_url"]).json()
        if status["status"] in TERMINAL:
            break
        time.sleep(0.5)
    return {"ok": status.get("status") == "completed", "status": status.get("status"),
            "error_code": status.get("error_code"), "latency_s": round(time.perf_counter() - started, 2)}


def speech(client: httpx.Client) -> dict:
    started = time.perf_counter()
    response = client.post("/api/tts", json={"text": "안녕하세요, 한글동행이에요.", "lang": "ko"})
    return {"ok": response.status_code == 200, "http_status": response.status_code,
            "content_type": response.headers.get("content-type"), "voice": response.headers.get("x-tts-voice"),
            "latency_s": round(time.perf_counter() - started, 2),
            "error_code": None if response.status_code == 200 else response.json().get("error_code")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="http://127.0.0.1:8000")
    parser.add_argument("--vision-limit", type=float, default=90.0, help="Seconds to wait for the vision job.")
    args = parser.parse_args(argv)
    with httpx.Client(base_url=args.broker, timeout=40.0, trust_env=False, follow_redirects=False) as client:
        health = client.get("/api/health").json()
        if not health.get("worker_connected"):
            print(json.dumps({"ok": False, "reason": "worker not connected", "health": health}))
            return 2
        created = client.post("/api/sessions", json={})
        if created.status_code != 200:
            print(json.dumps({"ok": False, "reason": "session refused", "error_code": created.json().get("error_code")}))
            return 2
        report = {"vision": vision(client, created.json()["session_id"], args.vision_limit), "tts": speech(client)}
    report["ok"] = report["vision"]["ok"] and report["tts"]["ok"]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
