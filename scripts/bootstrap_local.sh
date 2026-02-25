#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log() { echo "[bootstrap] $*"; }

check_python() {
    if ! command -v python3 &>/dev/null; then
        echo "ERROR: python3 not found. Install Python 3.11+" >&2
        exit 1
    fi
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    log "Python version: $PYTHON_VERSION"
}

create_venv() {
    if [ ! -d ".venv" ]; then
        log "Creating virtual environment at .venv"
        python3 -m venv .venv
    fi
}

activate_venv() {
    log "Activating virtual environment"
    source .venv/bin/activate
}

install_deps() {
    log "Installing pip (upgrade)"
    pip install --quiet --upgrade pip

    log "Installing packages/common"
    pip install --quiet -e packages/common

    log "Installing packages/eval"
    pip install --quiet -e packages/eval

    log "Installing services/api"
    pip install --quiet -e services/api 2>/dev/null || pip install --quiet -r services/api/requirements.txt

    log "Installing services/worker"
    pip install --quiet -r services/worker/requirements.txt

    log "Installing services/gateway"
    pip install --quiet -r services/gateway/requirements.txt

    log "Installing dev tools"
    pip install --quiet pytest pytest-asyncio pytest-cov ruff mypy alembic
}

setup_env() {
    if [ ! -f ".env" ]; then
        log "Creating .env from .env.example"
        cp .env.example .env
        log "IMPORTANT: Edit .env and fill in real values before running services"
    else
        log ".env already exists, skipping"
    fi
}

wait_for_postgres() {
    log "Waiting for Postgres to be ready..."
    local max_attempts=30
    local attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if docker compose -f docker-compose.dev.yml exec -T postgres pg_isready -U civicproof &>/dev/null; then
            log "Postgres is ready"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    echo "ERROR: Postgres did not become ready in time" >&2
    exit 1
}

run_migrations() {
    log "Running database migrations"
    export DATABASE_URL="${DATABASE_URL:-postgresql://civicproof:changeme@localhost:5432/civicproof}"
    cd packages/common
    alembic upgrade head
    cd "$ROOT"
    log "Migrations complete"
}

seed_data() {
    log "Seeding initial data"
    bash scripts/seed_data.sh
}

main() {
    log "Starting CivicProof local bootstrap"

    check_python
    create_venv
    activate_venv
    install_deps
    setup_env

    if command -v docker &>/dev/null && docker compose -f docker-compose.dev.yml ps &>/dev/null; then
        wait_for_postgres
        run_migrations
        seed_data
    else
        log "Docker stack not running — skipping migrations and seed"
        log "Run 'make dev-up' then 'make migrate' and 'make seed' manually"
    fi

    log "Bootstrap complete. Run 'source .venv/bin/activate' to activate the environment."
}

main "$@"
