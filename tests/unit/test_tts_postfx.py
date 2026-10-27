"""GPU-host TTS post-processing proxy against a local fake Magpie; no ffmpeg or network needed."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import wave

import pytest

from infra import tts_postfx


def wav_bytes(seconds=0.1):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(22050)
        handle.writeframes(b"\x00\x00" * int(22050 * seconds))
    return buffer.getvalue()


class FakeMagpie(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        body = json.dumps({"en-US,ko-KR": {"voices": ["Magpie-Multilingual.EN-US.Mia"]}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        FakeMagpie.seen.append((self.headers["Content-Type"], body))
        if b"bad-voice" in body:
            payload, status, kind = b'{"detail":"unknown voice"}', 400, "application/json"
        else:
            payload, status, kind = wav_bytes(), 200, "audio/wav"
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def proxy(monkeypatch):
    FakeMagpie.seen = []
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeMagpie)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    servers = [upstream]

    def start(ffmpeg):
        server = tts_postfx.make_server(0, f"http://127.0.0.1:{upstream.server_address[1]}",
                                        tts_postfx.DEFAULT_FILTER, ffmpeg)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()


def synth(base, body=b"--b\r\nContent-Disposition: form-data; name=\"text\"\r\n\r\nhello\r\n--b--\r\n"):
    request = Request(base + "/v1/audio/synthesize", data=body, method="POST",
                      headers={"Content-Type": "multipart/form-data; boundary=b"})
    return urlopen(request, timeout=10)


def test_without_ffmpeg_the_original_audio_is_returned_and_multipart_passes_through(proxy):
    base = proxy("/nonexistent/ffmpeg")
    with synth(base) as response:
        assert response.status == 200 and response.headers["Content-Type"] == "audio/wav"
        assert response.headers["X-TTS-Postfx"] == "skipped"
        assert response.read() == wav_bytes()
    content_type, body = FakeMagpie.seen[0]
    assert content_type == "multipart/form-data; boundary=b" and b"hello" in body


def test_filter_is_applied_when_ffmpeg_succeeds(proxy, monkeypatch):
    calls = []

    def fake_filter(audio, chain, ffmpeg=None):
        calls.append(chain)
        return b"RIFF" + b"\x01" * 60

    monkeypatch.setattr(tts_postfx, "apply_filter", fake_filter)
    with synth(proxy(None)) as response:
        assert response.headers["X-TTS-Postfx"] == "applied" and response.read().startswith(b"RIFF\x01")
    assert calls == ["atempo=1.125,treble=g=6:f=3000,alimiter=limit=0.95"]


def test_failing_ffmpeg_keeps_original(tmp_path):
    broken = tmp_path / "ffmpeg.bat"
    broken.write_text("@exit /b 1\n")
    assert tts_postfx.apply_filter(wav_bytes(), tts_postfx.DEFAULT_FILTER, str(broken)) is None


def test_upstream_errors_and_other_paths(proxy):
    base = proxy("/nonexistent/ffmpeg")
    with pytest.raises(HTTPError) as error:
        synth(base, b"--b\r\nContent-Disposition: form-data; name=\"voice\"\r\n\r\nbad-voice\r\n--b--\r\n")
    assert error.value.code == 400
    with urlopen(base + "/v1/audio/list_voices", timeout=10) as response:
        assert "Mia" in response.read().decode()
    with pytest.raises(HTTPError) as error:
        urlopen(base + "/etc/passwd", timeout=10)
    assert error.value.code == 404
    with pytest.raises(HTTPError) as error:
        synth(base, b"x" * (tts_postfx.MAX_REQUEST_BYTES + 1))
    assert error.value.code == 413


@pytest.mark.parametrize("value", ["amovie=/etc/passwd", "atempo=1.1;rm", "volume=2,movie=x.wav", "a b"])
def test_filter_env_rejects_unsafe_chains(monkeypatch, value):
    monkeypatch.setenv("TTS_POSTFX_FILTER", value)
    with pytest.raises(SystemExit):
        tts_postfx.audio_filter()


def test_default_filter_and_loopback_upstream(monkeypatch):
    monkeypatch.delenv("TTS_POSTFX_FILTER", raising=False)
    assert tts_postfx.audio_filter() == "atempo=1.125,treble=g=6:f=3000,alimiter=limit=0.95"
    monkeypatch.setenv("TTS_UPSTREAM", "http://10.0.0.5:9000")
    with pytest.raises(SystemExit):
        tts_postfx.upstream_base()
