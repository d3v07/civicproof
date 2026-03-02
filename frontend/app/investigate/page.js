'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { Search, Plus, ArrowRight, Building2, User, Landmark } from 'lucide-react';
import { mockEntities } from '../lib/mock-data';
import * as api from '../lib/api';
import { useToast } from '../components/ToastProvider';
import LiveInvestigation from '../components/LiveInvestigation';

const TYPE_ICONS = { vendor: Building2, agency: Landmark, person: User };

function NewCaseModal({ onClose, onLaunch }) {
  const [title, setTitle] = useState('');
  const [seedType, setSeedType] = useState('vendor_name');
  const [seedValue, setSeedValue] = useState('');
  const [error, setError] = useState('');

  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title.trim() || !seedValue.trim()) { setError('Title and seed value are required.'); return; }
    setSubmitting(true);
    let caseId = null;
    try {
      const data = await api.createCase(title, { [seedType]: seedValue });
      caseId = data.case_id;
    } catch {
      // API unavailable — launch without real caseId
    }
    onLaunch({ title, seedValue, caseId });
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>Start Research</h2>
        <p style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 20, lineHeight: 1.5 }}>
          Provide a seed identifier. 6 agents will search federal data sources and compose a cited dossier.
        </p>
        {error && <div style={{ padding: '8px 12px', borderRadius: 6, background: 'var(--red-glow)', color: 'var(--red)', fontSize: 13, marginBottom: 12 }}>{error}</div>}
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 14 }}>
            <label className="form-label">Reference Title</label>
            <input className="form-input" placeholder="e.g., Acme Corp — Sole Source Analysis" value={title} onChange={(e) => { setTitle(e.target.value); setError(''); }} autoFocus />
          </div>
          <div style={{ marginBottom: 14 }}>
            <label className="form-label">Identifier Type</label>
            <select className="form-select" value={seedType} onChange={(e) => setSeedType(e.target.value)}>
              <option value="vendor_name">Vendor Name</option>
              <option value="uei">UEI (12-char)</option>
              <option value="cage_code">CAGE Code (5-char)</option>
              <option value="award_id">Federal Award ID</option>
            </select>
          </div>
          <div style={{ marginBottom: 20 }}>
            <label className="form-label">Seed Value</label>
            <input className="form-input" placeholder="Enter identifier..." value={seedValue} onChange={(e) => { setSeedValue(e.target.value); setError(''); }} />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Launching...' : 'Launch Research'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function InvestigateContent() {
  const searchParams = useSearchParams();
  const initialQ = searchParams.get('q') || '';
  const [query, setQuery] = useState(initialQ);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [liveSession, setLiveSession] = useState(null);
  const { addToast } = useToast();

  useEffect(() => { if (initialQ) doSearch(initialQ); }, [initialQ]);

  async function doSearch(q) {
    setLoading(true);
    try {
      const data = await api.searchEntities(q);
      setResults(data?.items || []);
    } catch {
      const filtered = mockEntities.items.filter((e) =>
        e.canonical_name.toLowerCase().includes(q.toLowerCase()) || e.uei === q || e.cage_code === q
      );
      setResults(filtered);
    }
    setLoading(false);
  }

  const handleSearch = (e) => {
    e.preventDefault();
    if (query.trim()) doSearch(query.trim());
    else setResults(mockEntities.items);
  };

  const handleLaunch = ({ title, seedValue, caseId }) => {
    setLiveSession({ title, seedValue, caseId });
    addToast({ message: `Research launched: ${title}`, type: 'success' });
  };

  // Show live investigation view
  if (liveSession) {
    return (
      <LiveInvestigation
        title={liveSession.title}
        seedValue={liveSession.seedValue}
        caseId={liveSession.caseId}
        onComplete={() => setLiveSession(null)}
      />
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 4 }}>Investigate</h1>
          <p style={{ fontSize: 13, color: 'var(--text-3)' }}>Search entity records or launch a new research query</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
          <Plus size={14} /> New Research
        </button>
      </div>

      <form onSubmit={handleSearch} style={{ marginBottom: 24 }}>
        <div className="search-wrap">
          <span className="search-icon"><Search size={16} /></span>
          <input className="search-input" placeholder="Search by vendor name, UEI, CAGE code..." value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
      </form>

      {loading && <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-3)' }}>Searching...</div>}

      {!loading && results.length > 0 && (
        <div>
          <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 10 }}>
            {results.length} result{results.length !== 1 ? 's' : ''}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {results.map((entity) => {
              const Icon = TYPE_ICONS[entity.entity_type] || Building2;
              return (
                <div key={entity.entity_id} className="card" style={{ padding: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                    <div style={{ width: 34, height: 34, borderRadius: 7, background: 'var(--bg-hover)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <Icon size={15} style={{ color: 'var(--text-3)' }} />
                    </div>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 600 }}>{entity.canonical_name}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
                        {entity.uei && `UEI: ${entity.uei}`}
                        {entity.uei && entity.cage_code && ' · '}
                        {entity.cage_code && `CAGE: ${entity.cage_code}`}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className={`badge badge-${entity.entity_type === 'vendor' ? 'finding' : 'hypothesis'}`}>{entity.entity_type}</span>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={async () => {
                        let caseId = null;
                        try {
                          const data = await api.createCase(`${entity.canonical_name} — Investigation`, { vendor_name: entity.canonical_name });
                          caseId = data.case_id;
                        } catch { /* API unavailable */ }
                        handleLaunch({ title: `${entity.canonical_name} — Investigation`, seedValue: entity.canonical_name, caseId });
                      }}
                    >
                      Investigate <ArrowRight size={12} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!loading && results.length === 0 && query && (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-3)' }}>
          <div style={{ fontSize: 15, marginBottom: 8 }}>No results for &ldquo;{query}&rdquo;</div>
          <div style={{ fontSize: 13 }}>Try a different term or <button onClick={() => setShowModal(true)} style={{ color: 'var(--accent-2)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>launch a new research query</button></div>
        </div>
      )}

      {showModal && <NewCaseModal onClose={() => setShowModal(false)} onLaunch={handleLaunch} />}
    </div>
  );
}

export default function InvestigatePage() {
  return (
    <Suspense fallback={<div style={{ padding: 40, color: 'var(--text-3)' }}>Loading...</div>}>
      <InvestigateContent />
    </Suspense>
  );
}
