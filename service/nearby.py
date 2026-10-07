"""User-triggered public OSM lookup; no photos, credentials or model calls.

Single broker process: one in-flight lookup, Nominatim <=1 request/second.
Caller must display OpenStreetMap attribution and supply only public landmark
names or explicitly user-chosen coordinates. Never call for autocomplete.
References checked 2026-10-07:
https://operations.osmfoundation.org/policies/nominatim/
https://nominatim.org/release-docs/latest/api/Search/
https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import os
import threading
import time

import httpx

_GEOCODE = "https://nominatim.openstreetmap.org/search"
_OVERPASS = "https://overpass-api.de/api/interpreter"
_UA = "HangulDonghaeng/0.1 (+https://github.com/jangjunseo05/hangul-donghaeng)"
_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="osm-nearby")
_FLIGHT = threading.BoundedSemaphore(1)
_LOCK = threading.Lock()
_CACHE: OrderedDict = OrderedDict()
_GEO: OrderedDict = OrderedDict()
_LAST_GEOCODE = 0.0
_MAX_BYTES = 1_000_000


class _Failure(Exception):
    pass


def _empty(code=None, origin=None, label="", needs_location=False):
    return {"places": [], "evidence": [], "search_origin": origin,
            "search_origin_label": label, "error_code": code,
            "provider": "OpenStreetMap", "needs_location": needs_location}


def _cached(cache, key):
    with _LOCK:
        item = cache.get(key)
        if item is None:
            return None
        if item[0] <= time.monotonic():
            del cache[key]
            return None
        cache.move_to_end(key)
        return deepcopy(item[1])


def _remember(cache, key, value, ttl):
    with _LOCK:
        cache[key] = (time.monotonic() + ttl, deepcopy(value))
        cache.move_to_end(key)
        while len(cache) > 128:
            cache.popitem(last=False)


def _coords(lat, lng, *, text=False):
    if not text and (type(lat) not in (int, float) or type(lng) not in (int, float)):
        raise ValueError("invalid coordinates")
    lat, lng = float(lat), float(lng)
    if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("invalid coordinates")
    return lat, lng


def _distance(lat, lng, other_lat, other_lng):
    a, b, c, d = map(math.radians, (lat, lng, other_lat, other_lng))
    value = math.sin((c - a) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, value))))


async def _json(client, url, *, params=None, data=None):
    # URLs are constants, not derived from names, OSM responses or caller input.
    if url not in (_GEOCODE, _OVERPASS):
        raise _Failure("invalid_provider")
    provider = "geocode" if url == _GEOCODE else "overpass"
    try:
        async with client.stream("GET" if data is None else "POST", url,
                                 params=params, data=data) as response:
            if response.status_code != 200:
                raise _Failure(provider + "_http_" + str(response.status_code))
            size = response.headers.get("content-length")
            if size and int(size) > _MAX_BYTES:
                raise _Failure(provider + "_response_too_large")
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=8192):
                body.extend(chunk)
                if len(body) > _MAX_BYTES:
                    raise _Failure(provider + "_response_too_large")
            return json.loads(body)
    except httpx.TimeoutException as exc:
        raise _Failure(provider + "_timeout") from exc
    except httpx.HTTPError as exc:
        raise _Failure(provider + "_transport_error") from exc
    except (ValueError, TypeError, RecursionError) as exc:
        raise _Failure(provider + "_invalid_response") from exc


async def _lookup(name, location, radius):
    global _LAST_GEOCODE
    origin = None
    label = name or "User-selected location"
    try:
        async with httpx.AsyncClient(follow_redirects=False, trust_env=False,
                                    timeout=httpx.Timeout(7.0, connect=3.0),
                                    headers={"User-Agent": _UA, "Accept": "application/json",
                                             "Accept-Encoding": "identity"}) as client:
            if name:
                center = _cached(_GEO, name.casefold())
                if center is None:
                    await asyncio.sleep(max(0.0, 1.01 - (time.monotonic() - _LAST_GEOCODE)))
                    _LAST_GEOCODE = time.monotonic()
                    geocode = await _json(client, _GEOCODE, params={"q": name,
                        "format": "jsonv2", "countrycodes": "kr", "limit": 1,
                        "addressdetails": 0, "accept-language": "ko,en"})
                    if not isinstance(geocode, list):
                        raise _Failure("geocode_invalid_response")
                    if not geocode:
                        return _empty("landmark_not_found", label=label)
                    try:
                        center = _coords(geocode[0]["lat"], geocode[0]["lon"], text=True)
                    except (KeyError, TypeError, ValueError, IndexError):
                        raise _Failure("geocode_invalid_response")
                    _remember(_GEO, name.casefold(), center, 86400)
                lat, lng = center
            else:
                lat, lng = location
            origin = {"lat": lat, "lng": lng, "origin": "selected"}
            query = (f'[out:json][timeout:8][maxsize:33554432];'
                     f'nwr["amenity"="restaurant"]["name"](around:{radius},{lat:.8f},{lng:.8f});out center;')
            result = await _json(client, _OVERPASS, data={"data": query})
            if not isinstance(result, dict) or not isinstance(result.get("elements"), list):
                raise _Failure("overpass_invalid_response")
            if result.get("remark"):
                raise _Failure("overpass_incomplete_response")
            places = {}
            for element in result["elements"]:
                if not isinstance(element, dict):
                    continue
                tags = element.get("tags")
                if not isinstance(tags, dict) or tags.get("amenity") != "restaurant":
                    continue
                title = tags.get("name")
                kind, identity = element.get("type"), element.get("id")
                if (not isinstance(title, str) or not title.strip() or len(title) > 200
                        or any(ord(c) < 32 for c in title) or kind not in {"node", "way", "relation"}
                        or type(identity) is not int or identity <= 0):
                    continue
                coords = element if kind == "node" else element.get("center")
                try:
                    point = _coords(coords["lat"], coords["lon"])
                except (KeyError, TypeError, ValueError):
                    continue
                distance = _distance(lat, lng, *point)
                if distance > radius:
                    continue
                key = f"osm:{kind}:{identity}"
                places[key] = {"place_id": key, "name": title.strip(), "lat": point[0],
                    "lng": point[1], "distance_m": distance, "source_id": key,
                    "catalog_version": "osm-live-20261007", "kind": "restaurant"}
            selected = sorted(places.values(), key=lambda p: (p["distance_m"], p["place_id"]))[:3]
            fetched = datetime.now(timezone.utc).isoformat()
            evidence = []
            for place in selected:
                place["distance_m"] = round(place["distance_m"], 1)
                _, kind, identity = place["source_id"].split(":")
                evidence.append({"id": place["source_id"],
                    "source": f"https://www.openstreetmap.org/{kind}/{identity}",
                    "as_of": fetched, "type": "document", "dataset_id": "real_place"})
            return {**_empty(origin=origin, label=label), "places": selected, "evidence": evidence}
    except _Failure as exc:
        return _empty(str(exc), origin=origin, label=label)


def _run(name, location, radius, deadline):
    async def bounded():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return _empty("nearby_timeout")
        try:
            return await asyncio.wait_for(_lookup(name, location, radius), timeout=remaining)
        except asyncio.TimeoutError:
            return _empty("nearby_timeout", label=name or "User-selected location")
    return asyncio.run(bounded())


def search_nearby(*, landmark_name: str | None, location: dict | None, radius_m: int) -> dict:
    """Return up to three named OSM restaurants; distance only, no quality claims.

    ~15-second caller bound including network; busy/failure returns explicit empty
    results. Named landmark takes precedence, without fallback to user location.
    Cache/rate limit cover this single broker process, not multiple deployments.
    NEARBY_OSM_ENABLED=false disables external lookup without a code change.
    """
    if os.environ.get("NEARBY_OSM_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        return _empty("nearby_disabled")
    if type(radius_m) is not int or not 1 <= radius_m <= 3000:
        return _empty("invalid_radius")
    if landmark_name is not None and not isinstance(landmark_name, str):
        return _empty("invalid_landmark")
    name = " ".join(landmark_name.split()) if landmark_name else ""
    if name and (len(name) > 160 or "://" in name or "@" in name
                 or any(ord(c) < 32 for c in landmark_name)):
        return _empty("invalid_landmark")
    center = None
    if not name:
        if location is None:
            return _empty("location_required", needs_location=True)
        try:
            if not isinstance(location, dict) or location.get("origin") not in {None, "selected", "gps"}:
                return _empty("invalid_location", needs_location=True)
            center = _coords(location["lat"], location["lng"])
        except (KeyError, TypeError, ValueError):
            return _empty("invalid_location", needs_location=True)
    key = (name.casefold(), center, radius_m)
    hit = _cached(_CACHE, key)
    if hit is not None:
        return hit
    if not _FLIGHT.acquire(blocking=False):
        return _empty("nearby_busy", label=name or "User-selected location")
    try:
        future = _POOL.submit(_run, name, center, radius_m, time.monotonic() + 14.5)
    except RuntimeError:
        _FLIGHT.release()
        return _empty("nearby_unavailable")
    future.add_done_callback(lambda _: _FLIGHT.release())
    try:
        result = future.result(timeout=15.0)
    except FutureTimeout:
        return _empty("nearby_timeout", label=name or "User-selected location")
    except Exception:
        return _empty("nearby_provider_error", label=name or "User-selected location")
    _remember(_CACHE, key, result, 300 if result["error_code"] is None else 30)
    return deepcopy(result)
