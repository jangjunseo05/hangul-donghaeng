"""Run INSIDE the sandbox; controlled fixture only. No credentials/body dumps."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
import httpx

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", action="store_true")
    args = parser.parse_args()
    sentinel = Path("/app/probe/sentinel")
    before = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    denied = {}
    for operation in ("write", "unlink"):
        try:
            if operation == "write":
                with sentinel.open("ab") as stream:
                    stream.write(b"PROBE")
            else:
                sentinel.unlink()
            denied[operation] = False
        except PermissionError:
            denied[operation] = True
    after = hashlib.sha256(sentinel.read_bytes()).hexdigest() if sentinel.exists() else None
    print(json.dumps({"check": "filesystem_fixture", "denied": denied, "unchanged": before == after}))
    if not all(denied.values()) or before != after:
        raise SystemExit(1)
    url = os.environ.get("GUIDE_SERVER_URL")
    if url:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            for method in ("GET", "POST"):
                try:
                    response = client.request(method, url + "/api/health")
                    print(json.dumps({"check": "service_network", "method": method, "status": response.status_code}))
                except httpx.HTTPError as exc:
                    print(json.dumps({"check": "service_network", "method": method, "error_type": type(exc).__name__}))
    if args.model:
        hosted = urlsplit(os.environ["NVIDIA_BASE_URL"]).hostname == "integrate.api.nvidia.com"
        key = os.environ.get("NVIDIA_API_KEY" if hosted else "SELF_HOSTED_API_KEY", "")
        headers = {"Authorization": "Bearer " + key} if key else {}
        payload = {"model": os.environ["NVIDIA_MODEL"], "messages": [{"role": "system", "content": "/no_think"}, {"role": "user", "content": "Reply with READY only."}],
                   "max_tokens": 16, "temperature": 0}
        started = time.monotonic()
        try:
            with httpx.Client(timeout=45, follow_redirects=False) as client:
                response = client.post(os.environ["NVIDIA_BASE_URL"] + "/chat/completions", headers=headers, json=payload)
            valid = response.is_success and bool(response.json().get("choices"))
            print(json.dumps({"check": "real_model", "http_status": response.status_code, "choices_present": valid,
                              "elapsed_seconds": round(time.monotonic() - started, 3)}))
            if not valid:
                raise SystemExit(2)
        except (httpx.HTTPError, ValueError) as exc:
            print(json.dumps({"check": "real_model", "error_type": type(exc).__name__}))
            raise SystemExit(2)
    print("Probe finished; network denial requires matching OpenShell logs and receiver evidence.")

if __name__ == "__main__":
    main()
