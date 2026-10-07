"""Small trusted broker. Run a single process: state and jobs are in memory."""
from __future__ import annotations

import hmac
import io
import json
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError

from shared.models import GuideRequest, GuideResult, SearchRequest, WorkerFailure, WorkerResult
from service import catalog
from service.render import html_card, markdown_card

ROOT = Path(__file__).resolve().parents[1]
Image.MAX_IMAGE_PIXELS = 20_000_000
COOKIE = "guide_session"
TERMINAL = {"completed", "failed", "superseded"}
SESSION_MAX_AGE = 6 * 3600
SESSION_IDLE_AGE = 3600


def abort(status: int, code: str, message: str):
    raise HTTPException(status, detail={"error_code": code, "detail": message})


@dataclass
class Session:
    id: str
    active_request_id: str | None = None
    history: list[dict] = field(default_factory=list)
    photos: set[str] = field(default_factory=set)
    created: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)
    history_mode: str | None = None


class Store:
    def __init__(self, runtime: Path):
        self.lock = threading.RLock()
        self.sessions: dict[str, Session] = {}
        self.jobs: dict[str, dict] = {}
        self.photos: dict[str, dict] = {}
        self.worker_seen = 0.0
        self.session_attempts: dict[str, list[float]] = {}
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
            for photo_id in session.photos:
                photo = self.photos.pop(photo_id, None)
                if photo:
                    photo["path"].unlink(missing_ok=True)
        self.jobs = {rid: job for rid, job in self.jobs.items()
                     if job["request"]["session_id"] not in expired_ids}
        self.session_attempts = {ip: recent for ip, attempts in self.session_attempts.items()
                                 if (recent := [t for t in attempts if now - t < 60])}

    def expire(self, job: dict):
        if job["status"] not in TERMINAL and time.monotonic() - job["created"] > 30:
            job["error_code"] = "WORKER_UNAVAILABLE" if job["status"] == "queued" else "REQUEST_TIMEOUT"
            job["status"] = "failed"

    def active_job(self, sid: str, rid: str, running: bool = True) -> dict:
        job = self.jobs.get(rid)
        if not job or job["request"]["session_id"] != sid:
            abort(404, "JOB_NOT_FOUND", "No job belongs to this session.")
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


