'use client';

import { useState } from 'react';
import { Database, RefreshCw, CheckCircle2, Clock, Zap } from 'lucide-react';
import { mockSources } from '../lib/mock-data';
import * as api from '../lib/api';
import { useToast } from '../components/ToastProvider';

function SourceCard({ source }) {
  const [syncing, setSyncing] = useState(false);
  const { addToast } = useToast();

  const handleSync = async () => {
    setSyncing(true);
    try {
      await api.triggerIngest(source.source_id);
      addToast({ message: `Sync triggered: ${source.name}`, type: 'success' });
    } catch {
      addToast({ message: `Sync triggered: ${source.name} (demo)`, type: 'success' });
    }
    setTimeout(() => setSyncing(false), 2000);
  };

  const lastRun = new Date(source.last_run);
  const hoursAgo = Math.round((Date.now() - lastRun.getTime()) / (1000 * 60 * 60));

  return (
    <div className="card" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>{source.name}</div>
          <span className="badge badge-active">{source.status}</span>
        </div>
        <div style={{ width: 36, height: 36, borderRadius: 8, background: 'var(--color-accent-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Database size={16} style={{ color: 'var(--color-accent)' }} />
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 12 }}>
        <div>
          <div style={{ color: 'var(--color-text-muted)', marginBottom: 2 }}>Rate Limit</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{source.rate_limit}</div>
        </div>
        <div>
          <div style={{ color: 'var(--color-text-muted)', marginBottom: 2 }}>Schedule</div>
          <div style={{ fontWeight: 600 }}>{source.schedule}</div>
        </div>
        <div>
          <div style={{ color: 'var(--color-text-muted)', marginBottom: 2 }}>Artifacts</div>
          <div style={{ fontWeight: 600 }}>{source.artifacts_total.toLocaleString()}</div>
        </div>
        <div>
          <div style={{ color: 'var(--color-text-muted)', marginBottom: 2 }}>Last Sync</div>
          <div style={{ fontWeight: 600 }}>{hoursAgo}h ago</div>
        </div>
      </div>

      <button
        className={`btn ${syncing ? 'btn-ghost' : 'btn-primary'} btn-sm`}
        style={{ width: '100%', marginTop: 'auto' }}
        onClick={handleSync}
        disabled={syncing}
      >
        <RefreshCw size={12} className={syncing ? 'animate-spin' : ''} />
        {syncing ? 'Syncing...' : 'Trigger Sync'}
      </button>
    </div>
  );
}

export default function SourcesPage() {
  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 4 }}>Data Sources</h1>
        <p style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
          {mockSources.length} federal data connectors — rate-limited, idempotent, content-hashed
        </p>
      </div>

      <div className="source-grid" style={{ marginBottom: 32 }}>
        {mockSources.map((s) => <SourceCard key={s.source_id} source={s} />)}
      </div>

      <div className="card">
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: 12 }}>Rate Limit Compliance</div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Source</th>
              <th>Limit</th>
              <th>Auth</th>
              <th>Schedule</th>
              <th>Total Artifacts</th>
            </tr>
          </thead>
          <tbody>
            {mockSources.map((s) => (
              <tr key={s.source_id}>
                <td style={{ fontWeight: 600, color: 'var(--color-text)' }}>{s.name}</td>
                <td style={{ fontFamily: 'var(--font-mono)' }}>{s.rate_limit}</td>
                <td>
                  {['sam_gov', 'openfec'].includes(s.source_id)
                    ? <span className="badge badge-risk_signal">API Key</span>
                    : <span className="badge badge-finding">Public</span>}
                </td>
                <td style={{ fontFamily: 'var(--font-mono)' }}>{s.schedule}</td>
                <td style={{ fontFamily: 'var(--font-mono)' }}>{s.artifacts_total.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
