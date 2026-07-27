<#
.SYNOPSIS
    Puesta en marcha en un solo paso de la infraestructura local de Postgres para DAG_DECISION (Windows).

.DESCRIPTION
    Prepara todo lo necesario para ejecutar la base de datos local del proyecto:
      1. Comprueba que Docker Desktop esta instalado y que su daemon esta en marcha (lo arranca si hace falta).
      2. Comprueba que Python esta instalado.
      3. Crea un entorno virtual (.venv) e instala requirements.txt.
      4. Crea .env a partir de .env.example si todavia no existe (nunca sobreescribe un .env existente).
      5. Levanta el contenedor de Postgres via docker compose y espera a que este healthy.
      6. Aplica las migraciones de Alembic (esquema de negocio).
      7. Prepara las tablas del checkpointer de Postgres para LangGraph.
      8. Ejecuta la prueba de humo de conexion.

    Seguro de volver a ejecutar: cada paso es idempotente.

.NOTES
    Ejecutar desde cualquier ubicacion; el script resuelve las rutas relativas a su propia ubicacion.
#>

$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

function Write-Step($message) {
    Write-Host ""
    Write-Host "==> $message" -ForegroundColor Cyan
}

function Write-Ok($message) {
    Write-Host "    OK: $message" -ForegroundColor Green
}

function Write-Fail($message) {
    Write-Host "    ERROR: $message" -ForegroundColor Red
}


# 1. Docker instalado?
Write-Step "Comprobando Docker"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Fail "Docker no esta instalado o no esta en el PATH."
    Write-Host "    Instala Docker Desktop desde https://www.docker.com/products/docker-desktop/ y vuelve a ejecutar este script."
    Start-Process "https://www.docker.com/products/docker-desktop/"
    exit 1
}
Write-Ok "Docker CLI encontrado ($(docker --version))"

# 2. Daemon de Docker en marcha? Arranca Docker Desktop si no lo esta, y espera.
docker info > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "    El daemon de Docker no responde, intentando arrancar Docker Desktop..."
    $dockerDesktopExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerDesktopExe) {
        Start-Process $dockerDesktopExe
    } else {
        Write-Fail "No se encontro Docker Desktop en la ruta por defecto. Arrancalo manualmente y vuelve a ejecutar el script."
        exit 1
    }

    $ready = $false
    for ($i = 0; $i -lt 24; $i++) {
        Start-Sleep -Seconds 5
        docker info > $null 2>&1
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    }
    if (-not $ready) {
        Write-Fail "Docker Desktop no arranco a tiempo (2 min). Arrancalo manualmente y vuelve a ejecutar el script."
        exit 1
    }
}
Write-Ok "Docker daemon activo"

# 3. Python instalado?
Write-Step "Comprobando Python"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Fail "Python no esta instalado o no esta en el PATH. Instala Python 3.11+ desde https://www.python.org/downloads/"
    exit 1
}
Write-Ok "Python encontrado ($(python --version))"

# 4. Entorno virtual + dependencias
Write-Step "Preparando entorno virtual (.venv) y dependencias"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "No se pudo crear el entorno virtual."
        exit 1
    }
    Write-Ok "Entorno virtual creado"
} else {
    Write-Ok "Entorno virtual ya existia"
}
.venv\Scripts\python -m pip install --upgrade pip | Out-Null
.venv\Scripts\python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Fallo instalando dependencias de requirements.txt."
    exit 1
}
Write-Ok "Dependencias instaladas"

# 5. Archivo .env
Write-Step "Preparando archivo .env"
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Ok ".env creado a partir de .env.example (revisa/ajusta usuario y password si lo necesitas)"
} else {
    Write-Ok ".env ya existia, no se ha modificado"
}

# 6. Levanta el contenedor de Postgres y espera a que este healthy
Write-Step "Levantando Postgres (docker compose up -d)"
docker compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Fail "No se pudo levantar el contenedor. Si el error menciona un puerto ya en uso, cambia POSTGRES_PORT en .env y reintenta."
    exit 1
}

$healthy = $false
for ($i = 0; $i -lt 24; $i++) {
    $status = docker inspect --format="{{.State.Health.Status}}" dag_decision_postgres 2>$null
    if ($status -eq "healthy") { $healthy = $true; break }
    Start-Sleep -Seconds 5
}
if (-not $healthy) {
    Write-Fail "El contenedor de Postgres no llego a estar healthy a tiempo. Revisa 'docker logs dag_decision_postgres'."
    exit 1
}
Write-Ok "Contenedor Postgres healthy"

# 7. Migraciones de Alembic
Write-Step "Aplicando migraciones (esquema de negocio)"
.venv\Scripts\python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Fallo aplicando las migraciones de Alembic."
    exit 1
}
Write-Ok "Migraciones aplicadas"

# 8. Tablas de checkpoint de LangGraph
Write-Step "Preparando tablas de checkpoint de LangGraph"
.venv\Scripts\python src\db\checkpointer.py
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Fallo preparando las tablas de checkpoint de LangGraph."
    exit 1
}
Write-Ok "Checkpointer listo"

# 9. Prueba de humo
Write-Step "Verificando conexion y listado de tablas"
.venv\Scripts\python scripts\check_db_connection.py

Write-Host ""
Write-Host "Todo listo. La base de datos local esta operativa." -ForegroundColor Green
