"""Launch with gateway-held credentials, never secret values in argv."""
import argparse
import json
import os
import re
from pathlib import Path
import subprocess
import sys
from render_policy import generate

def run(*args, private=False):
    sink = subprocess.DEVNULL if private else None
    subprocess.run(args, check=True, stdout=sink, stderr=sink)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--image", default="hangul-worker:day-of")
    parser.add_argument("--hosted-nvidia", action="store_true")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--env-file", type=Path, help="Local ignored environment file; values are never printed")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,18}", args.name):
        parser.error("Name must use lowercase letters, digits and hyphens, max 19 characters")
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=False)
    required = ["GUIDE_SERVER_URL", "WORKER_TOKEN", "NVIDIA_BASE_URL", "NVIDIA_MODEL"]
    if args.hosted_nvidia:
        required.append("NVIDIA_API_KEY")
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        parser.error("Missing environment variable names: " + ", ".join(missing))
    docs = generate(os.environ["GUIDE_SERVER_URL"], os.environ["NVIDIA_BASE_URL"], args.hosted_nvidia)
    for profile_name in ("guide-profile.json", "nvidia-profile.json"):
        if profile_name in docs:
            docs[profile_name]["id"] += "-" + args.name
    out = Path(__file__).resolve().parent / "generated" / args.name
    out.mkdir(parents=True, exist_ok=True)
    for name, doc in docs.items():
        (out / name).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    for file in sorted(out.glob("*-profile.json")):
        if file.name not in docs:
            continue
        run("openshell", "profile", "lint", "-f", str(file))
        run("openshell", "profile", "import", "-f", str(file))
    run("openshell", "provider", "create", "--name", args.name + "-guide",
        "--type", "hangul-guide-" + args.name, "--credential", "WORKER_TOKEN", private=True)
    command = ["openshell", "sandbox", "create", "--name", args.name, "--from", args.image,
               "--policy", str(out / "worker-policy.json"), "--no-auto-providers",
               "--provider", args.name + "-guide", "--no-tty"]
    if args.hosted_nvidia:
        run("openshell", "provider", "create", "--name", args.name + "-nvidia",
            "--type", "hangul-nvidia-" + args.name, "--credential", "NVIDIA_API_KEY", private=True)
        command += ["--provider", args.name + "-nvidia"]
    else:
        # Public model served on an explicitly allowed local endpoint: no hosted NVIDIA key.
        command += ["--env", "NVIDIA_ALLOW_UNAUTHENTICATED_SELF_HOSTED=true", "--env", "NVIDIA_ALLOW_HTTP_SELF_HOSTED=true"]
    for key in ("GUIDE_SERVER_URL", "NVIDIA_BASE_URL", "NVIDIA_MODEL"):
        command += ["--env", key + "=" + os.environ[key]]
    command += ["--env", "RUN_CONTEXT=openshell", "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "GUIDE_ALLOW_HTTP_OPENSHELL_GATEWAY=true"]
    if args.probe:
        command += ["--", "sh", "-c", "sleep 12; exec python /app/runtime_probe.py --model"]
    else:
        command += ["--detach", "--", "sh", "-c", "sleep 12; exec python -u -m agent.worker >> /tmp/worker-events.jsonl 2>&1"]
    run(*command)

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print("OpenShell command failed; exit=" + str(exc.returncode), file=sys.stderr)
        sys.exit(exc.returncode)
