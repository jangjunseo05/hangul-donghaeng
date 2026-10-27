"""Wikipedia summary tool with a mocked network; checks title resolution and refusals."""
import httpx
import pytest

from service import wiki

SUMMARY = {"type": "standard", "pageid": 482, "title": "Gyeongbokgung",
           "extract": "Gyeongbokgung is the main royal palace of the Joseon dynasty.",
           "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Gyeongbokgung"}}}


@pytest.fixture
def web(monkeypatch):
    calls, routes = [], {}

    def handler(request):
        calls.append(request)
        for prefix, reply in routes.items():
            if str(request.url).startswith(prefix):
                return reply() if callable(reply) else httpx.Response(200, json=reply)
        return httpx.Response(404)

    monkeypatch.setattr(wiki, "_TRANSPORT", httpx.MockTransport(handler))
    wiki._CACHE.clear()
    yield calls, routes
    wiki._CACHE.clear()


def test_wikidata_sitelink_resolves_summary_as_public_source(web):
    calls, routes = web
    routes["https://www.wikidata.org/wiki/Special:EntityData/Q482439.json"] = {
        "entities": {"Q482439": {"sitelinks": {"enwiki": {"title": "Gyeongbokgung"}, "kowiki": {"title": "경복궁"}}}}}
    routes["https://en.wikipedia.org/api/rest_v1/page/summary/Gyeongbokgung"] = SUMMARY
    found = wiki.lookup({"place_id": "osm:way:10", "name": "경복궁", "wikidata": "Q482439"}, "en")
    assert found["error_code"] is None
    record = found["records"][0]
    assert record["id"] == "wikipedia:en:482"
    assert record["verification"] == "public_source" and record["license"].startswith("CC BY-SA 4.0")
    assert record["source"] == "https://en.wikipedia.org/wiki/Gyeongbokgung"
    assert all(call.headers["User-Agent"].startswith("HangulDonghaeng/0.2") for call in calls)


def test_osm_wikipedia_tag_is_used_directly(web):
    calls, routes = web
    routes["https://ko.wikipedia.org/api/rest_v1/page/summary/"] = {**SUMMARY, "pageid": 7,
        "content_urls": {"desktop": {"page": "https://ko.wikipedia.org/wiki/%EA%B2%BD%EB%B3%B5%EA%B6%81"}}}
    found = wiki.lookup({"place_id": "osm:way:10", "name": "경복궁", "wikipedia": "ko:경복궁"}, "en")
    assert found["records"][0]["id"] == "wikipedia:ko:7"
    assert len(calls) == 2  # an en card first asks for the en interlanguage link (none here), then uses the tag


def test_disambiguation_and_foreign_host_urls_are_not_evidence(web):
    _, routes = web
    routes["https://en.wikipedia.org/api/rest_v1/page/summary/"] = {**SUMMARY, "type": "disambiguation"}
    assert wiki.lookup({"place_id": "osm:node:1", "name": "Gate", "wikipedia": "en:Gate"}, "en")["records"] == []
    wiki._CACHE.clear()
    routes["https://en.wikipedia.org/api/rest_v1/page/summary/"] = {**SUMMARY,
        "content_urls": {"desktop": {"page": "https://evil.example/wiki/Gate"}}}
    assert wiki.lookup({"place_id": "osm:node:1", "name": "Gate", "wikipedia": "en:Gate"}, "en")["records"] == []


def test_name_search_requires_exact_title_match(web):
    _, routes = web
    routes["https://en.wikipedia.org/w/rest.php/v1/search/title"] = {"pages": [{"title": "Gwanghwamun Square"}]}
    found = wiki.lookup({"place_id": "osm:node:2", "name": "광화문", "name_en": "Gwanghwamun"}, "en")
    assert found["records"] == []
    wiki._CACHE.clear()
    routes["https://en.wikipedia.org/w/rest.php/v1/search/title"] = {"pages": [{"title": "Gwanghwamun"}]}
    routes["https://en.wikipedia.org/api/rest_v1/page/summary/Gwanghwamun"] = {**SUMMARY, "pageid": 9}
    found = wiki.lookup({"place_id": "osm:node:2", "name": "광화문", "name_en": "Gwanghwamun"}, "en")
    assert found["records"][0]["id"] == "wikipedia:en:9"


def test_upstream_failure_is_explicit_and_unknown_language_refused(web):
    _, routes = web
    routes["https://en.wikipedia.org/"] = lambda: httpx.Response(503)
    assert wiki.lookup({"place_id": "osm:node:3", "name": "X", "wikipedia": "en:X"}, "en")["error_code"] == "wiki_http_503"
    assert wiki.lookup({"place_id": "osm:node:3", "name": "X"}, "ja")["error_code"] == "wiki_invalid_lang"


def test_korean_card_prefers_korean_article_through_langlinks(web):
    calls, routes = web
    routes["https://en.wikipedia.org/w/api.php"] = {"query": {"pages": [{"title": "Deoksugung",
                                                                          "langlinks": [{"lang": "ko", "title": "덕수궁"}]}]}}
    routes["https://ko.wikipedia.org/api/rest_v1/page/summary/"] = {**SUMMARY, "pageid": 55, "title": "덕수궁",
        "content_urls": {"desktop": {"page": "https://ko.wikipedia.org/wiki/%EB%8D%95%EC%88%98%EA%B6%81"}}}
    found = wiki.lookup({"place_id": "osm:way:5", "name": "덕수궁", "wikipedia": "en:Deoksugung"}, "ko")
    assert found["records"][0]["id"] == "wikipedia:ko:55"
    assert calls[0].url.params["lllang"] == "ko"


def test_missing_langlink_keeps_the_tagged_article(web):
    _, routes = web
    routes["https://en.wikipedia.org/w/api.php"] = {"query": {"pages": [{"title": "Deoksugung"}]}}
    routes["https://en.wikipedia.org/api/rest_v1/page/summary/"] = SUMMARY
    assert wiki.lookup({"place_id": "osm:way:5", "name": "덕수궁", "wikipedia": "en:Deoksugung"}, "ko")["records"][0]["id"] == "wikipedia:en:482"
