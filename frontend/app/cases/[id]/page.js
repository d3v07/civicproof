'use client';

import { useState, useEffect, useMemo } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import { ArrowLeft, Download, Copy, ChevronDown, ChevronRight, ExternalLink, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';
import { mockCases, mockCasePack } from '../../lib/mock-data';
import * as api from '../../lib/api';
import { useToast } from '../../components/ToastProvider';

const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false });

function synthesizeGraph(claims, citations) {
  const nodeMap = new Map();
  const links = [];

  claims.forEach((claim) => {
    const entities = extractEntities(claim.statement);
    entities.forEach((name) => {
      if (!nodeMap.has(name)) {
        nodeMap.set(name, {
          id: name,
          name,
          type: claim.claim_type,
          val: 1,
        });
      } else {
        nodeMap.get(name).val += 1;
      }
    });

    for (let i = 0; i < entities.length; i++) {
      for (let j = i + 1; j < entities.length; j++) {
        links.push({ source: entities[i], target: entities[j], claim_id: claim.claim_id });
      }
    }
  });

  return { nodes: Array.from(nodeMap.values()), links };
}

function extractEntities(text) {
  const words = text.match(/[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*/g) || [];
  const stopwords = new Set(['The', 'This', 'That', 'These', 'Those', 'However', 'Although', 'While', 'During', 'Between', 'Within', 'Through', 'Federal', 'Contract', 'Award', 'Government']);
  return [...new Set(words.filter((w) => w.length > 2 && !stopwords.has(w)))].slice(0, 8);
}

const NODE_COLORS = {
  finding: '#22c55e',
  risk_signal: '#f59e0b',
  hypothesis: '#8b5cf6',
};

const STAGE_META = {
  intake: { agent: 'Data Engineer', color: '#3b82f6' },
  entity_resolution: { agent: 'Entity Resolver', color: '#22c55e' },
  evidence_retrieval: { agent: 'Evidence Retriever', color: '#f59e0b' },
  graph_builder: { agent: 'Graph Builder', color: '#8b5cf6' },
  graph_construction: { agent: 'Graph Builder', color: '#8b5cf6' },
  anomaly_detection: { agent: 'Anomaly Detector', color: '#ef4444' },
  case_composition: { agent: 'Case Composer', color: '#f97316' },
  audit: { agent: 'AI Auditor', color: '#dc2626' },
  auditor_review: { agent: 'AI Auditor', color: '#dc2626' },
  approval: { agent: 'AI Auditor', color: '#dc2626' },
};

function ConfidenceBar({ value }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.8 ? 'var(--green)' : value >= 0.5 ? 'var(--amber)' : 'var(--red)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 100 }}>
      <div style={{ flex: 1, height: 4, background: 'var(--bg-hover)', borderRadius: 2 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2, transition: 'width 300ms' }} />
      </div>
      <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-2)', minWidth: 32 }}>{pct}%</span>
    </div>
  );
}

