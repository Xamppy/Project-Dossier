# Vacía la base Redis configurada en REDIS_URL (.env).
# Uso: .\scripts\flush-redis.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:PYTHONPATH = Join-Path $Root "src"

python -c @"
from dossier.config import load_env
load_env()
from dossier.cache.corporate_dossier_redis import dossier_corporate_redis_health, dossier_redis_shared_client

health = dossier_corporate_redis_health()
if not health.get('enabled'):
    raise SystemExit('Redis no configurado (REDIS_URL vacío o DOSSIER_REDIS_ENABLED=0)')
client = dossier_redis_shared_client()
if client is None:
    raise SystemExit(f'No se pudo conectar a Redis ({health.get(\"target\")})')
before = client.dbsize()
client.flushdb()
after = client.dbsize()
print(f'OK: {health.get(\"target\")} — claves {before} -> {after}')
"@

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
