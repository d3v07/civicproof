'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Plus } from 'lucide-react';
import { mockCases } from '../lib/mock-data';
import * as api from '../lib/api';

export default function CasesPage() {
  const [filter, setFilter] = useState('all');
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    api.listCases()
      .then((data) => setCases(data.items || data))
      .catch(() => setCases(mockCases))
      .finally(() => setLoading(false));
  }, []);

  const filtered = filter === 'all' ? cases : cases.filter((c) => c.status === filter);

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
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-3)' }}>
          <div style={{ fontSize: 13 }}>Loading...</div>
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
                <th>Opened</th>
                <th>Updated</th>
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