function ClaimCard({ claim, citations, isOpen, onToggle }) {
  const claimCits = citations.filter((c) => c.claim_id === claim.claim_id);
  const typeClass = claim.claim_type === 'finding' ? 'badge-finding' : claim.claim_type === 'risk_signal' ? 'badge-risk_signal' : 'badge-hypothesis';

  return (
    <div className="card" style={{ marginBottom: 8, padding: 14 }}>
      <div style={{ cursor: 'pointer' }} onClick={onToggle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span className={`badge ${typeClass}`}>{claim.claim_type.replace('_', ' ')}</span>
              {claim.audit_passed && <CheckCircle2 size={13} style={{ color: 'var(--green)' }} />}
              <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-3)' }}>{claim.claim_id}</span>
              <span style={{ marginLeft: 'auto' }}>
                {isOpen ? <ChevronDown size={14} style={{ color: 'var(--text-3)' }} /> : <ChevronRight size={14} style={{ color: 'var(--text-3)' }} />}
              </span>
            </div>
            <p style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.6, margin: 0 }}>{claim.statement}</p>
          </div>
          <ConfidenceBar value={claim.confidence} />
        </div>
      </div>

      {isOpen && claimCits.length > 0 && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
            Citations ({claimCits.length})
          </div>
          {claimCits.map((cit) => (
            <div key={cit.citation_id} style={{ padding: '8px 12px', background: 'var(--bg-hover)', border: '1px solid var(--border)', borderRadius: 6, marginBottom: 6, fontSize: 13 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent)', marginBottom: 4 }}>
                {cit.artifact_id}
              </div>
              <div style={{ color: 'var(--text-2)', fontStyle: 'italic' }}>&ldquo;{cit.excerpt}&rdquo;</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function EntityGraph({ claims, citations }) {
  const graphData = useMemo(() => synthesizeGraph(claims, citations), [claims, citations]);

  if (graphData.nodes.length === 0) {
    return (
      <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-3)' }}>
        No entity relationships found in claims.
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden', borderRadius: 10 }}>
      <ForceGraph2D
        graphData={graphData}
        width={800}
        height={450}
        backgroundColor="#06060a"
        nodeLabel={(node) => `${node.name} (${node.type})`}
        nodeColor={(node) => NODE_COLORS[node.type] || '#6366f1'}
        nodeRelSize={6}
        nodeVal={(node) => node.val}
        linkColor={() => '#1a1a25'}
        linkWidth={1.5}
        linkDirectionalParticles={1}
        linkDirectionalParticleWidth={2}
        linkDirectionalParticleColor={() => '#6366f133'}
        nodeCanvasObject={(node, ctx, globalScale) => {
          const fontSize = Math.max(10 / globalScale, 3);
          const color = NODE_COLORS[node.type] || '#6366f1';
          const size = Math.sqrt(node.val || 1) * 4;

          ctx.beginPath();
          ctx.arc(node.x, node.y, size, 0, 2 * Math.PI);
          ctx.fillStyle = color + '33';
          ctx.fill();
          ctx.strokeStyle = color;
          ctx.lineWidth = 1.5 / globalScale;
          ctx.stroke();

          ctx.fillStyle = '#e4e4e7';
          ctx.font = `${fontSize}px sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillText(node.name, node.x, node.y + size + 2);
        }}
        cooldownTicks={60}
      />
    </div>
  );
}

export default function CaseDetailPage() {
  const params = useParams();
  const [caseData, setCaseData] = useState(null);
  const [pack, setPack] = useState(null);
  const [openClaim, setOpenClaim] = useState(null);
  const [activeTab, setActiveTab] = useState('findings');
  const { addToast } = useToast();

  useEffect(() => {
    async function load() {
      try {
        const c = await api.getCase(params.id);
        setCaseData(c);
        const p = await api.getCasePack(params.id);
        setPack(p);
      } catch {
        setCaseData(mockCases.find((c) => c.case_id === params.id) || mockCases[0]);
        setPack(mockCasePack);
      }
    }
    load();
  }, [params.id]);

  if (!caseData || !pack) {
    return (
      <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-3)' }}>Loading case...</div>
    );
  }

  const findings = pack.claims.filter((c) => c.claim_type === 'finding');
  const riskSignals = pack.claims.filter((c) => c.claim_type === 'risk_signal');
  const hypotheses = pack.claims.filter((c) => c.claim_type === 'hypothesis');

  const handleCopy = () => {
    navigator.clipboard.writeText(window.location.href);
    addToast({ message: 'Link copied', type: 'success' });
  };

  const handleExport = async () => {
    try {
      const pdfBlob = await api.getCasePackPdf(params.id);
      const url = URL.createObjectURL(pdfBlob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `civicproof_${caseData.case_id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      addToast({ message: 'PDF exported', type: 'success' });
    } catch {
      const blob = new Blob([JSON.stringify(pack, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `civicproof_${caseData.case_id}.json`;
      a.click();
      URL.revokeObjectURL(url);
      addToast({ message: 'Exported as JSON (PDF unavailable)', type: 'info' });
    }
  };

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <Link href="/cases" style={{ fontSize: 12, color: 'var(--text-3)', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4, marginBottom: 12 }}>
          <ArrowLeft size={12} /> Back to Cases
        </Link>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 6 }}>{caseData.title}</h1>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span className={`badge badge-${caseData.status}`}>{caseData.status}</span>
              <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-3)' }}>{caseData.case_id}</span>
              <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
                {new Date(caseData.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
              </span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn btn-ghost btn-sm" onClick={handleCopy}><Copy size={13} /> Share</button>
            <button className="btn btn-ghost btn-sm" onClick={handleExport}><Download size={13} /> Export</button>
          </div>
        </div>
      </div>

      {/* Pipeline progress */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 24, overflowX: 'auto' }}>
        {pack.audit_events.map((event, i) => {
          const meta = STAGE_META[event.stage] || { agent: 'System', color: '#71717a' };
          const passed = event.policy_decision === 'accepted' || event.policy_decision === 'approved';
          return (
            <div key={event.audit_event_id} style={{ display: 'contents' }}>
              {i > 0 && <div className="pipeline-connector" />}
              <div className={`pipeline-step done`} style={{ borderColor: passed ? meta.color + '33' : 'var(--red-glow)', background: passed ? meta.color + '15' : 'var(--red-glow)', color: passed ? meta.color : 'var(--red)' }}>
                {passed ? <CheckCircle2 size={10} /> : <XCircle size={10} />}
                {event.stage.replace(/_/g, ' ')}
              </div>
            </div>
          );
        })}
      </div>

      {/* Summary stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 24 }}>
        <div className="card" style={{ padding: 14, textAlign: 'center' }}>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{pack.claims.length}</div>
          <div style={{ fontSize: 12, color: 'var(--text-3)' }}>Claims</div>
        </div>
        <div className="card" style={{ padding: 14, textAlign: 'center' }}>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{pack.citations.length}</div>
          <div style={{ fontSize: 12, color: 'var(--text-3)' }}>Citations</div>
        </div>
        <div className="card" style={{ padding: 14, textAlign: 'center' }}>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{pack.audit_events.length}</div>
          <div style={{ fontSize: 12, color: 'var(--text-3)' }}>Pipeline Steps</div>
        </div>
        <div className="card" style={{ padding: 14, textAlign: 'center' }}>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-mono)', fontSize: 14, wordBreak: 'break-all' }}>{pack.pack_hash?.slice(0, 16)}</div>
          <div style={{ fontSize: 12, color: 'var(--text-3)' }}>Pack Hash</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs">
        <button className={`tab ${activeTab === 'findings' ? 'active' : ''}`} onClick={() => setActiveTab('findings')}>
          Findings ({findings.length})
        </button>
        <button className={`tab ${activeTab === 'risks' ? 'active' : ''}`} onClick={() => setActiveTab('risks')}>
          Risk Signals ({riskSignals.length})
        </button>
        <button className={`tab ${activeTab === 'hypotheses' ? 'active' : ''}`} onClick={() => setActiveTab('hypotheses')}>
          Hypotheses ({hypotheses.length})
        </button>
        <button className={`tab ${activeTab === 'graph' ? 'active' : ''}`} onClick={() => setActiveTab('graph')}>
          Entity Graph
        </button>
        <button className={`tab ${activeTab === 'audit' ? 'active' : ''}`} onClick={() => setActiveTab('audit')}>
          Audit Trail
        </button>
      </div>

      {/* Entity Graph */}
      {activeTab === 'graph' && (
        <EntityGraph claims={pack.claims} citations={pack.citations} />
      )}

      {/* Claims */}
      {activeTab !== 'audit' && activeTab !== 'graph' && (
        <div>
          {(activeTab === 'findings' ? findings : activeTab === 'risks' ? riskSignals : hypotheses).map((claim) => (
            <ClaimCard
              key={claim.claim_id}
              claim={claim}
              citations={pack.citations}
              isOpen={openClaim === claim.claim_id}
              onToggle={() => setOpenClaim(openClaim === claim.claim_id ? null : claim.claim_id)}
            />
          ))}
        </div>
      )}

      {/* Audit trail */}
      {activeTab === 'audit' && (
        <div className="card" style={{ padding: 0 }}>
          {pack.audit_events.map((event, i) => {
            const meta = STAGE_META[event.stage] || { agent: 'System', color: '#71717a' };
            return (
              <div key={event.audit_event_id} style={{ display: 'flex', gap: 12, padding: '12px 16px', borderBottom: i < pack.audit_events.length - 1 ? '1px solid var(--border)' : 'none' }}>
                <div className="agent-avatar" style={{ width: 28, height: 28, backgroundColor: meta.color, fontSize: 10 }}>
                  {meta.agent.split(' ').map(w => w[0]).join('')}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{meta.agent}</span>
                    <span style={{ fontSize: 12, color: 'var(--text-3)' }}>{event.stage.replace(/_/g, ' ')}</span>
                    <span className={`badge badge-${event.policy_decision}`}>{event.policy_decision}</span>
                    <span style={{ marginLeft: 'auto', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-3)' }}>
                      {new Date(event.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </span>
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{event.detail}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Disclaimer */}
      <div style={{ marginTop: 24, padding: '12px 16px', borderRadius: 8, background: 'var(--amber-glow)', border: '1px solid rgba(245,158,11,0.2)' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
          <AlertTriangle size={14} style={{ color: 'var(--amber)', flexShrink: 0, marginTop: 2 }} />
          <div style={{ fontSize: 12, color: 'var(--amber)', lineHeight: 1.5 }}>
            This document contains risk signals and hypotheses from publicly available data. It does not constitute an accusation of wrongdoing. All findings require independent corroboration.
          </div>
        </div>
      </div>
    </div>
  );
}
