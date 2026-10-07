"""Separate public-input evaluation sandbox. Never operates on product workers.

Default only prepares an isolated build context. --execute requires a separately
authorized GPU slot. No credentials are read, copied, printed or auto-discovered.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {".txt", ".md", ".json", ".csv", ".tsv"}
MODEL = "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16"


def safe_source(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    if any(part.lower() in {"restricted", "secrets"} for part in path.parts):
        raise ValueError("forbidden_input_path")
    for item in reversed((path, *path.parents)):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("symlink_input_path")
    return path


def stage_inputs(source: Path, destination: Path) -> list[dict]:
    source = safe_source(source)
    if not source.is_dir():
        raise ValueError("missing_input_directory")
    manifest, total = [], 0
    for directory, dirs, files in os.walk(source, followlinks=False):
        for name in dirs:
            safe_source(Path(directory) / name)
        for name in sorted(files):
            path = safe_source(Path(directory) / name)
            if path.suffix.lower() not in EXTENSIONS:
                raise ValueError("unsupported_input_extension")
            info = path.stat()
            if not path.is_file() or info.st_nlink != 1 or info.st_size > 512 * 1024:
                raise ValueError("unsafe_or_oversize_input")
            total += info.st_size
            if total > 1024 * 1024 or len(manifest) >= 64:
                raise ValueError("input_budget_exceeded")
            content = path.read_bytes()
            content.decode("utf-8-sig")
            relative = path.relative_to(source)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            manifest.append({"path": relative.as_posix(), "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)})
    if not manifest:
        raise ValueError("empty_input")
    return sorted(manifest, key=lambda row: row["path"])


def policy_compatible(document: dict) -> bool:
    policy = document.get("policy", document)
    expected = json.loads((ROOT / "policy/challenge-policy.json").read_text(encoding="utf-8"))
    fs = policy.get("filesystem_policy", {})
    # Gateway adds /var/log to its baseline. Permit no other expansion.
    ro = set(fs.get("read_only", []))
    wanted = set(expected["filesystem_policy"]["read_only"])
    network = json.loads(json.dumps(policy.get("network_policies", {})))
    for name, value in network.items():
        if value.get("name") == name:
            value.pop("name")  # OpenShell materializes the map key as a field.
    return (fs.get("include_workdir") is False and wanted <= ro <= wanted | {"/var/log"}
            and set(fs.get("read_write", [])) == set(expected["filesystem_policy"]["read_write"])
            and policy.get("landlock") == expected["landlock"]
            and policy.get("process") == expected["process"]
            and network == expected["network_policies"])


def command(args: list[str], *, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout)


def write_json(path: Path, value: dict | list) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export_outputs(name: str, destination: Path) -> list[dict]:
    # OpenShell download is confined to its /tmp workspace. Read only fixed
    # application-generated answer files through the same enforced exec policy.
    script = '''import base64,json,re
from pathlib import Path
rows=[]
for run in Path('/hackathon/output').iterdir():
 if not re.fullmatch(r'challenge-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}',run.name): continue
 if run.is_symlink() or not run.is_dir(): raise ValueError('unsafe_output')
 for name in ('answer.json','answer.md'):
  p=run/name
  if p.is_symlink() or not p.is_file() or p.stat().st_size>1048576: raise ValueError('unsafe_output')
  rows.append({'path':run.name+'/'+name,'content':base64.b64encode(p.read_bytes()).decode('ascii')})
 if len(rows)>32: raise ValueError('output_budget')
print(json.dumps(rows))'''
    result = command(["openshell", "sandbox", "exec", "--name", name,
                      "--no-login-shell", "--no-tty", "--workdir", "/app", "--timeout", "15",
                      "--", "/usr/local/bin/python3.11", "-c", script], timeout=20)
    manifest = []
    for item in json.loads(result.stdout):
        if not re.fullmatch(r"challenge-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}/answer\.(json|md)", item["path"]):
            raise ValueError("unsafe_output_name")
        content = base64.b64decode(item["content"], validate=True)
        target = destination / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(content)
        manifest.append({"path": item["path"], "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)})
    if not manifest:
        raise ValueError("missing_answers")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="Unique hangul-eval-NN name")
    parser.add_argument("--base-image", required=True, help="Existing local worker image ID; no pull")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--gpu-slot-approved", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"hangul-eval-[0-9]{2}", args.name):
        parser.error("Dedicated hangul-eval-NN name required; product names forbidden")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", args.base_image):
        parser.error("Pinned local image ID required")
    if args.execute and not args.gpu_slot_approved:
        parser.error("Actual model run requires root's exclusive GPU slot")
    if not args.question.strip() or len(args.question) > 2000:
        parser.error("Question must be 1..2000 characters")
    if not (ROOT / "agent/challenge.py").is_file():
        parser.error("pN challenge runner not ready")
    out = ROOT / "infra/generated" / args.name
    out.mkdir(parents=True, exist_ok=False)
    context = out / "context"
    context.mkdir()
    manifest = stage_inputs(args.input_dir, context / "input")
    write_json(out / "input-manifest.json", manifest)
    shutil.copyfile(ROOT / "agent/challenge.py", context / "challenge.py")
    shutil.copyfile(ROOT / "policy/challenge-policy.json", out / "policy.json")
    base_tag = args.name + "-base:pinned"
    image = args.name + ":submission"
    (context / "Dockerfile").write_text(
        f"FROM {base_tag}\nUSER 0:0\nCOPY challenge.py /app/agent/challenge.py\n"
        "COPY input/ /hackathon/input/\n"
        "RUN mkdir -p /hackathon/output && chown 1000:1000 /hackathon/output && "
        "chmod 700 /hackathon/output && chmod -R a-w /hackathon/input\n"
        "USER 1000:1000\nWORKDIR /tmp\nCMD [\"sleep\",\"infinity\"]\n", encoding="utf-8")
    receipt = {"name": args.name, "prepared_at": datetime.now(timezone.utc).isoformat(),
               "base_image_id": args.base_image, "input_files": len(manifest),
               "runner_sha256": hashlib.sha256((context / "challenge.py").read_bytes()).hexdigest(),
               "policy_file_sha256": hashlib.sha256((out / "policy.json").read_bytes()).hexdigest(),
               "execution": "unverified", "model": MODEL, "product_worker_modified": False}
    write_json(out / "receipt.json", receipt)
    if not args.execute:
        print(json.dumps({"prepared": str(out), "execution": "unverified"}))
        return 0
    try:
        command(["docker", "image", "inspect", args.base_image])
        command(["docker", "tag", args.base_image, base_tag])
        build = command(["docker", "build", "--pull=false", "--network=none", "-t", image, str(context)], timeout=120)
        (out / "build.log").write_text(build.stdout + build.stderr, encoding="utf-8")
        receipt["image_id"] = command(["docker", "image", "inspect", "--format", "{{.Id}}", image]).stdout.strip()
        command(["openshell", "sandbox", "create", "--name", args.name, "--from", image,
                 "--policy", str(out / "policy.json"), "--no-auto-providers", "--detach", "--no-tty",
                 "--env", "NVIDIA_BASE_URL=http://host.openshell.internal:8001/v1",
                 "--env", "NVIDIA_MODEL=" + MODEL,
                 "--env", "NVIDIA_ALLOW_UNAUTHENTICATED_SELF_HOSTED=true",
                 "--env", "NVIDIA_ALLOW_HTTP_SELF_HOSTED=true",
                 "--env", "RUN_CONTEXT=openshell", "--", "sleep", "infinity"], timeout=120)
        effective = None
        for _ in range(20):
            data = json.loads(command(["openshell", "policy", "get", args.name, "--full", "-o", "json"]).stdout)
            if data.get("status") == "effective" and policy_compatible(data):
                effective = data
                break
            time.sleep(1)
        if effective is None:
            raise ValueError("effective_policy_not_confirmed")
        write_json(out / "effective-policy.json", effective)
        receipt["effective_policy_hash"] = effective["hash"]
        receipt["policy_verified"] = True
        started = time.monotonic()
        result = subprocess.run(["openshell", "sandbox", "exec", "--name", args.name,
            "--no-login-shell", "--no-tty", "--workdir", "/app", "--timeout", "70",
            "--env", "NVIDIA_BASE_URL=http://host.openshell.internal:8001/v1",
            "--env", "NVIDIA_MODEL=" + MODEL,
            "--env", "NVIDIA_ALLOW_UNAUTHENTICATED_SELF_HOSTED=true",
            "--env", "NVIDIA_ALLOW_HTTP_SELF_HOSTED=true", "--env", "PYTHONDONTWRITEBYTECODE=1", "--",
            "/usr/local/bin/python3.11", "-m", "agent.challenge", "--question", args.question,
            "--input", "/hackathon/input", "--output", "/hackathon/output"],
            capture_output=True, text=True, timeout=85)
        (out / "execution.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        receipt.update(exit_code=result.returncode, elapsed_seconds=round(time.monotonic() - started, 3),
                       execution="completed" if result.returncode == 0 else "failed", semantic_acceptance="unreviewed")
        write_json(out / "receipt.json", receipt)
        if result.returncode == 0:
            receipt["output_files"] = export_outputs(args.name, out / "download")
            receipt["output_export"] = "bounded_exec"
            write_json(out / "receipt.json", receipt)
        print(json.dumps(receipt, ensure_ascii=False))
        return result.returncode
    except (subprocess.SubprocessError, ValueError, OSError) as exc:
        if receipt.get("exit_code") == 0:
            receipt["output_export"] = "failed"
        else:
            receipt["execution"] = "failed"
        receipt["error_type"] = type(exc).__name__
        if isinstance(exc, ValueError) and str(exc) == "effective_policy_not_confirmed":
            receipt["error_code"] = str(exc)
        if isinstance(exc, subprocess.CalledProcessError):
            # Only our fixed Docker/OpenShell setup commands run here, no model bodies.
            (out / "setup-error.log").write_text(exc.stdout + exc.stderr, encoding="utf-8")
        write_json(out / "receipt.json", receipt)
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, "receipt": str(out / "receipt.json")}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
