#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT/.dev-pids"

log() { echo "[dev-stop] $*"; }

stop_services() {
    if [ ! -f "$PID_FILE" ]; then
        log "No $PID_FILE found — nothing to stop"
        return
    fi

    while IFS='=' read -r name pid; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" && log "stopped $name (pid $pid)"
        else
            log "$name (pid $pid) already stopped"
        fi
    done < "$PID_FILE"

    rm -f "$PID_FILE"
    log "All services stopped"
}

stop_infra() {
    read -r -p "Stop docker-compose infra? [y/N] " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
        docker compose -f "$ROOT/docker-compose.dev.yml" down
        log "Infra stopped"
    else
        log "Infra left running"
    fi
}

stop_services
stop_infra
