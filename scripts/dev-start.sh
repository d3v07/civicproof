#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PID_FILE="$ROOT/.dev-pids"
LOG_DIR="$ROOT/.dev-logs"

log()  { echo "[dev-start] $*"; }
ok()   { echo "[dev-start] ✓ $*"; }
err()  { echo "[dev-start] ERROR: $*" >&2; exit 1; }

# ── prereqs ───────────────────────────────────────────────────────────────────

check_prereqs() {
    command -v docker  &>/dev/null || err "docker not found"
    command -v python3.12 &>/dev/null || err "python3.12 not found (required)"
    [ -f "$ROOT/.env" ] || err ".env not found — copy .env.example and fill in values"
    ok "prereqs"
}

# ── infra (docker) ────────────────────────────────────────────────────────────

start_infra() {
    log "Starting docker-compose (postgres, redis, minio, opensearch)..."
    docker compose -f docker-compose.dev.yml up -d
    ok "infra containers started"

    log "Waiting for Postgres..."
    local attempts=0
    until docker compose -f docker-compose.dev.yml exec -T postgres \
          pg_isready -U civicproof &>/dev/null; do
        attempts=$((attempts + 1))
        [ $attempts -ge 30 ] && err "Postgres never became ready"
        sleep 2
    done
    ok "postgres ready"
}

# ── python env ────────────────────────────────────────────────────────────────

setup_python() {
    if [ ! -d "$ROOT/.venv" ]; then
        log "Creating .venv with python3.12..."
        python3.12 -m venv "$ROOT/.venv"
    fi
    # shellcheck disable=SC1091
    source "$ROOT/.venv/bin/activate"

    log "Installing/syncing dependencies..."
    pip install --quiet --upgrade pip
    pip install --quiet -e packages/common -e packages/eval
    pip install --quiet -r services/api/requirements.txt \
                        -r services/worker/requirements.txt \
                        -r services/gateway/requirements.txt
    pip install --quiet pytest pytest-asyncio pytest-cov ruff mypy alembic httpx
    ok "python deps ready"
}

# ── migrations ────────────────────────────────────────────────────────────────

run_migrations() {
    log "Running alembic migrations..."
    set -a && source "$ROOT/.env" && set +a
    (cd packages/common && alembic upgrade head 2>&1)
    ok "migrations applied"
}

# ── seed ─────────────────────────────────────────────────────────────────────

run_seed() {
    if command -v psql &>/dev/null; then
        log "Seeding data sources..."
        bash scripts/seed_data.sh 2>&1
        ok "seed done"
    else
        log "psql not found — skipping seed (data sources won't appear in Sources page)"
    fi
}

# ── services ─────────────────────────────────────────────────────────────────

start_services() {
    mkdir -p "$LOG_DIR"
    rm -f "$PID_FILE"

    # shellcheck disable=SC1091
    source "$ROOT/.venv/bin/activate"
    set -a && source "$ROOT/.env" && set +a

    log "Starting API (port 8080)..."
    (cd "$ROOT/services/api" && \
     PYTHONPATH="$ROOT/services/api/src" \
     uvicorn src.main:app --host 0.0.0.0 --port 8080 \
     > "$LOG_DIR/api.log" 2>&1) &
    echo "api=$!" >> "$PID_FILE"

    log "Starting Gateway (port 8090)..."
    (cd "$ROOT/services/gateway" && \
     PYTHONPATH="$ROOT/services/gateway/src" \
     uvicorn src.main:app --host 0.0.0.0 --port 8090 \
     > "$LOG_DIR/gateway.log" 2>&1) &
    echo "gateway=$!" >> "$PID_FILE"

    log "Starting Worker..."
    (cd "$ROOT/services/worker" && \
     PYTHONPATH="$ROOT/services/worker/src" \
     python -m src.main \
     > "$LOG_DIR/worker.log" 2>&1) &
    echo "worker=$!" >> "$PID_FILE"

    # wait for API to be up
    local attempts=0
    log "Waiting for API to be ready..."
    until curl -sf http://localhost:8080/health &>/dev/null; do
        attempts=$((attempts + 1))
        [ $attempts -ge 20 ] && {
            echo "API did not start — last log lines:"
            tail -20 "$LOG_DIR/api.log" >&2
            err "API failed to start"
        }
        sleep 2
    done
    ok "API ready at http://localhost:8080"

    log "PIDs saved to $PID_FILE"
}

# ── frontend ─────────────────────────────────────────────────────────────────

start_frontend() {
    if [ ! -d "$ROOT/frontend/node_modules" ]; then
        log "Installing frontend node_modules..."
        (cd "$ROOT/frontend" && npm install --silent)
    fi

    log "Starting Next.js frontend (port 3000)..."
    (cd "$ROOT/frontend" && npm run dev > "$LOG_DIR/frontend.log" 2>&1) &
    echo "frontend=$!" >> "$PID_FILE"

    local attempts=0
    until curl -sf http://localhost:3000 &>/dev/null; do
        attempts=$((attempts + 1))
        [ $attempts -ge 30 ] && {
            echo "Frontend did not start — last log lines:"
            tail -20 "$LOG_DIR/frontend.log" >&2
            err "Frontend failed to start"
        }
        sleep 2
    done
    ok "Frontend ready at http://localhost:3000"
}

# ── main ─────────────────────────────────────────────────────────────────────

main() {
    log "CivicProof dev stack starting..."
    check_prereqs
    start_infra
    setup_python
    run_migrations
    run_seed
    start_services
    start_frontend

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  CivicProof dev stack is running"
    echo ""
    echo "  Frontend  →  http://localhost:3000"
    echo "  API       →  http://localhost:8080"
    echo "  Gateway   →  http://localhost:8090"
    echo "  MinIO UI  →  http://localhost:9001"
    echo ""
    echo "  Logs in $LOG_DIR/"
    echo "  Stop with: bash scripts/dev-stop.sh"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

main "$@"
