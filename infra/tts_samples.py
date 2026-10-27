"""Generate Magpie voice samples for the user's listening test (research M1 §5).

PLAN ONLY until Magpie runs on the approved L40S and infra/open_tts_tunnel.sh is up:
  python -B infra/tts_samples.py --base-url http://127.0.0.1:9000 --out ../.orchestra/backend/tts-samples --run
Without --run it prints the planned requests and makes no network call. Voice gender is not
documented; the user decides by listening. Voice ids are listed by the server when available
(GET /v1/audio/list_voices); the names below are the support-matrix speakers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

import httpx

SENTENCES = {
    "ko": "경복궁에 오신 걸 환영해요! 이 궁궐은 1395년에 지어졌어요. 천천히 둘러보면서 광화문의 아치 모양 문 세 개를 찾아보세요.",
    "en": "Welcome to Gyeongbokgung! This palace was built in 1395 — take your time, and look for the three arched gates at Gwanghwamun.",
}
SPEAKERS = {
    "ko": ["Louise", "Aria", "Pascal", "Diego", "Ray", "HouZhen", "Phung"],
    "en": ["Aria", "Mia", "Sofia", "Louise", "Isabela"],
}
LANGUAGE_CODES = {"ko": "ko-KR", "en": "en-US"}


def listed_voices(client: httpx.Client, base: str) -> dict[str, list[str]]:
    """Map 'ko'/'en' to server voice ids whose name contains a candidate speaker."""
    response = client.get(base + "/v1/audio/list_voices")
    response.raise_for_status()
    text = json.dumps(response.json())
    found = {}
    for lang, speakers in SPEAKERS.items():
        code = LANGUAGE_CODES[lang]
        ids = sorted({token.strip('"') for token in text.replace(",", " ").split()
                      if code.casefold() in token.casefold()
                      and any(speaker.casefold() in token.casefold() for speaker in speakers)})
        found[lang] = ids
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:9000")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run", action="store_true", help="Actually call the TTS server.")
    args = parser.parse_args(argv)
    parts = urlsplit(args.base_url)
    if parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost"}:
        print("Use the local tunnel (http://127.0.0.1:9000).", file=sys.stderr)
        return 2
    if not args.run:
        for lang, speakers in SPEAKERS.items():
            for speaker in speakers:
                print(f"PLAN {lang} {speaker}: POST {args.base_url}/v1/audio/synthesize "
                      f"language={LANGUAGE_CODES[lang]} text={SENTENCES[lang][:30]}...")
        print("NOT_RUN: pass --run after Magpie and the tunnel are verified.")
        return 0
    args.out.mkdir(parents=True, exist_ok=True)
    report = []
    with httpx.Client(timeout=30.0, trust_env=False, follow_redirects=False) as client:
        voices = listed_voices(client, args.base_url)
        for lang, ids in voices.items():
            for voice in ids:
                started = time.perf_counter()
                response = client.post(args.base_url + "/v1/audio/synthesize",
                                       data={"text": SENTENCES[lang], "language": LANGUAGE_CODES[lang], "voice": voice})
                elapsed = round(time.perf_counter() - started, 3)
                ok = response.status_code == 200 and response.headers.get("content-type", "").startswith("audio/")
                name = f"{lang}-{voice.replace('/', '_').replace(':', '_')}.wav"
                if ok:
                    (args.out / name).write_bytes(response.content)
                report.append({"lang": lang, "voice": voice, "status": response.status_code,
                               "file": name if ok else None, "elapsed_s": elapsed})
    (args.out / "samples.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report and all(item["file"] for item in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
