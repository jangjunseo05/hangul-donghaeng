"""One real synthetic product request; no mock provider and no credential logging."""
import json
import time
import hashlib
import httpx

def main():
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=10, follow_redirects=False) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        print(json.dumps({"check": "health", "body": health.json()}), flush=True)
        session = client.post("/api/sessions", json={})
        session.raise_for_status()
        request = {"schema_version": 1, "session_id": session.json()["session_id"],
                   "question": "I confirmed samgyetang. Find the curated restaurant near my selected location, explain the dish and relevant Korean dining context, and give me a polite ordering question. Say what is unknown.",
                   "photo_id": None, "dataset_mode": "real_place", "response_language": "en",
                   "location": {"lat": 37.5790, "lng": 126.9730, "origin": "selected"},
                   "radius_m": 1000, "confirmed_food_id": "samgyetang", "confirmed_shop_id": None}
        created = client.post("/api/requests", json=request)
        created.raise_for_status()
        job = created.json()
        started = time.monotonic()
        while time.monotonic() - started < 60:
            response = client.get(job["poll_url"])
            response.raise_for_status()
            state = response.json()
            if state["status"] in {"completed", "failed", "superseded"}:
                break
            time.sleep(1)
        else:
            raise SystemExit("runtime_roundtrip_timeout")
        result = state.get("result") or {}
        evidence = {"check": "real_product_roundtrip", "request_id": job["request_id"],
                    "status": state["status"], "error_code": state.get("error_code"),
                    "result_status": result.get("status"), "places": len(result.get("places", [])),
                    "menus": len(result.get("menus", [])), "evidence": len(result.get("evidence", [])),
                    "elapsed_seconds": round(time.monotonic() - started, 3), "downloads": {}}
        if state["status"] == "completed":
            for fmt in ("json", "html", "md"):
                download = client.get("/api/results/" + job["request_id"] + "/download", params={"format": fmt})
                evidence["downloads"][fmt] = {"status": download.status_code, "bytes": len(download.content),
                    "sha256": hashlib.sha256(download.content).hexdigest()}
        print(json.dumps(evidence), flush=True)
        if state["status"] != "completed" or any(v["status"] != 200 for v in evidence["downloads"].values()):
            raise SystemExit(1)

if __name__ == "__main__":
    main()
