"""Broker-only public evidence lookup: Wikipedia REST page summary for one OSM place.

Fixed hosts (en/ko Wikipedia, Wikidata); the title comes from the place's OSM
wikipedia/wikidata tags, or an exact-title match of its name. No photos, model
output, user text or credentials leave through this tool. Serial requests,
identifying User-Agent, 24 h cache (Wikimedia API etiquette, research §4).
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import json
import re
import threading
import time
from urllib.parse import quote, urlsplit

import httpx

from service.nearby import USER_AGENT

LICENSE = "CC BY-SA 4.0 (Wikipedia text); attribution + link required"
_HOSTS = {"en": "https://en.wikipedia.org", "ko": "https://ko.wikipedia.org"}
_WIKIDATA = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"
_QID = re.compile(r"^Q[1-9][0-9]{0,11}$")
_MAX_BYTES = 1_000_000
_MAX_TEXT = 1500
_TRANSPORT = None  # Tests inject httpx.MockTransport.
_FLIGHT = threading.BoundedSemaphore(1)
_LOCK = threading.Lock()
_CACHE: OrderedDict = OrderedDict()


class _Failure(Exception):
    pass


def _get(client, url, params=None):
    if not (url.startswith(tuple(host + "/" for host in _HOSTS.values()))
            or url.startswith("https://www.wikidata.org/wiki/Special:EntityData/")):
        raise _Failure("wiki_invalid_provider")
    try:
        with client.stream("GET", url, params=params) as response:
            if response.status_code == 404:
                return None
            if response.status_code != 200:
                raise _Failure("wiki_http_" + str(response.status_code))
            body = bytearray()
            for chunk in response.iter_bytes(chunk_size=8192):
                body.extend(chunk)
                if len(body) > _MAX_BYTES:
                    raise _Failure("wiki_response_too_large")
            return json.loads(body)
    except httpx.TimeoutException as exc:
        raise _Failure("wiki_timeout") from exc
    except httpx.HTTPError as exc:
        raise _Failure("wiki_transport_error") from exc
    except (ValueError, TypeError, RecursionError) as exc:
        raise _Failure("wiki_invalid_response") from exc


def _key(value: str) -> str:
    return re.sub(r"[\W_]", "", value).casefold()


def _titles(client, place: dict, lang: str) -> list[tuple[str, str]]:
    """Candidate (lang, title) pairs, most trustworthy first."""
    found = []
    tag = place.get("wikipedia")
    if isinstance(tag, str) and ":" in tag:
        tag_lang, title = tag.split(":", 1)
        if tag_lang in _HOSTS:
            found.append((tag_lang, title))
    qid = place.get("wikidata")
    if isinstance(qid, str) and _QID.fullmatch(qid):
        entity = _get(client, _WIKIDATA.format(qid))
        links = ((entity or {}).get("entities", {}).get(qid, {}) or {}).get("sitelinks", {})
        for site_lang in (lang, "en", "ko"):
            title = (links.get(site_lang + "wiki") or {}).get("title")
            if isinstance(title, str) and title:
                found.append((site_lang, title))
    if not found:
        # Exact title only: a fuzzy search hit could describe a different place.
        for site_lang, name in ((lang, place.get("name_en") if lang == "en" else place.get("name")),
                                ("ko", place.get("name")), ("en", place.get("name_en"))):
            if not isinstance(name, str) or not name.strip():
                continue
            hits = _get(client, _HOSTS[site_lang] + "/w/rest.php/v1/search/title", {"q": name, "limit": 1})
            pages = (hits or {}).get("pages") or []
            if pages and isinstance(pages[0].get("title"), str) and _key(pages[0]["title"]) == _key(name):
                found.append((site_lang, pages[0]["title"]))
                break
    if found and all(site_lang != lang for site_lang, _ in found):
        # Prefer the visitor's language (ko card -> ko article) through the article's interlanguage link.
        site_lang, title = found[0]
        links = _get(client, _HOSTS[site_lang] + "/w/api.php", {
            "action": "query", "prop": "langlinks", "lllang": lang, "titles": title,
            "format": "json", "formatversion": 2})
        pages = ((links or {}).get("query") or {}).get("pages") or []
        linked = ((pages[0].get("langlinks") or [{}])[0].get("title")) if pages and isinstance(pages[0], dict) else None
        if isinstance(linked, str) and linked.strip():
            found.insert(0, (lang, linked))
    preferred = sorted(dict.fromkeys(found), key=lambda item: item[0] != lang)
    return preferred[:2]


def _summary(client, site_lang: str, title: str) -> dict | None:
    data = _get(client, _HOSTS[site_lang] + "/api/rest_v1/page/summary/" + quote(title.replace(" ", "_"), safe=""))
    if not isinstance(data, dict) or data.get("type") != "standard":
        return None  # Disambiguation and missing pages are not evidence.
    page_id, extract = data.get("pageid"), data.get("extract")
    url = ((data.get("content_urls") or {}).get("desktop") or {}).get("page")
    if (type(page_id) is not int or page_id <= 0 or not isinstance(extract, str) or not extract.strip()
            or not isinstance(url, str) or urlsplit(url).netloc != urlsplit(_HOSTS[site_lang]).netloc):
        return None
    text = " ".join(extract.split())[:_MAX_TEXT]
    return {"id": f"wikipedia:{site_lang}:{page_id}", "source": url, "title": str(data.get("title", title))[:200],
            "text": text, "license": LICENSE, "verification": "public_source",
            "as_of": datetime.now(timezone.utc).isoformat(), "type": "document", "dataset_id": "real_place"}


def lookup(place: dict, lang: str) -> dict:
    """Return {'records': [...], 'error_code'}; records carry text for the worker prompt."""
    if lang not in _HOSTS:
        return {"records": [], "error_code": "wiki_invalid_lang"}
    cache_key = (place.get("place_id"), lang)
    with _LOCK:
        item = _CACHE.get(cache_key)
        if item and item[0] > time.monotonic():
            return deepcopy(item[1])
    if not _FLIGHT.acquire(timeout=8.0):
        return {"records": [], "error_code": "wiki_busy"}
    try:
        with httpx.Client(follow_redirects=False, trust_env=False, transport=_TRANSPORT,
                          timeout=httpx.Timeout(6.0, connect=3.0),
                          headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                                   "Accept-Encoding": "identity"}) as client:
            records = []
            for site_lang, title in _titles(client, place, lang):
                record = _summary(client, site_lang, title)
                if record and record["id"] not in {item["id"] for item in records}:
                    records.append(record)
                    break  # One article is enough for a short card.
            result = {"records": records, "error_code": None}
    except _Failure as exc:
        result = {"records": [], "error_code": str(exc)}
    finally:
        _FLIGHT.release()
    with _LOCK:
        _CACHE[cache_key] = (time.monotonic() + (86400 if result["error_code"] is None else 60), deepcopy(result))
        while len(_CACHE) > 256:
            _CACHE.popitem(last=False)
    return result
