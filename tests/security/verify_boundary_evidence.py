"""Host-side verdict joins sandbox observations, independent receivers and enforcement logs."""
import argparse
import json
from pathlib import Path

def verify(root):
    rows = [json.loads(line) for line in (root / "boundary-matrix-01.log").read_text().splitlines()
            if line.startswith("{")]
    by_check = {r["check"]: r for r in rows if r.get("check")}
    fs = by_check["filesystem_matrix"]
    allowed = json.loads((root / "receiver-8012-counts.json").read_text())
    forbidden = json.loads((root / "receiver-8013-counts.json").read_text())
    dac = json.loads((root / "dac-control-01.json").read_text())
    logs = (root / "boundary-matrix-01-runtime.log").read_text()
    checks = {
        "filesystem_denials": fs["write_denied"] and fs["delete_denied"] and fs["outside_read_denied"],
        "fixture_unchanged": fs["before_sha256"] == fs["after_sha256"],
        "ordinary_permissions_allow": fs["uid"] == 1000 and fs["fixture_mode"] == "0o666" and fs["fixture_parent_mode"] == "0o777",
        "read_control": dac["uid"] == fs["uid"] and dac["ordinary_container_can_read"] and dac["outside_fixture_mode"] == "0o444",
        "allowed_health": by_check["allowed_health"].get("http_status") == 200,
        "reservation_rejected": by_check["denied_reservation"].get("http_status") == 403,
        "destination_transport_denied": by_check["denied_destination"].get("error_type") in {"ConnectError", "ProxyError", "RemoteProtocolError"},
        "allowed_receiver_count": allowed == {"GET_health": 1, "POST_health": 0, "POST_reservations": 0},
        "forbidden_receiver_count": forbidden == {"GET_health": 0, "POST_health": 0, "POST_reservations": 0},
        "reservation_enforcement_log": "DENIED POST http://host.openshell.internal:8012/reservations" in logs,
        "destination_enforcement_log": "8013" in logs and "[reason:transparent_tcp_mapping_denied]" in logs,
    }
    return checks

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("evidence_dir", type=Path)
    args = p.parse_args()
    checks = verify(args.evidence_dir)
    print(json.dumps({"check": "boundary_combined_verdict", "verdict": "PASS" if all(checks.values()) else "FAIL", "checks": checks}))
    raise SystemExit(0 if all(checks.values()) else 1)