def create_app(runtime_dir: Path | None = None, worker_token: str | None = None) -> FastAPI:
    app = FastAPI(title="Hangul Donghaeng", version="0.1.0")
    app.add_middleware(BodyLimitMiddleware)
    store = Store(runtime_dir or ROOT / ".runtime")
    app.state.store = store
    token = worker_token or os.getenv("WORKER_TOKEN", "")
    cookie_secure = os.getenv("GUIDE_COOKIE_SECURE", "false").lower() == "true"
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

    def worker_auth(authorization: str | None = Header(default=None)):
        expected = f"Bearer {token}"
        if not token or not authorization or not hmac.compare_digest(authorization, expected):
            abort(401, "WORKER_AUTH_REQUIRED", "Worker authentication failed.")
        with store.lock:
            store.worker_seen = time.monotonic()

    @app.get("/api/health")
    def health():
        return {"status": "ok", "worker_connected": time.monotonic() - store.worker_seen < 15,
                "model_configured": bool(os.getenv("NVIDIA_API_KEY")), "sandbox_verified": False,
                "catalog_count": catalog.catalog_summary()["catalog_count"], "version": "0.1.0"}

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
            if len(attempts) >= 10:
                abort(429, "SESSION_RATE_LIMIT", "Please wait a minute before starting another session.")
            if len(store.sessions) >= 64:
                abort(503, "SESSION_LIMIT", "All demo sessions are in use. Please try again later.")
            attempts.append(now)
            key = secrets.token_urlsafe(32)
            session = Session(id=uuid.uuid4().hex)
            store.sessions[key] = session
            response.set_cookie(COOKIE, key, httponly=True, secure=cookie_secure, samesite="strict", max_age=21600)
            return {"session_id": session.id}

    @app.post("/api/photos")
    async def upload_photo(file: UploadFile, session: Session = Depends(browser_session)):
        with store.lock:
            if len(session.photos) >= 20:
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
            session.photos.add(photo_id)
            store.photos[photo_id] = {"session_id": session.id, "path": path}
        return {"photo_id": photo_id, "width": width, "height": height}

    @app.post("/api/requests", status_code=202)
    def submit(body: GuideRequest, session: Session = Depends(browser_session)):
        with store.lock:
            if body.session_id != session.id:
                abort(403, "SESSION_MISMATCH", "Use your own session.")
            if body.photo_id and body.photo_id not in session.photos:
                abort(404, "PHOTO_NOT_FOUND", "Upload a photo in this session first.")
            if body.confirmed_food_id and body.confirmed_food_id not in catalog.valid_food_ids():
                abort(422, "UNKNOWN_FOOD", "Choose one of the available food candidates.")
            if body.confirmed_shop_id and not catalog.get_place(body.confirmed_shop_id):
                abort(422, "UNKNOWN_PLACE", "Choose a listed place.")
            if len(store.jobs) >= 1500:
                abort(503, "JOB_LIMIT", "Demo capacity reached.")
            if session.history_mode != body.dataset_mode:
                session.history.clear()
                session.history_mode = body.dataset_mode
            previous = store.jobs.get(session.active_request_id)
            if previous and previous["status"] not in TERMINAL:
                previous["status"] = "superseded"
            rid = uuid.uuid4().hex
            session.active_request_id = rid
            store.jobs[rid] = {"request_id": rid, "request": body.model_dump(mode="json"), "status": "queued",
                               "result": None, "error_code": None, "created": time.monotonic(), "session": session,
                               "history": list(session.history[-6:]), "search_count": 0, "searched_places": {}}
            return {"request_id": rid, "status": "queued", "poll_url": f"/api/requests/{rid}"}

    @app.get("/api/requests/{request_id}")
    def poll(request_id: str, session: Session = Depends(browser_session)):
        with store.lock:
            job = store.jobs.get(request_id)
            if not job or job["request"]["session_id"] != session.id:
                abort(404, "JOB_NOT_FOUND", "No matching request.")
            store.expire(job)
            return {key: job[key] for key in ("request_id", "status", "result", "error_code")}

    @app.get("/worker/jobs/next", dependencies=[Depends(worker_auth)])
    def next_job():
        with store.lock:
            for job in store.jobs.values():
                store.expire(job)
                if job["status"] == "queued":
                    job["status"] = "running"
                    req = job["request"]
                    return {"session_id": req["session_id"], "request_id": job["request_id"], "request": req,
                            "history": job["history"], "allowed_source_ids": [e["id"] for e in catalog.evidence_for_mode(req["dataset_mode"])]}
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
        with store.lock:
            job = store.active_job(body.session_id, body.request_id)
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
            found = catalog.search_places(body.food_id, body.shop_id, req["location"], body.radius_m)
            job["searched_places"] = {p["place_id"]: p for p in found["places"]}
            return found

    def validate_grounding(result: GuideResult, job: dict):
        req = job["request"]
        if result.session_id != req["session_id"] or result.request_id != job["request_id"]:
            abort(422, "RESULT_ID_MISMATCH", "Result IDs do not match the assigned request.")
        if result.dataset_mode != req["dataset_mode"] or result.response_language != req["response_language"]:
            abort(422, "RESULT_MODE_MISMATCH", "Result mode or language does not match.")
        approved = {e["id"]: e for e in catalog.evidence_for_mode(req["dataset_mode"])}
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
        for place in result.places:
            if place.model_dump() != job["searched_places"].get(place.place_id):
                abort(422, "INVALID_PLACE", "Places must come from this job's validated search.")

    @app.post("/worker/results", dependencies=[Depends(worker_auth)])
    def save_result(body: WorkerResult):
        with store.lock:
            job = store.active_job(body.session_id, body.request_id)
            validate_grounding(body.result, job)
            result = body.result.model_dump(mode="json")
            rid = job["request_id"]
            # The worker proposes content, never filenames. Exclusive creation
            # and latest-request validation share the same lock.
            directory = store.output / rid
            try:
                directory.mkdir()
                for suffix, content in (("json", json.dumps(result, ensure_ascii=False, indent=2)),
                                        ("html", html_card(result)), ("md", markdown_card(result))):
                    with (directory / f"travel-card.{suffix}").open("x", encoding="utf-8", newline="\n") as handle:
                        handle.write(content)
            except (OSError, FileExistsError):
                job.update(status="failed", error_code="SAVE_FAILED")
                abort(500, "SAVE_FAILED", "A new result could not be saved.")
            job.update(status="completed", result=result)
            session = job["session"]
            session.history.extend([{"role": "user", "content": job["request"]["question"]},
                                    {"role": "assistant", "content": result["speech_text"]}])
            session.history = session.history[-6:]
            return {"saved": True, "result_id": rid}

    @app.post("/worker/fail", dependencies=[Depends(worker_auth)])
    def fail_job(body: WorkerFailure):
        with store.lock:
            job = store.active_job(body.session_id, body.request_id)
            job.update(status="failed", error_code=body.error_code)
            # Deliberately do not persist or echo upstream exception details.
            return {"accepted": True}

    @app.get("/api/results/{request_id}/download")
    def download(request_id: str, format: Literal["json", "html", "md"] = "json", session: Session = Depends(browser_session)):
        with store.lock:
            job = store.jobs.get(request_id)
            if not job or job["request"]["session_id"] != session.id or job["status"] != "completed":
                abort(404, "RESULT_NOT_FOUND", "No saved result in this session.")
            path = store.output / job["request_id"] / f"travel-card.{format}"
            media = {"json": "application/json", "html": "text/html", "md": "text/markdown"}[format]
            return FileResponse(path, media_type=media, filename=f"hangul-donghaeng-{request_id}.{format}")

    dist = ROOT / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app


app = create_app()
