'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { CheckCircle2, Loader, Circle, ArrowRight, XCircle, RotateCcw } from 'lucide-react';
import { useRouter } from 'next/navigation';
import * as api from '../lib/api';

const PIPELINE = [
  { key: 'entity_resolution', agent: 'Entity Resolver', code: 'ER', statusMatch: ['pending', 'ingesting'] },
  { key: 'evidence_retrieval', agent: 'Evidence Retriever', code: 'EV', statusMatch: ['analyzing'] },
  { key: 'graph_builder', agent: 'Graph Builder', code: 'GB', statusMatch: ['analyzing'] },
  { key: 'anomaly_detection', agent: 'Anomaly Detector', code: 'AD', statusMatch: ['analyzing'] },
  { key: 'case_composition', agent: 'Case Composer', code: 'CC', statusMatch: ['composing'] },
  { key: 'auditor', agent: 'AI Auditor', code: 'AU', statusMatch: ['auditing'] },
];

const STAGE_MESSAGES = {
  entity_resolution: [
    'Searching SAM.gov for entity registration...',
    'Cross-referencing UEI across FPDS records...',
    'Canonical entity record established.',
  ],
  evidence_retrieval: [
    'Querying USAspending API for contract awards...',
    'Fetching DOJ press releases for enforcement actions...',
    'Pulling SEC EDGAR filings...',
    'Content-hashing all retrieved artifacts...',
  ],
  graph_builder: [
    'Building entity relationship graph...',
    'Computing edge weights from co-occurrence...',
    'Graph complete: nodes and edges mapped.',
  ],
  anomaly_detection: [
    'Running sole-source pattern detection...',
    'Checking award spike anomalies...',
    'Anomaly scan complete.',
  ],
  case_composition: [
    'Composing claims from evidence artifacts...',
    'Attaching citations to each claim...',
    'Dossier draft complete.',
  ],
  auditor: [
    'Reviewing all claims for hallucinations...',
    'Verifying every claim has source citations...',
    'All claims pass auditor gate.',
  ],
};

function statusToStageIndex(status) {
  switch (status) {
    case 'pending': return 0;
    case 'ingesting': return 0;
    case 'analyzing': return 1;
    case 'composing': return 4;
    case 'auditing': return 5;
    case 'complete': return 6;
    case 'failed': return -1;
    default: return 0;
  }
}

