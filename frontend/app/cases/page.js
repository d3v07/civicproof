'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Plus, AlertTriangle } from 'lucide-react';
import * as api from '../lib/api';

export default function CasesPage() {
  const [filter, setFilter] = useState('all');
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sortField, setSortField] = useState('updated_at');
  const [sortDir, setSortDir] = useState('desc');
  const router = useRouter();

  useEffect(() => {
    api.listCases()
      .then((data) => setCases(data.items || data))
      .catch((e) => setError(e.message || 'Failed to load cases'))
      .finally(() => setLoading(false));
  }, []);

  const sorted = [...cases].sort((a, b) => {
    const aVal = a[sortField] || '';
    const bVal = b[sortField] || '';
    return sortDir === 'desc' ? (bVal > aVal ? 1 : -1) : (aVal > bVal ? 1 : -1);
  });
  const filtered = filter === 'all' ? sorted : sorted.filter((c) => c.status === filter);

  const counts = {
    all: cases.length,
    complete: cases.filter(c => c.status === 'complete').length,
    processing: cases.filter(c => c.status === 'processing').length,
    blocked: cases.filter(c => c.status === 'blocked').length,
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 4 }}>Cases</h1>
          <p style={{ fontSize: 13, color: 'var(--text-3)' }}>
            {cases.length} investigation{cases.length !== 1 ? 's' : ''} total
          </p>
        </div>
        <Link href="/investigate" className="btn btn-primary" style={{ textDecoration: 'none' }}>
          <Plus size={14} /> New Research
        </Link>
      </div>

      <div className="tabs">
        {Object.entries(counts).map(([key, count]) => (
          <button
            key={key}
            className={`tab ${filter === key ? 'active' : ''}`}
            onClick={() => setFilter(key)}
          >
            {key === 'all' ? 'All' : key.charAt(0).toUpperCase() + key.slice(1)} ({count})
          </button>
        ))}
      </div>

      {loading ? (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          {[...Array(5)].map((_, i) => (
            <div key={i} style={{ display: 'flex', gap: 16, padding: '14px 16px', borderBottom: '1px solid var(--border)' }}>
              <div style={{ flex: 2 }}>
                <div style={{ height: 14, width: '60%', background: 'var(--bg-hover)', borderRadius: 4, marginBottom: 6 }} className="skeleton-pulse" />
                <div style={{ height: 10, width: '30%', background: 'var(--bg-hover)', borderRadius: 4 }} className="skeleton-pulse" />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ height: 14, width: '40%', background: 'var(--bg-hover)', borderRadius: 4 }} className="skeleton-pulse" />
              </div>
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="card" style={{ padding: 40, textAlign: 'center' }}>
          <AlertTriangle size={20} style={{ color: 'var(--amber)', marginBottom: 8 }} />
          <div style={{ fontSize: 14, color: 'var(--text-2)', marginBottom: 4 }}>Unable to load cases</div>
          <div style={{ fontSize: 12, color: 'var(--text-3)' }}>{error}</div>
        </div>
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-3)' }}>
          <div style={{ fontSize: 15, marginBottom: 8 }}>No {filter === 'all' ? '' : filter + ' '}cases found</div>
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Case</th>
                <th>Status</th>
                <th>Seed</th>
                <th style={{ cursor: 'pointer' }} onClick={() => { setSortField('created_at'); setSortDir(sortField === 'created_at' && sortDir === 'desc' ? 'asc' : 'desc'); }}>
                  Opened {sortField === 'created_at' ? (sortDir === 'desc' ? '\u25BE' : '\u25B4') : ''}
                </th>
                <th style={{ cursor: 'pointer' }} onClick={() => { setSortField('updated_at'); setSortDir(sortField === 'updated_at' && sortDir === 'desc' ? 'asc' : 'desc'); }}>
                  Updated {sortField === 'updated_at' ? (sortDir === 'desc' ? '\u25BE' : '\u25B4') : ''}
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr
                  key={c.case_id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => router.push(`/cases/${c.case_id}`)}
                >
                  <td>
                    <div style={{ fontWeight: 600, color: 'var(--text)' }}>{c.title}</div>
                    <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-3)', marginTop: 2 }}>{c.case_id}</div>
                  </td>
                  <td><span className={`badge badge-${c.status}`}>{c.status}</span></td>
                  <td style={{ fontSize: 12, fontFamily: 'var(--font-mono)' }}>
                    {Object.values(c.seed_input).join(', ')}
                  </td>
                  <td style={{ fontSize: 12, fontFamily: 'var(--font-mono)' }}>
                    {new Date(c.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  </td>
                  <td style={{ fontSize: 12, fontFamily: 'var(--font-mono)' }}>
                    {new Date(c.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
