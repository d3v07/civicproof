'use client';

import { useEffect, useState } from 'react';
import { mockCases } from './lib/mock-data';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { AgentProgressInline } from './components/AgentActivity';

export default function HomePage() {
  const [cases, setCases] = useState([]);
  const [query, setQuery] = useState('');
  const router = useRouter();

  useEffect(() => {
    setCases(mockCases);
  }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    if (query.trim()) {
      router.push(`/investigate?q=${encodeURIComponent(query.trim())}`);
    }
  };

  const activeCases = cases.filter(c => c.status === 'processing');
  const completedCases = cases.filter(c => c.status === 'complete');

  return (
    <div>
      {/* Search-first hero */}
      <div className="home-hero">
        <h1 className="home-hero-title">Research public spending data</h1>
        <form onSubmit={handleSearch} className="home-search-form">
          <div className="search-container" style={{ maxWidth: 640 }}>
            <span className="search-icon" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="8" cy="8" r="5.5" /><line x1="12" y1="12" x2="16" y2="16" />
              </svg>
            </span>
            <input
              className="search-input"
              placeholder="Enter a company name, UEI, CAGE code, or award ID..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search federal entities"
              autoFocus
            />
          </div>
        </form>
      </div>

      <div className="page-body">
        {/* Active investigations */}
        {activeCases.length > 0 && (
          <div className="home-section">
            <div className="home-section-header">
              <h2 className="home-section-title">In Progress</h2>
              <span className="home-section-count">{activeCases.length}</span>
            </div>
            {activeCases.map((c) => (
              <Link key={c.case_id} href={`/cases/${c.case_id}`} className="case-row">
                <div className="case-row-main">
                  <span className="case-row-title">{c.title}</span>
                  <span className="case-row-meta">{Object.values(c.seed_input).join(' · ')}</span>
                  <AgentProgressInline caseId={c.case_id} />
                </div>
                <div className="case-row-right">
                  <span className={`badge badge-${c.status}`}>{c.status}</span>
                  <span className="case-row-date">{new Date(c.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
                </div>
              </Link>
            ))}
          </div>
        )}

        {/* Completed */}
        {completedCases.length > 0 && (
          <div className="home-section">
            <div className="home-section-header">
              <h2 className="home-section-title">Completed</h2>
              <span className="home-section-count">{completedCases.length}</span>
            </div>
            {completedCases.map((c) => (
              <Link key={c.case_id} href={`/cases/${c.case_id}`} className="case-row">
                <div className="case-row-main">
                  <span className="case-row-title">{c.title}</span>
                  <span className="case-row-meta">{Object.values(c.seed_input).join(' · ')}</span>
                </div>
                <div className="case-row-right">
                  <span className={`badge badge-${c.status}`}>{c.status}</span>
                  <span className="case-row-date">{new Date(c.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
                </div>
              </Link>
            ))}
          </div>
        )}

        {cases.length === 0 && (
          <div className="empty-state" style={{ padding: '80px 0', maxWidth: 480, margin: '0 auto' }}>
            <svg width="64" height="64" viewBox="0 0 64 64" fill="none" stroke="var(--color-primary-light)" strokeWidth="1.5" style={{ marginBottom: 24 }}>
              <circle cx="28" cy="28" r="16" />
              <line x1="39" y1="39" x2="56" y2="56" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--color-gray-90)', margin: '0 0 12px 0' }}>Start Your First Research Query</h2>
            <p style={{ fontSize: 15, color: 'var(--color-gray-60)', margin: '0 0 24px 0', lineHeight: 1.6 }}>
              CivicProof analyzes publicly available federal spending data, retrieves evidence, and maps entity relationships.
            </p>
            <div style={{ textAlign: 'left', background: 'var(--color-gray-2)', border: '1px solid var(--color-gray-10)', borderRadius: 'var(--radius)', padding: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--color-gray-50)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 12 }}>Try searching for a demo entity:</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {['Acme Corp', 'SpaceX', 'Palantir Technologies', '0445R8M2N'].map(chip => (
                  <button
                    key={chip}
                    className="badge badge-handling"
                    style={{ background: 'var(--color-white)', border: '1px solid var(--color-gray-20)', color: 'var(--color-primary-dark)', cursor: 'pointer', fontSize: 13, padding: '6px 14px' }}
                    onClick={() => {
                      setQuery(chip);
                      document.querySelector('.search-input').focus();
                    }}
                  >
                    {chip}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
