param(
    [string]$HostName = "minipc",
    [string]$RemoteDir = "/home/cj/beatbridge-sync",
    [string]$RepoUrl = "https://github.com/SageTheThird/SpotiTube-Library-Sync.git",
    [switch]$SyncRuntimeData
)

$ErrorActionPreference = "Stop"
$ssh = "C:\Windows\System32\OpenSSH\ssh.exe"
$scp = "C:\Windows\System32\OpenSSH\scp.exe"

& $ssh $HostName "set -e; if [ ! -d '$RemoteDir/.git' ]; then git clone '$RepoUrl' '$RemoteDir'; else git -C '$RemoteDir' fetch origin main && git -C '$RemoteDir' reset --hard origin/main; fi; mkdir -p '$RemoteDir/data/auth' '$RemoteDir/data/cache' '$RemoteDir/data/plans' '$RemoteDir/data/sync' '$RemoteDir/data/exports' '$RemoteDir/data/logs'"

if ($SyncRuntimeData) {
    & $scp ".env" "${HostName}:$RemoteDir/.env"
    & $scp -r "data/auth" "${HostName}:$RemoteDir/data/"
    & $scp -r "data/cache" "${HostName}:$RemoteDir/data/"
    & $scp -r "data/plans" "${HostName}:$RemoteDir/data/"
    & $scp -r "data/sync" "${HostName}:$RemoteDir/data/"
    & $scp -r "data/exports" "${HostName}:$RemoteDir/data/"
}

& $ssh $HostName "set -e; cd '$RemoteDir'; chmod 700 data/auth 2>/dev/null || true; chmod +x scripts/*.sh; docker compose build beatbridge; python3 - <<'PY'
from pathlib import Path
required = [
    Path('.env'),
    Path('data/auth/secrets.json'),
    Path('data/auth/token.json'),
    Path('data/auth/spotify_cache'),
]
missing = [str(path) for path in required if not path.exists()]
if missing:
    print('Missing runtime files: ' + ', '.join(missing))
    raise SystemExit(1)
print('Runtime files present.')
PY"

Write-Output "Deployment files are ready at $HostName`:$RemoteDir"
