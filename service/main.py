"""Small trusted broker. Run a single process: state and jobs are in memory."""
from __future__ import annotations

from collections import OrderedDict
import hmac
import io
import json
import re
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError

from shared.cards import build_card, catalog_card, evidence_label, has_catalog_card
from shared.models import (Evidence, GuideRequest, GuideResult, Location, NearbyPlace, NearbyResponse, Place,
                           PlaceCandidate, ReviewRequest, SandboxProbeRequest, SearchRequest, TtsRequest, WikiRequest,
                           WorkerFailure, WorkerProbeResult, WorkerProgress, WorkerResult, WorkerReviewResult)
from service import catalog, content, tts
from service.render import html_card, markdown_card

ROOT = Path(__file__).resolve().parents[1]
Image.MAX_IMAGE_PIXELS = 20_000_000
COOKIE = "guide_session"
TERMINAL = {"completed", "failed", "superseded"}
SESSION_MAX_AGE = 6 * 3600
SESSION_IDLE_AGE = 3600
REQUEST_TIMEOUT_SECONDS = 65.0
OBSERVE_FRAME_RING = 2
ISSUED_PLACE_LIMIT = 200
CANDIDATE_LIMIT = 5
CANDIDATE_RADIUS_M = 1000
# Observe waits at most this long for OSM; catalog candidates alone are enough to proceed.
CANDIDATE_OSM_BUDGET_S = 4.0
OSM_ATTRIBUTION = "© OpenStreetMap contributors (ODbL)"
EVIDENCE_DIR = ROOT / "docs" / "runtime" / "evidence"
TRACE_LIMIT = 40
WORKER_MODEL_ID = re.compile(r"^[A-Za-z0-9_.:/-]{1,120}$")
TRACE_TERMINAL = {"grounding_check", "result_saved", "worker_failed"}


def abort(status: int, code: str, message: str):
    raise HTTPException(status, detail={"error_code": code, "detail": message})


def add_trace(job: dict, kind: str, name: str, ok: bool = True, detail: str | None = None):
    """Append a broker-observed step. The worker can only reach the broker and model, so every
    tool call and result check passes here; model calls appear only as worker-reported stages."""
    events = job.setdefault("trace", [])
    # Keep room for the final check/save/failure so a flood of rejected calls cannot hide them.
    if name in TRACE_TERMINAL:
        if len(events) >= TRACE_LIMIT:
            return
    elif len(events) >= TRACE_LIMIT - 4:
        return
    elif len(events) == TRACE_LIMIT - 5:
        kind, name, ok, detail = "broker", "trace_truncated", False, None
    events.append({"t_ms": max(0, int((time.monotonic() - job["created"]) * 1000)),
                   "kind": kind, "name": name, "ok": ok, "detail": detail})


def error_code(exc: HTTPException) -> str:
    return exc.detail.get("error_code", "ERROR") if isinstance(exc.detail, dict) else "ERROR"


SESSION_JOB_KEEP = 20


MD_LINE_START = re.compile(r"^(?:[-=+*#>_~|`:]|\d+[.)])")


def flatten_text(value):
    """Collapse line breaks in user/model strings before Markdown rendering, and put a zero-width space in front
    of line-start syntax (-, =, +, #, 1. ...) so a value can never become a heading, list, rule or quote."""
    if isinstance(value, str):
        text = " ".join(value.split())
        return "\u200b" + text if MD_LINE_START.match(text) else text
    if isinstance(value, list):
        return [flatten_text(item) for item in value]
    if isinstance(value, dict):
        return {key: flatten_text(item) for key, item in value.items()}
    return value


def count_detail(count: int, noun: str, code: str | None) -> str:
    return f"{count} {noun}" + (f" · {code}" if code else "")


def load_sandbox_evidence() -> dict | None:
    """Summarize stored OpenShell deployment evidence. This is not a live check of the running worker."""
    try:
        readiness = json.loads((EVIDENCE_DIR / "latest-readiness.json").read_text(encoding="utf-8"))
        verdict = json.loads((EVIDENCE_DIR / "boundary-combined-verdict.json").read_text(encoding="utf-8"))
        policy = json.loads((EVIDENCE_DIR / "latest-effective-policy.json").read_text(encoding="utf-8"))
        probe_log = (EVIDENCE_DIR / "boundary-matrix-01.log").read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None
    if not all(isinstance(item, dict) for item in (readiness, verdict, policy)):
        return None
    rules = policy.get("policy") if isinstance(policy.get("policy"), dict) else {}
    files = rules.get("filesystem_policy") if isinstance(rules.get("filesystem_policy"), dict) else {}
    allow = []
    for group in (rules.get("network_policies") or {}).values():
        for endpoint in (group.get("endpoints") or []) if isinstance(group, dict) else []:
            for rule in endpoint.get("rules") or []:
                found = (rule or {}).get("allow") or {}
                if found.get("method") and found.get("path"):
                    allow.append(f"{found['method']} :{endpoint.get('port')}{found['path']}")
    probe = next((line.split(":", 1)[1].strip() for line in probe_log.splitlines()
                  if line.startswith("Created sandbox:")), None)
    checks = verdict.get("checks") or {}
    policy_hash = readiness.get("effective_policy_hash")
    return {"scope": "stored_deployment_evidence", "runtime": "OpenShell 0.1.2",
            "worker": readiness.get("worker"), "captured_at": readiness.get("captured_at"),
            "policy_hash": policy_hash,
            "policy_loaded": any("CONFIG:LOADED" in line and f"hash:{policy_hash}" in line
                                 for line in readiness.get("runtime_policy_ack", [])),
            "boundary_verdict": verdict.get("verdict"), "boundary_sandbox": probe,
            "boundary_checks_passed": sum(1 for value in checks.values() if value is True),
            "boundary_checks_total": len(checks),
            "policy_read_only": [str(path) for path in files.get("read_only", [])],
            "policy_read_write": [str(path) for path in files.get("read_write", [])],
            "policy_network_allow": sorted(set(allow))}


@dataclass
class Session:
    id: str
    active_request_id: str | None = None
    history: list[dict] = field(default_factory=list)
    photos: set[str] = field(default_factory=set)
    created: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)
    history_mode: str | None = None
    last_visual_observation: dict | None = None
    # Observe frames do not count toward the 20-photo bound; oldest first, at most 2.
    observe_photos: list[str] = field(default_factory=list)
    # OSM places the broker showed this session (nearby lists, observe candidates);
    # only these external ids may be confirmed.
    issued_places: OrderedDict = field(default_factory=OrderedDict)

    def issue(self, place: dict):
        self.issued_places[place["place_id"]] = place
        self.issued_places.move_to_end(place["place_id"])
        while len(self.issued_places) > ISSUED_PLACE_LIMIT:
            self.issued_places.popitem(last=False)


