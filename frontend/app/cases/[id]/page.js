'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { mockCases, mockCasePack } from '../../lib/mock-data';
import { useToast } from '../../components/ToastProvider';

const PIPELINE_STAGES = [
    { key: 'intake', label: 'Intake' },
    { key: 'entity_resolution', label: 'Entity Res.' },
    { key: 'evidence_retrieval', label: 'Evidence' },
    { key: 'graph_construction', label: 'Graph' },
    { key: 'case_composition', label: 'Composition' },
    { key: 'auditor_review', label: 'Audit' },
    { key: 'approval', label: 'Approval' },
];

function StepIndicator({ events }) {
    const completedStages = events.map(e => e.stage);
    const blockedStages = events.filter(e => e.policy_decision === 'blocked').map(e => e.stage);

    return (
        <div className="step-indicator" role="progressbar" aria-label="Pipeline progress">
            {PIPELINE_STAGES.map((stage) => {
                const isCompleted = completedStages.includes(stage.key);
                const isBlocked = blockedStages.includes(stage.key);
                const isCurrent = !isCompleted && completedStages.length > 0 && PIPELINE_STAGES.indexOf(stage) === completedStages.length;
                const cls = isBlocked ? 'blocked' : isCompleted ? 'completed' : isCurrent ? 'current' : '';
                return (
                    <button
                        key={stage.key}
                        className={`step-indicator-step ${cls}`}
                        onClick={() => document.getElementById('agent-decision-log')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                        style={{ cursor: 'pointer', textAlign: 'left', background: 'none', border: 'none', padding: 0, font: 'inherit', color: 'inherit' }}
                        title="Click to view in Agent Decision Log"
                    >
                        {isCompleted && !isBlocked ? '✓ ' : isBlocked ? '✕ ' : ''}{stage.label}
                    </button>
                );
            })}
        </div>
    );
}

function ConfidenceGauge({ confidence }) {
    const pct = confidence * 100;
    const circumference = 2 * Math.PI * 20;
    const offset = circumference - (pct / 100) * circumference;
    const color = confidence >= 0.8 ? 'var(--color-success)' : confidence >= 0.5 ? 'var(--color-warning)' : 'var(--color-error)';

    return (
        <svg width="52" height="52" viewBox="0 0 52 52" style={{ flexShrink: 0 }}>
            <circle cx="26" cy="26" r="20" fill="none" stroke="var(--color-gray-10)" strokeWidth="4" />
            <circle cx="26" cy="26" r="20" fill="none" stroke={color} strokeWidth="4"
                strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={offset}
                transform="rotate(-90 26 26)"
                style={{ transition: 'stroke-dashoffset 500ms ease' }}
            />
            <text x="26" y="30" textAnchor="middle" fontFamily="var(--font-body)" fontSize="11" fontWeight="700" fill="var(--color-gray-90)">
                {pct.toFixed(0)}%
            </text>
        </svg>
    );
}

function ClaimRow({ claim, citations, isOpen, onToggle }) {
    const claimCitations = citations.filter((c) => c.claim_id === claim.claim_id);
    const typeClass = claim.claim_type === 'finding' ? 'badge-finding' : claim.claim_type === 'risk_signal' ? 'badge-risk-signal' : 'badge-hypothesis';

    return (
        <div className="card" style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', cursor: 'pointer', gap: 16 }} onClick={onToggle}>
                <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                        <span className={`badge ${typeClass}`}>{claim.claim_type.replace('_', ' ')}</span>
                        <span className="mono" style={{ fontSize: 12, color: 'var(--color-gray-50)' }}>{claim.claim_id}</span>
                    </div>
                    <p style={{ fontSize: 15, color: 'var(--color-gray-80)', lineHeight: 1.7 }}>{claim.statement}</p>
                    <div style={{ fontSize: 12, color: 'var(--color-gray-50)', marginTop: 6 }}>
                        {claimCitations.length} citation{claimCitations.length !== 1 ? 's' : ''} · {claim.is_audited ? 'Audited' : 'Pending audit'}
                    </div>
                </div>
                <ConfidenceGauge confidence={claim.confidence} />
            </div>

            {isOpen && claimCitations.length > 0 && (
                <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--color-gray-10)' }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--color-gray-50)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
                        Supporting Citations
                    </div>
                    {claimCitations.map((cit) => (
                        <div key={cit.citation_id} style={{ padding: '10px 14px', background: 'var(--color-gray-2)', border: '1px solid var(--color-gray-10)', borderRadius: 'var(--radius)', marginBottom: 8 }}>
                            <div className="mono" style={{ fontSize: 11, color: 'var(--color-primary)', marginBottom: 4, fontWeight: 500 }}>
                                Artifact: {cit.artifact_id}
                            </div>
                            <div style={{ fontSize: 13, color: 'var(--color-gray-70)', fontStyle: 'italic' }}>&ldquo;{cit.excerpt}&rdquo;</div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

// Map pipeline stages to responsible agents and data sources
const STAGE_AGENT_MAP = {
    intake: { agent: 'Data Engineer', initials: 'DE', color: '#2378c3', sources: ['USAspending', 'SAM.gov'] },
    entity_resolution: { agent: 'Entity Resolver', initials: 'ER', color: '#216e1f', sources: ['SAM.gov', 'FPDS', 'SEC EDGAR'] },
    evidence_retrieval: { agent: 'Evidence Retriever', initials: 'EV', color: '#c2850c', sources: ['USAspending', 'DOJ Press Releases', 'FEC'] },
    graph_construction: { agent: 'Graph Builder', initials: 'GB', color: '#6b21a8', sources: [] },
    case_composition: { agent: 'Claim Composer', initials: 'CC', color: '#8b6b00', sources: [] },
    auditor_review: { agent: 'AI Auditor', initials: 'AU', color: '#b50d12', sources: [] },
    approval: { agent: 'AI Auditor', initials: 'AU', color: '#b50d12', sources: [] },
};

function AgentDecisionLog({ events }) {
    const [expandedEvent, setExpandedEvent] = useState(null);

    return (
        <div className="card" id="agent-decision-log">
            <h2 className="section-title-full">Agent Decision Log</h2>
            <p style={{ fontSize: 13, color: 'var(--color-gray-50)', marginBottom: 16, marginTop: -8 }}>
                Every pipeline decision is logged — which agent acted, which sources were queried, and what was decided
            </p>
            <div className="timeline">
                {events.map((event) => {
                    const stageInfo = STAGE_AGENT_MAP[event.stage] || { agent: 'System', initials: 'SY', color: '#71767a', sources: [] };
                    const dotClass = event.policy_decision === 'accepted' || event.policy_decision === 'approved' ? 'accepted' : event.policy_decision === 'blocked' ? 'blocked' : '';
                    const isOpen = expandedEvent === event.audit_event_id;

                    return (
                        <div key={event.audit_event_id} className="timeline-item" style={{ cursor: 'pointer' }} onClick={() => setExpandedEvent(isOpen ? null : event.audit_event_id)}>
                            <div className={`timeline-dot ${dotClass}`} />
                            <div style={{ flex: 1 }}>
                                <div className="timeline-title" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                    <span
                                        className="agent-avatar"
                                        style={{ width: 22, height: 22, backgroundColor: stageInfo.color, fontSize: 9 }}
                                        title={stageInfo.agent}
                                    >
                                        {stageInfo.initials}
                                    </span>
                                    <strong>{stageInfo.agent}</strong>
                                    <span style={{ color: 'var(--color-gray-40)' }}>→</span>
                                    <span>{event.stage.replace(/_/g, ' ')}</span>
                                    <span className={`badge badge-${event.policy_decision === 'blocked' ? 'blocked' : 'approved'}`}>{event.policy_decision}</span>
                                    <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--color-gray-30)', fontFamily: 'var(--font-mono)' }}>
                                        {isOpen ? '▾' : '▸'}
                                    </span>
                                </div>

                                {stageInfo.sources.length > 0 && (
                                    <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
                                        {stageInfo.sources.map(src => (
                                            <span key={src} className="source-tag">{src}</span>
                                        ))}
                                    </div>
                                )}

                                {isOpen && (
                                    <div style={{ marginTop: 10, padding: '10px 14px', background: 'var(--color-gray-2)', border: '1px solid var(--color-gray-10)', borderRadius: 'var(--radius)' }}>
                                        <div className="timeline-meta" style={{ marginBottom: 4 }}>
                                            {new Date(event.timestamp).toLocaleString('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                                        </div>
                                        <div style={{ fontSize: 13, color: 'var(--color-gray-70)', lineHeight: 1.6 }}>{event.detail}</div>
                                        {stageInfo.sources.length > 0 && (
                                            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--color-gray-50)' }}>
                                                <strong>Sources queried:</strong> {stageInfo.sources.join(', ')}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

export default function CaseDetailPage() {
    const params = useParams();
    const [caseData, setCaseData] = useState(null);
    const [pack, setPack] = useState(null);
    const [openClaim, setOpenClaim] = useState(null);
    const { addToast } = useToast();

    useEffect(() => {
        setCaseData(mockCases.find((c) => c.case_id === params.id) || mockCases[0]);
        setPack(mockCasePack);
    }, [params.id]);

    const handleCopyLink = () => {
        navigator.clipboard.writeText(window.location.href);
        addToast({ message: 'Share link copied to clipboard', type: 'success' });
    };

    const handleExportJson = () => {
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(pack, null, 2));
        const extMatch = caseData?.case_id?.split('-')[1] || 'export';
        const downloadAnchorNode = document.createElement('a');
        downloadAnchorNode.setAttribute("href", dataStr);
        downloadAnchorNode.setAttribute("download", `civicproof_dossier_${extMatch}.json`);
        document.body.appendChild(downloadAnchorNode); // required for firefox
        downloadAnchorNode.click();
        downloadAnchorNode.remove();
        addToast({ message: 'Dossier exported to JSON', type: 'success' });
    };

    if (!caseData || !pack) return (
        <div className="page-body">
            <div className="skeleton skeleton-title"></div>
            <div className="skeleton skeleton-card"></div>
            <div className="skeleton skeleton-card"></div>
        </div>
    );

    const findings = pack.claims.filter((c) => c.claim_type === 'finding');
    const riskSignals = pack.claims.filter((c) => c.claim_type === 'risk_signal');
    const hypotheses = pack.claims.filter((c) => c.claim_type === 'hypothesis');

    const claimsWithCitations = pack.claims.filter(c => c.citation_ids?.length > 0).length;
    const groundingRate = pack.claims.length > 0 ? claimsWithCitations / pack.claims.length : 0;

    return (
        <div>
            <div className="page-header">
                <nav className="breadcrumb" aria-label="Breadcrumb">
                    <a href="/">Dashboard</a>
                    <span className="breadcrumb-separator">/</span>
                    <a href="/cases">Cases</a>
                    <span className="breadcrumb-separator">/</span>
                    <span>{caseData.case_id}</span>
                </nav>
                <div className="flex justify-between items-center">
                    <div>
                        <h1 className="page-title">{caseData.title}</h1>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 8 }}>
                            <span className={`badge badge-${caseData.status}`}>{caseData.status}</span>
                            <span className="mono" style={{ fontSize: 12, color: 'var(--color-gray-50)' }}>Case ID: {caseData.case_id}</span>
                        </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                        <button className="btn btn-sm btn-outline" onClick={handleCopyLink}>Copy Link</button>
                        <button className="btn btn-sm btn-outline" onClick={handleExportJson}>Export JSON</button>
                        <button className="btn btn-sm btn-primary" onClick={() => window.print()}>Print Report</button>
                    </div>
                </div>
            </div>

            <div className="page-body">
                {/* Step Indicator */}
                <StepIndicator events={pack.audit_events} />

                {/* Case Summary Box */}
                <div className="summary-box">
                    <div className="summary-box-title">Case Summary</div>
                    <div className="summary-box-body">
                        <dl>
                            <dt>Status</dt>
                            <dd><span className={`badge badge-${caseData.status}`}>{caseData.status}</span></dd>
                            <dt>Grounding Rate</dt>
                            <dd><strong>{(groundingRate * 100).toFixed(0)}%</strong></dd>
                            <dt>Claims</dt>
                            <dd>{findings.length} findings · {riskSignals.length} risk signals · {hypotheses.length} hypotheses</dd>
                            <dt>Citations</dt>
                            <dd>{pack.citations.length}</dd>
                            <dt>Pipeline Steps</dt>
                            <dd>{pack.audit_events.length}</dd>
                            <dt>Pack Hash</dt>
                            <dd><span className="mono" style={{ color: 'var(--color-primary)', fontSize: 12 }}>{pack.pack_hash}</span></dd>
                        </dl>
                    </div>
                </div>

                <div className="grid-2">
                    <div>
                        <h2 className="section-title">Claims & Findings ({pack.claims.length})</h2>
                        <p style={{ fontSize: 13, color: 'var(--color-gray-50)', marginBottom: 16, marginTop: -8 }}>
                            Each claim includes a confidence score and supporting citations from federal data sources
                        </p>
                        {pack.claims.map((claim) => (
                            <ClaimRow
                                key={claim.claim_id}
                                claim={claim}
                                citations={pack.citations}
                                isOpen={openClaim === claim.claim_id}
                                onToggle={() => setOpenClaim(openClaim === claim.claim_id ? null : claim.claim_id)}
                            />
                        ))}
                    </div>
                    <div>
                        <h2 className="section-title">Provenance Record</h2>
                        <p style={{ fontSize: 13, color: 'var(--color-gray-50)', marginBottom: 16, marginTop: -8 }}>
                            Full transparency — every agent decision, every source queried, every policy check
                        </p>
                        <AgentDecisionLog events={pack.audit_events} />

                        <div className="alert alert-warning mt-6" role="alert">
                            <span className="alert-icon">⚠</span>
                            <div>
                                <strong>Legal Disclaimer:</strong> This document contains risk signals and hypotheses derived from publicly available federal procurement data.
                                It does not constitute an accusation of fraud, waste, abuse, or any other wrongdoing. All findings require independent corroboration before any action is taken.
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
