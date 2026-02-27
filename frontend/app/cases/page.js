'use client';

import { useState } from 'react';
import { mockCases } from '../lib/mock-data';

const ITEMS_PER_PAGE = 5;

export default function CasesPage() {
    const [filter, setFilter] = useState('all');
    const [page, setPage] = useState(1);
    const [cases] = useState(mockCases);

    const filtered = filter === 'all' ? cases : cases.filter((c) => c.status === filter);
    const totalPages = Math.max(1, Math.ceil(filtered.length / ITEMS_PER_PAGE));
    const paginated = filtered.slice((page - 1) * ITEMS_PER_PAGE, page * ITEMS_PER_PAGE);

    const statusCounts = {
        all: cases.length,
        complete: cases.filter(c => c.status === 'complete').length,
        processing: cases.filter(c => c.status === 'processing').length,
        blocked: cases.filter(c => c.status === 'blocked').length,
    };

    return (
        <div>
            <div className="page-header">
                <nav className="breadcrumb" aria-label="Breadcrumb">
                    <a href="/">Dashboard</a>
                    <span className="breadcrumb-separator">/</span>
                    <span>Cases</span>
                </nav>
                <div className="flex justify-between items-center">
                    <div>
                        <h1 className="page-title">Case Registry</h1>
                        <p className="page-subtitle">
                            {cases.length} total cases · {statusCounts.complete} approved dossiers · {statusCounts.processing} under review
                        </p>
                    </div>
                    <a href="/investigate" className="btn btn-primary">+ New Investigation</a>
                </div>
            </div>

            <div className="page-body">
                <div className="tabs" role="tablist">
                    {Object.entries(statusCounts).map(([key, count]) => (
                        <button
                            key={key}
                            className={`tab ${filter === key ? 'active' : ''}`}
                            onClick={() => { setFilter(key); setPage(1); }}
                            role="tab"
                            aria-selected={filter === key}
                        >
                            {key === 'all' ? 'All Cases' : key.charAt(0).toUpperCase() + key.slice(1)} ({count})
                        </button>
                    ))}
                </div>

                <div style={{ fontSize: 13, color: 'var(--color-gray-50)', marginBottom: 12 }}>
                    Showing {paginated.length} of {filtered.length} cases · Page {page} of {totalPages}
                </div>

                <div className="card">
                    <table className="data-table" aria-label="Case registry">
                        <thead>
                            <tr>
                                <th scope="col">Case Title</th>
                                <th scope="col">Status</th>
                                <th scope="col">Seed Identifier</th>
                                <th scope="col">Date Opened</th>
                                <th scope="col">Last Updated</th>
                            </tr>
                        </thead>
                        <tbody>
                            {paginated.map((c) => (
                                <tr key={c.case_id} onClick={() => router.push(`/cases/${c.case_id}`)} tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && router.push(`/cases/${c.case_id}`)}>
                                    <td>
                                        <span style={{ fontWeight: 700, color: 'var(--color-gray-90)' }}>{c.title}</span>
                                        <div className="mono" style={{ fontSize: 11, color: 'var(--color-gray-50)', marginTop: 2 }}>{c.case_id}</div>
                                    </td>
                                    <td><span className={`badge badge-${c.status}`}>{c.status}</span></td>
                                    <td className="mono" style={{ fontSize: 12 }}>
                                        {Object.entries(c.seed_input).map(([k, v]) => `${k}: ${v}`).join(', ')}
                                    </td>
                                    <td className="mono">{new Date(c.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}</td>
                                    <td className="mono">{new Date(c.updated_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>

                    {filtered.length === 0 && (
                        <div className="empty-state" style={{ padding: '60px 0' }}>
                            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="var(--color-gray-30)" strokeWidth="1.5" style={{ margin: '0 auto 16px' }}>
                                <rect x="6" y="6" width="36" height="36" rx="4" />
                                <line x1="14" y1="18" x2="34" y2="18" /><line x1="14" y1="24" x2="34" y2="24" /><line x1="14" y1="30" x2="26" y2="30" />
                            </svg>
                            <h3 style={{ fontSize: 16, color: 'var(--color-gray-90)', margin: '0 0 8px 0' }}>No {filter} cases found</h3>
                            <p style={{ fontSize: 14, color: 'var(--color-gray-50)', margin: '0 0 20px 0' }}>There are currently no investigations matching this status filter.</p>
                            <button className="btn btn-outline" onClick={() => { setFilter('all'); setPage(1); }}>View All Cases</button>
                        </div>
                    )}
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                    <div className="pagination" aria-label="Pagination">
                        <button className="pagination-btn" disabled={page === 1} onClick={() => setPage(p => p - 1)}>← Previous</button>
                        {Array.from({ length: totalPages }, (_, i) => (
                            <button key={i + 1} className={`pagination-btn ${page === i + 1 ? 'active' : ''}`} onClick={() => setPage(i + 1)}>
                                {i + 1}
                            </button>
                        ))}
                        <button className="pagination-btn" disabled={page === totalPages} onClick={() => setPage(p => p + 1)}>Next →</button>
                    </div>
                )}
            </div>
        </div>
    );
}
