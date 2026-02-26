'use client';

import { useState } from 'react';
import { mockEntities, mockCases } from '../lib/mock-data';

import { useToast } from '../components/ToastProvider';

function NewCaseModal({ onClose, onLaunch }) {
    const [step, setStep] = useState(1);
    const [title, setTitle] = useState('');
    const [seedType, setSeedType] = useState('vendor_name');
    const [seedValue, setSeedValue] = useState('');
    const [error, setError] = useState('');
    const { addToast } = useToast();

    const validateInput = () => {
        if (!title.trim()) return 'Case title is required.';
        if (!seedValue.trim()) return 'Seed value is required.';

        if (seedType === 'uei' && seedValue.trim().length !== 12) {
            return 'UEI must be exactly 12 characters.';
        }
        if (seedType === 'cage_code' && seedValue.trim().length !== 5) {
            return 'CAGE Code must be exactly 5 characters.';
        }
        return '';
    };

    const handleNext = () => {
        const err = validateInput();
        if (err) {
            setError(err);
            return;
        }
        setError('');
        setStep(2);
    };

    const handleSubmit = () => {
        addToast({
            message: `Investigation initiated: Agents gathering data for ${seedValue}`,
            type: 'success'
        });
        if (onLaunch) onLaunch(title, seedValue);
        onClose();
    };

    const handleKeyDown = (e) => { if (e.key === 'Escape') onClose(); };

    return (
        <div className="modal-overlay" onClick={onClose} onKeyDown={handleKeyDown} role="dialog" aria-modal="true" aria-label="Initiate new investigation">
            <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 520 }}>

                {/* Header with Step Indicator */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                    <h2 className="modal-title" style={{ margin: 0 }}>Start Research</h2>
                    <div style={{ display: 'flex', gap: 6 }}>
                        <div className={`step-dot ${step >= 1 ? 'active' : ''}`} />
                        <div className={`step-dot ${step >= 2 ? 'active' : ''}`} />
                    </div>
                </div>

                {step === 1 && (
                    <div className="modal-step-content blur-in">
                        <p style={{ fontSize: 14, color: 'var(--color-gray-60)', marginBottom: 20 }}>
                            Provide a starting identifier. The system will search public datasets from this seed.
                        </p>

                        {error && <div className="alert alert-error" style={{ marginBottom: 16 }}>{error}</div>}

                        <div className="form-group">
                            <label className="form-label" htmlFor="case-title">Research Reference Title</label>
                            <input id="case-title" className="form-input" placeholder="e.g., Acme Corp — Sole Source Analysis" value={title} onChange={(e) => { setTitle(e.target.value); setError(''); }} autoFocus />
                        </div>
                        <div className="form-group">
                            <label className="form-label" htmlFor="seed-type">Seed Identifier Type</label>
                            <select id="seed-type" className="form-select" value={seedType} onChange={(e) => { setSeedType(e.target.value); setError(''); }}>
                                <option value="vendor_name">Vendor Name</option>
                                <option value="uei">Unique Entity Identifier (UEI)</option>
                                <option value="cage_code">CAGE Code</option>
                                <option value="award_id">Federal Award ID</option>
                                <option value="tip_text">Narrative Tip</option>
                            </select>
                            <div className="form-hint">
                                {seedType === 'uei' ? 'UEI is a 12-character alphanumeric value assigned in SAM.gov.' :
                                    seedType === 'cage_code' ? 'CAGE is a 5-character ID for commercial and government entities.' :
                                        'Enter the exact legal name or common DBA.'}
                            </div>
                        </div>
                        <div className="form-group">
                            <label className="form-label" htmlFor="seed-value">Seed Value</label>
                            <input id="seed-value" className="form-input" placeholder="Enter identifier or keyword..." value={seedValue} onChange={(e) => { setSeedValue(e.target.value); setError(''); }} />
                        </div>
                        <div className="modal-actions" style={{ marginTop: 28 }}>
                            <button className="btn btn-outline" onClick={onClose}>Cancel</button>
                            <button className="btn btn-primary" onClick={handleNext}>Continue →</button>
                        </div>
                    </div>
                )}

                {step === 2 && (
                    <div className="modal-step-content blur-in">
                        <div style={{ background: 'var(--color-primary-lightest)', borderRadius: 'var(--radius)', padding: '16px 20px', marginBottom: 20, border: '1px solid rgba(26, 68, 128, 0.1)' }}>
                            <h3 style={{ fontSize: 13, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--color-primary-dark)', margin: '0 0 12px 0' }}>Agentic Pipeline Preview</h3>
                            <p style={{ fontSize: 14, color: 'var(--color-gray-80)', margin: '0 0 12px 0', lineHeight: 1.5 }}>
                                CivicProof will search public data sources for <strong>{seedValue}</strong>.
                            </p>
                            <ul style={{ fontSize: 13, color: 'var(--color-gray-70)', margin: 0, paddingLeft: 18, lineHeight: 1.6 }}>
                                <li><strong>6 public data sources</strong> will be queried (USAspending, SEC EDGAR, DOJ, etc.).</li>
                                <li>Entity resolution and relationship mapping will run automatically.</li>
                                <li>All findings cite source artifacts with full provenance.</li>
                                <li>Results contain risk signals and hypotheses only -- not accusations.</li>
                            </ul>
                        </div>

                        <div className="form-group">
                            <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <input type="checkbox" defaultChecked />
                                <span>Notify me via email when the assessment completes (est. 4-6 minutes)</span>
                            </label>
                        </div>

                        <div className="modal-actions" style={{ marginTop: 28 }}>
                            <button className="btn btn-outline" onClick={() => setStep(1)}>← Back</button>
                            <button className="btn btn-primary" onClick={handleSubmit}>Start Research</button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default function InvestigatePage() {
    const [query, setQuery] = useState('');
    const [activeTab, setActiveTab] = useState('entities');
    const [showNewCase, setShowNewCase] = useState(false);
    const [results, setResults] = useState(mockEntities.items);

    const handleSearch = (e) => {
        e.preventDefault();
        if (!query.trim()) { setResults(mockEntities.items); return; }
        const filtered = mockEntities.items.filter((ent) =>
            ent.canonical_name.toLowerCase().includes(query.toLowerCase()) || ent.uei === query || ent.cage_code === query
        );
        setResults(filtered);
    };

    return (
        <div>
            <div className="page-header">
                <nav className="breadcrumb" aria-label="Breadcrumb">
                    <a href="/">Dashboard</a>
                    <span className="breadcrumb-separator">/</span>
                    <span>Investigate</span>
                </nav>
                <div className="flex justify-between items-center">
                    <div>
                        <h1 className="page-title">Investigate</h1>
                        <p className="page-subtitle">Search public entity records and launch new research queries</p>
                    </div>
                    <button className="btn btn-primary" onClick={() => setShowNewCase(true)}>+ New Research</button>
                </div>
            </div>

            <div className="page-body">
                <form onSubmit={handleSearch}>
                    <div className="search-container">
                        <span className="search-icon" aria-hidden="true">
                            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
                                <circle cx="8" cy="8" r="5.5" /><line x1="12" y1="12" x2="16" y2="16" />
                            </svg>
                        </span>
                        <input className="search-input" placeholder="Search by vendor name, UEI, CAGE code, or keyword..." value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search entities" />
                    </div>
                </form>

                <div className="tabs" style={{ marginTop: 24 }} role="tablist">
                    <button className={`tab ${activeTab === 'entities' ? 'active' : ''}`} onClick={() => setActiveTab('entities')} role="tab" aria-selected={activeTab === 'entities'}>
                        Entities ({results.length})
                    </button>
                    <button className={`tab ${activeTab === 'artifacts' ? 'active' : ''}`} onClick={() => setActiveTab('artifacts')} role="tab" aria-selected={activeTab === 'artifacts'}>
                        Artifacts
                    </button>
                </div>

                {activeTab === 'entities' && (
                    <>
                        <div style={{ fontSize: 13, color: 'var(--color-gray-50)', marginBottom: 12 }} aria-live="polite">
                            Showing {results.length} of {mockEntities.items.length} entities
                            {query && ` matching "${query}"`}
                        </div>
                        <div className="card">
                            <table className="data-table" aria-label="Entity search results">
                                <thead>
                                    <tr>
                                        <th scope="col">Entity Name</th>
                                        <th scope="col">Type</th>
                                        <th scope="col">UEI</th>
                                        <th scope="col">CAGE</th>
                                        <th scope="col">Known Aliases</th>
                                        <th scope="col">Action</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {results.map((entity) => (
                                        <tr key={entity.entity_id} style={{ cursor: 'default' }}>
                                            <td style={{ fontWeight: 600, color: 'var(--color-gray-90)' }}>{entity.canonical_name}</td>
                                            <td><span className={`badge ${entity.entity_type === 'vendor' ? 'badge-finding' : 'badge-hypothesis'}`}>{entity.entity_type}</span></td>
                                            <td className="mono">{entity.uei || '—'}</td>
                                            <td className="mono">{entity.cage_code || '—'}</td>
                                            <td style={{ fontSize: 13, color: 'var(--color-gray-50)' }}>{entity.aliases.join(', ') || '—'}</td>
                                            <td><button className="btn btn-sm btn-primary">Investigate →</button></td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                            {results.length === 0 && (
                                <div className="empty-state">
                                    <svg width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="var(--color-gray-30)" strokeWidth="1.5" style={{ margin: '0 auto 12px' }}>
                                        <circle cx="20" cy="20" r="14" /><line x1="30" y1="30" x2="42" y2="42" />
                                    </svg>
                                    <div>No entities match &ldquo;{query}&rdquo;</div>
                                    <div style={{ fontSize: 13, color: 'var(--color-gray-30)', marginTop: 8 }}>Try a different vendor name, UEI, or CAGE code</div>
                                </div>
                            )}
                        </div>
                    </>
                )}

                {activeTab === 'artifacts' && (
                    <div className="card">
                        <div className="empty-state">
                            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="var(--color-gray-30)" strokeWidth="1.5" style={{ margin: '0 auto 12px' }}>
                                <rect x="8" y="4" width="32" height="40" rx="3" /><line x1="16" y1="14" x2="32" y2="14" /><line x1="16" y1="22" x2="32" y2="22" /><line x1="16" y1="30" x2="28" y2="30" />
                            </svg>
                            <div>Enter a search query to locate federal artifacts</div>
                            <div style={{ fontSize: 13, color: 'var(--color-gray-30)', marginTop: 8 }}>Search by URL, content hash, or artifact metadata</div>
                        </div>
                    </div>
                )}

                <div className="summary-box mt-6">
                    <div className="summary-box-title">Recent Investigations</div>
                    <div className="summary-box-body">
                        {mockCases.slice(0, 3).map((c) => (
                            <a key={c.case_id} href={`/cases/${c.case_id}`} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--color-gray-5)', textDecoration: 'none', color: 'inherit' }}>
                                <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-gray-90)' }}>{c.title}</span>
                                <span className={`badge badge-${c.status}`}>{c.status}</span>
                            </a>
                        ))}
                    </div>
                </div>
            </div>

            {showNewCase && <NewCaseModal onClose={() => setShowNewCase(false)} />}
        </div>
    );
}
