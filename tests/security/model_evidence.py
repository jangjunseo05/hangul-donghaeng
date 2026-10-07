"""A tiny real NVIDIA request; prints metadata only, never body or credentials."""
import json
import os
import time
import httpx

model = os.environ["NVIDIA_MODEL"]
request = {"model": model, "messages": [{"role": "system", "content": "/no_think"},
            {"role": "user", "content": "Reply READY only."}], "max_tokens": 16, "temperature": 0}
started = time.monotonic()
with httpx.Client(timeout=30, follow_redirects=False) as client:
    response = client.post(os.environ["NVIDIA_BASE_URL"] + "/chat/completions", json=request)
elapsed = time.monotonic() - started
metadata = {"check": "real_nvidia_response_metadata", "request": request,
            "http_status": response.status_code, "elapsed_seconds": round(elapsed, 3)}
if response.is_success:
    data = response.json()
    choice = data["choices"][0]
    metadata.update({"actual_model": data.get("model"), "finish_reason": choice.get("finish_reason"),
                     "usage": data.get("usage"), "response_contains_text": bool(choice.get("message", {}).get("content"))})
print(json.dumps(metadata), flush=True)
if not response.is_success:
    raise SystemExit(1)
