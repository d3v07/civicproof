'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Search, ArrowRight, Clock, Shield, Zap } from 'lucide-react';
import { mockCases } from './lib/mock-data';
import * as api from './lib/api';

export default function HomePage() {
  const [query, setQuery] = useState('');
  const [cases, setCases] = useState([]);
  const router = useRouter();

  useEffect(() => {
    async function load() {
      try {
        const data = await api.searchEntities('', null, 1, 5);
        if (data?.items) setCases(data.items);
      } catch {
        setCases(mockCases);
      }
    }
    load();
  }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    if (query.trim()) {
      router.push(`/investigate?q=${encodeURIComponent(query.trim())}`);
    }
  };

  const suggestions = ['Acme Defense Solutions', 'GLBTCH1234', 'SPE4A121D0042'];

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', paddingTop: 80 }}>
      <h1 style={{ fontSize: 32, fontWeight: 700, letterSpacing: '-0.03em', marginBottom: 8 }}>
        Research public spending data
      </h1>
      <p style={{ fontSize: 15, color: 'var(--color-text-secondary)', marginBottom: 32, lineHeight: 1.6 }}>
        Enter a company name, UEI, CAGE code, or award ID. CivicProof will search
        6 federal data sources, map entity relationships, and surface risk signals.
      </p>

      <form onSubmit={handleSearch}>
        <div className="search-wrap" style={{ marginBottom: 12 }}>
          <span className="search-icon"><Search size={16} /></span>
          <input
            className="search-input"
            style={{ padding: '14px 14px 14px 40px', fontSize: 15, borderRadius: 10 }}
            placeholder="Search vendor, UEI, CAGE, or award ID..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
        </div>
      </form>

      <div style={{ display: 'flex', gap: 6, marginBottom: 48, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12, color: 'var(--color-text-muted)', padding: '4px 0' }}>Try:</span>
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => { setQuery(s); }}
            className="btn-ghost btn-sm"
            style={{ borderRadius: 20, fontSize: 12, padding: '4px 12px', cursor: 'pointer', background: 'var(--color-surface-2)', border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
          >
            {s}
          </button>
        ))}
      </div>

      {/* How it works - subtle, not a dashboard */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 48 }}>
        {[
          { icon: Search, title: 'Search', desc: '6 federal data sources queried in parallel' },
          { icon: Zap, title: 'Analyze', desc: 'AI agents resolve entities, build evidence graphs' },
          { icon: Shield, title: 'Audit', desc: 'Every claim cited, every step logged' },
        ].map((step) => (
          <div key={step.title} style={{ padding: 16, borderRadius: 10, border: '1px solid var(--color-border)', background: 'var(--color-surface)' }}>
            <step.icon size={18} style={{ color: 'var(--color-accent)', marginBottom: 10 }} strokeWidth={1.8} />
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{step.title}</div>
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)', lineHeight: 1.5 }}>{step.desc}</div>
          </div>
        ))}
      </div>

      {/* Recent cases */}
      {cases.length > 0 && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h2 style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text-secondary)' }}>
              <Clock size={14} style={{ marginRight: 6, verticalAlign: -2 }} />
              Recent Investigations
            </h2>
            <Link href="/cases" style={{ fontSize: 12, color: 'var(--color-accent)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
              View all <ArrowRight size={12} />
            </Link>
          </div>
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            {cases.slice(0, 5).map((c, i) => (
              <Link
                key={c.case_id || i}
                href={`/cases/${c.case_id}`}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '12px 16px', borderBottom: i < 4 ? '1px solid var(--color-border)' : 'none',
                  textDecoration: 'none', color: 'inherit', transition: 'background 80ms',
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = 'var(--color-surface-2)'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
              >
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{c.title || c.canonical_name}</div>
                  <div style={{ fontSize: 12, color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
                    {c.case_id || c.entity_id}
                  </div>
                </div>
                <span className={`badge badge-${c.status || 'active'}`}>{c.status || c.entity_type}</span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
