"""TTS post-processing proxy for the GPU host (standard library only; ffmpeg on PATH).

  python3 tts_postfx.py            # binds 127.0.0.1:${TTS_POSTFX_PORT:-9100}

POST /v1/audio/synthesize (multipart, passed through unchanged) -> Magpie at TTS_UPSTREAM
(default http://127.0.0.1:9000). A 200 audio/wav reply is filtered with ffmpeg
(TTS_POSTFX_FILTER, default the user-approved 1.125x tempo + 3 kHz treble +6 dB + limiter)
and returned as audio/wav. GET /v1/health/ready and /v1/audio/list_voices are proxied as is.
If ffmpeg is missing or fails, the original Magpie audio is returned and the failure is logged.
Loopback only: the broker reaches it through infra/open_tts_tunnel.sh (TTS_TUNNEL_PORT=9100).
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

DEFAULT_FILTER = "atempo=1.125,treble=g=6:f=3000,alimiter=limit=0.95"
# Only simple filter chains (name=key=value:...), so env cannot smuggle file-reading filters.
FILTER_PATTERN = re.compile(r"^[a-z]+(?:=[A-Za-z0-9.:=_-]+)?(?:,[a-z]+(?:=[A-Za-z0-9.:=_-]+)?)*$")
BLOCKED_FILTERS = {"amovie", "movie", "sendcmd", "asendcmd", "azmq", "zmq"}
PASSTHROUGH = {"/v1/health/ready", "/v1/health/live", "/v1/audio/list_voices", "/v1/version", "/v1/models"}
SYNTH_PATH = "/v1/audio/synthesize"
MAX_REQUEST_BYTES = 64 * 1024
MAX_AUDIO_BYTES = 10 * 1024 * 1024
UPSTREAM_TIMEOUT_S = 20.0
FFMPEG_TIMEOUT_S = 15.0
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def log(event: str, **fields):
    print(json.dumps({"event": event, "ts": round(time.time(), 3), **fields}), file=sys.stderr, flush=True)


def upstream_base() -> str:
    value = os.getenv("TTS_UPSTREAM", "http://127.0.0.1:9000").rstrip("/")
    parts = urlsplit(value)
    if parts.scheme != "http" or parts.hostname not in LOOPBACK or parts.path not in {"", "/"} or parts.query:
        raise SystemExit("TTS_UPSTREAM must be http://<loopback>:<port>")
    return value


def audio_filter() -> str:
    value = os.getenv("TTS_POSTFX_FILTER", DEFAULT_FILTER).strip()
    names = {part.split("=", 1)[0] for part in value.split(",")} if value else set()
    if not FILTER_PATTERN.fullmatch(value) or names & BLOCKED_FILTERS:
        raise SystemExit("TTS_POSTFX_FILTER must be a simple audio filter chain")
    return value


def apply_filter(audio: bytes, chain: str, ffmpeg: str | None = None) -> bytes | None:
    """Return filtered WAV bytes, or None when ffmpeg is unavailable or fails (caller keeps the original)."""
    binary = ffmpeg or os.getenv("TTS_POSTFX_FFMPEG") or shutil.which("ffmpeg")
    if not binary or not (os.path.isfile(binary) or shutil.which(binary)):
        log("postfx_skipped", reason="ffmpeg_not_found")
        return None
    with tempfile.TemporaryDirectory(prefix="tts-postfx-") as directory:
        output = os.path.join(directory, "out.wav")  # seekable file: a complete WAV header
        try:
            done = subprocess.run([binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "wav",
                                   "-i", "pipe:0", "-af", chain, "-c:a", "pcm_s16le", "-f", "wav", output],
                                  input=audio, capture_output=True, timeout=FFMPEG_TIMEOUT_S, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            log("postfx_failed", reason=type(exc).__name__)
            return None
        if done.returncode != 0 or not os.path.exists(output):
            log("postfx_failed", reason="ffmpeg_exit", code=done.returncode, stderr=done.stderr.decode(errors="replace")[-300:])
            return None
        with open(output, "rb") as handle:
            data = handle.read(MAX_AUDIO_BYTES + 1)
        return data if 44 < len(data) <= MAX_AUDIO_BYTES and data[:4] == b"RIFF" else None


class Handler(BaseHTTPRequestHandler):
    server_version = "tts-postfx/1"
    upstream = "http://127.0.0.1:9000"
    chain = DEFAULT_FILTER
    ffmpeg: str | None = None

    def log_message(self, fmt, *args):  # keep stderr for structured events only
        pass

    def _reply(self, status: int, body: bytes, content_type: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _forward(self, method: str, body: bytes | None, content_type: str | None):
        request = Request(self.upstream + self.path, data=body, method=method,
                          headers={"Content-Type": content_type} if content_type else {})
        try:
            with urlopen(request, timeout=UPSTREAM_TIMEOUT_S) as response:
                data = response.read(MAX_AUDIO_BYTES + 1)
                return response.status, data, response.headers.get("Content-Type", "application/octet-stream")
        except HTTPError as exc:
            return exc.code, exc.read(4096), exc.headers.get("Content-Type", "application/json")
        except (URLError, OSError, TimeoutError):
            return 502, b'{"detail":"upstream unavailable"}', "application/json"

    def do_GET(self):
        if self.path not in PASSTHROUGH:
            return self._reply(404, b'{"detail":"not found"}', "application/json")
        status, data, content_type = self._forward("GET", None, None)
        self._reply(status, data[:MAX_AUDIO_BYTES], content_type)

    def do_POST(self):
        if self.path != SYNTH_PATH:
            return self._reply(404, b'{"detail":"not found"}', "application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 < length <= MAX_REQUEST_BYTES:
            if MAX_REQUEST_BYTES < length <= 1024 * 1024:
                self.rfile.read(length)  # drain so the client sees the 413 instead of a reset
            self.close_connection = True
            return self._reply(413, b'{"detail":"request too large"}', "application/json")
        body = self.rfile.read(length)
        started = time.perf_counter()
        status, data, content_type = self._forward("POST", body, self.headers.get("Content-Type"))
        synth_s = round(time.perf_counter() - started, 3)
        if (status != 200 or not content_type.lower().startswith("audio/") or data[:4] != b"RIFF"
                or len(data) > MAX_AUDIO_BYTES):
            log("passthrough", status=status, content_type=content_type, synth_s=synth_s)
            return self._reply(status if status != 200 else 502, data[:4096] if status != 200 else b"",
                               content_type if status != 200 else "application/json")
        filtered = apply_filter(data, self.chain, self.ffmpeg)
        log("synthesized", synth_s=synth_s, postfx_s=round(time.perf_counter() - started - synth_s, 3),
            postfx=filtered is not None, bytes_in=len(data), bytes_out=len(filtered or data))
        self._reply(200, filtered or data, "audio/wav", {"X-TTS-Postfx": "applied" if filtered else "skipped"})


def make_server(port: int, upstream: str, chain: str, ffmpeg: str | None = None) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"upstream": upstream, "chain": chain, "ffmpeg": ffmpeg})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def main() -> int:
    port = int(os.getenv("TTS_POSTFX_PORT", "9100"))
    server = make_server(port, upstream_base(), audio_filter())
    log("listening", port=port, upstream=server.RequestHandlerClass.upstream, filter=server.RequestHandlerClass.chain,
        ffmpeg=shutil.which("ffmpeg"))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
