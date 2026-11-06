from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(max_length=2000)]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")]
Radius = Literal[500, 1000, 2000, 3000]
Mode = Literal["real_place", "fictional_task"]
Language = Literal["en", "ko"]
# catalog: data/evidence.json record; public_source: broker-fetched OSM/Wikipedia record;
# model_unverified: model general knowledge, shown to the visitor as "확인 필요 / unverified".
Verification = Literal["catalog", "public_source", "model_unverified"]
VERIFICATION_ORDER = ("catalog", "public_source", "model_unverified")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Location(StrictModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    origin: Literal["gps", "selected"]


class GuideRequest(StrictModel):
    schema_version: Literal[1]
    session_id: Identifier
    question: str = Field(min_length=1, max_length=4000)
    photo_id: Identifier | None
    dataset_mode: Mode
    response_language: Literal["en", "ko"]
    location: Location | None
    radius_m: Radius
    confirmed_food_id: Identifier | None
    confirmed_shop_id: Identifier | None
    confirmed_place_id: Identifier | None = None
    interaction_mode: Literal["ask", "observe"] = "ask"


class FoodCandidate(StrictModel):
    id: Identifier
    name_ko: Text
    name_en: Text


class Scene(StrictModel):
    food_candidates: list[FoodCandidate] = Field(max_length=3)
    confirmed_food_id: Identifier | None
    confirmed_shop_id: Identifier | None
    place_candidates: list[FoodCandidate] = Field(default_factory=list, max_length=3)
    confirmed_place_id: Identifier | None = None
    observed_place_name: str | None = Field(default=None, max_length=120)
    # catalog/osm: closed choice among broker-issued GPS candidates (place_candidates[0]);
    # model: free recognition outside the candidates, never a verified identity.
    observed_place_source: Literal["catalog", "osm", "model"] | None = None
    # Model self-report, not a calibrated probability.
    observed_place_confidence: Literal["high", "medium", "low"] | None = None


class Place(StrictModel):
    place_id: Identifier
    name: Text
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    distance_m: float = Field(ge=0, le=3000)
    source_id: Identifier
    catalog_version: Identifier
    kind: Literal["restaurant", "heritage"] = "restaurant"


class Menu(StrictModel):
    name_ko: Text
    description: Text
    evidence_ids: list[Identifier] = Field(min_length=1, max_length=10)
    unknowns: list[Text] = Field(max_length=10)


class Claim(StrictModel):
    text: Text
    scope: Literal["menu", "operation", "culture"]
    evidence_ids: list[Identifier] = Field(min_length=1, max_length=10)


class Evidence(StrictModel):
    id: Identifier
    source: Text
    as_of: Text | None
    type: Literal["document", "live_statement", "example"]
    dataset_id: Identifier


class Conflict(StrictModel):
    evidence_ids: list[Identifier] = Field(min_length=1, max_length=10)
    decision: Text
    reason: Text


class ItineraryItem(StrictModel):
    time: Text
    activity: Text
    buffer_minutes: int | None = Field(ge=0, le=1440)
    evidence_ids: list[Identifier] = Field(min_length=1, max_length=10)


class StoryBlock(StrictModel):
    text: str = Field(min_length=1, max_length=600)
    evidence_ids: list[Identifier] = Field(max_length=10)
    verification: Verification
    analogy: bool = False  # Explanatory framing, not a factual claim.
    # Reference date of a dated note (visit_note only): newest as_of among its cited sources.
    as_of: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def _grounded(self):
        if self.verification != "model_unverified" and not self.evidence_ids:
            raise ValueError("verified block requires evidence_ids")
        return self


class StoryBlocks(StrictModel):
    what_it_is: StoryBlock
    why_it_matters: StoryBlock
    what_to_look_for: StoryBlock
    fun_fact: StoryBlock | None = None


class CardSource(StrictModel):
    """Attribution for a cited record: link + license only, never the quoted source text."""
    id: Identifier
    url: str = Field(max_length=300)
    title: str | None = Field(default=None, max_length=200)
    license: str | None = Field(default=None, max_length=160)
    verification: Literal["catalog", "public_source"]


class LandmarkCard(StrictModel):
    schema_version: Literal[1] = 1
    place_id: Identifier | None  # null only for a model-only (unmatched) landmark
    name: Text
    lang: Language
    blocks: StoryBlocks
    # Operation facts (hours, fees, closures) stay out of the 4 blocks and need a visit-day check.
    visit_note: StoryBlock | None = None
    evidence_ids: list[Identifier] = Field(max_length=30)  # union of block evidence
    verification: Verification  # weakest block verification
    sources: list[CardSource] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def _summary(self):
        blocks = [getattr(self.blocks, name) for name in StoryBlocks.model_fields] + [self.visit_note]
        blocks = [block for block in blocks if block is not None]
        if set(self.evidence_ids) != {item for block in blocks for item in block.evidence_ids}:
            raise ValueError("evidence_ids must be the union of block evidence")
        if self.verification != max((block.verification for block in blocks), key=VERIFICATION_ORDER.index):
            raise ValueError("verification must be the weakest block verification")
        if self.sources and {source.id for source in self.sources} != set(self.evidence_ids):
            raise ValueError("sources must describe exactly the cited evidence")
        return self


class GuideResult(StrictModel):
    schema_version: Literal[1]
    session_id: Identifier
    request_id: Identifier
    captured_at: datetime
    dataset_mode: Mode
    status: Literal["need_confirmation", "ready", "failed"]
    speech_text: Text
    response_language: Literal["en", "ko"]
    scene: Scene
    places: list[Place] = Field(max_length=3)
    menus: list[Menu] = Field(max_length=3)
    claims: list[Claim] = Field(max_length=15)
    evidence: list[Evidence] = Field(max_length=30)
    conflicts: list[Conflict] = Field(max_length=10)
    itinerary: list[ItineraryItem] = Field(max_length=20)
    order_ko: Text | None
    unknowns: list[Text] = Field(max_length=20)
    next_question: Text | None
    error_code: Identifier | None
    search_origin: Location | None = None
    search_origin_label: str | None = Field(default=None, max_length=160)
    landmark_card: LandmarkCard | None = None


JobStage = Literal["observing", "matching", "writing"]


class TraceEvent(StrictModel):
    """One step observed by the trusted broker (worker claims, stages, tool calls, result checks)."""
    t_ms: int = Field(ge=0)
    kind: Literal["broker", "sandbox", "stage", "tool", "check"]  # broker trace_truncated marks dropped events
    name: Identifier
    ok: bool
    detail: str | None = Field(default=None, max_length=200)


class RequestStatus(StrictModel):
    """GET /api/requests/{id}. stage is a progress hint while running, null otherwise."""
    request_id: Identifier
    status: Literal["queued", "running", "completed", "failed", "superseded"]
    stage: JobStage | None = None
    trace: list[TraceEvent] = Field(default_factory=list, max_length=40)
    result: GuideResult | None
    error_code: Identifier | None


class NearbyPlace(StrictModel):
    place_id: Identifier  # local:* catalog or osm:<type>:<id>
    name: Text
    name_en: Text | None = None
    kind: Literal["restaurant", "landmark"]
    category: str | None = Field(default=None, max_length=80)  # e.g. "cuisine=korean", "historic=palace"
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    distance_m: float = Field(ge=0, le=3000)  # straight line from origin
    source_id: Identifier
    osm_url: str | None = Field(default=None, max_length=200)
    has_card: bool = False  # GET /api/landmarks/{place_id}/card is available


# Every code service/nearby.py can produce (M4 decision 6); http_<status> keeps the upstream status.
NEARBY_ERROR_PATTERN = (r"^(?:nearby_(?:disabled|busy|unavailable|timeout|provider_error)"
                        r"|invalid_(?:tab|radius|landmark|location|provider)|location_required|landmark_not_found"
                        r"|(?:geocode|overpass)_(?:timeout|transport_error|invalid_response|response_too_large"
                        r"|incomplete_response|http_[0-9]{3}))$")
NearbyErrorCode = Annotated[str, StringConstraints(pattern=NEARBY_ERROR_PATTERN)]


class NearbyResponse(StrictModel):
    """GET /api/nearby?tab=food|landmark&lat&lng&radius_m. No model call."""
    schema_version: Literal[1] = 1
    tab: Literal["food", "landmark"]
    origin: Location
    radius_m: Radius
    places: list[NearbyPlace] = Field(max_length=20)
    evidence: list[Evidence] = Field(max_length=40)
    attribution: Text
    unknowns: list[Text] = Field(max_length=10)
    error_code: NearbyErrorCode | None = None


class RouteStop(StrictModel):
    order: int = Field(ge=1, le=12)
    place_id: Identifier
    name: Text
    kind: Literal["restaurant", "heritage", "landmark"]
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    dwell_min_estimate: int = Field(ge=0, le=240)
    note: Text | None = None
    has_card: bool = False


class RouteLeg(StrictModel):
    from_place_id: Identifier
    to_place_id: Identifier
    straight_line_m: int = Field(ge=0, le=20000)  # haversine between stop coordinates
    est_walk_min: int = Field(ge=0, le=600)  # ceil(straight_line_m * 1.3 / 70); heuristic
    route_verified: Literal[False] = False
    note: Text | None = None


class Route(StrictModel):
    route_id: Identifier
    title: Text
    summary: Text
    stops: list[RouteStop] = Field(min_length=2, max_length=12)
    legs: list[RouteLeg] = Field(min_length=1, max_length=11)
    total_straight_line_m: int = Field(ge=0, le=50000)
    total_dwell_min_estimate: int = Field(ge=0, le=1440)
    distance_basis: Literal["straight_line"] = "straight_line"
    ui_note: Text
    evidence_ids: list[Identifier] = Field(max_length=30)
    # Dated visiting restriction for the route (e.g. Bukchon red zone); check again on the visit day.
    visit_note: StoryBlock | None = None

    @model_validator(mode="after")
    def _connected(self):
        ids = [stop.place_id for stop in sorted(self.stops, key=lambda stop: stop.order)]
        if [stop.order for stop in self.stops] != list(range(1, len(self.stops) + 1)):
            raise ValueError("stops must be ordered 1..n")
        if [(leg.from_place_id, leg.to_place_id) for leg in self.legs] != list(zip(ids, ids[1:])):
            raise ValueError("legs must connect consecutive stops")
        if self.total_straight_line_m != sum(leg.straight_line_m for leg in self.legs):
            raise ValueError("total_straight_line_m must equal the leg sum")
        return self


class RoutesResponse(StrictModel):
    """GET /api/routes?near=<lat>,<lng>&lang=en|ko. Deterministic templates; no model call."""
    schema_version: Literal[1] = 1
    lang: Language
    routes: list[Route] = Field(max_length=2)
    unknowns: list[Text] = Field(max_length=10)


class TtsRequest(StrictModel):
    """POST /api/tts -> 200 audio/wav; 503 {error_code:"TTS_UNAVAILABLE"} means use browser TTS."""
    text: str = Field(min_length=1, max_length=600)
    lang: Language


class SearchRequest(StrictModel):
    session_id: Identifier
    request_id: Identifier
    food_id: Identifier | None
    shop_id: Identifier | None
    radius_m: Radius
    # landmark (live only): catalog heritage + OSM landmark candidates for closed-set observation.
    kind: Literal["restaurant", "heritage", "landmark"] | None = None
    landmark_name: str | None = Field(default=None, min_length=1, max_length=120)
    live: bool = False


class PlaceCandidate(StrictModel):
    """Broker-issued recognition candidate; ids become confirmable for this session."""
    id: Identifier
    name_ko: Text
    name_en: Text
    kind: Literal["heritage", "landmark"]
    distance_m: float = Field(ge=0, le=3000)
    source: Literal["catalog", "osm"]


class WorkerProgress(StrictModel):
    session_id: Identifier
    request_id: Identifier
    stage: JobStage


class WikiRequest(StrictModel):
    """Worker asks the broker to fetch public evidence for the job's confirmed external place."""
    session_id: Identifier
    request_id: Identifier
    lang: Language


class WorkerResult(StrictModel):
    session_id: Identifier
    request_id: Identifier
    result: GuideResult


class WorkerFailure(StrictModel):
    session_id: Identifier
    request_id: Identifier
    error_code: Identifier
    detail: Text = ""
