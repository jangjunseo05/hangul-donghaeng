from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(max_length=2000)]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")]
Radius = Literal[500, 1000, 2000, 3000]
Mode = Literal["real_place", "fictional_task"]


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


class SearchRequest(StrictModel):
    session_id: Identifier
    request_id: Identifier
    food_id: Identifier | None
    shop_id: Identifier | None
    radius_m: Radius
    kind: Literal["restaurant", "heritage"] | None = None


class WorkerResult(StrictModel):
    session_id: Identifier
    request_id: Identifier
    result: GuideResult


class WorkerFailure(StrictModel):
    session_id: Identifier
    request_id: Identifier
    error_code: Identifier
    detail: Text = ""
