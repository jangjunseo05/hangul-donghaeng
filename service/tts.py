"""Broker-side speech synthesis through a self-hosted NVIDIA Magpie TTS NIM.

TTS_BASE_URL (http://127.0.0.1:9100 through infra/open_tts_tunnel.sh: infra/tts_postfx.py
in front of Magpie on the GPU host, adding the approved tempo/brightness filter),
TTS_VOICE_KO, TTS_VOICE_EN, TTS_SSML_PITCH (x-high = approved tone; empty = plain text).
The voice is fixed by the server, never by the browser. Unset or unreachable ->
TtsUnavailable so the browser uses its own TTS.
HTTP API per the NIM Speech TTS REST reference (research M3-2, documents only):
POST /v1/audio/synthesize, multipart/form-data text/language/voice -> 200 audio/wav;
an unknown voice is a 400, so the configured voice is checked once against
GET /v1/audio/list_voices and omitted (model default) when absent. Verified
against Magpie NIM 1.10.1 (M4 live check).
"""
from __future__ import annotations

from collections import OrderedDict
import os
import re
import threading
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

import httpx

SYNTH_PATH = "/v1/audio/synthesize"
VOICES_PATH = "/v1/audio/list_voices"
LANGUAGE_CODES = {"ko": "ko-KR", "en": "en-US"}
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
TIMEOUT_SECONDS = 10.0
MAX_AUDIO_BYTES = 5 * 1024 * 1024
_TRANSPORT = None  # Tests inject httpx.MockTransport.
_LOCK = threading.Lock()
_CACHE: OrderedDict = OrderedDict()
_ACTIVE_SESSIONS: set[str] = set()
_CAPACITY = threading.BoundedSemaphore(2)
_VOICES: dict[str, set[str] | None] = {}  # base url -> listed voice ids (None: listing unavailable)


# An aside glued to a Korean particle ("품계석(…)을") is dropped so the sentence stays grammatical;
# other brackets become a comma aside.
_GLUED_ASIDE = re.compile(r"\s*[(（［\[][^()（）［］\[\]]*[)）］\]](?=[가-힣])")
_OPEN = re.compile(r"\s*[(（［\[]\s*")
_CLOSE = re.compile(r"\s*[)）］\]]\s*")


def speakable(text: str) -> str:
    """Spoken form of on-screen text: no brackets, which TTS reads badly (research M2-3 B)."""
    value = _GLUED_ASIDE.sub("", text)
    value = _OPEN.sub(", ", value)
    value = _CLOSE.sub(" ", value)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s+([,.!?。])", r"\1", value)
    value = re.sub(r",\s*([,.!?。])", r"\1", value)
    return value.strip(" ,")


# Magpie honours SSML prosody pitch names (x-high verified); rate is ignored and semitone/percent
# pitch values are rejected with 400 (orchestrator measurement 2026-10-27), so only names pass.
SSML_PITCHES = {"x-low", "low", "medium", "high", "x-high"}


def ssml_pitch() -> str | None:
    value = os.getenv("TTS_SSML_PITCH", "").strip()
    return value if value in SSML_PITCHES else None


def to_ssml(text: str, pitch: str) -> str:
    """Wrap already-normalized text; &, <, > and quotes are escaped so user text stays text."""
    body = escape(text, {'"': "&quot;", "'": "&apos;"})
    return f'<speak><prosody pitch="{pitch}">{body}</prosody></speak>'


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


def _listed_voices(client: httpx.Client, base: str) -> set[str] | None:
    """Voice ids from list_voices ({"<locales>": {"voices": [...]}}); cached per base URL."""
    if base in _VOICES:
        return _VOICES[base]
    voices = None
    try:
        response = client.get(base + VOICES_PATH)
        if response.status_code == 200 and len(response.content) <= 1_000_000:
            data = response.json()
            voices = {voice for entry in data.values() if isinstance(entry, dict)
                      for voice in entry.get("voices", []) if isinstance(voice, str)} if isinstance(data, dict) else None
    except (httpx.HTTPError, ValueError):
        voices = None
    if voices is not None:
        _VOICES[base] = voices  # A failed listing is retried next time (server may be initializing).
    return voices


def synthesize(text: str, lang: str, session_id: str) -> tuple[bytes, str, str]:
    """Return (audio, content_type, voice). Raises TtsUnavailable or TtsBusy."""
    base = _base_url()
    if base is None or lang not in LANGUAGE_CODES:
        raise TtsUnavailable()
    voice = os.getenv("TTS_VOICE_KO" if lang == "ko" else "TTS_VOICE_EN", "").strip()
    text = speakable(text)
    if not text:
        raise TtsUnavailable()
    pitch = ssml_pitch()
    key = (lang, voice, pitch, text)  # a pitch change must not replay cached audio
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
            with httpx.Client(follow_redirects=False, trust_env=False, transport=_TRANSPORT,
                              timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=2.0)) as client:
                listed = _listed_voices(client, base) if voice else None
                used = voice if voice and (listed is None or voice in listed) else ""
                # multipart/form-data, as the NIM reference specifies.
                spoken = to_ssml(text, pitch) if pitch else text  # brackets were normalized above
                form = {"text": (None, spoken), "language": (None, LANGUAGE_CODES[lang])}
                if used:
                    form["voice"] = (None, used)
                with client.stream("POST", base + SYNTH_PATH, files=form) as response:
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
        value = (bytes(audio), content_type, used or "default")
        with _LOCK:
            _CACHE[key] = value
            while len(_CACHE) > 64:
                _CACHE.popitem(last=False)
        return value
    finally:
        with _LOCK:
            _ACTIVE_SESSIONS.discard(session_id)
