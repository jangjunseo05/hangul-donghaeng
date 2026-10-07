"""Generate OpenShell 0.1.2 policy; configuration only, never reads secrets."""
import argparse
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

PYTHON = "/usr/local/bin/python3.11"
WORKER_ROUTES = [("GET", "/worker/jobs/next"), ("GET", "/worker/photos/*"),
                 ("POST", "/worker/search"), ("POST", "/worker/results"), ("POST", "/worker/fail")]

def endpoint(url, *, model=False):
    p = urlsplit(url)
    if p.username or p.password or p.query or p.fragment:
        raise ValueError("URL must not contain credentials, query or fragment")
    if not p.hostname or not re.fullmatch(r"[a-zA-Z0-9.-]+", p.hostname):
        raise ValueError("Use one exact hostname; wildcards are forbidden")
    if p.scheme != "https" and not (p.scheme == "http" and p.hostname == "host.openshell.internal"):
        raise ValueError("HTTPS required except explicit gateway-host local development")
    try:
        addr = ipaddress.ip_address(p.hostname)
    except ValueError:
        addr = None
    if p.hostname == "localhost" or (addr and (addr.is_loopback or addr.is_link_local or addr.is_unspecified)):
        raise ValueError("Use host.openshell.internal for the gateway host")
    expected = "/v1" if model else ""
    if p.path.rstrip("/") != expected:
        raise ValueError("Server URL must be origin only; model URL must end in /v1")
    return {"host": p.hostname, "port": p.port or (443 if p.scheme == "https" else 80),
            "protocol": "rest", "enforcement": "enforce"}

def rules(pairs):
    return [{"allow": {"method": method, "path": path}} for method, path in pairs]

def profile(profile_id, env_key, ep, pairs, category="data"):
    return {"id": profile_id, "display_name": profile_id,
            "description": "Hangul Donghaeng fixed endpoint access",
            "category": category, "inference_capable": category == "inference",
            "credentials": [{"name": "api_key", "description": "Gateway-held bearer credential",
                             "env_vars": [env_key], "required": True,
                             "auth_style": "bearer", "header_name": "authorization"}],
            "discovery": {"credentials": ["api_key"]},
            "endpoints": [{**ep, "rules": rules(pairs)}], "binaries": [PYTHON]}

def generate(server_url, model_url, hosted=False):
    server = endpoint(server_url)
    model = endpoint(model_url, model=True)
    base = {"version": 1,
            "filesystem_policy": {"include_workdir": False,
                                  "read_only": ["/app", "/usr", "/lib", "/lib64", "/etc", "/proc", "/dev/urandom"],
                                  "read_write": ["/tmp", "/dev/null"]},
            "landlock": {"compatibility": "hard_requirement"},
            "process": {"run_as_user": "1000", "run_as_group": "1000"},
            "network_policies": {
                "service_health": {"endpoints": [{**server, "rules": rules([("GET", "/api/health")])}],
                                   "binaries": [{"path": PYTHON}]}}}
    result = {"worker-policy.json": base,
              "guide-profile.json": profile("hangul-guide", "WORKER_TOKEN",
                                            {**server, "path": "/worker/**"}, WORKER_ROUTES)}
    if hosted:
        if model["host"] != "integrate.api.nvidia.com" or model["port"] != 443:
            raise ValueError("Hosted NVIDIA credential is bound to its native endpoint")
        result["nvidia-profile.json"] = profile("hangul-nvidia", "NVIDIA_API_KEY",
            {**model, "path": "/v1/chat/completions"}, [("POST", "/v1/chat/completions")], "inference")
    else:
        base["network_policies"]["local_model"] = {
            "endpoints": [{**model, "rules": rules([("GET", "/v1/models"), ("POST", "/v1/chat/completions")])}],
            "binaries": [{"path": PYTHON}]}
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--server-url", required=True)
    p.add_argument("--model-url", required=True)
    p.add_argument("--hosted-nvidia", action="store_true")
    p.add_argument("--out", default="infra/generated")
    args = p.parse_args()
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    for name, doc in generate(args.server_url, args.model_url, args.hosted_nvidia).items():
        (output / name).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print("Generated configuration; runtime verification remains required.")

if __name__ == "__main__":
    main()
