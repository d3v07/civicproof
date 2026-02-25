#!/usr/bin/env bash
set -euo pipefail

DB_URL="${DATABASE_URL:-postgresql://civicproof:changeme@localhost:5432/civicproof}"

if ! command -v psql &>/dev/null; then
    echo "ERROR: psql not found. Install postgresql-client." >&2
    exit 1
fi

log() { echo "[seed] $*"; }

PSQL="psql $DB_URL --no-psqlrc --tuples-only --quiet"

seed_data_sources() {
    log "Seeding data_source table"

    $PSQL <<'SQL'
INSERT INTO data_source (source_id, name, base_url, rate_limit_rps, requires_api_key, is_active)
VALUES
    (
        gen_random_uuid()::text,
        'usaspending',
        'https://api.usaspending.gov/api/v2',
        5.0,
        false,
        true
    ),
    (
        gen_random_uuid()::text,
        'sec_edgar',
        'https://efts.sec.gov/LATEST/search-index',
        10.0,
        false,
        true
    ),
    (
        gen_random_uuid()::text,
        'doj',
        'https://www.justice.gov/api/v1',
        4.0,
        false,
        true
    ),
    (
        gen_random_uuid()::text,
        'sam_gov',
        'https://api.sam.gov/opportunities/v2',
        4.0,
        true,
        true
    ),
    (
        gen_random_uuid()::text,
        'oversight_gov',
        'https://www.oversight.gov/api/1.0',
        2.0,
        false,
        true
    ),
    (
        gen_random_uuid()::text,
        'openfec',
        'https://api.open.fec.gov/v1',
        0.277,
        true,
        true
    )
ON CONFLICT (name) DO UPDATE SET
    base_url = EXCLUDED.base_url,
    rate_limit_rps = EXCLUDED.rate_limit_rps,
    requires_api_key = EXCLUDED.requires_api_key,
    is_active = EXCLUDED.is_active;
SQL

    log "Data sources seeded:"
    $PSQL -c "SELECT name, base_url, rate_limit_rps, requires_api_key FROM data_source ORDER BY name;"
}

seed_data_sources
log "Seed complete"
