<#
.SYNOPSIS
Hidden, detached WSL broker/tunnel launcher. Default Status is read-only.
.DESCRIPTION
Prepare only: do not run Start/Stop until root's explicit GO after 07 QA.
Latest root handoff: broker PTY 55926 / Linux PID 1789203; tunnel PTY 50918.
PTY numbers are NOT OS PIDs. These existing processes are never
adopted or stopped. Root handles any legacy handoff after saving session cards.
Cloudflared, GPU, OpenShell and SSH credentials/configuration are untouched.
No install, retry loop, automatic restart or secret command-line arguments.

Root handoff (use the existing WSL distribution, not a newly installed one):
  .\infra\local-demo.ps1 -Action Status -Distro <existing-distro>
  # Only once legacy ports are released by root and 07 QA GO is given:
  .\infra\local-demo.ps1 -Action Start -Distro <existing-distro> -RootGo
  .\infra\local-demo.ps1 -Action Status -Distro <existing-distro>
  # Keep the existing tunnel: root releases only broker port after GO, then:
  .\infra\local-demo.ps1 -Action Start -Component Broker -Distro <existing-distro> -RootGo
  # Choose All OR Broker above; do not run both starts.
  # After presentation, only this launcher's matching processes:
  .\infra\local-demo.ps1 -Action Stop -Distro <existing-distro> -RootGo

Broker start requires the EXISTING venv, web/dist and .env with WORKER_TOKEN.
Tunnel start requires approved GPU_SSH_ALIAS set privately in the invoking
process environment; Broker-only start does not need this alias.
Existing SSH keys/known_hosts/config are used in place, never copied.
The tunnel script reads only GPU_SSH_ALIAS; keep its value in private local
environment/SSH config, never in this helper, documentation or commits.
Broker configuration must already match the root-owned runtime (.env or
explicit existing environment). Broker handoff WILL reset in-memory sessions;
save session cards first. Broker GUIDE_BIND is the confirmed 0.0.0.0:8000
runtime for OpenShell Docker host access; SSH tunnel binding stays unchanged.
Runtime metadata/logs live under ignored .runtime/local-demo; do not publish.
Detached process startup is NOT health, GPU, policy or product QA evidence.
Root must verify actual service/worker/HTTPS after GO. Machine sleep, WSL
shutdown and logout are not covered. Persistence across Codex exit is UNVERIFIED;
root decides and validates the final lifecycle handoff after 07 QA GO.
#>
[CmdletBinding()]
param(
    [ValidateSet('Status','Start','Stop')][string]$Action = 'Status',
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9_.-]+$')][string]$Distro,
    [ValidateSet('All','Broker','Tunnel')][string]$Component = 'All',
    [switch]$RootGo
)
$ErrorActionPreference = 'Stop'
if ($Action -ne 'Status' -and !$RootGo) { throw 'Root GO after 07 QA is required; nothing changed.' }
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (!(Test-Path -LiteralPath (Join-Path $repo 'service\__main__.py')) -or
    !(Test-Path -LiteralPath (Join-Path $repo 'infra\open_model_tunnel.sh'))) {
    throw 'Expected product checkout not found.'
}
if ((Get-Content -LiteralPath (Join-Path $repo '.gitignore')) -notcontains '.runtime/') {
    throw '.runtime/ must already be ignored.'
}
$runtime = [IO.Path]::GetFullPath((Join-Path $repo '.runtime\local-demo'))
if (!$runtime.StartsWith($repo.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Runtime path escaped checkout.'
}
foreach ($part in @('.runtime', '.runtime\local-demo')) {
    $candidate = Join-Path $repo $part
    if ((Test-Path -LiteralPath $candidate) -and
        ((Get-Item -LiteralPath $candidate).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Runtime reparse points are not supported.'
    }
}
$wsl = (Get-Command wsl.exe -ErrorAction Stop).Source
$linuxRepo = (& $wsl --distribution $Distro --exec wslpath -a $repo | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or !$linuxRepo.StartsWith('/')) { throw 'Existing WSL checkout path unavailable.' }
$settings = @{action=$Action.ToLowerInvariant(); component=$Component.ToLowerInvariant(); repo=$linuxRepo}
$settings64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($settings | ConvertTo-Json -Compress)))
$python = @'
import base64, fcntl, hashlib, json, os, signal, subprocess, time
from pathlib import Path