class Store:
    def __init__(self, runtime: Path):
        self.lock = threading.RLock()
        self.sessions: dict[str, Session] = {}
        self.jobs: dict[str, dict] = {}
        self.photos: dict[str, dict] = {}
        self.worker_seen = 0.0
        self.worker_model = None
        self.session_attempts: dict[str, list[float]] = {}
        self.canary_hits = 0  # requests that reached the worker-unlisted /worker/canary route
        self.runtime = runtime.resolve()
        self.output = Path(os.getenv("GUIDE_OUTPUT_DIR", str(self.runtime / "output"))).resolve()
        (self.runtime / "photos").mkdir(parents=True, exist_ok=True)
        self.output.mkdir(parents=True, exist_ok=True)

    def prune_sessions(self, now: float):
        expired = {key for key, session in self.sessions.items()
                   if now - session.created >= SESSION_MAX_AGE
                   or now - session.last_seen >= SESSION_IDLE_AGE}
        expired_ids = {self.sessions[key].id for key in expired}
        for key in expired:
            session = self.sessions.pop(key)
            for photo_id in [*session.photos, *session.observe_photos]:
                self.drop_photo(photo_id)
        self.jobs = {rid: job for rid, job in self.jobs.items()
                     if job["request"]["session_id"] not in expired_ids}
        self.session_attempts = {ip: recent for ip, attempts in self.session_attempts.items()
                                 if (recent := [t for t in attempts if now - t < 60])}

    def prune_session_jobs(self, session_id: str, keep: int = SESSION_JOB_KEEP):
        """Forget all but the newest `keep` finished jobs of one session (any kind), so one client cannot fill
        JOB_LIMIT (64 sessions x 21 < 1500). The newest finished guide "ask" job is always kept, so automatic
        observe frames never evict the answer card on screen. Saved files stay on disk."""
        finished = sorted((job for job in self.jobs.values()
                           if job["request"]["session_id"] == session_id and job["status"] in TERMINAL),
                          key=lambda job: job["created"])
        asks = [job for job in finished if job.get("kind", "guide") == "guide"
                and job["request"].get("interaction_mode", "ask") == "ask"]
        protected = asks[-1]["request_id"] if asks else None
        for job in finished[:max(0, len(finished) - keep)]:
            if job["request_id"] != protected:
                self.jobs.pop(job["request_id"], None)

    def drop_photo(self, photo_id: str):
        photo = self.photos.pop(photo_id, None)
        if photo:
            photo["path"].unlink(missing_ok=True)

    def finish(self, job: dict, status: str, error_code: str | None = None):
        """Terminal transition; an observe frame used by this job is deleted with it."""
        job["status"] = status
        if error_code is not None:
            job["error_code"] = error_code
        job["stage"] = None
        photo_id = job["request"].get("photo_id")
        session = job["session"]
        if photo_id and photo_id in session.observe_photos:
            session.observe_photos.remove(photo_id)
            self.drop_photo(photo_id)

    def expire(self, job: dict):
        if job["status"] not in TERMINAL and time.monotonic() - job["created"] > REQUEST_TIMEOUT_SECONDS:
            self.finish(job, "failed", "WORKER_UNAVAILABLE" if job["status"] == "queued" else "REQUEST_TIMEOUT")

    def active_job(self, sid: str, rid: str, running: bool = True, kind: str | None = "guide") -> dict:
        job = self.jobs.get(rid)
        if not job or job["request"]["session_id"] != sid:
            abort(404, "JOB_NOT_FOUND", "No job belongs to this session.")
        if kind is not None and job.get("kind", "guide") != kind:
            abort(409, "JOB_KIND_MISMATCH", "This endpoint does not handle this job type.")
        self.expire(job)
        session = job["session"]
        if session.active_request_id != rid or job["status"] in TERMINAL:
            abort(409, "STALE_REQUEST", "This request is no longer active.")
        if running and job["status"] != "running":
            abort(409, "JOB_NOT_CLAIMED", "Worker must claim this job first.")
        return job


