"""Generalized OSM lookup with a mocked network: no request leaves the test process."""
import json
from urllib.parse import parse_qs

import httpx
import pytest

from service import nearby

SEOCHON = {"lat": 37.579, "lng": 126.973, "origin": "selected"}


@pytest.fixture
def osm(monkeypatch):
    calls = []
    state = {"geocode": [{"lat": "37.5759", "lon": "126.9768"}], "elements": []}

    def handler(request):
        calls.append(request)
        if request.url.host == "nominatim.openstreetmap.org":
            return httpx.Response(200, json=state["geocode"])
        assert request.url.host == "overpass-api.de"
        return httpx.Response(200, json={"elements": state["elements"]})

    monkeypatch.setattr(nearby, "_TRANSPORT", httpx.MockTransport(handler))
    monkeypatch.setattr(nearby, "_LAST_GEOCODE", 0.0)
    nearby._CACHE.clear()
    nearby._GEO.clear()
    yield calls, state
    nearby._CACHE.clear()
    nearby._GEO.clear()


def element(identity, tags, lat=37.5795, lng=126.9732, kind="node"):
    return {"type": kind, "id": identity, "lat": lat, "lon": lng, "tags": tags}


def overpass_query(request):
    return parse_qs(request.content.decode())["data"][0]


def test_food_tab_includes_cafes_and_returns_rich_entries_with_identifying_user_agent(osm):
    calls, state = osm
    state["elements"] = [element(1, {"amenity": "cafe", "name": "Cafe A", "name:en": "Cafe A"}),
                         element(2, {"amenity": "restaurant", "name": "식당 B"}, lat=37.5800),
                         element(3, {"amenity": "bank", "name": "Bank"}),
                         element(4, {"amenity": "restaurant", "name": "Far"}, lat=37.60)]
    found = nearby.search_nearby(landmark_name=None, location=SEOCHON, radius_m=1000, tab="food")
    assert found["error_code"] is None
    assert [p["place_id"] for p in found["places"]] == ["osm:node:1", "osm:node:2"]
    assert found["places"][0]["category"] == "amenity=cafe"
    assert found["places"][0]["osm_url"] == "https://www.openstreetmap.org/node/1"
    assert "catalog_version" not in found["places"][0]
    assert 'amenity"~"^(restaurant|cafe|fast_food)$"' in overpass_query(calls[0])
    assert calls[0].headers["User-Agent"].startswith(
        "HangulDonghaeng/0.2 (+https://github.com/jangjunseo05/hangul-donghaeng) httpx/")
    assert "@" not in calls[0].headers["User-Agent"]


def test_restaurant_worker_shape_is_unchanged_and_limited_to_three(osm):
    _, state = osm
    state["elements"] = [element(index, {"amenity": "restaurant", "name": f"R{index}"},
                                 lat=37.579 + index * 0.0001) for index in range(1, 6)]
    found = nearby.search_nearby(landmark_name=None, location=SEOCHON, radius_m=1000)
    assert len(found["places"]) == 3
    assert set(found["places"][0]) == {"place_id", "name", "lat", "lng", "distance_m", "source_id",
                                       "catalog_version", "kind"}


def test_named_lookup_is_worldwide_biased_to_user_point_without_country_filter(osm):
    calls, state = osm
    paris = {"lat": 48.8584, "lng": 2.2945, "origin": "gps"}
    state["geocode"] = [{"lat": "48.8584", "lon": "2.2945"}]
    found = nearby.search_nearby(landmark_name="Eiffel Tower", location=paris, radius_m=500)
    params = calls[0].url.params
    assert "countrycodes" not in params
    assert params["viewbox"] == "2.19,48.96,2.39,48.76" and params["bounded"] == "0"
    assert found["search_origin_label"] == "Eiffel Tower"
    assert found["search_origin"]["lat"] == 48.8584


def test_unknown_name_falls_back_to_user_point(osm):
    calls, state = osm
    state["geocode"] = []
    found = nearby.search_nearby(landmark_name="Unmapped Gate", location=SEOCHON, radius_m=500)
    assert found["error_code"] is None
    assert found["search_origin_label"] == "User-selected location"
    assert found["search_origin"]["lat"] == SEOCHON["lat"]
    assert len(calls) == 2


def test_unknown_name_without_location_is_explicit(osm):
    _, state = osm
    state["geocode"] = []
    assert nearby.search_nearby(landmark_name="Unmapped Gate", location=None, radius_m=500)["error_code"] == "landmark_not_found"


def test_landmark_tab_keeps_heritage_and_public_tags_but_drops_minor_memorials(osm):
    calls, state = osm
    state["elements"] = [
        element(10, {"historic": "palace", "name": "경복궁", "name:en": "Gyeongbokgung", "wikidata": "Q482439",
                     "wikipedia": "ko:경복궁"}, kind="way"),
        element(11, {"historic": "memorial", "name": "Small plaque"}),
        element(12, {"tourism": "museum", "name": "Museum", "wikidata": "not-a-qid"}),
    ]
    state["elements"][0]["center"] = {"lat": 37.5796, "lon": 126.977}
    found = nearby.search_nearby(landmark_name=None, location=SEOCHON, radius_m=1000, tab="landmark")
    ids = [p["place_id"] for p in found["places"]]
    assert ids == ["osm:node:12", "osm:way:10"]
    palace = found["places"][1]
    assert palace["kind"] == "landmark" and palace["wikidata"] == "Q482439" and palace["wikipedia"] == "ko:경복궁"
    assert found["places"][0]["wikidata"] is None
    query = overpass_query(calls[0])
    assert 'nwr["historic"]["name"]' in query and "tourism" in query
    assert {e["id"] for e in found["evidence"]} == set(ids)


def test_invalid_tab_and_provider_failure_are_explicit(osm, monkeypatch):
    assert nearby.search_nearby(landmark_name=None, location=SEOCHON, radius_m=500, tab="hotel")["error_code"] == "invalid_tab"
    monkeypatch.setattr(nearby, "_TRANSPORT", httpx.MockTransport(lambda request: httpx.Response(429)))
    found = nearby.search_nearby(landmark_name=None, location=SEOCHON, radius_m=500, tab="landmark")
    assert found["places"] == [] and found["error_code"] == "overpass_http_429"
