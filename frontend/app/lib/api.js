/**
 * CivicProof API Client
 * 
 * Centralized fetch wrapper for all backend API calls.
 * Uses demo mock data when NEXT_PUBLIC_API_URL is not set.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

/**
 * Fetch wrapper with error handling and JSON parsing.
 */
async function apiFetch(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const res = await fetch(url, {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
        ...options,
    });

    if (!res.ok) {
        const error = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(error.detail?.error || error.error || `API error: ${res.status}`);
    }

    return res.json();
}

// ── Health ──

export async function getHealth() {
    return apiFetch('/health');
}

export async function getReadiness() {
    return apiFetch('/ready');
}

// ── Cases ──

export async function createCase(title, seedInput) {
    return apiFetch('/v1/cases', {
        method: 'POST',
        body: JSON.stringify({ title, seed_input: seedInput }),
    });
}

export async function getCase(caseId) {
    return apiFetch(`/v1/cases/${caseId}`);
}

export async function getCasePack(caseId) {
    return apiFetch(`/v1/cases/${caseId}/pack`);
}

// ── Search ──

export async function searchEntities(q, entityType = null, page = 1, pageSize = 20) {
    const params = new URLSearchParams({ q, page, page_size: pageSize });
    if (entityType) params.set('entity_type', entityType);
    return apiFetch(`/v1/search/entities?${params}`);
}

export async function searchArtifacts(q, source = null, page = 1, pageSize = 20) {
    const params = new URLSearchParams({ q, page, page_size: pageSize });
    if (source) params.set('source', source);
    return apiFetch(`/v1/search/artifacts?${params}`);
}

// ── Ingest ──

export async function triggerIngest(sourceName, parameters = {}) {
    return apiFetch('/v1/ingest/runs', {
        method: 'POST',
        body: JSON.stringify({ source_name: sourceName, parameters }),
    });
}

// ── Metrics ──

export async function getMetrics() {
    return apiFetch('/v1/metrics/public');
}
