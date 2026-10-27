"""Broker-side speech synthesis through a self-hosted NVIDIA Magpie TTS NIM.

TTS_BASE_URL (e.g. http://127.0.0.1:9000 through infra/open_tts_tunnel.sh),
TTS_VOICE_KO, TTS_VOICE_EN. The voice is fixed by the server, never by the
browser. Unset or unreachable -> TtsUnavailable so the browser uses its own TTS.
HTTP API path and form fields follow the Speech NIM docs and are unverified
against a live server until Magpie is deployed.
"""
from __future__ import annotations

from collections import OrderedDict
import os
import threading
from urllib.parse import urlsplit

import httpx

SYNTH_PATH = "/v1/audio/synthesize"
LANGUAGE_CODES = {"ko": "ko-KR", "en": "en-US"}
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
TIMEOUT_SECONDS = 10.0
MAX_AUDIO_BYTES = 5 * 1024 * 1024
_TRANSPORT = None  # Tests inject httpx.MockTransport.
_LOCK = threading.Lock()
_CACHE: OrderedDict = OrderedDict()
_ACTIVE_SESSIONS: set[str] = set()
_CAPACITY = threading.BoundedSemaphore(2)


class TtsUnavailable(Exception):
    pass


class TtsBusy(Exception):
    pass


def _base_url() -> str | None:
    value = os.getenv("TTS_BASE_URL", "").strip().rstrip("/")
    if not value:
        return None
    parts = urlsplit(value)
    if (parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path not in {"", "/"}):
        return None
    if parts.scheme == "http" and parts.hostname not in LOOPBACK_HOSTS:
        return None  # Plain HTTP only through the local SSH tunnel.
    return value


def configured() -> bool:
    return _base_url() is not None


def synthesize(text: str, lang: str, session_id: str) -> tuple[bytes, str, str]:
    """Return (audio, content_type, voice). Raises TtsUnavailable or TtsBusy."""
    base = _base_url()
    if base is None or lang not in LANGUAGE_CODES:
        raise TtsUnavailable()
    voice = os.getenv("TTS_VOICE_KO" if lang == "ko" else "TTS_VOICE_EN", "").strip()
    key = (lang, voice, text)
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
        if session_id in _ACTIVE_SESSIONS:
            raise TtsBusy()
        _ACTIVE_SESSIONS.add(session_id)
    try:
        if not _CAPACITY.acquire(timeout=1.0):
            raise TtsBusy()
        try:
            form = {"text": text, "language": LANGUAGE_CODES[lang]}
            if voice:
                form["voice"] = voice
            with httpx.Client(follow_redirects=False, trust_env=False, transport=_TRANSPORT,
                              timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=2.0)) as client:
                with client.stream("POST", base + SYNTH_PATH, data=form) as response:
                    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                    if response.status_code != 200 or not content_type.startswith("audio/"):
                        raise TtsUnavailable()
                    audio = bytearray()
                    for chunk in response.iter_bytes(chunk_size=65536):
                        audio.extend(chunk)
                        if len(audio) > MAX_AUDIO_BYTES:
                            raise TtsUnavailable()
        except httpx.HTTPError as exc:
            raise TtsUnavailable() from exc
        finally:
            _CAPACITY.release()
        if not audio:
            raise TtsUnavailable()
        value = (bytes(audio), content_type, voice or "default")
        with _LOCK:
            _CACHE[key] = value
            while len(_CACHE) > 64:
                _CACHE.popitem(last=False)
        return value
    finally:
        with _LOCK:
            _ACTIVE_SESSIONS.discard(session_id)