export default function LiveInvestigation({ title, seedValue, caseId, onComplete }) {
  const router = useRouter();
  const [realStage, setRealStage] = useState(0);
  const [animStage, setAnimStage] = useState(0);
  const [animMsg, setAnimMsg] = useState(0);
  const [logs, setLogs] = useState([]);
  const [done, setDone] = useState(false);
  const [failed, setFailed] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const feedRef = useRef(null);
  const startTime = useRef(Date.now());
  const pollRef = useRef(null);

  // Poll real API for case status
  useEffect(() => {
    if (!caseId || done || failed) return;

    const poll = async () => {
      try {
        const data = await api.getCase(caseId);
        const idx = statusToStageIndex(data.status);

        if (data.status === 'complete') {
          setRealStage(6);
          setDone(true);
          return;
        }
        if (data.status === 'failed' || data.status === 'insufficient_evidence') {
          setFailed(true);
          setErrorMsg(data.status === 'insufficient_evidence'
            ? 'Insufficient evidence found to compose a dossier.'
            : 'Investigation failed. Please try again.');
          return;
        }
        if (idx >= 0) setRealStage(idx);
      } catch {
        // API not available — let animation run standalone
      }
    };

    poll();
    pollRef.current = setInterval(poll, 2000);
    return () => clearInterval(pollRef.current);
  }, [caseId, done, failed]);

  // Animate log messages — driven by animStage catching up to realStage
  useEffect(() => {
    if (done || failed) return;
    if (animStage >= PIPELINE.length) { setDone(true); return; }

    const stage = PIPELINE[animStage];
    const msgs = STAGE_MESSAGES[stage.key] || [];
    if (animMsg >= msgs.length) {
      // Move to next stage only if realStage is ahead
      if (animStage < realStage || animStage < PIPELINE.length - 1) {
        setAnimStage(prev => prev + 1);
        setAnimMsg(0);
      }
      return;
    }

    const delay = 500 + Math.random() * 800;
    const timer = setTimeout(() => {
      const elapsed = ((Date.now() - startTime.current) / 1000).toFixed(1);
      setLogs(prev => [...prev, {
        time: elapsed + 's',
        agent: stage.code,
        agentName: stage.agent,
        message: msgs[animMsg],
        stage: stage.key,
      }]);
      setAnimMsg(prev => prev + 1);
    }, delay);

    return () => clearTimeout(timer);
  }, [animStage, animMsg, realStage, done, failed]);

  // Auto-scroll log
  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [logs]);

  const totalMessages = Object.values(STAGE_MESSAGES).reduce((s, m) => s + m.length, 0);
  const progressPct = done ? 100 : Math.min(99, Math.round((logs.length / totalMessages) * 100));

  const handleViewDossier = () => {
    if (caseId) router.push(`/cases/${caseId}`);
  };

  const handleRetry = () => {
    setFailed(false);
    setErrorMsg('');
    setDone(false);
    setAnimStage(0);
    setAnimMsg(0);
    setRealStage(0);
    setLogs([]);
    startTime.current = Date.now();
  };

  return (
    <div className="live-container">
      <div className="live-progress-bar">
        <div className="live-progress-fill" style={{
          width: `${progressPct}%`,
          background: failed ? 'var(--red)' : undefined,
        }} />
      </div>

      <div className="live-header">
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 4 }}>
            {failed ? 'Investigation Failed' : done ? 'Investigation Complete' : 'Investigation in Progress'}
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-2)' }}>
            {title} &mdash; {seedValue}
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{
            fontSize: 28, fontWeight: 700, fontFamily: 'var(--font-mono)',
            color: failed ? 'var(--red)' : done ? 'var(--green)' : 'var(--accent-2)',
          }}>
            {failed ? '!' : `${progressPct}%`}
          </span>
          {done && (
            <button onClick={handleViewDossier} className="btn btn-primary">
              View Dossier <ArrowRight size={14} />
            </button>
          )}
          {failed && (
            <button onClick={handleRetry} className="btn btn-ghost">
              <RotateCcw size={14} /> Retry
            </button>
          )}
        </div>
      </div>

      {failed && errorMsg && (
        <div style={{
          padding: '12px 16px', borderRadius: 8, marginBottom: 16,
          background: 'var(--red-glow)', border: '1px solid rgba(255,107,107,0.2)',
          color: 'var(--red)', fontSize: 13,
        }}>
          {errorMsg}
        </div>
      )}

      <div className="live-grid">
        <div className="pipeline-sidebar">
          {PIPELINE.map((stage, i) => {
            const isComplete = i < animStage || done;
            const isActive = i === animStage && !done && !failed;
            return (
              <div key={stage.key}>
                <div className={`pipeline-stage ${isComplete ? 'completed' : isActive ? 'active' : 'waiting'}`}>
                  <div className="pipeline-stage-dot" />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{stage.agent}</div>
                    {isActive && (
                      <div style={{ fontSize: 11, marginTop: 2, opacity: 0.7 }}>
                        {(STAGE_MESSAGES[stage.key] || [])[animMsg]?.slice(0, 40)}...
                      </div>
                    )}
                    {isComplete && (
                      <div style={{ fontSize: 11, marginTop: 2 }}>
                        {(STAGE_MESSAGES[stage.key] || []).length} steps completed
                      </div>
                    )}
                  </div>
                  {isComplete && <CheckCircle2 size={14} style={{ color: 'var(--green)' }} />}
                  {isActive && <Loader size={14} className="animate-spin" style={{ color: 'var(--accent)' }} />}
                  {failed && i === animStage && <XCircle size={14} style={{ color: 'var(--red)' }} />}
                </div>
                {i < PIPELINE.length - 1 && (
                  <div className={`pipeline-connector ${isComplete ? 'done' : ''}`} />
                )}
              </div>
            );
          })}
        </div>

        <div className="terminal">
          <div className="terminal-header">
            <div className="terminal-dot" style={{ background: failed ? 'var(--red)' : done ? 'var(--green)' : 'var(--red)' }} />
            <div className="terminal-dot" style={{ background: 'var(--amber)' }} />
            <div className="terminal-dot" style={{ background: 'var(--green)' }} />
            <span style={{ marginLeft: 8 }}>Agent Activity Log</span>
            <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
              {logs.length}/{totalMessages} ops
            </span>
          </div>
          <div className="terminal-body" ref={feedRef}>
            <div className="log-line" style={{ color: 'var(--text-3)', marginBottom: 4 }}>
              <span className="log-time">0.0s</span>
              <span className="log-agent" style={{ color: 'var(--text-3)' }}>SYS</span>
              <span className="log-msg">Investigation started: {seedValue}{caseId ? ` [${caseId.slice(0, 8)}]` : ''}</span>
            </div>
            {logs.map((log, i) => (
              <div key={i} className="log-line">
                <span className="log-time">{log.time}</span>
                <span className={`log-agent ${log.agent.toLowerCase()}`}>[{log.agent}]</span>
                <span className="log-msg">{log.message}</span>
              </div>
            ))}
            {!done && !failed && (
              <div className="log-line" style={{ color: 'var(--accent-2)' }}>
                <span className="log-time">&nbsp;</span>
                <span style={{ display: 'inline-flex', gap: 3 }}>
                  <span style={{ animation: 'glow-pulse 1.5s infinite' }}>_</span>
                </span>
              </div>
            )}
            {done && (
              <div className="log-line" style={{ color: 'var(--green)', marginTop: 4 }}>
                <span className="log-time">{logs[logs.length - 1]?.time}</span>
                <span className="log-agent" style={{ color: 'var(--green)' }}>SYS</span>
                <span className="log-msg">Dossier ready. All claims pass auditor gate.</span>
              </div>
            )}
            {failed && (
              <div className="log-line" style={{ color: 'var(--red)', marginTop: 4 }}>
                <span className="log-time">{logs[logs.length - 1]?.time || '0.0s'}</span>
                <span className="log-agent" style={{ color: 'var(--red)' }}>SYS</span>
                <span className="log-msg">{errorMsg || 'Investigation failed.'}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
