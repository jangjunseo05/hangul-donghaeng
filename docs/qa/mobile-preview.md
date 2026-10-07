# BUILD-HTTPS-01: real-phone HTTPS preview

Status: READY_FOR_REVIEW for HTTPS transport, static delivery and unauthenticated access checks. Product execution and phone voice remain unverified.

- Checked: 2026-10-07T13:33:34.4532224+09:00
- Public URL: https://arrive-relationship-halifax-triple.trycloudflare.com
- Origin: http://127.0.0.1:8000 (existing Windows forwarding to the WSL broker).
- Tunnel PID: 45096; hidden background process, kept running.
- cloudflared: cloudflared version 2026.10.0 (built 2026-10-05T08:39 UTC)
- Binary SHA256: 86aee4017b26625cee8484c113558f48effa4cd47f7aa05fcf425604e5d2b23c (matched official GitHub release asset digest before execution).
- Download: https://github.com/cloudflare/cloudflared/releases/download/2026.10.0/cloudflared-windows-amd64.exe
- All binary, logs and state: ignored `.runtime/mobile-preview/`. No global installation, account, paid resource, firewall or system configuration changes.

## Verification

TLS certificate verification remained enabled. Both local preflight and public HTTPS returned:

| Probe | Expected and observed |
|---|---|
| GET /api/health; GET / | 200 |
| GET /worker/jobs/next | 401 without bearer token |
| GET /worker/photos/mobile-preview-missing?request_id=mobile-preview-missing | 401 without bearer token |
| POST /worker/search, /worker/results, /worker/fail with empty JSON | 401 without bearer token |
| GET /api/requests/mobile-preview-missing | 401 without session |
| GET /api/results/mobile-preview-missing/download?format=json | 401 without session |
| GET /.env; GET /v1/models | 404 |

External HTML SHA256 matched current `web/dist/index.html`. JavaScript asset `/assets/index-fsgBFGsR.js` returned 200. The broker mounts only `web/dist`; its result/download handlers verify session ownership in source. A two-session test against real completed results was not performed. No inference job was created.

Observed health JSON: `{"status":"ok","worker_connected":true,"model_configured":false,"sandbox_verified":false,"catalog_count":1,"version":"0.1.0"}`

Evidence files: `.runtime/mobile-preview/preflight.json`, `external-checks.json`, `public-index.html`, `state.json`, and timestamped tunnel stdout/stderr logs. These are local runtime evidence and must stay ignored. The startup script's empty-log race was corrected; this already-running tunnel was recovered and verified without restarting it. PowerShell parser validation passed. A second fresh tunnel launch was deliberately not performed.

## Root handoff before phone demo

1. Add exactly `https://arrive-relationship-halifax-triple.trycloudflare.com` to GUIDE_ALLOWED_ORIGINS in the actual broker environment, preserving required existing origins.
2. Root applied per-request HTTPS Secure cookies while preserving localhost HTTP development. Public HTTPS POST /api/sessions with the exact Origin returned 200 and a Secure/HttpOnly cookie at 13:35 KST. The configuration and broker restart are complete; phone interaction remains to be tested.
3. In the phone browser, open the URL, create a session, grant microphone permission, and verify secure context, Secure/HttpOnly session cookie, voice capture, submitted request, worker result and downloadable output. These are human acceptance checks, still pending. Health flags above do not prove model/OpenShell execution.
4. Check cross-session result isolation with completed demo results during integration review. Do not expose GPU model ports or distribute worker credentials.

## Lifecycle

Start from product root after local broker is ready:

```powershell
& .\infra\mobile-preview.ps1
```

Stop only this owned tunnel when the demo is finished; leave broker and worker running:

```powershell
& 'C:\Users\USER\Desktop\hangul-donghaeng\infra\mobile-preview.ps1' -Stop
```

The cleanup checks PID, executable path and process start time against state.json before stopping. The current PID is 45096. Restarting creates a new random URL, requiring a new exact-origin setting. The script refuses to launch another tunnel while its recorded process exists. Existing cloudflared configuration or missing official asset digest is a blocker, not a reason to bypass checks. Inspect state.json and logs if startup or external verification fails; failed verification does not automatically terminate runtime.

## Official references

Verified 2026-10-07:

- [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/): temporary random trycloudflare.com URL, no account/domain required; lifetime follows the process; no uptime guarantee; 200 concurrent in-flight requests and no SSE. Current app uses polling.
- [Official cloudflared downloads](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/).
- [Upstream release 2026.10.0](https://github.com/cloudflare/cloudflared/releases/tag/2026.10.0).
- [Release metadata and asset digest](https://api.github.com/repos/cloudflare/cloudflared/releases/tags/2026.10.0).
