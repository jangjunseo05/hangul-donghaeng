"""Controlled runtime denials; never touches real restricted or secret paths."""
import hashlib
import json
import os
from pathlib import Path
import stat
import httpx

fixture = Path("/app/probe/sentinel")
before = fixture.read_bytes()
file_mode = oct(stat.S_IMODE(fixture.stat().st_mode))
parent_mode = oct(stat.S_IMODE(fixture.parent.stat().st_mode))
denied = {}
for action in ("write", "unlink"):
    try:
        if action == "write":
            with fixture.open("ab") as stream:
                stream.write(b"controlled-probe")
        else:
            fixture.unlink()
        denied[action] = False
    except PermissionError:
        denied[action] = True
after = fixture.read_bytes() if fixture.exists() else b""
outside = Path("/probe-denied/sentinel")
outside_mode = oct(stat.S_IMODE(outside.stat().st_mode))
try:
    outside.read_bytes()
    read_denied = False
except PermissionError:
    read_denied = True
print(json.dumps({"check": "filesystem_matrix", "uid": os.getuid(),
    "fixture_mode": file_mode, "fixture_parent_mode": parent_mode,
    "before_sha256": hashlib.sha256(before).hexdigest(),
    "after_sha256": hashlib.sha256(after).hexdigest(),
    "write_denied": denied["write"], "delete_denied": denied["unlink"],
    "outside_fixture_mode": outside_mode, "outside_read_denied": read_denied}), flush=True)
network_outcomes = {}
with httpx.Client(timeout=5, follow_redirects=False) as client:
    for name, method, url in [
        ("allowed_health", "GET", "http://host.openshell.internal:8012/api/health"),
        ("denied_reservation", "POST", "http://host.openshell.internal:8012/reservations"),
        ("denied_destination", "GET", "http://host.openshell.internal:8013/api/health")]:
        try:
            r = client.request(method, url)
            result = {"http_status": r.status_code}
        except httpx.HTTPError as exc:
            result = {"error_type": type(exc).__name__}
        network_outcomes[name] = result
        print(json.dumps({"check": name, **result}), flush=True)
network_ok = (network_outcomes["allowed_health"].get("http_status") == 200
    and network_outcomes["denied_reservation"].get("http_status") == 403
    and network_outcomes["denied_destination"].get("error_type") in {"ConnectError", "ProxyError", "RemoteProtocolError"})
if not (all(denied.values()) and read_denied and before == after and network_ok):
    raise SystemExit(1)

print(json.dumps({"verdict": "INCOMPLETE", "required": "Host verify_boundary_evidence.py must join receiver counts and OpenShell denial logs"}))
raise SystemExit(3)