class BodyLimitMiddleware:
    """Count received bytes before JSON/multipart parsing, including chunked bodies."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = 9 * 1024 * 1024 if scope["path"] == "/api/photos" else 256 * 1024
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    abort(413, "BODY_TOO_LARGE", "The request is too large.")
            return message

        await self.app(scope, bounded_receive, send)


def _session_rate() -> int:
    """New sessions per client IP per minute; demos behind one NAT/tunnel IP may need ~60."""
    try:
        value = int(os.getenv("GUIDE_SESSION_RATE_PER_MIN", "10"))
    except ValueError:
        return 10
    return value if 1 <= value <= 1000 else 10


def create_app(runtime_dir: Path | None = None, worker_token: str | None = None) -> FastAPI:
    app = FastAPI(title="Hangul Donghaeng", version="0.1.0")
    app.add_middleware(BodyLimitMiddleware)
    store = Store(runtime_dir or ROOT / ".runtime")
    app.state.store = store
    token = worker_token or os.getenv("WORKER_TOKEN", "")
    cookie_secure = os.getenv("GUIDE_COOKIE_SECURE", "false").lower() == "true"
    session_rate = _session_rate()
    allowed_origins = set(os.getenv("GUIDE_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000").split(","))

    @app.exception_handler(HTTPException)
    async def http_error(_request, exc):
        detail = exc.detail if isinstance(exc.detail, dict) else {"error_code": "REQUEST_ERROR", "detail": str(exc.detail)}
        return JSONResponse(detail, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, _exc):
        # Do not echo submitted credentials, arbitrary model output or personal text.
        return JSONResponse({"error_code": "INVALID_INPUT", "detail": "Input does not match the API contract."}, status_code=422)

    @app.middleware("http")
    async def browser_boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path.startswith("/api/"):
            if origin and origin not in allowed_origins:
                return JSONResponse({"error_code": "ORIGIN_DENIED", "detail": "Use the configured app origin."}, status_code=403)
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"error_code": "INVALID_INPUT", "detail": "Invalid body length."}, status_code=400)
        limit = 9 * 1024 * 1024 if request.url.path == "/api/photos" else 256 * 1024
        if length > limit:
            return JSONResponse({"error_code": "BODY_TOO_LARGE", "detail": "The request is too large."}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.path.startswith(("/api/", "/worker/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    def browser_session(request: Request) -> Session:
        cookie = request.cookies.get(COOKIE, "")
        with store.lock:
            now = time.monotonic()
            store.prune_sessions(now)
            session = store.sessions.get(cookie)
            if not session:
                abort(401, "SESSION_REQUIRED", "Start a new session.")
            session.last_seen = now
            return session

    def worker_auth(authorization: str | None = Header(default=None),
                    x_worker_model: str | None = Header(default=None),
                    x_worker_thinking: str | None = Header(default=None),
                    x_worker_context: str | None = Header(default=None)):
        expected = f"Bearer {token}"
        if not token or not authorization or not hmac.compare_digest(authorization, expected):
            abort(401, "WORKER_AUTH_REQUIRED", "Worker authentication failed.")
        with store.lock:
            store.worker_seen = time.monotonic()
            # Self-reported by the authenticated worker; not proof of which model answered.
            store.worker_model = ({"id": x_worker_model, "thinking": x_worker_thinking
                                   if x_worker_thinking in {"disabled", "default"} else "default",
                                   "run_context": x_worker_context
                                   if x_worker_context in {"local-dev", "openshell"} else "unknown"}
                                  if x_worker_model and WORKER_MODEL_ID.fullmatch(x_worker_model) else None)

    sandbox_evidence = load_sandbox_evidence()

    @app.get("/api/health")
    def health():
        # Keep a busy single worker connected through the bounded request deadline.
        connected = time.monotonic() - store.worker_seen < REQUEST_TIMEOUT_SECONDS + 5
        return {"status": "ok", "worker_connected": connected,
                "model_configured": bool(os.getenv("NVIDIA_API_KEY")), "sandbox_verified": False,
                # Only for a connected worker, so a stopped worker's label never lingers.
                "worker_model": store.worker_model if connected else None,
                "sandbox_evidence": sandbox_evidence,
                "catalog_count": catalog.catalog_summary()["catalog_count"], "version": "0.1.0"}

    @app.get("/api/catalog")
    def public_catalog():
        return catalog.public_catalog()

    @app.post("/api/sessions")
    def start_session(request: Request, response: Response):
        with store.lock:
            now = time.monotonic()
            store.prune_sessions(now)
            existing = store.sessions.get(request.cookies.get(COOKIE, ""))
            if existing:
                existing.last_seen = now
                return {"session_id": existing.id}
            client_ip = request.client.host if request.client else "unknown"
            attempts = store.session_attempts.setdefault(client_ip, [])
            if len(attempts) >= session_rate:
                abort(429, "SESSION_RATE_LIMIT", "Please wait a minute before starting another session.")
            if len(store.sessions) >= 64:
                abort(503, "SESSION_LIMIT", "All demo sessions are in use. Please try again later.")
            attempts.append(now)
            key = secrets.token_urlsafe(32)
            session = Session(id=uuid.uuid4().hex)
            store.sessions[key] = session
            response.set_cookie(COOKIE, key, httponly=True,
                                secure=cookie_secure or request.url.scheme == "https",
                                samesite="strict", max_age=21600)
            return {"session_id": session.id}

    @app.post("/api/tts")
    def synthesize(body: TtsRequest, session: Session = Depends(browser_session)):
        # 503/429 tell the browser to use its own speech; the voice is fixed by server config.
        try:
            audio, content_type, voice = tts.synthesize(body.text, body.lang, session.id)
        except tts.TtsBusy:
            abort(429, "TTS_BUSY", "Speech is being prepared; use device speech.")
        except tts.TtsUnavailable:
            abort(503, "TTS_UNAVAILABLE", "Server speech is not available; use device speech.")
        return Response(audio, media_type=content_type, headers={"X-TTS-Voice": voice})

    def nearby_entry(place: dict, distance: float, *, has_card: bool) -> dict:
        return NearbyPlace.model_validate({
            "place_id": place["place_id"], "name": place["name"], "name_en": place.get("name_en"),
            "kind": place["kind"], "category": place.get("category"), "lat": place["lat"], "lng": place["lng"],
            "distance_m": round(distance, 1), "source_id": place["source_id"], "osm_url": place.get("osm_url"),
            "has_card": has_card}).model_dump()

    def catalog_nearby(tab: str, lat: float, lng: float, radius_m: int) -> list[dict]:
        kind = "heritage" if tab == "landmark" else "restaurant"
        found = []
        for place in catalog.catalog_places():
            if place.get("kind", "restaurant") != kind:
                continue
            distance = content.distance_m(lat, lng, place["lat"], place["lng"])
            if distance <= radius_m:
                found.append(nearby_entry({**place, "kind": "landmark" if tab == "landmark" else "restaurant",
                                           "name_en": place.get("name_en")}, distance,
                                          has_card=has_catalog_card(place["place_id"])))
        return found

    def merge_external(local: list[dict], external: list[dict], limit: int) -> tuple[list[dict], list[dict]]:
        """Drop OSM duplicates of catalog places (same name within 300 m); nearest first."""
        names = {}
        for place in local:
            for value in (place["name"], place.get("name_en")):
                if value:
                    names.setdefault(content.name_key(value), []).append(place)
        kept = []
        for place in external:
            twins = [item for value in (place["name"], place.get("name_en")) if value
                     for item in names.get(content.name_key(value), [])]
            if any(content.distance_m(place["lat"], place["lng"], twin["lat"], twin["lng"]) <= 300 for twin in twins):
                continue
            kept.append(place)
        merged = sorted([*local, *kept], key=lambda item: (item["distance_m"], item["place_id"]))[:limit]
        chosen = {item["place_id"] for item in merged}
        return merged, [place for place in kept if place["place_id"] in chosen]

    @app.get("/api/nearby")
    def nearby(tab: Literal["food", "landmark"], lat: float = Query(ge=-90, le=90),
               lng: float = Query(ge=-180, le=180), radius_m: int = 1000,
               origin: Literal["gps", "selected"] = "selected", lang: Literal["en", "ko"] = "en",
               session: Session = Depends(browser_session)):
        if radius_m not in {500, 1000, 2000, 3000}:
            abort(422, "INVALID_INPUT", "Choose a supported radius.")
        from service.nearby import search_nearby
        found = search_nearby(landmark_name=None, location={"lat": lat, "lng": lng, "origin": origin},
                              radius_m=radius_m, tab=tab)
        external = [place for place in found.get("places", []) if place["place_id"].startswith("osm:")]
        local = catalog_nearby(tab, lat, lng, radius_m)
        places, kept = merge_external(local, [nearby_entry(place, place["distance_m"], has_card=False)
                                              for place in external], 20)
        raw = {place["place_id"]: place for place in external}
        with store.lock:
            for place in kept:
                session.issue({**raw[place["place_id"]], "kind": place["kind"]})
        kept_ids = {place["place_id"] for place in kept}
        ko = lang == "ko"
        unknowns = ([("평점·인기·현재 영업·알레르기 안전은 확인하지 않았어요." if ko else
                      "Ratings, popularity, current opening and allergy suitability are not verified.")]
                    if tab == "food" else
                    [("관람 시간·입장 조건은 확인하지 않았어요." if ko else "Opening hours and admission are not verified.")])
        return NearbyResponse.model_validate({
            "schema_version": 1, "tab": tab, "origin": {"lat": lat, "lng": lng, "origin": origin},
            "radius_m": radius_m, "places": places,
            "evidence": [item for item in found.get("evidence", []) if item["id"] in kept_ids],
            "attribution": OSM_ATTRIBUTION, "unknowns": unknowns,
            "error_code": found.get("error_code")}).model_dump(mode="json")

    @app.get("/api/landmarks/{place_id}/card")
    def landmark_card(place_id: str, lang: Literal["en", "ko"] = "en",
                      session: Session = Depends(browser_session)):
        card = catalog_card(place_id, lang)
        if card is None:
            abort(404, "CARD_NOT_FOUND", "No prepared card for this place.")
        return card

    @app.get("/api/routes")
    def list_routes(near: str | None = Query(default=None, max_length=60), lang: Literal["en", "ko"] = "en",
                    session: Session = Depends(browser_session)):
        point = None
        if near is not None:
            try:
                lat_text, lng_text = near.split(",")
                point = (float(lat_text), float(lng_text))
                Location.model_validate({"lat": point[0], "lng": point[1], "origin": "selected"})
            except (ValueError, TypeError):
                abort(422, "INVALID_INPUT", "near must be '<lat>,<lng>'.")
        return content.routes(lang, point)

    @app.post("/api/photos")
    async def upload_photo(file: UploadFile, purpose: Literal["capture", "observe"] = Form(default="capture"),
                           session: Session = Depends(browser_session)):
        with store.lock:
            if purpose == "capture" and len(session.photos) >= 20:
                abort(429, "PHOTO_LIMIT", "This demo session has reached its photo limit.")
        raw = await file.read(8 * 1024 * 1024 + 1)
        await file.close()
        if len(raw) > 8 * 1024 * 1024:
            abort(413, "PHOTO_TOO_LARGE", "Choose a JPEG or PNG smaller than 8 MiB.")
        try:
            with Image.open(io.BytesIO(raw)) as original:
                if original.format not in {"JPEG", "PNG"} or original.width * original.height > 20_000_000:
                    abort(422, "PHOTO_FORMAT", "Choose a JPEG or PNG up to 20 megapixels.")
                normalized = ImageOps.exif_transpose(original).convert("RGB")
                normalized.thumbnail((1280, 1280))
                # Fresh image removes EXIF, text and other input metadata.
                clean = Image.new("RGB", normalized.size)
                clean.paste(normalized)
                output = io.BytesIO()
                clean.save(output, format="JPEG", quality=85)
                width, height = clean.size
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            abort(422, "PHOTO_FORMAT", "The photo could not be decoded safely.")
        photo_id = uuid.uuid4().hex
        path = store.runtime / "photos" / f"{photo_id}.jpg"
        with store.lock:
            with path.open("xb") as handle:
                handle.write(output.getvalue())
            if purpose == "observe":
                # A ring of recent frames: never downloadable, deleted when its job ends.
                while len(session.observe_photos) >= OBSERVE_FRAME_RING:
                    store.drop_photo(session.observe_photos.pop(0))
                session.observe_photos.append(photo_id)
            else:
                session.photos.add(photo_id)
            store.photos[photo_id] = {"session_id": session.id, "path": path, "purpose": purpose}
        return {"photo_id": photo_id, "width": width, "height": height, "purpose": purpose}

    @app.post("/api/requests", status_code=202)
    def submit(body: GuideRequest, session: Session = Depends(browser_session)):
        with store.lock:
            if body.session_id != session.id:
                abort(403, "SESSION_MISMATCH", "Use your own session.")
            if body.photo_id and body.photo_id not in session.photos and body.photo_id not in session.observe_photos:
                abort(404, "PHOTO_NOT_FOUND", "Upload a photo in this session first.")
            if body.confirmed_food_id and body.confirmed_food_id not in catalog.valid_food_ids():
                abort(422, "UNKNOWN_FOOD", "Choose one of the available food candidates.")
            if body.confirmed_shop_id and not catalog.get_place(body.confirmed_shop_id):
                abort(422, "UNKNOWN_PLACE", "Choose a listed place.")
            external = None
            if body.confirmed_place_id and not catalog.get_place(body.confirmed_place_id):
                external = session.issued_places.get(body.confirmed_place_id)
                if external is None or body.dataset_mode != "real_place":
                    abort(422, "UNKNOWN_PLACE", "Choose a listed place.")
            if body.confirmed_place_id and body.confirmed_shop_id and body.confirmed_place_id != body.confirmed_shop_id:
                abort(422, "PLACE_CONFIRMATION_MISMATCH", "Use one confirmed place.")
            previous = store.jobs.get(session.active_request_id)
            if previous:
                store.expire(previous)
            if body.interaction_mode == "observe" and previous and previous["status"] not in TERMINAL:
                abort(409, "JOB_BUSY", "Wait for the current question before observing another scene.")
            store.prune_session_jobs(session.id)
            if len(store.jobs) >= 1500:
                abort(503, "JOB_LIMIT", "Demo capacity reached.")
            if session.history_mode != body.dataset_mode:
                session.last_visual_observation = None
                # Automated observation must not erase the visitor's stated needs.
                if body.interaction_mode == "ask":
                    session.history.clear()
                    session.history_mode = body.dataset_mode
            if previous and previous["status"] not in TERMINAL:
                store.finish(previous, "superseded")
            rid = uuid.uuid4().hex
            session.active_request_id = rid
            visual_context = None
            if session.last_visual_observation:
                visual_context = {**session.last_visual_observation,
                                  "same_photo": body.photo_id == session.last_visual_observation.get("photo_id")}
            history = list(session.history[-6:]) if session.history_mode == body.dataset_mode else []
            if visual_context and visual_context.get("question"):
                history.append({"role": "assistant", "content": visual_context["question"]})
            store.jobs[rid] = {"request_id": rid, "request": body.model_dump(mode="json"), "status": "queued",
                               "result": None, "error_code": None, "created": time.monotonic(), "session": session,
                               "history": history, "last_visual_observation": visual_context,
                               "search_count": 0, "searched_places": {}, "searched_evidence": {},
                               "search_origin": None, "search_origin_label": None, "stage": None,
                               "candidates": {}, "public_records": {}, "wiki_count": 0,
                               "confirmed_external_place": None if external is None else {
                                   key: external.get(key) for key in ("place_id", "name", "name_en", "kind", "category")}}
            add_trace(store.jobs[rid], "broker", "request_accepted",
                      detail="photo normalized, EXIF removed" if body.photo_id else None)
            return {"request_id": rid, "status": "queued", "poll_url": f"/api/requests/{rid}"}

    @app.get("/api/requests/{request_id}")
    def poll(request_id: str, session: Session = Depends(browser_session)):
        with store.lock:
            job = owned_job(request_id, session, "guide")
            return {**{key: job[key] for key in ("request_id", "status", "result", "error_code")},
                    "stage": job.get("stage") if job["status"] == "running" else None,
                    "trace": list(job.get("trace", []))}

    @app.get("/worker/jobs/next", dependencies=[Depends(worker_auth)])
    def next_job():
        with store.lock:
            for job in store.jobs.values():
                store.expire(job)
                if job["status"] == "queued":
                    job["status"] = "running"
                    add_trace(job, "sandbox", "job_claimed")
                    req = job["request"]
                    if job.get("kind", "guide") != "guide":
                        job["canary_start"] = store.canary_hits
                        return {"kind": job["kind"], "session_id": req["session_id"], "request_id": job["request_id"],
                                **{key: req[key] for key in ("question", "condition", "response_language") if key in req}}
                    return {"session_id": req["session_id"], "request_id": job["request_id"], "request": req,
                            "history": job["history"], "last_visual_observation": job.get("last_visual_observation"),
                            "confirmed_external_place": job.get("confirmed_external_place"),
                            "allowed_source_ids": [e["id"] for e in catalog.evidence_for_mode(req["dataset_mode"])]}
        return Response(status_code=204)

    @app.get("/worker/photos/{photo_id}", dependencies=[Depends(worker_auth)])
    def worker_photo(photo_id: str, request_id: str):
        with store.lock:
            photo = store.photos.get(photo_id)
            if not photo:
                abort(404, "PHOTO_NOT_FOUND", "No assigned photo.")
            job = store.active_job(photo["session_id"], request_id)
            if job["request"]["photo_id"] != photo_id:
                abort(403, "PHOTO_NOT_ASSIGNED", "Photo does not belong to this job.")
            return FileResponse(photo["path"], media_type="image/jpeg")

    @app.post("/worker/search", dependencies=[Depends(worker_auth)])
    def search(body: SearchRequest):
        tool = ("landmark_candidates" if body.kind == "landmark" else
                "osm_live_search" if body.live else "catalog_search")
        with store.lock:
            job = store.active_job(body.session_id, body.request_id)
            try:
                location = check_search(body, job)
            except HTTPException as exc:
                add_trace(job, "tool", tool, False, error_code(exc))
                raise
        # Public map lookups must not block polling, cancellation or other sessions.
        try:
            if body.kind == "landmark":
                found = landmark_candidates(body, location, job["request"]["response_language"])
                count, noun = len(found["candidates"]), "candidates"
            else:
                found = run_search(body, location, job["request"])
                count, noun = len(found["places"]), "results"
        except HTTPException as exc:
            with store.lock:
                add_trace(job, "tool", tool, False, error_code(exc))
            raise
        except Exception:
            with store.lock:
                add_trace(job, "tool", tool, False, "LOOKUP_FAILED")
            raise
        with store.lock:
            add_trace(job, "tool", tool, not found.get("error_code"), count_detail(count, noun, found.get("error_code")))
        return found

    def check_search(body: SearchRequest, job: dict) -> dict | None:
        """Validate a worker search against the assigned job; returns the request location."""
        req = job["request"]
        if req["dataset_mode"] != "real_place":
            abort(403, "MODE_BOUNDARY", "Fictional places cannot use real map search.")
        if body.radius_m != req["radius_m"]:
            abort(422, "RADIUS_MISMATCH", "Use the radius selected by the user.")
        if body.food_id and body.food_id not in catalog.valid_food_ids():
            abort(422, "UNKNOWN_FOOD", "Unknown food ID.")
        if body.shop_id and not catalog.get_place(body.shop_id):
            abort(422, "UNKNOWN_PLACE", "Unknown place ID.")
        if job["search_count"] >= 2:
            abort(429, "SEARCH_LIMIT", "Search limit reached.")
        job["search_count"] += 1
        if body.live and body.kind not in {"restaurant", "landmark"}:
            abort(422, "SEARCH_KIND", "Live lookup supports restaurants and landmark candidates.")
        if body.kind == "landmark" and (not body.live or body.landmark_name or body.food_id or body.shop_id):
            abort(422, "SEARCH_KIND", "Landmark candidates use only the request location.")
        visual = job.get("last_visual_observation") or {}
        if body.live and body.landmark_name and body.landmark_name != visual.get("landmark_name"):
            abort(422, "LANDMARK_CONTEXT_MISMATCH", "Use the landmark from the assigned conversation.")
        return req["location"]

    def run_search(body: SearchRequest, location: dict | None, req: dict) -> dict:
        if body.live:
            from service.nearby import search_nearby
            found = search_nearby(landmark_name=body.landmark_name, location=location, radius_m=body.radius_m)
            if not body.landmark_name and location and found.get("search_origin"):
                found["search_origin"] = dict(location)
                ko = req["response_language"] == "ko"
                found["search_origin_label"] = (("내 위치" if ko else "Your location")
                    if location["origin"] == "gps" else ("선택한 지도 지점" if ko else "Selected map point"))
        else:
            found = catalog.search_places(body.food_id, body.shop_id, location, body.radius_m, kind=body.kind)
        with store.lock:
            job = store.active_job(body.session_id, body.request_id)
            found["places"] = [Place.model_validate(p).model_dump() for p in found["places"]]
            job["searched_places"].update({p["place_id"]: p for p in found["places"]})
            if body.live:
                found["evidence"] = [Evidence.model_validate(e).model_dump() for e in found.get("evidence", [])]
                job["searched_evidence"].update({e["id"]: e for e in found["evidence"]})
                origin = found.get("search_origin")
                job["search_origin"] = Location.model_validate(origin).model_dump() if origin else None
                job["search_origin_label"] = found.get("search_origin_label")
            return found

    def landmark_candidates(body: SearchRequest, location: dict | None, language: str) -> dict:
        """Catalog heritage + OSM landmarks near the request location for closed-set recognition."""
        if location is None:
            return {"candidates": [], "error_code": None, "needs_location": True}
        from service.nearby import search_nearby
        radius = min(body.radius_m, CANDIDATE_RADIUS_M)
        lat, lng = round(location["lat"], 4), round(location["lng"], 4)
        found = search_nearby(landmark_name=None, location={"lat": lat, "lng": lng, "origin": location["origin"]},
                              radius_m=radius, tab="landmark", budget_s=CANDIDATE_OSM_BUDGET_S)
        external = [place for place in found.get("places", []) if place["place_id"].startswith("osm:")]
        local = catalog_nearby("landmark", location["lat"], location["lng"], radius)
        merged, kept = merge_external(local, [nearby_entry(place, place["distance_m"], has_card=False)
                                              for place in external], CANDIDATE_LIMIT)
        raw = {place["place_id"]: place for place in external}
        candidates = []
        for place in merged:
            catalog_place = catalog.get_place(place["place_id"])
            source = "catalog" if catalog_place else "osm"
            name_en = place.get("name_en") or place["name"]
            name_ko = place["name"]
            if catalog_place:
                full = next(item for item in catalog.catalog_places() if item["place_id"] == place["place_id"])
                name_ko, name_en = full.get("name_ko", full["name"]), full.get("name_en", full["name"])
            candidates.append(PlaceCandidate.model_validate({
                "id": place["place_id"], "name_ko": name_ko, "name_en": name_en,
                "kind": "heritage" if source == "catalog" else "landmark",
                "distance_m": place["distance_m"], "source": source}).model_dump())
        with store.lock:
            job = store.active_job(body.session_id, body.request_id)
            for place in kept:
                job["session"].issue({**raw[place["place_id"]], "kind": "landmark"})
            job["candidates"].update({item["id"]: item for item in candidates})
        return {"candidates": candidates, "error_code": found.get("error_code")}

    @app.post("/worker/progress", dependencies=[Depends(worker_auth)])
    def report_progress(body: WorkerProgress):
        with store.lock:
            job = store.active_job(body.session_id, body.request_id, kind=None)
            # Trace a stage only when it changes, so repeated calls cannot crowd out later events.
            if job.get("stage") != body.stage:
                add_trace(job, "stage", body.stage)
            job["stage"] = body.stage
            return {"accepted": True}

    @app.post("/worker/wiki", dependencies=[Depends(worker_auth)])
    def public_evidence(body: WikiRequest):
        with store.lock:
            job = store.active_job(body.session_id, body.request_id)
            place = job.get("confirmed_external_place")
            try:
                if job["request"]["dataset_mode"] != "real_place" or not place:
                    abort(403, "MODE_BOUNDARY", "Public evidence is only for a confirmed external place.")
                if job["wiki_count"] >= 1:
                    abort(429, "SEARCH_LIMIT", "Public evidence lookup limit reached.")
            except HTTPException as exc:
                add_trace(job, "tool", "wikipedia", False, error_code(exc))
                raise
            job["wiki_count"] += 1
            issued = job["session"].issued_places.get(place["place_id"]) or place
        from service.wiki import lookup
        found = lookup(issued, body.lang)
        with store.lock:
            job = store.active_job(body.session_id, body.request_id)
            add_trace(job, "tool", "wikipedia", not found["error_code"],
                      count_detail(len(found["records"]), "records", found["error_code"]))
            records = []
            for record in found["records"]:
                evidence = Evidence.model_validate({key: record[key] for key in
                                                    ("id", "source", "as_of", "type", "dataset_id")}).model_dump()
                job["searched_evidence"][evidence["id"]] = evidence
                job["public_records"][evidence["id"]] = {key: record[key] for key in
                    ("source", "title", "license", "verification")}
                records.append({key: record[key] for key in ("id", "source", "title", "license", "text")})
            return {"evidence": list(job["searched_evidence"][item["id"]] for item in records),
                    "records": records, "error_code": found["error_code"]}

    def validate_card(result: GuideResult, job: dict):
        card = result.landmark_card
        if card is None:
            return
        req = job["request"]
        target = req.get("confirmed_place_id") or req.get("confirmed_shop_id")
        if card.lang != req["response_language"] or card.place_id != target:
            abort(422, "INVALID_CARD", "A card must describe the confirmed place in the reply language.")
        dumped = card.model_dump(mode="json")
        if catalog.get_place(target):
            if dumped != catalog_card(target, card.lang):
                abort(422, "INVALID_CARD", "Catalog cards must match the prepared content.")
            return
        known = {item["id"]: {"source": item["source"], "verification": evidence_label(item["id"])}
                 for item in catalog.evidence_for_mode("real_place")}
        known.update(job.get("public_records", {}))
        blocks = {name: (None if block is None else block.model_dump()) for name, block in card.blocks}
        expected = build_card(card.place_id, card.name, card.lang, blocks,
                              None if card.visit_note is None else card.visit_note.model_dump(), known)
        external = job.get("confirmed_external_place") or {}
        if dumped != expected or card.name not in {external.get("name"), external.get("name_en")}:
            abort(422, "INVALID_CARD", "Card evidence and labels must match approved records.")

    def validate_grounding(result: GuideResult, job: dict):
        req = job["request"]
        if result.session_id != req["session_id"] or result.request_id != job["request_id"]:
            abort(422, "RESULT_ID_MISMATCH", "Result IDs do not match the assigned request.")
        if result.dataset_mode != req["dataset_mode"] or result.response_language != req["response_language"]:
            abort(422, "RESULT_MODE_MISMATCH", "Result mode or language does not match.")
        approved = {e["id"]: e for e in catalog.evidence_for_mode(req["dataset_mode"])}
        approved.update(job.get("searched_evidence", {}))
        provided = set()
        for evidence in result.evidence:
            if evidence.id in provided or evidence.id not in approved or evidence.model_dump() != approved[evidence.id]:
                abort(422, "INVALID_EVIDENCE", "Evidence must match approved source records.")
            provided.add(evidence.id)
        for section in (result.menus, result.claims, result.conflicts, result.itinerary):
            for item in section:
                if not set(item.evidence_ids).issubset(provided):
                    abort(422, "MISSING_EVIDENCE", "Every claim must cite supplied approved evidence.")
        if req["dataset_mode"] == "fictional_task" and result.places:
            abort(422, "MODE_BOUNDARY", "Fictional itineraries must not contain real map places.")
        if result.scene.confirmed_place_id != req.get("confirmed_place_id"):
            abort(422, "PLACE_CONFIRMATION_MISMATCH", "A scene cannot invent user confirmation.")
        if result.scene.confirmed_shop_id != req.get("confirmed_shop_id"):
            abort(422, "PLACE_CONFIRMATION_MISMATCH", "A scene cannot invent legacy place confirmation.")
        issued = job["session"].issued_places
        for candidate in result.scene.place_candidates:
            if not catalog.get_place(candidate.id) and candidate.id not in issued:
                abort(422, "UNKNOWN_PLACE", "Scene candidates must use approved catalog or issued IDs.")
        source = result.scene.observed_place_source
        if source in {"catalog", "osm"}:
            first = result.scene.place_candidates[0].id if result.scene.place_candidates else None
            if (first not in job.get("candidates", {}) or job["candidates"][first]["source"] != source):
                abort(422, "INVALID_OBSERVATION", "A closed-set choice must be one of this job's candidates.")
        if source == "model" and not result.scene.observed_place_name:
            abort(422, "INVALID_OBSERVATION", "Free recognition needs a tentative name.")
        validate_card(result, job)
        if req["dataset_mode"] == "fictional_task" and result.scene.place_candidates:
            abort(422, "MODE_BOUNDARY", "Fictional scenes cannot contain real place candidates.")
        for place in result.places:
            if place.model_dump() != job["searched_places"].get(place.place_id):
                abort(422, "INVALID_PLACE", "Places must come from this job's validated search.")
        if result.search_origin and result.search_origin.model_dump() != job.get("search_origin"):
            abort(422, "INVALID_SEARCH_ORIGIN", "Search origin must come from this job's lookup.")
        if result.search_origin_label and result.search_origin_label != job.get("search_origin_label"):
            abort(422, "INVALID_SEARCH_ORIGIN", "Search origin label must match the lookup.")

    @app.post("/worker/results", dependencies=[Depends(worker_auth)])
    def save_result(body: WorkerResult):
        with store.lock:
            job = store.active_job(body.session_id, body.request_id)
            try:
                validate_grounding(body.result, job)
            except HTTPException as exc:
                add_trace(job, "check", "grounding_check", False, error_code(exc))
                raise
            add_trace(job, "check", "grounding_check",
                      detail=f"{len(body.result.evidence)} sources · {len(body.result.conflicts)} conflicts")
            result = body.result.model_dump(mode="json")
            rid = job["request_id"]
            # The worker proposes content, never filenames. Exclusive creation
            # and latest-request validation share the same lock.
            directory = store.output / rid
            try:
                directory.mkdir()
                for suffix, content in (("json", json.dumps(result, ensure_ascii=False, indent=2)),
                                        ("html", html_card(result, job["request"].get("location"))),
                                        ("md", markdown_card(result, job["request"].get("location")))):
                    with (directory / f"travel-card.{suffix}").open("x", encoding="utf-8", newline="\n") as handle:
                        handle.write(content)
            except (OSError, FileExistsError):
                store.finish(job, "failed", "SAVE_FAILED")
                abort(500, "SAVE_FAILED", "A new result could not be saved.")
            job["result"] = result
            store.finish(job, "completed")
            add_trace(job, "broker", "result_saved")
            session = job["session"]
            if job["request"].get("interaction_mode", "ask") == "observe":
                name = body.result.scene.observed_place_name
                if name and body.result.next_question:
                    session.last_visual_observation = {
                        "landmark_name": name, "is_cultural_landmark": True,
                        "identification_supported": True, "photo_id": job["request"].get("photo_id"),
                        "question": body.result.next_question,
                    }
                else:
                    session.last_visual_observation = None
            # Automated scene checks must not displace the visitor's stated needs.
            if job["request"].get("interaction_mode", "ask") == "ask":
                session.history.extend([{"role": "user", "content": job["request"]["question"]},
                                        {"role": "assistant", "content": result["speech_text"]}])
                session.history = session.history[-6:]
            return {"saved": True, "result_id": rid}

    @app.post("/worker/fail", dependencies=[Depends(worker_auth)])
    def fail_job(body: WorkerFailure):
        with store.lock:
            job = store.active_job(body.session_id, body.request_id, kind=None)
            store.finish(job, "failed", body.error_code)
            add_trace(job, "sandbox", "worker_failed", False, body.error_code)
            # Deliberately do not persist or echo upstream exception details.
            return {"accepted": True}

    def owned_job(request_id: str, session: Session, kind: str) -> dict:
        job = store.jobs.get(request_id)
        if not job or job["request"]["session_id"] != session.id or job.get("kind", "guide") != kind:
            abort(404, "JOB_NOT_FOUND", "No matching request.")
        store.expire(job)
        return job

    def start_side_job(session: Session, kind: str, request: dict) -> dict:
        """Queue a review/probe job; like guide requests it supersedes the session's active job."""
        previous = store.jobs.get(session.active_request_id)
        if previous:
            store.expire(previous)
            if previous["status"] not in TERMINAL:
                if kind == "probe" and previous.get("kind") == "probe":
                    abort(409, "JOB_BUSY", "A sandbox probe is already running.")
                store.finish(previous, "superseded")
        store.prune_session_jobs(session.id)
        if len(store.jobs) >= 1500:
            abort(503, "JOB_LIMIT", "Demo capacity reached.")
        rid = uuid.uuid4().hex
        session.active_request_id = rid
        store.jobs[rid] = {"request_id": rid, "kind": kind, "request": request, "status": "queued", "result": None,
                           "error_code": None, "created": time.monotonic(), "session": session, "stage": None}
        add_trace(store.jobs[rid], "broker", "request_accepted")
        return store.jobs[rid]

    def side_status(job: dict) -> dict:
        return {**{key: job[key] for key in ("request_id", "status", "result", "error_code")},
                "trace": list(job.get("trace", []))}

    demo_cache: dict = {}

    def demo_sources() -> dict:
        """The bundled demo input as read by the broker (cached; it ships with the code)."""
        if "sources" not in demo_cache:
            from agent.challenge import ChallengeError, load_sources
            from agent.review import DEMO_INPUT
            try:
                demo_cache["sources"] = {item.id: item for item in load_sources(DEMO_INPUT)}
            except (ChallengeError, OSError):
                return {}
        return demo_cache["sources"]

    @app.get("/api/reviews/inputs")
    def review_inputs(session: Session = Depends(browser_session)):
        from agent.review import as_of
        sources = list(demo_sources().values())
        return {"input_label": "review-demo", "sources": [
            {"id": item.id, "path": item.path, "sha256": item.sha256, "bytes": len(item.text.encode("utf-8")),
             "as_of": as_of(item.text)} for item in sources]}

    @app.post("/api/reviews", status_code=202)
    def submit_review(body: ReviewRequest, session: Session = Depends(browser_session)):
        with store.lock:
            if body.session_id != session.id:
                abort(403, "SESSION_MISMATCH", "Use your own session.")
            job = start_side_job(session, "review", body.model_dump(mode="json"))
            return {"request_id": job["request_id"], "status": "queued", "poll_url": f"/api/reviews/{job['request_id']}"}

    @app.get("/api/reviews/{request_id}")
    def poll_review(request_id: str, session: Session = Depends(browser_session)):
        with store.lock:
            return side_status(owned_job(request_id, session, "review"))

    @app.get("/api/reviews/{request_id}/download")
    def download_review(request_id: str, format: Literal["json", "md"] = "json", session: Session = Depends(browser_session)):
        with store.lock:
            job = owned_job(request_id, session, "review")
            if job["status"] != "completed":
                abort(404, "RESULT_NOT_FOUND", "No saved result in this session.")
            path = store.output / job["request_id"] / f"answer.{format}"
            media = {"json": "application/json", "md": "text/markdown"}[format]
            return FileResponse(path, media_type=media, filename=f"hangul-donghaeng-review-{request_id}.{format}")

    def check_cited(item, allowed: set, excerpt_text: dict):
        if not set(item.source_ids) <= allowed or {quote.source_id for quote in item.quotes} != set(item.source_ids):
            abort(422, "MISSING_EVIDENCE", "Every claim must cite considered sources with quotes.")
        for quote in item.quotes:
            # A quote must sit inside ONE excerpt so it cannot straddle two joined windows.
            if not any(quote.text in chunk for chunk in excerpt_text.get(quote.source_id, [])):
                abort(422, "MISSING_EVIDENCE", "Quotes must be exact text from the supplied excerpts.")

    def validate_review(body: WorkerReviewResult, job: dict) -> bool:
        """Validate a worker review result; returns True when the broker verified the demo input itself."""
        from agent.challenge import select_evidence
        from agent.review import INJECTION, as_of, relevant
        result, req = body.result, job["request"]
        if (result.question, result.condition) != (req["question"], req.get("condition")):
            abort(422, "RESULT_MODE_MISMATCH", "Result does not answer the assigned question.")
        ids = [source.id for source in result.sources]
        if len(set(ids)) != len(ids):
            abort(422, "INVALID_EVIDENCE", "Duplicate source IDs.")
        used = {source.id for source in result.sources if source.verdict == "used"}
        # Superseded sources may appear in a conflict (that is why they lost), never as claim support.
        superseded = {source.id for source in result.sources if source.reason in {"outdated", "conflict_superseded"}}
        excerpt_text = {}
        for excerpt in body.excerpts:
            if excerpt.source_id not in used | superseded:
                abort(422, "INVALID_EVIDENCE", "Excerpts must come from considered sources.")
            excerpt_text.setdefault(excerpt.source_id, []).append(excerpt.text)
        full_text = {}
        actual = demo_sources()
        # The broker, not the worker's label, decides whether this is the demo set it can verify.
        # Any demo file name or hash in the result means it must pass the full demo verification.
        demo_paths = {item.path for item in actual.values()}
        demo_hashes = {item.sha256 for item in actual.values()}
        is_demo = (result.input_label == "review-demo"
                   or any(s.path in demo_paths or s.sha256 in demo_hashes for s in result.sources))
        if is_demo:
            if not actual:
                abort(500, "INPUT_UNAVAILABLE", "Demo input cannot be read.")
            for source in result.sources:
                item = actual.get(source.id)
                if item is None or (item.path, item.sha256) != (source.path, source.sha256):
                    abort(422, "INVALID_EVIDENCE", "Sources must match the demo input files.")
                full_text[source.id] = item.text
            if set(actual) != set(ids):
                abort(422, "INVALID_EVIDENCE", "Every input file must be listed with a verdict.")
            for excerpt in body.excerpts:
                if excerpt.text not in full_text[excerpt.source_id]:
                    abort(422, "INVALID_EVIDENCE", "Excerpts must be exact input text.")
            # Re-run the deterministic rules: an injected source is never used, an off-topic one never cited.
            search_text = req["question"] + (" " + req["condition"] if req.get("condition") else "")
            candidates = [item for item in actual.values()
                          if not INJECTION.search(item.text) and relevant(search_text, item)]
            selected = ({item["source_id"] for item in select_evidence(search_text, candidates)[0]}
                        if candidates else set())
            for source in result.sources:
                if source.reason == "unreadable":
                    abort(422, "INVALID_EVIDENCE", "The broker read every demo file; none is unreadable.")
                if source.reason == "not_selected" and source.id in selected:
                    abort(422, "INVALID_EVIDENCE", "This source was within the excerpt budget.")
                injected = bool(INJECTION.search(full_text[source.id]))
                if injected != (source.reason == "untrusted_instruction"):
                    abort(422, "INVALID_EVIDENCE", "Instruction-like sources, and only those, must be excluded as such.")
                on_topic = relevant(search_text, actual[source.id])
                if not injected and on_topic == (source.reason == "irrelevant"):
                    abort(422, "INVALID_EVIDENCE", "Relevance verdicts must match the question terms.")
                if source.as_of != as_of(full_text[source.id]):
                    abort(422, "INVALID_EVIDENCE", "as_of must be read from the source file.")
        elif os.getenv("REVIEW_ALLOW_EXTERNAL_INPUT", "").lower() != "true":
            abort(422, "INVALID_EVIDENCE", "Only the bundled demo input is accepted on this broker.")
        for claim in result.claims:
            check_cited(claim, used, excerpt_text)
        for conflict in result.conflicts:
            check_cited(conflict, used | superseded, excerpt_text)
        for conflict in result.conflicts:
            if len(set(conflict.source_ids)) < 2:
                abort(422, "INVALID_EVIDENCE", "A conflict needs two distinct sources.")
        if result.status == "answered" and not result.claims:
            abort(422, "INVALID_EVIDENCE", "An answer needs at least one claim.")
        return is_demo

    @app.post("/worker/review-results", dependencies=[Depends(worker_auth)])
    def save_review(body: WorkerReviewResult):
        from agent.challenge import _markdown
        with store.lock:
            job = store.active_job(body.session_id, body.request_id, kind="review")
            try:
                verified = validate_review(body, job)
            except HTTPException as exc:
                add_trace(job, "check", "grounding_check", False, error_code(exc))
                raise
            result = {**body.result.model_dump(mode="json"), "verified_input": verified}
            used = sum(1 for source in result["sources"] if source["verdict"] == "used")
            add_trace(job, "tool", "review_sources", detail=f"{used} used · {len(result['sources']) - used} excluded")
            add_trace(job, "check", "grounding_check",
                      detail=f"{used} sources · {len(result['conflicts'])} conflicts")
            document = flatten_text({**result, "limitations": [
                "Bounded excerpts, not an exhaustive review of every input byte.",
                "Citation membership and exact quotes checked; semantic entailment is not mechanically proven.",
                "Source notes are the model's stated reasons, not verified judgements.",
                "Broker verified: input files and hashes, excerpts, instruction/relevance/date verdicts. "
                "Not verified: claim wording and the model's outdated/superseded judgements and notes." if verified else
                "Input files were NOT visible to the broker; quotes were checked only against worker-supplied excerpts."],
                "sources": [{**source, "relative_path": source["path"]} for source in result["sources"]]})
            directory = store.output / job["request_id"]
            try:
                directory.mkdir()
                for name, content in (("answer.json", json.dumps(result, ensure_ascii=False, indent=2)),
                                      ("answer.md", _markdown(document))):
                    with (directory / name).open("x", encoding="utf-8", newline="\n") as handle:
                        handle.write(content)
            except (OSError, FileExistsError):
                store.finish(job, "failed", "SAVE_FAILED")
                abort(500, "SAVE_FAILED", "A new result could not be saved.")
            job["result"] = result
            store.finish(job, "completed")
            add_trace(job, "broker", "result_saved")
            return {"saved": True, "result_id": job["request_id"]}

    @app.post("/api/sandbox-probe", status_code=202)
    def submit_probe(body: SandboxProbeRequest, session: Session = Depends(browser_session)):
        with store.lock:
            if body.session_id != session.id:
                abort(403, "SESSION_MISMATCH", "Use your own session.")
            job = start_side_job(session, "probe", body.model_dump(mode="json"))
            return {"request_id": job["request_id"], "status": "queued",
                    "poll_url": f"/api/sandbox-probe/{job['request_id']}"}

    @app.get("/api/sandbox-probe/{request_id}")
    def poll_probe(request_id: str, session: Session = Depends(browser_session)):
        with store.lock:
            return side_status(owned_job(request_id, session, "probe"))

    @app.post("/worker/canary")
    def canary():
        """Deliberately NOT in the worker policy allowlist. Any request that arrives here got past the sandbox.
        No auth: a bypass without the gateway-injected token must still be counted. Anyone else hitting it
        can only cause a false "evidence mismatch", never a false "blocked"."""
        with store.lock:
            store.canary_hits += 1
            # Only a claimed, unfinished probe (its canary window is open) gets the event.
            # One trace event per probe (the count is in broker_received), so floods cannot crowd out the
            # per-attempt events. Cross-site POSTs from a visitor's browser can only cause "evidence mismatch".
            for job in store.jobs.values():
                if (job.get("kind") == "probe" and job["status"] == "running" and "canary_start" in job
                        and not job.get("canary_traced")):
                    job["canary_traced"] = True
                    add_trace(job, "broker", "canary_received", False, "request reached the broker")
            return {"received": True}

    @app.post("/worker/probe-results", dependencies=[Depends(worker_auth)])
    def save_probe(body: WorkerProbeResult):
        with store.lock:
            job = store.active_job(body.session_id, body.request_id, kind="probe")
            attempts = body.result.attempts
            if sorted(item.id for item in attempts) != sorted(
                    ["read_outside_allowlist", "write_code_dir", "egress_unlisted_host", "broker_unlisted_path"]):
                add_trace(job, "check", "probe_check", False, "INVALID_PROBE")
                abort(422, "INVALID_PROBE", "Report each probe attempt exactly once.")
            result = body.result.model_dump(mode="json")
            received = store.canary_hits - job.get("canary_start", store.canary_hits)
            for item in result["attempts"]:
                # The broker's own count is authoritative for the broker path; the worker never sets it.
                item["broker_received"] = received if item["id"] == "broker_unlisted_path" else None
                add_trace(job, "sandbox", "probe_" + item["id"], item["observed"] == "denied", item["detail"])
            job["result"] = result
            store.finish(job, "completed")
            add_trace(job, "broker", "result_saved")
            return {"saved": True, "result_id": job["request_id"]}

    @app.get("/api/results/{request_id}/download")
    def download(request_id: str, format: Literal["json", "html", "md"] = "json", session: Session = Depends(browser_session)):
        with store.lock:
            job = store.jobs.get(request_id)
            if (not job or job["request"]["session_id"] != session.id or job["status"] != "completed"
                    or job.get("kind", "guide") != "guide"):
                abort(404, "RESULT_NOT_FOUND", "No saved result in this session.")
            path = store.output / job["request_id"] / f"travel-card.{format}"
            media = {"json": "application/json", "html": "text/html", "md": "text/markdown"}[format]
            return FileResponse(path, media_type=media, filename=f"hangul-donghaeng-{request_id}.{format}")

    dist = ROOT / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app


app = create_app()
