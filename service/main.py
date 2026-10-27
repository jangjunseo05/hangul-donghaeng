"""Small trusted broker. Run a single process: state and jobs are in memory."""
from __future__ import annotations

from collections import OrderedDict
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

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError

from shared.cards import build_card, catalog_card, evidence_label, has_catalog_card
from shared.models import (Evidence, GuideRequest, GuideResult, Location, NearbyPlace, NearbyResponse, Place,
                           PlaceCandidate, SearchRequest, TtsRequest, WikiRequest, WorkerFailure, WorkerProgress,
                           WorkerResult)
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
OSM_ATTRIBUTION = "© OpenStreetMap contributors (ODbL)"


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
            for photo_id in [*session.photos, *session.observe_photos]:
                self.drop_photo(photo_id)
        self.jobs = {rid: job for rid, job in self.jobs.items()
                     if job["request"]["session_id"] not in expired_ids}
        self.session_attempts = {ip: recent for ip, attempts in self.session_attempts.items()
                                 if (recent := [t for t in attempts if now - t < 60])}

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
        # Keep a busy single worker connected through the bounded request deadline.
        return {"status": "ok", "worker_connected": time.monotonic() - store.worker_seen < REQUEST_TIMEOUT_SECONDS + 5,
                "model_configured": bool(os.getenv("NVIDIA_API_KEY")), "sandbox_verified": False,
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
            if len(attempts) >= 10:
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
            return {"request_id": rid, "status": "queued", "poll_url": f"/api/requests/{rid}"}

    @app.get("/api/requests/{request_id}")
    def poll(request_id: str, session: Session = Depends(browser_session)):
        with store.lock:
            job = store.jobs.get(request_id)
            if not job or job["request"]["session_id"] != session.id:
                abort(404, "JOB_NOT_FOUND", "No matching request.")
            store.expire(job)
            return {**{key: job[key] for key in ("request_id", "status", "result", "error_code")},
                    "stage": job.get("stage") if job["status"] == "running" else None}

    @app.get("/worker/jobs/next", dependencies=[Depends(worker_auth)])
    def next_job():
        with store.lock:
            for job in store.jobs.values():
                store.expire(job)
                if job["status"] == "queued":
                    job["status"] = "running"
                    req = job["request"]
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
            if body.live and body.kind not in {"restaurant", "landmark"}:
                abort(422, "SEARCH_KIND", "Live lookup supports restaurants and landmark candidates.")
            if body.kind == "landmark" and (not body.live or body.landmark_name or body.food_id or body.shop_id):
                abort(422, "SEARCH_KIND", "Landmark candidates use only the request location.")
            visual = job.get("last_visual_observation") or {}
            if body.live and body.landmark_name and body.landmark_name != visual.get("landmark_name"):
                abort(422, "LANDMARK_CONTEXT_MISMATCH", "Use the landmark from the assigned conversation.")
            location = req["location"]
        # Public map lookups must not block polling, cancellation or other sessions.
        if body.kind == "landmark":
            return landmark_candidates(body, location, req["response_language"])
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
                              radius_m=radius, tab="landmark")
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
            job = store.active_job(body.session_id, body.request_id)
            job["stage"] = body.stage
            return {"accepted": True}

    @app.post("/worker/wiki", dependencies=[Depends(worker_auth)])
    def public_evidence(body: WikiRequest):
        with store.lock:
            job = store.active_job(body.session_id, body.request_id)
            place = job.get("confirmed_external_place")
            if job["request"]["dataset_mode"] != "real_place" or not place:
                abort(403, "MODE_BOUNDARY", "Public evidence is only for a confirmed external place.")
            if job["wiki_count"] >= 1:
                abort(429, "SEARCH_LIMIT", "Public evidence lookup limit reached.")
            job["wiki_count"] += 1
            issued = job["session"].issued_places.get(place["place_id"]) or place
        from service.wiki import lookup
        found = lookup(issued, body.lang)
        with store.lock:
            job = store.active_job(body.session_id, body.request_id)
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
            validate_grounding(body.result, job)
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
            job = store.active_job(body.session_id, body.request_id)
            store.finish(job, "failed", body.error_code)
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
