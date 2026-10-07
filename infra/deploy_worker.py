"""One bounded sequential worker handoff; run only on root's explicit signal.
Usage: WSL venv python infra/deploy_worker.py --from-worker hangul-worker-04 --to-worker hangul-worker-05 --core-sha SHA --contract-sha SHA --qa-idle
No GPU/tunnel/broker changes, model generation, resource deletion or git operations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OLD, NEW = None, None
MODEL = "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot():
    paths = [p for folder in ("agent", "data", "shared") for p in (ROOT / folder).rglob("*")
             if p.is_file() and "__pycache__" not in p.parts
             and not p.name.startswith(".env") and p.suffix not in {".pem", ".key", ".pyc"}]
    paths += [ROOT / p for p in ("infra/Dockerfile.worker", "infra/Dockerfile.worker.dockerignore",
              "infra/requirements-worker.txt", "requirements-lock.txt", "infra/launch_worker.py", "infra/render_policy.py",
              "tests/security/runtime_probe.py")]
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths)}


def run(args, timeout=30, log=None, env=None):
    completed = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)
    if log:
        log.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    if completed.returncode:
        raise RuntimeError(f"{Path(args[0]).name}: exit {completed.returncode}; see local evidence")
    return completed.stdout


def containers(all_states=False):
    args = ["docker", "ps", "--format", "{{.Names}}"]
    if all_states:
        args.append("-a")
    return [n for n in run(args).splitlines()
            if n.startswith("openshell-default--hangul-worker-") and not n.endswith("-supervisor")]


def http_json(url):
    # Read-only probes bypass shell proxies; no model generation.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=5) as response:
        return json.load(response)


def check(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def main():
    global OLD, NEW
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-worker", required=True)
    parser.add_argument("--to-worker", required=True)
    parser.add_argument("--reference-policy", type=Path,
                        default=ROOT / "docs/runtime/evidence/worker-04-effective-policy.json")
    parser.add_argument("--core-sha", required=True)
    parser.add_argument("--contract-sha", required=True)
    parser.add_argument("--qa-idle", action="store_true",
                        help="Root confirms product requests are paused and no job is active")
    args = parser.parse_args()
    if not args.qa_idle or not all(re.fullmatch(r"[a-fA-F0-9]{64}", x) for x in (args.core_sha, args.contract_sha)):
        parser.error("Root's --qa-idle and two exact SHA256 values are required")
    names = (args.from_worker, args.to_worker)
    if not all(re.fullmatch(r"hangul-worker-[0-9]{2}", n) for n in names):
        parser.error("Only explicit hangul-worker-NN names are allowed")
    if int(args.to_worker[-2:]) != int(args.from_worker[-2:]) + 1:
        parser.error("The target must be the next sequential worker number")
    OLD, NEW = names
    reference_path = args.reference_policy.resolve()
    if not reference_path.is_relative_to((ROOT / "docs/runtime/evidence").resolve()):
        parser.error("Reference policy must be in docs/runtime/evidence")
    os.chdir(ROOT)
    evidence = ROOT / "infra/evidence-local" / (NEW + "-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    evidence.mkdir(parents=True, exist_ok=False)
    state = {"stage": "preflight", "old_worker": OLD, "new_worker": NEW, "old_stopped": False, "new_launched": False}
    try:
        check(sha(ROOT / "agent/core.py") == args.core_sha.lower(), "core SHA mismatch")
        check(sha(ROOT / "shared/api-contract.md") == args.contract_sha.lower(), "contract SHA mismatch")
        check((ROOT / ".env").is_file(), "local .env missing")
        check(not (ROOT / "infra/generated" / NEW).exists(), "target worker already attempted; root review required")
        current = containers()
        check(len(current) == 1 and current[0].startswith("openshell-default--" + OLD + "-"), "expected only the specified old worker")
        check(not any(n.startswith("openshell-default--" + NEW + "-") for n in containers(True)), "target worker already exists")
        check(http_json("http://127.0.0.1:8000/api/health")["status"] == "ok", "broker unavailable")
        check(MODEL in [r["id"] for r in http_json("http://127.0.0.1:8001/v1/models")["data"]], "existing tunnel/model unavailable")
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        reference_name = reference["sandbox"]
        check(bool(re.fullmatch(r"hangul-worker-[0-9]{2}", reference_name)), "invalid reference worker")
        def policy_for(name):
            return json.loads(json.dumps(reference["policy"]).replace(
                "_" + reference_name[-2:] + "_", "_" + name[-2:] + "_"))
        old_effective = json.loads(run(["openshell", "policy", "get", OLD, "--full", "-o", "json"]))
        check(old_effective["status"] == "effective" and old_effective["policy"] == policy_for(OLD),
              "old worker differs from validated reference allowlist")
        run(["openshell", "status"], log=evidence / "gateway-status.log")
        run([sys.executable, "-m", "unittest", "discover", "-s", "tests/security", "-p", "test_*.py", "-v"],
            timeout=60, log=evidence / "security-tests.log", env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        before = snapshot()
        (evidence / "source-snapshot.json").write_text(json.dumps(before, indent=2) + "\n")
        state["stage"] = "build"
        image = "hangul-worker:" + NEW.removeprefix("hangul-") + "-" + args.core_sha.lower()[:12]
        run(["docker", "build", "--progress=plain", "-f", "infra/Dockerfile.worker", "-t", image, "."],
            timeout=300, log=evidence / "build.log")
        check(snapshot() == before, "source changed during build; old worker preserved")
        image_id = run(["docker", "image", "inspect", "--format", "{{.Id}}", image]).strip()
        probe = ("import agent.worker,hashlib,json,subprocess;from pathlib import Path;"
                 "print(json.dumps({'core_sha256':hashlib.sha256(Path('/app/agent/core.py').read_bytes()).hexdigest(),"
                 "'freeze':subprocess.check_output(['python','-m','pip','freeze'],text=True).splitlines()}))")
        built = json.loads(run(["docker", "run", "--rm", "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--entrypoint", "python",
            image_id, "-c", probe], timeout=30, log=evidence / "image-check.json"))
        check(built["core_sha256"] == args.core_sha.lower(), "built image core SHA mismatch")
        wanted = set((ROOT / "infra/requirements-worker.txt").read_text().splitlines())
        check(set(built["freeze"]) == wanted, "worker dependency mismatch")
        check(wanted <= set((ROOT / "requirements-lock.txt").read_text().splitlines()), "root lock mismatch")
        # Root must keep QA paused throughout this script; the flag is an attestation, not a job query.
        check(snapshot() == before, "source changed before handoff; old worker preserved")
        state["stage"] = "stop_old"
        run(["openshell", "sandbox", "stop", OLD], log=evidence / "stop-old.log")
        state["old_stopped"] = True
        check(not containers(), "product consumer still active; launch withheld")
        state["stage"] = "launch_new"
        env = {**os.environ, "GUIDE_SERVER_URL": "http://host.openshell.internal:8000",
               "NVIDIA_BASE_URL": "http://host.openshell.internal:8001/v1", "NVIDIA_MODEL": MODEL}
        run([sys.executable, "infra/launch_worker.py", "--name", NEW, "--image", image, "--env-file", ".env"],
            timeout=90, log=evidence / "launch-new.log", env=env)
        state["new_launched"] = True
        state["stage"] = "readiness"
        deadline = time.monotonic() + 60
        while True:
            current = containers()
            if len(current) == 1 and current[0].startswith("openshell-default--" + NEW + "-"):
                processes = run(["docker", "top", current[0], "-eo", "pid,args"])
                logs = run(["openshell", "logs", NEW, "-n", "300"])
                worker_process_visible = "python -u -m agent.worker" in processes
                top_lines = processes.strip().splitlines()
                # This OpenShell backend can expose only the Docker ps header.
                # In that case, require actual polling plus the health/events checks below.
                top_header_only = len(top_lines) == 1 and bool(re.fullmatch(r"PID\s+COMMAND", top_lines[0].strip()))
                poll_marker = "ALLOWED GET http://host.openshell.internal:8000/worker/jobs/next"
                if (worker_process_visible or top_header_only) and logs.count(poll_marker) >= 2:
                    break
            if time.monotonic() >= deadline:
                raise TimeoutError("new worker readiness deadline")
            time.sleep(1)
        check(http_json("http://127.0.0.1:8000/api/health")["worker_connected"], "broker reports disconnected")
        events = run(["openshell", "sandbox", "exec", "--name", NEW, "--no-tty", "--no-login-shell",
                      "--", "cat", "/tmp/worker-events.jsonl"])
        check(not any(json.loads(line).get("event") in {"startup_failed", "poll_failed"} for line in events.splitlines() if line.strip()), "worker startup/poll error")
        policy_text = run(["openshell", "policy", "get", NEW, "--full", "-o", "json"])
        policy = json.loads(policy_text)
        check(policy["status"] == "effective" and policy["sandbox"] == NEW, "policy not effective")
        check(policy["policy"] == policy_for(NEW), "new worker differs from validated reference allowlist")
        check(policy["hash"] in logs and "CONFIG:LOADED" in logs, "runtime policy ACK missing")
        runtime_image = run(["docker", "inspect", "--format", "{{.Image}}", current[0]]).strip()
        check(runtime_image == image_id, "running image mismatch")
        (evidence / "effective-policy.json").write_text(policy_text)
        (evidence / "runtime.log").write_text(logs)
        (evidence / "worker-events.jsonl").write_text(events)
        state.update(stage="READY_FOR_REVIEW", worker=NEW, core_sha256=built["core_sha256"],
                     image_id=image_id, policy_hash=policy["hash"], policy_path=str(evidence / "effective-policy.json"),
                     single_consumer=True, same_validated_allowlist=True, reference_policy=str(reference_path), contract_sha256=args.contract_sha.lower(), docker_worker_process_visible=worker_process_visible, docker_top_header_only=top_header_only, model_generation="unverified on new worker; root QA next")
        (evidence / "receipt.json").write_text(json.dumps(state, indent=2) + "\n")
        print(json.dumps(state))
        return 0
    except (AssertionError, RuntimeError, TimeoutError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        state.update(result="BLOCKED", error_type=type(exc).__name__, evidence_dir=str(evidence), reason=str(exc) if isinstance(exc, (AssertionError, RuntimeError, TimeoutError)) else "See stage and local evidence")
        # Never auto-restart old/new consumers; preserve the exact partial state for root.
        (evidence / "failure.json").write_text(json.dumps(state, indent=2) + "\n")
        print(json.dumps(state), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