cfg = json.loads(base64.b64decode("__SETTINGS__"))
repo = Path(cfg["repo"]).resolve(strict=True)
runtime = repo / ".runtime" / "local-demo"
for path in (repo / ".runtime", runtime):
    if path.is_symlink():
        raise SystemExit("Runtime symlink refused.")
if not runtime.resolve().is_relative_to(repo):
    raise SystemExit("Runtime path escaped checkout.")
names = ["broker", "tunnel"] if cfg["component"] == "all" else [cfg["component"]]
ports = {"broker": 8000, "tunnel": 8001}

def identity(pid):
    try:
        p = Path("/proc") / str(int(pid))
        stat = (p / "stat").read_text()
        fields = stat[stat.rfind(")") + 2:].split()
        if fields[0] == "Z":
            return None
        return {"pid": int(pid), "start_ticks": fields[19],
                "uid": p.stat().st_uid, "exe": os.readlink(p / "exe"),
                "cwd": os.readlink(p / "cwd"),
                "cmd_sha256": hashlib.sha256((p / "cmdline").read_bytes()).hexdigest()}
    except (FileNotFoundError, ProcessLookupError):
        return None

def record(name):
    path = runtime / (name + ".json")
    if not path.exists():
        return None
    if path.is_symlink():
        raise RuntimeError("State symlink refused.")
    data = json.loads(path.read_text())
    if data.get("repo") != str(repo) or data.get("component") != name:
        raise RuntimeError("State ownership mismatch.")
    return data

def owned(name):
    data = record(name)
    if data is None:
        return None
    current = identity(data["identity"]["pid"])
    if current is None:
        return None
    if current != data["identity"] or current["uid"] != os.getuid():
        raise RuntimeError("PID identity mismatch; no signal sent.")
    return current

def listening(port):
    for source in ("/proc/net/tcp", "/proc/net/tcp6"):
        for line in Path(source).read_text().splitlines()[1:]:
            columns = line.split()
            if columns[3] == "0A" and int(columns[1].split(":")[-1], 16) == port:
                return True
    return False

def status():
    for name in names:
        current = owned(name)
        print(json.dumps({"component": name, "owned_running": current is not None,
                          "pid": current["pid"] if current else None,
                          "port_listening": listening(ports[name]),
                          "runtime_verified": False}))

