/**
 * Mock data for demo mode when no backend is connected.
 * Mirrors exact API response shapes.
 */

export const mockMetrics = {
    audited_dossier_pass_rate: 0.92,
    median_tip_to_dossier_seconds: 187,
    hallucination_caught_rate: 0.97,
    avg_cost_per_dossier_usd: 0.23,
    entity_resolution_coverage: 0.88,
    replay_determinism_rate: 1.0,
    total_cases_processed: 47,
    total_artifacts_ingested: 12450,
    sources_active: 6,
    last_24h: {
        cases_created: 3,
        artifacts_fetched: 892,
        audit_blocks: 1,
        model_cost_usd: 0.69,
    },
};

export const mockCases = [
    {
        case_id: 'c-7f3a2b1e',
        title: 'Acme Defense Solutions — Sole-Source Pattern',
        status: 'complete',
        seed_input: { vendor_name: 'Acme Defense Solutions' },
        created_at: '2025-02-24T14:30:00Z',
        updated_at: '2025-02-24T14:33:22Z',
    },
    {
        case_id: 'c-4e9d8c2f',
        title: 'GlobalTech Services — Award Spike Anomaly',
        status: 'complete',
        seed_input: { uei: 'GLBTCH1234' },
        created_at: '2025-02-23T09:15:00Z',
        updated_at: '2025-02-23T09:18:45Z',
    },
    {
        case_id: 'c-1a5b3d7g',
        title: 'SpecOps Consulting — Shell Company Network',
        status: 'processing',
        seed_input: { vendor_name: 'SpecOps Consulting Group' },
        created_at: '2025-02-25T08:00:00Z',
        updated_at: '2025-02-25T08:01:12Z',
    },
    {
        case_id: 'c-8k2m4n6p',
        title: 'Federal IT Partners — Bid Rigging Indicators',
        status: 'blocked',
        seed_input: { vendor_name: 'Federal IT Partners LLC' },
        created_at: '2025-02-22T11:20:00Z',
        updated_at: '2025-02-22T11:24:30Z',
    },
    {
        case_id: 'c-9q1r3s5t',
        title: 'Meridian Logistics — Geographic Clustering',
        status: 'complete',
        seed_input: { cage_code: 'MRDLN' },
        created_at: '2025-02-21T16:45:00Z',
        updated_at: '2025-02-21T16:48:15Z',
    },
];

export const mockCasePack = {
    case_id: 'c-7f3a2b1e',
    claims: [
        {
            claim_id: 'cl-001',
            statement: 'Acme Defense Solutions received 14 sole-source contracts from the Department of Defense between 2022-2024, totaling $42.3M.',
            claim_type: 'finding',
            confidence: 0.95,
            is_audited: true,
            audit_passed: true,
        },
        {
            claim_id: 'cl-002',
            statement: 'Award amounts show a 340% year-over-year increase inconsistent with agency-wide procurement trends.',
            claim_type: 'risk_signal',
            confidence: 0.78,
            is_audited: true,
            audit_passed: true,
        },
        {
            claim_id: 'cl-003',
            statement: 'Two subsidiaries of Acme share the same registered address at 1400 Defense Blvd, suggesting a potential shell company pattern.',
            claim_type: 'hypothesis',
            confidence: 0.62,
            is_audited: true,
            audit_passed: true,
        },
        {
            claim_id: 'cl-004',
            statement: 'DOJ press release (2023-08-15) references ongoing investigation into defense procurement irregularities in the same geographic region.',
            claim_type: 'finding',
            confidence: 0.88,
            is_audited: true,
            audit_passed: true,
        },
        {
            claim_id: 'cl-005',
            statement: 'SEC EDGAR filings show the parent company disclosed a material weakness in internal controls over government contract reporting.',
            claim_type: 'risk_signal',
            confidence: 0.82,
            is_audited: true,
            audit_passed: true,
        },
    ],
    citations: [
        { citation_id: 'cit-001', claim_id: 'cl-001', artifact_id: 'art-usa-4521', excerpt: 'Award ID: SPE4A121D0042, Recipient: Acme Defense Solutions, Amount: $8.2M, Type: Sole Source', page_ref: null },
        { citation_id: 'cit-002', claim_id: 'cl-001', artifact_id: 'art-usa-4522', excerpt: 'Award ID: SPE4A122D0089, Recipient: Acme Defense Solutions, Amount: $12.1M', page_ref: null },
        { citation_id: 'cit-003', claim_id: 'cl-002', artifact_id: 'art-usa-4523', excerpt: 'FY2022 total: $9.4M → FY2023 total: $32.1M (adjusted)', page_ref: null },
        { citation_id: 'cit-004', claim_id: 'cl-003', artifact_id: 'art-sam-0891', excerpt: 'Registered address: 1400 Defense Blvd, Suite 200, Arlington VA', page_ref: null },
        { citation_id: 'cit-005', claim_id: 'cl-004', artifact_id: 'art-doj-2847', excerpt: 'DOJ Press Release 23-891: False Claims Act investigation into defense contractor procurement', page_ref: null },
        { citation_id: 'cit-006', claim_id: 'cl-005', artifact_id: 'art-sec-1023', excerpt: '10-K Filing, Item 9A: Material weakness in internal controls over contract cost reporting', page_ref: null },
    ],
    audit_events: [
        { audit_event_id: 'ae-001', stage: 'intake', policy_decision: 'accepted', detail: 'Case created from seed input', timestamp: '2025-02-24T14:30:00Z' },
        { audit_event_id: 'ae-002', stage: 'entity_resolution', policy_decision: 'accepted', detail: 'Resolved to canonical entity: ACME-DEF-001', timestamp: '2025-02-24T14:30:15Z' },
        { audit_event_id: 'ae-003', stage: 'evidence_retrieval', policy_decision: 'accepted', detail: '47 artifacts retrieved from 4 sources', timestamp: '2025-02-24T14:31:02Z' },
        { audit_event_id: 'ae-004', stage: 'graph_builder', policy_decision: 'accepted', detail: 'Evidence graph: 12 nodes, 23 edges', timestamp: '2025-02-24T14:31:45Z' },
        { audit_event_id: 'ae-005', stage: 'anomaly_detection', policy_decision: 'accepted', detail: '3 anomalies detected: sole_source_pattern, award_spike, address_ring', timestamp: '2025-02-24T14:32:10Z' },
        { audit_event_id: 'ae-006', stage: 'case_composition', policy_decision: 'accepted', detail: '5 claims composed, all cited', timestamp: '2025-02-24T14:32:55Z' },
        { audit_event_id: 'ae-007', stage: 'audit', policy_decision: 'approved', detail: 'All 5 claims pass auditor gate: grounding=1.0, min_sources=4', timestamp: '2025-02-24T14:33:22Z' },
    ],
    generated_at: '2025-02-24T14:33:22Z',
    pack_hash: 'sha256:a3f8b2c1d4e5f6789012345678abcdef',
};

