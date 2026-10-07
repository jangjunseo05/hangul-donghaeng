[CmdletBinding()]
param([switch]$Stop)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$runtime = Join-Path $repo '.runtime\mobile-preview'
$statePath = Join-Path $runtime 'state.json'
$utf8 = [Text.UTF8Encoding]::new($false)
function Save-Json($Value, $Path) { [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 8), $utf8) }
if ($Stop) {
    if (!(Test-Path -LiteralPath $statePath)) { throw 'No owned tunnel state.' }
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $running = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
    if (!$running) { Write-Output 'Tunnel is already stopped.'; return }
    if ($running.Path -ne $state.executable -or $running.StartTime.ToUniversalTime().ToString('o') -ne $state.started_utc) { throw 'PID ownership mismatch; refusing to stop.' }
    Stop-Process -Id $running.Id
    Write-Output 'Owned mobile preview tunnel stopped; broker and worker untouched.'
    return
}
if (!(Test-Path -LiteralPath (Join-Path $repo 'web\dist\index.html'))) { throw 'Build web/dist first.' }
if ((Get-Content -LiteralPath (Join-Path $repo '.gitignore')) -notcontains '.runtime/') { throw '.runtime/ must already be ignored.' }
if (Test-Path -LiteralPath $statePath) {
    $previous = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    if (Get-Process -Id $previous.pid -ErrorAction SilentlyContinue) { throw 'A recorded process is still running; inspect state.json before starting another tunnel.' }
}
foreach ($configuration in @((Join-Path $env:USERPROFILE '.cloudflared\config.yml'), (Join-Path $env:USERPROFILE '.cloudflared\config.yaml'))) {
    if (Test-Path -LiteralPath $configuration) { throw 'Existing cloudflared configuration: quick tunnel not launched; configuration left untouched.' }
}
if ($env:TUNNEL_TOKEN -or $env:TUNNEL_CONFIG) { throw 'Existing tunnel credential/config environment: refusing implicit configuration.' }
$null = New-Item -ItemType Directory -Path $runtime -Force
function Status-Code([string]$Base, [string]$Path, [string]$Method='GET') {
    $arguments = @('--silent','--show-error','--max-time','12','--output','NUL','--write-out','%{http_code}','--request',$Method)
    if ($Base -eq 'http://127.0.0.1:8000') { $arguments += @('--noproxy','*') }
    if ($Method -eq 'POST') { $arguments += @('--header','Content-Type: application/json','--data','{}') }
    $status = & curl.exe @arguments ($Base + $Path)
    if ($LASTEXITCODE -ne 0) { throw "Connection failed for $Method $Path" }
    return [int]$status
}
$checks = @(
    @('GET','/api/health',200), @('GET','/',200),
    @('GET','/worker/jobs/next',401),
    @('GET','/worker/photos/mobile-preview-missing?request_id=mobile-preview-missing',401),
    @('POST','/worker/search',401), @('POST','/worker/results',401), @('POST','/worker/fail',401),
    @('GET','/api/requests/mobile-preview-missing',401),
    @('GET','/api/results/mobile-preview-missing/download?format=json',401),
    @('GET','/.env',404), @('GET','/v1/models',404)
)
$observations = @()
foreach ($check in $checks) {
    $actual = Status-Code 'http://127.0.0.1:8000' $check[1] $check[0]
    $observations += [pscustomobject]@{method=$check[0];path=$check[1];status=$actual;expected=$check[2]}
    if ($actual -ne $check[2]) { throw "Preflight failed: $($check[0]) $($check[1]) = $actual" }
}
Save-Json $observations (Join-Path $runtime 'preflight.json')
$installed = Get-Command cloudflared -ErrorAction SilentlyContinue
$releaseTag = '2026.10.0'
$downloadSource = $null
if ($installed) { $executable = $installed.Source } else {
    if (![Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { throw 'This download lane supports Windows AMD64 only.' }
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/cloudflare/cloudflared/releases/tags/$releaseTag" -Headers @{'User-Agent'='hangul-donghaeng-mobile-preview'} -TimeoutSec 20
    $asset = @($release.assets | Where-Object name -eq 'cloudflared-windows-amd64.exe')[0]
    if (!$asset -or $asset.digest -notmatch '^sha256:[a-fA-F0-9]{64}$') { throw 'Official release SHA256 digest unavailable; refusing unverified download.' }
    $downloadSource = $asset.browser_download_url
    if ($downloadSource -ne "https://github.com/cloudflare/cloudflared/releases/download/$releaseTag/cloudflared-windows-amd64.exe") { throw 'Unexpected release URL.' }
    $executable = Join-Path $runtime 'cloudflared.exe'
    $expected = $asset.digest.Substring(7).ToLowerInvariant()
    if (!(Test-Path -LiteralPath $executable) -or (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
        & curl.exe --fail --location --silent --show-error --max-time 90 --output $executable $downloadSource
        if ($LASTEXITCODE -ne 0) { throw 'Official binary download failed.' }
    }
    if ((Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Binary checksum mismatch; not executing.' }
}
$version = (& $executable --version | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'cloudflared version check failed.' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stderr = Join-Path $runtime "tunnel-$stamp.stderr.log"
$stdout = Join-Path $runtime "tunnel-$stamp.stdout.log"
$tunnel = Start-Process -FilePath $executable -ArgumentList @('tunnel','--no-autoupdate','--url','http://127.0.0.1:8000') -WorkingDirectory $runtime -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$state = [ordered]@{pid=$tunnel.Id; executable=$executable; started_utc=$tunnel.StartTime.ToUniversalTime().ToString('o'); version=$version; binary_sha256=(Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant(); download_source=$downloadSource; origin='http://127.0.0.1:8000'; url=$null; stdout=$stdout; stderr=$stderr; status='starting'; cleanup='& .\infra\mobile-preview.ps1 -Stop'}
Save-Json $state $statePath
$deadline = (Get-Date).AddSeconds(45)
while ((Get-Date) -lt $deadline) {
    $tunnel.Refresh()
    if ($tunnel.HasExited) { throw "Quick tunnel exited. Inspect $stderr; no alternate tunnel is started." }
    if (Test-Path -LiteralPath $stderr) {
        $logText = Get-Content -LiteralPath $stderr -Raw
        $urlMatch = $null
        if (![string]::IsNullOrEmpty($logText)) { $urlMatch = [regex]::Match($logText, 'https://[a-z0-9-]+\.trycloudflare\.com') }
        if ($urlMatch -and $urlMatch.Success) { $state.url = $urlMatch.Value; break }
    }
    Start-Sleep -Milliseconds 500
}
if (!$state.url) { throw "Quick tunnel URL unavailable; inspect $stderr and state.json. Process is not automatically stopped." }
$state.status = 'url-assigned'
Save-Json $state $statePath
Write-Output ("URL=" + $state.url)
Write-Output ("PID=" + $state.pid)
$verified = $false
for ($attempt=0; $attempt -lt 10; $attempt++) {
    try { if ((Status-Code $state.url '/api/health') -eq 200) { $verified=$true; break } } catch {}
    Start-Sleep -Seconds 2
}
if (!$verified) { throw 'Public HTTPS health is not ready; retained tunnel state for review.' }
$publicChecks = @()
foreach ($check in $checks) {
    $actual = Status-Code $state.url $check[1] $check[0]
    $publicChecks += [pscustomobject]@{method=$check[0];path=$check[1];status=$actual;expected=$check[2]}
    if ($actual -ne $check[2]) { Save-Json $publicChecks (Join-Path $runtime 'external-checks.json'); throw "External check failed: $($check[1]) = $actual" }
}
$indexPath = Join-Path $runtime 'public-index.html'
& curl.exe --fail --silent --show-error --max-time 15 --output $indexPath ($state.url + '/')
if ($LASTEXITCODE -ne 0) { throw 'Public index retrieval failed.' }
$localIndex = Join-Path $repo 'web\dist\index.html'
if ((Get-FileHash -LiteralPath $indexPath).Hash -ne (Get-FileHash -LiteralPath $localIndex).Hash) { throw 'Public HTML differs from current web/dist/index.html; build may have changed.' }
$assetMatch = [regex]::Match((Get-Content -LiteralPath $indexPath -Raw), 'src="(/assets/[^" ]+\.js)"')
if (!$assetMatch.Success -or (Status-Code $state.url $assetMatch.Groups[1].Value) -ne 200) { throw 'Frontend JavaScript asset check failed.' }
Save-Json $publicChecks (Join-Path $runtime 'external-checks.json')
$state.status = 'https-health-static-auth-verified'
$state.checked_at = (Get-Date).ToString('o')
$state.static_asset = $assetMatch.Groups[1].Value
$state.mobile_voice = 'human-verification-pending'
$state.root_action = 'Set exact GUIDE_ALLOWED_ORIGINS and GUIDE_COOKIE_SECURE=true in the actual broker environment.'
Save-Json $state $statePath
$state | ConvertTo-Json -Depth 5