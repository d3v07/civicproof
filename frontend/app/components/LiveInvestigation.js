'use client';

import { useState, useEffect, useRef } from 'react';
import { CheckCircle2, Loader, Circle, ArrowRight } from 'lucide-react';
import Link from 'next/link';

const PIPELINE = [
  {
    key: 'entity_resolution', agent: 'Entity Resolver', code: 'ER',
    messages: [
      'Searching SAM.gov for entity registration...',
      'Cross-referencing UEI across FPDS records...',
      'Resolving subsidiary and parent relationships...',
      'Matching CAGE codes to known entities...',
      'Canonical entity record established.',
    ],
  },
  {
    key: 'evidence_retrieval', agent: 'Evidence Retriever', code: 'EV',
    messages: [
      'Querying USAspending API for contract awards...',
      'Fetching DOJ press releases for enforcement actions...',
      'Pulling SEC EDGAR filings (10-K, 10-Q)...',
      'Checking Oversight.gov IG reports...',
      'Retrieving OpenFEC campaign finance data...',
      'Content-hashing all retrieved artifacts...',
    ],
  },
  {
    key: 'graph_builder', agent: 'Graph Builder', code: 'GB',
    messages: [
      'Building entity relationship graph...',
      'Computing edge weights from co-occurrence...',
      'Identifying cluster communities...',
      'Calculating centrality scores...',
      'Graph complete: nodes and edges mapped.',
    ],
  },
  {
    key: 'anomaly_detection', agent: 'Anomaly Detector', code: 'AD',
    messages: [
      'Running sole-source pattern detection...',
      'Checking award spike anomalies...',
      'Scanning for geographic clustering signals...',
      'Evaluating bid rotation indicators...',
      'Anomaly scan complete.',
    ],
  },
  {
    key: 'case_composition', agent: 'Case Composer', code: 'CC',
    messages: [
      'Composing claims from evidence artifacts...',
      'Attaching citations to each claim...',
      'Classifying: findings, risk signals, hypotheses...',
      'Generating executive summary...',
      'Dossier draft complete.',
    ],
  },
  {
    key: 'auditor', agent: 'AI Auditor', code: 'AU',
    messages: [
      'Reviewing all claims for hallucinations...',
      'Verifying every claim has source citations...',
      'Checking for unsupported entity relationships...',
      'Validating provenance chain integrity...',
      'All claims pass auditor gate.',
    ],
  },
];

export default function LiveInvestigation({ title, seedValue, onComplete }) {
  const [currentStage, setCurrentStage] = useState(0);
  const [currentMsg, setCurrentMsg] = useState(0);
  const [logs, setLogs] = useState([]);
  const [done, setDone] = useState(false);
  const feedRef = useRef(null);
  const startTime = useRef(Date.now());

  useEffect(() => {
    if (done) return;

    const stage = PIPELINE[currentStage];
    if (!stage) {
      setDone(true);
      return;
    }

    const delay = 600 + Math.random() * 1200;
    const timer = setTimeout(() => {
      const msg = stage.messages[currentMsg];
      if (!msg) return;

      const elapsed = ((Date.now() - startTime.current) / 1000).toFixed(1);
      setLogs((prev) => [...prev, {
        time: elapsed + 's',
        agent: stage.code,
        agentName: stage.agent,
        message: msg,
        stage: stage.key,
      }]);

      if (currentMsg + 1 < stage.messages.length) {
        setCurrentMsg(currentMsg + 1);
      } else {
        if (currentStage + 1 < PIPELINE.length) {
          setCurrentStage(currentStage + 1);
          setCurrentMsg(0);
        } else {
          setDone(true);
        }
      }
    }, delay);

    return () => clearTimeout(timer);
  }, [currentStage, currentMsg, done]);

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [logs]);

  const totalMessages = PIPELINE.reduce((sum, s) => sum + s.messages.length, 0);
  const progressPct = Math.min(100, Math.round((logs.length / totalMessages) * 100));

  return (
    <div className="live-container">
      {/* Progress bar */}
      <div className="live-progress-bar">
        <div className="live-progress-fill" style={{ width: `${progressPct}%` }} />
      </div>

      {/* Header */}
      <div className="live-header">
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 4 }}>
            {done ? 'Investigation Complete' : 'Investigation in Progress'}
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-2)' }}>
            {title} &mdash; {seedValue}
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 28, fontWeight: 700, fontFamily: 'var(--font-mono)', color: done ? 'var(--green)' : 'var(--accent-2)' }}>
            {progressPct}%
          </span>
          {done && (
            <Link href="/cases/c-7f3a2b1e" className="btn btn-primary" style={{ textDecoration: 'none' }}>
              View Dossier <ArrowRight size={14} />
            </Link>
          )}
        </div>
      </div>

      {/* Grid: pipeline + terminal */}
      <div className="live-grid">
        {/* Pipeline stages */}
        <div className="pipeline-sidebar">
          {PIPELINE.map((stage, i) => {
            const isComplete = i < currentStage || done;
            const isActive = i === currentStage && !done;
            const isWaiting = i > currentStage && !done;

            return (
              <div key={stage.key}>
                <div className={`pipeline-stage ${isComplete ? 'completed' : isActive ? 'active' : 'waiting'}`}>
                  <div className="pipeline-stage-dot" />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{stage.agent}</div>
                    {isActive && (
                      <div style={{ fontSize: 11, marginTop: 2, opacity: 0.7 }}>
                        {stage.messages[currentMsg]?.slice(0, 40)}...
                      </div>
                    )}
                    {isComplete && (
                      <div style={{ fontSize: 11, marginTop: 2 }}>
                        {stage.messages.length} steps completed
                      </div>
                    )}
                  </div>
                  {isComplete && <CheckCircle2 size={14} style={{ color: 'var(--green)' }} />}
                  {isActive && <Loader size={14} className="animate-spin" style={{ color: 'var(--accent)' }} />}
                </div>
                {i < PIPELINE.length - 1 && (
                  <div className={`pipeline-connector ${isComplete ? 'done' : ''}`} />
                )}
              </div>
            );
          })}
        </div>

        {/* Terminal log */}
        <div className="terminal">
          <div className="terminal-header">
            <div className="terminal-dot" style={{ background: done ? 'var(--green)' : 'var(--red)' }} />
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
              <span className="log-msg">Investigation started: {seedValue}</span>
            </div>
            {logs.map((log, i) => (
              <div key={i} className="log-line">
                <span className="log-time">{log.time}</span>
                <span className={`log-agent ${log.agent.toLowerCase()}`}>[{log.agent}]</span>
                <span className="log-msg">{log.message}</span>
              </div>
            ))}
            {!done && (
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
          </div>
        </div>
      </div>
    </div>
  );
}
