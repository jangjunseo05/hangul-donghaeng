"""Regenerate shared/*.schema.json from shared/models.py: python -m shared.export_schemas"""
import json
from pathlib import Path

from shared.models import (GuideRequest, GuideResult, LandmarkCard, NearbyResponse, RequestStatus,
                           RoutesResponse, TtsRequest)

SCHEMAS = {"request": GuideRequest, "result": GuideResult, "request-status": RequestStatus,
           "nearby": NearbyResponse, "routes": RoutesResponse, "landmark-card": LandmarkCard,
           "tts-request": TtsRequest}
DIRECTORY = Path(__file__).resolve().parent


def rendered(model) -> str:
    return json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    for name, model in SCHEMAS.items():
        (DIRECTORY / f"{name}.schema.json").write_text(rendered(model), encoding="utf-8", newline="\n")