export const mockEntities = {
    items: [
        { entity_id: 'ent-001', entity_type: 'vendor', canonical_name: 'Acme Defense Solutions', uei: 'ACMDEF123', cage_code: 'ACME1', aliases: ['Acme Def Sol', 'ADS Inc'] },
        { entity_id: 'ent-002', entity_type: 'vendor', canonical_name: 'GlobalTech Services', uei: 'GLBTCH1234', cage_code: 'GLTCH', aliases: ['GT Services'] },
        { entity_id: 'ent-003', entity_type: 'agency', canonical_name: 'Department of Defense', uei: null, cage_code: null, aliases: ['DoD', 'DPAP'] },
        { entity_id: 'ent-004', entity_type: 'vendor', canonical_name: 'Meridian Logistics Corp', uei: 'MRDLN5678', cage_code: 'MRDLN', aliases: ['Meridian LC'] },
    ],
    total: 4,
    page: 1,
    page_size: 20,
};

export const mockSources = [
    { name: 'USAspending', source_id: 'usaspending', rate_limit: '5 RPS', schedule: 'Daily 03:00 UTC', status: 'active', last_run: '2025-02-25T03:00:00Z', artifacts_total: 5420 },
    { name: 'DOJ Press Releases', source_id: 'doj', rate_limit: '4 RPS', schedule: 'Every 6h', status: 'active', last_run: '2025-02-25T06:00:00Z', artifacts_total: 1893 },
    { name: 'SEC EDGAR', source_id: 'sec_edgar', rate_limit: '10 RPS', schedule: 'Every 6h', status: 'active', last_run: '2025-02-25T06:00:00Z', artifacts_total: 2134 },
    { name: 'Oversight.gov', source_id: 'oversight', rate_limit: '2 RPS', schedule: 'Weekly Sun', status: 'active', last_run: '2025-02-23T06:00:00Z', artifacts_total: 1567 },
    { name: 'SAM.gov', source_id: 'sam_gov', rate_limit: '4 RPS', schedule: 'Daily 04:00 UTC', status: 'active', last_run: '2025-02-25T04:00:00Z', artifacts_total: 892 },
    { name: 'OpenFEC', source_id: 'openfec', rate_limit: '1000/hr', schedule: 'Daily 05:00 UTC', status: 'active', last_run: '2025-02-25T05:00:00Z', artifacts_total: 544 },
];
