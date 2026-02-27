'use client';

import { useState } from 'react';
import { mockSources } from '../lib/mock-data';

function SourceCard({ source }) {
    const [triggering, setTriggering] = useState(false);
    const [triggered, setTriggered] = useState(false);
    const [historyOpen, setHistoryOpen] = useState(false);

    const handleTrigger = () => {
        setTriggering(true);
        setTimeout(() => { setTriggering(false); setTriggered(true); setTimeout(() => setTriggered(false), 3000); }, 1000);
    };

    // Progress indicator for schedule
    const getScheduleProgress = () => {
        const now = new Date();
        const lastRun = new Date(source.last_run);
        const hoursSince = (now - lastRun) / (1000 * 60 * 60);
        const scheduleHours = source.schedule.includes('Daily') ? 24 : source.schedule.includes('6h') ? 6 : source.schedule.includes('12h') ? 12 : 168;
        return Math.min(1, hoursSince / scheduleHours);
    };

    const progress = getScheduleProgress();

    // Mock history based on last_run
    const lastRunDate = new Date(source.last_run);
    const mockHistory = [
        { id: 1, date: lastRunDate, status: 'Success', records: Math.floor(Math.random() * 5000) + 100 },
        { id: 2, date: new Date(lastRunDate.getTime() - 24 * 60 * 60 * 1000), status: 'Success', records: Math.floor(Math.random() * 5000) + 100 },
        { id: 3, date: new Date(lastRunDate.getTime() - 48 * 60 * 60 * 1000), status: 'Success', records: Math.floor(Math.random() * 5000) + 100 },
    ];

    return (
        <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
            <div className="source-card-header">
                <div className="source-icon" aria-hidden="true" style={{ position: 'relative' }}>
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="var(--color-primary)" strokeWidth="1.5">
                        <ellipse cx="10" cy="5" rx="7" ry="2.5" />
                        <path d="M3 5v5c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5V5" />
                        <path d="M3 10v5c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5V10" />
                    </svg>
                    {/* Live connection dot */}
                    {source.status === 'active' && (
                        <div style={{ position: 'absolute', bottom: -2, right: -2, width: 8, height: 8, background: 'var(--color-success)', borderRadius: '50%', border: '2px solid white' }}>
                            <div style={{ position: 'absolute', top: -2, left: -2, width: 8, height: 8, background: 'var(--color-success)', borderRadius: '50%', animation: 'thinking-pulse 2s infinite' }} />
                        </div>
                    )}
                </div>
                <div>
                    <div className="source-name">{source.name}</div>
                    <span className="badge badge-active" style={{ marginTop: 4 }}>{source.status}</span>
                </div>
            </div>

            <div className="source-meta">
                <div className="source-meta-row"><span className="source-meta-label">Rate Limit</span><span className="source-meta-value">{source.rate_limit}</span></div>
                <div className="source-meta-row"><span className="source-meta-label">Schedule</span><span className="source-meta-value">{source.schedule}</span></div>
                <div className="source-meta-row"><span className="source-meta-label">Last Run</span><span className="source-meta-value">{new Date(source.last_run).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span></div>
                <div className="source-meta-row"><span className="source-meta-label">Total Artifacts</span><span className="source-meta-value">{source.artifacts_total.toLocaleString()}</span></div>
            </div>

            <div style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--color-gray-50)', marginBottom: 4, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    <span>Ingestion Window</span>
                    <span>{(progress * 100).toFixed(0)}%</span>
                </div>
                <div style={{ height: 4, background: 'var(--color-gray-10)', borderRadius: 2, overflow: 'hidden' }}>
                    <div style={{ width: `${progress * 100}%`, height: '100%', background: progress >= 0.9 ? 'var(--color-warning)' : 'var(--color-primary)', borderRadius: 2, transition: 'width 400ms ease' }} />
                </div>
            </div>

            {/* Expandable History */}
            <div style={{ marginTop: 'auto', borderTop: '1px solid var(--color-gray-10)', paddingTop: 12 }}>
                <button
                    onClick={() => setHistoryOpen(!historyOpen)}
                    style={{ width: '100%', background: 'none', border: 'none', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 13, color: 'var(--color-gray-70)', fontWeight: 600, cursor: 'pointer', padding: '4px 0' }}
                >
                    <span>Run History</span>
                    <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}>{historyOpen ? '▼' : '▶'}</span>
                </button>

                {historyOpen && (
                    <div className="blur-in" style={{ marginTop: 12, background: 'var(--color-gray-2)', borderRadius: 'var(--radius)', padding: 12, border: '1px solid var(--color-gray-10)' }}>
                        {mockHistory.map(run => (
                            <div key={run.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 8, paddingBottom: 8, borderBottom: run.id !== 3 ? '1px solid var(--color-gray-10)' : 'none' }}>
                                <div style={{ color: 'var(--color-gray-50)', fontFamily: 'var(--font-mono)' }}>
                                    {run.date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                                </div>
                                <div style={{ color: 'var(--color-success)', fontWeight: 600 }}>{run.status}</div>
                                <div style={{ color: 'var(--color-gray-70)', fontFamily: 'var(--font-mono)' }}>+{run.records}</div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <button className={`btn w-full btn-sm ${triggered ? 'btn-outline' : 'btn-primary'}`} style={{ marginTop: 16 }} onClick={handleTrigger} disabled={triggering} aria-label={`Trigger ingestion for ${source.name}`}>
                {triggering ? 'Initiating...' : triggered ? '✓ Run Triggered' : 'Trigger Manual Sync'}
            </button>
        </div>
    );
}

export default function SourcesPage() {
    return (
        <div>
            <div className="page-header">
                <nav className="breadcrumb" aria-label="Breadcrumb">
                    <a href="/">Dashboard</a>
                    <span className="breadcrumb-separator">/</span>
                    <span>Data Sources</span>
                </nav>
                <h1 className="page-title">Data Sources</h1>
                <p className="page-subtitle">Public data connectors — rate-limited, idempotent, content-hashed</p>
            </div>

            <div className="page-body">
                <div className="summary-box">
                    <div className="summary-box-title">Connector Overview</div>
                    <div className="summary-box-body">
                        <dl>
                            <dt>Active Sources</dt>
                            <dd><strong>{mockSources.filter(s => s.status === 'active').length}</strong> operational</dd>
                            <dt>Total Artifacts</dt>
                            <dd><strong>{mockSources.reduce((sum, s) => sum + s.artifacts_total, 0).toLocaleString()}</strong> fetched and content-hashed</dd>
                            <dt>Connectors Deployed</dt>
                            <dd><strong>{mockSources.length}</strong> federal data sources</dd>
                        </dl>
                    </div>
                </div>

                <h2 className="section-title">Public Data Connectors</h2>
                <p style={{ fontSize: 13, color: 'var(--color-gray-50)', marginBottom: 16, marginTop: -8 }}>
                    Each connector enforces upstream rate limits and produces content-hashed artifacts from public APIs
                </p>
                <div className="source-grid">{mockSources.map((s) => <SourceCard key={s.source_id} source={s} />)}</div>

                <div className="card mt-8">
                    <h2 className="section-title-full">Rate Limit Compliance Matrix</h2>
                    <p style={{ fontSize: 13, color: 'var(--color-gray-50)', marginBottom: 16, marginTop: -8 }}>
                        All connectors implement token-bucket rate limiters to respect upstream API policies
                    </p>
                    <table className="data-table" style={{ cursor: 'default' }} aria-label="Rate limit compliance">
                        <thead><tr><th scope="col">Source</th><th scope="col">Rate Limit</th><th scope="col">Authentication</th><th scope="col">Schedule</th><th scope="col">Documentation</th></tr></thead>
                        <tbody>
                            {mockSources.map((s) => (
                                <tr key={s.source_id} style={{ cursor: 'default' }}>
                                    <td style={{ fontWeight: 700, color: 'var(--color-gray-90)' }}>{s.name}</td>
                                    <td className="mono">{s.rate_limit}</td>
                                    <td>{['sam_gov', 'openfec'].includes(s.source_id) ? <span className="badge badge-risk-signal">API Key</span> : <span className="badge badge-finding">Public</span>}</td>
                                    <td className="mono">{s.schedule}</td>
                                    <td><a href="#" style={{ fontSize: 13 }}>View Docs →</a></td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