def preflight(name):
    if owned(name):
        raise RuntimeError("Owned process already running; no duplicate launch.")
    if listening(ports[name]):
        raise RuntimeError("Port occupied; existing process left untouched.")
    if name == "broker":
        executable = Path.home() / ".venvs" / "hangul-broker" / "bin" / "python"
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise RuntimeError("Existing broker venv missing; no installation attempted.")
        if not (repo / "web/dist/index.html").is_file() or not (repo / ".env").is_file():
            raise RuntimeError("Existing web build and .env required.")
        # Validate privately, before service.__main__ could create/replace a token.
        check = "from dotenv import dotenv_values; import sys; sys.exit(0 if dotenv_values('.env').get('WORKER_TOKEN') else 2)"
        completed = subprocess.run([str(executable), "-c", check], cwd=repo,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if completed.returncode:
            raise RuntimeError("Existing broker token/dependency check failed; no configuration changed.")
        return [str(executable), "-m", "service"]
    if not os.environ.get("GPU_SSH_ALIAS"):
        raise RuntimeError("Set existing approved GPU_SSH_ALIAS privately; no credentials copied.")
    return ["/bin/bash", str(repo / "infra/open_model_tunnel.sh")]

def start():
    commands = {name: preflight(name) for name in names}  # Check all before starting any.
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in names:
        # Recheck to reduce concurrent double-start risk; underlying port bind also enforces exclusion.
        preflight(name)
        stamp = str(time.time_ns())
        log_path = runtime / (name + "-" + stamp + ".log")
        child_env = os.environ.copy()
        if name == "broker":
            # WSLENV can forward unset Windows values as empty strings. Let
            # service load existing .env values instead of masking them.
            for key in ("GUIDE_ALLOWED_ORIGINS", "GUIDE_COOKIE_SECURE"):
                if not child_env.get(key, "").strip():
                    child_env.pop(key, None)
            # Match confirmed root runtime for OpenShell Docker host access.
            child_env["GUIDE_BIND"] = "0.0.0.0"
            child_env["GUIDE_PORT"] = "8000"
        with log_path.open("xb") as log:
            child = subprocess.Popen(commands[name], cwd=repo, env=child_env,
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                     start_new_session=True, close_fds=True)
        time.sleep(0.5)
        if child.poll() is not None:
            raise RuntimeError("Child exited; inspect private runtime log. Other started components retained.")
        current = identity(child.pid)
        if current is None:
            raise RuntimeError("Child identity unavailable; inspect runtime before retrying.")
        data = {"repo": str(repo), "component": name, "identity": current,
                "log_file": log_path.name, "runtime_verified": False}
        temporary = runtime / (name + "-" + stamp + ".tmp")
        temporary.write_text(json.dumps(data), encoding="utf-8")
        temporary.replace(runtime / (name + ".json"))
    status()

def stop():
    targets = {name: owned(name) for name in names}  # Validate all identities before signaling.
    for name, target in targets.items():
        if target is None:
            continue
        if owned(name) != target:
            raise RuntimeError("PID changed; refusing signal.")
        os.kill(target["pid"], signal.SIGTERM)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and any(owned(name) for name in names):
        time.sleep(0.2)
    status()  # No SIGKILL, process-tree kill, port-owner kill, cleanup or WSL shutdown.

try:
    lock = None
    if cfg["action"] != "status":
        runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_path = runtime / "control.lock"
        if lock_path.is_symlink():
            raise RuntimeError("Lock symlink refused.")
        lock = lock_path.open("a")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    {"status": status, "start": start, "stop": stop}[cfg["action"]]()
except Exception as error:
    # No raw command arguments, environment, SSH alias, or remote error body.
    print(json.dumps({"status": "blocked", "error_type": type(error).__name__,
                      "detail": str(error) if isinstance(error, RuntimeError) else "Local control failed; inspect private state."}))
    raise SystemExit(1)
'@
$python = $python.Replace('__SETTINGS__', $settings64)
$payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($python))
$entry = "import base64;exec(base64.b64decode('$payload'))"
$previousWslEnv = [Environment]::GetEnvironmentVariable('WSLENV', 'Process')
try {
    # Forward existing process environment by NAME only. Never serialize secret values.
    $forwardNames = @('GPU_SSH_ALIAS/u','GUIDE_ALLOWED_ORIGINS/u','GUIDE_COOKIE_SECURE/u')
    $forward = @($previousWslEnv -split ':' | Where-Object { $_ }) + $forwardNames
    [Environment]::SetEnvironmentVariable('WSLENV', (($forward | Select-Object -Unique) -join ':'), 'Process')
    if ($Action -eq 'Start') {
        $null = New-Item -ItemType Directory -Path $runtime -Force
        $receipt = Join-Path $runtime ('launch-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff'))
        # Keep the known WSL user context; Linux children detach with setsid and
        # file-backed stdio. This short launcher opens no extra Windows window.
        & $wsl --distribution $Distro --exec python3 -c $entry | Set-Content -LiteralPath ($receipt + '.jsonl') -Encoding UTF8
        if ($LASTEXITCODE -ne 0) { throw 'Start blocked; inspect private local-demo receipt. No automatic rollback.' }
        Write-Output 'Detached launch prepared; run Status, then root runtime QA. Cloudflared untouched.'
    } else {
        & $wsl --distribution $Distro --exec python3 -c $entry
        if ($LASTEXITCODE -ne 0) { throw 'Local demo control refused; existing unowned processes were not adopted.' }
    }
} finally {
    [Environment]::SetEnvironmentVariable('WSLENV', $previousWslEnv, 'Process')
}
