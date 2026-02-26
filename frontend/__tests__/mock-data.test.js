import { mockMetrics, mockCases, mockCasePack, mockEntities, mockSources } from '../app/lib/mock-data';

describe('Mock Data Structure Validation', () => {
    describe('mockMetrics', () => {
        it('has all required fields', () => {
            expect(mockMetrics).toHaveProperty('audited_dossier_pass_rate');
            expect(mockMetrics).toHaveProperty('total_cases_processed');
            expect(mockMetrics).toHaveProperty('total_artifacts_ingested');
            expect(mockMetrics).toHaveProperty('hallucination_caught_rate');
            expect(mockMetrics).toHaveProperty('avg_cost_per_dossier_usd');
            expect(mockMetrics).toHaveProperty('replay_determinism_rate');
        });

        it('has last_24h object', () => {
            expect(mockMetrics.last_24h).toHaveProperty('cases_created');
            expect(mockMetrics.last_24h).toHaveProperty('artifacts_fetched');
            expect(mockMetrics.last_24h).toHaveProperty('audit_blocks');
            expect(mockMetrics.last_24h).toHaveProperty('model_cost_usd');
        });

        it('has valid rate values between 0 and 1', () => {
            expect(mockMetrics.audited_dossier_pass_rate).toBeGreaterThanOrEqual(0);
            expect(mockMetrics.audited_dossier_pass_rate).toBeLessThanOrEqual(1);
            expect(mockMetrics.hallucination_caught_rate).toBeGreaterThanOrEqual(0);
            expect(mockMetrics.hallucination_caught_rate).toBeLessThanOrEqual(1);
        });
    });

    describe('mockCases', () => {
        it('is an array of cases', () => {
            expect(Array.isArray(mockCases)).toBe(true);
            expect(mockCases.length).toBeGreaterThan(0);
        });

        it('each case has required fields', () => {
            mockCases.forEach((c) => {
                expect(c).toHaveProperty('case_id');
                expect(c).toHaveProperty('title');
                expect(c).toHaveProperty('status');
                expect(c).toHaveProperty('seed_input');
                expect(c).toHaveProperty('created_at');
                expect(c).toHaveProperty('updated_at');
            });
        });

        it('case status is valid', () => {
            const validStatuses = ['complete', 'processing', 'blocked', 'failed'];
            mockCases.forEach((c) => {
                expect(validStatuses).toContain(c.status);
            });
        });
    });

    describe('mockCasePack', () => {
        it('has claims, citations, and audit_events', () => {
            expect(mockCasePack).toHaveProperty('claims');
            expect(mockCasePack).toHaveProperty('citations');
            expect(mockCasePack).toHaveProperty('audit_events');
            expect(mockCasePack).toHaveProperty('pack_hash');
        });

        it('claims have correct structure', () => {
            mockCasePack.claims.forEach((claim) => {
                expect(claim).toHaveProperty('claim_id');
                expect(claim).toHaveProperty('claim_type');
                expect(claim).toHaveProperty('statement');
                expect(claim).toHaveProperty('confidence');
                expect(claim).toHaveProperty('is_audited');
                expect(claim.confidence).toBeGreaterThanOrEqual(0);
                expect(claim.confidence).toBeLessThanOrEqual(1);
            });
        });

        it('claim types are valid', () => {
            const validTypes = ['finding', 'risk_signal', 'hypothesis'];
            mockCasePack.claims.forEach((c) => {
                expect(validTypes).toContain(c.claim_type);
            });
        });

        it('citations reference valid claim IDs', () => {
            const claimIds = mockCasePack.claims.map(c => c.claim_id);
            mockCasePack.citations.forEach((cit) => {
                expect(claimIds).toContain(cit.claim_id);
            });
        });
    });

    describe('mockEntities', () => {
        it('has items array', () => {
            expect(mockEntities).toHaveProperty('items');
            expect(Array.isArray(mockEntities.items)).toBe(true);
        });

        it('entities have required fields', () => {
            mockEntities.items.forEach((e) => {
                expect(e).toHaveProperty('entity_id');
                expect(e).toHaveProperty('canonical_name');
                expect(e).toHaveProperty('entity_type');
                expect(e).toHaveProperty('aliases');
            });
        });
    });

    describe('mockSources', () => {
        it('is an array with correct length', () => {
            expect(Array.isArray(mockSources)).toBe(true);
            expect(mockSources.length).toBe(6);
        });

        it('sources have required fields', () => {
            mockSources.forEach((s) => {
                expect(s).toHaveProperty('source_id');
                expect(s).toHaveProperty('name');
                expect(s).toHaveProperty('status');
                expect(s).toHaveProperty('rate_limit');
                expect(s).toHaveProperty('schedule');
                expect(s).toHaveProperty('last_run');
                expect(s).toHaveProperty('artifacts_total');
            });
        });
    });
});
