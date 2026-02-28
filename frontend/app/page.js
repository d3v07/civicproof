'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Search, ArrowRight, Clock, Shield, Zap, Database } from 'lucide-react';
import { mockCases } from './lib/mock-data';
import * as api from './lib/api';

export default function HomePage() {
  const [query, setQuery] = useState('');
  const [cases, setCases] = useState([]);
  const router = useRouter();

  useEffect(() => {
    api.listCases(1, 5)
      .then((data) => setCases(data.items || data))
      .catch(() => setCases(mockCases));
  }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    if (query.trim()) {
      router.push(`/investigate?q=${encodeURIComponent(query.trim())}`);
    }
  };

  const suggestions = ['Acme Defense Solutions', 'GLBTCH1234', 'SPE4A121D0042', 'Meridian Logistics'];

  return (
    <div style={{ maxWidth: 680, margin: '0 auto', paddingTop: 80 }}>
      {/* Hero */}
      <div style={{ marginBottom: 40 }}>
        <h1 style={{ fontSize: 36, fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1.1, marginBottom: 12 }}>
          Trace federal spending.
          <br />
          <span style={{ color: 'var(--accent-2)' }}>Surface what matters.</span>
        </h1>
        <p style={{ fontSize: 15, color: 'var(--text-2)', lineHeight: 1.6, maxWidth: 520 }}>
          Search 6 federal data sources. AI agents resolve entities, build evidence
          graphs, and surface risk signals — every claim cited, every step audited.
        </p>
      </div>

      {/* Search */}
      <form onSubmit={handleSearch} style={{ marginBottom: 12 }}>
        <div className="search-wrap">
          <span className="search-icon"><Search size={17} /></span>
          <input
            className="search-input"
            style={{ padding: '14px 14px 14px 44px', fontSize: 15 }}
            placeholder="Company name, UEI, CAGE code, or award ID..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
        </div>
      </form>

      <div style={{ display: 'flex', gap: 6, marginBottom: 56, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)', padding: '4px 0' }}>Try:</span>
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => { setQuery(s); }}
            style={{
              padding: '4px 12px', borderRadius: 20, fontSize: 12, cursor: 'pointer',
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              color: 'var(--text-2)', transition: 'all 100ms',
            }}
            onMouseEnter={(e) => { e.target.style.borderColor = 'var(--accent)'; e.target.style.color = 'var(--accent-2)'; }}
            onMouseLeave={(e) => { e.target.style.borderColor = 'var(--border)'; e.target.style.color = 'var(--text-2)'; }}
          >
            {s}
          </button>
        ))}
      </div>

      {/* How it works */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 48 }}>
        {[
          { icon: Database, label: 'Search', sub: '6 sources queried' },
          { icon: Zap, label: 'Analyze', sub: '6 AI agents' },
          { icon: Shield, label: 'Audit', sub: 'Every claim cited' },
        ].map((s) => (
          <div key={s.label} style={{
            padding: '16px', borderRadius: 10,
            border: '1px solid var(--border)', background: 'var(--bg-card)',
            textAlign: 'center',
          }}>
            <s.icon size={20} style={{ color: 'var(--accent)', marginBottom: 8 }} strokeWidth={1.5} />
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 2 }}>{s.label}</div>
            <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{s.sub}</div>
          </div>
        ))}
      </div>

      {/* Recent */}
      {cases.length > 0 && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-3)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Clock size={13} /> Recent
            </h2>
            <Link href="/cases" style={{ fontSize: 12, color: 'var(--accent-2)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
              All cases <ArrowRight size={11} />
            </Link>
          </div>
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            {cases.slice(0, 5).map((c, i) => (
              <Link
                key={c.case_id}
                href={`/cases/${c.case_id}`}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '11px 14px',
                  borderBottom: i < Math.min(cases.length, 5) - 1 ? '1px solid var(--border)' : 'none',
                  textDecoration: 'none', color: 'inherit', transition: 'background 80ms',
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-hover)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
              >
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{c.title}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>{c.case_id}</div>
                </div>
                <span className={`badge badge-${c.status}`}>{c.status}</span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
