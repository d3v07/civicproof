'use client';

import { Search, Plus, FolderOpen, Database, Shield, FileText, ArrowRight, Zap, Eye, Download } from 'lucide-react';
import Link from 'next/link';

function Step({ number, title, description, icon: Icon, children }) {
  return (
    <div style={{ display: 'flex', gap: 16, marginBottom: 32 }}>
      <div style={{ width: 36, height: 36, borderRadius: 8, background: 'var(--color-accent-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontSize: 14, fontWeight: 700, color: 'var(--color-accent)', fontFamily: 'var(--font-mono)' }}>
        {number}
      </div>
      <div style={{ flex: 1 }}>
        <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>{title}</h3>
        <p style={{ fontSize: 13, color: 'var(--color-text-secondary)', lineHeight: 1.6, marginBottom: children ? 12 : 0 }}>{description}</p>
        {children}
      </div>
    </div>
  );
}

function KeyboardShortcut({ keys, action }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--color-border)' }}>
      <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>{action}</span>
      <div style={{ display: 'flex', gap: 4 }}>
        {keys.map((k) => (
          <kbd key={k} style={{ padding: '2px 6px', borderRadius: 4, background: 'var(--color-surface-3)', border: '1px solid var(--color-border)', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--color-text-muted)' }}>{k}</kbd>
        ))}
      </div>
    </div>
  );
}

export default function GuidePage() {
  return (
    <div style={{ maxWidth: 700, margin: '0 auto', paddingTop: 32 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: '-0.03em', marginBottom: 8 }}>User Guide</h1>
      <p style={{ fontSize: 14, color: 'var(--color-text-secondary)', lineHeight: 1.7, marginBottom: 40 }}>
        CivicProof helps you research federal spending data. Search entities, launch investigations, and review AI-generated dossiers — all backed by cited evidence from public data sources.
      </p>

      {/* Quick Start */}
      <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 20, paddingBottom: 8, borderBottom: '1px solid var(--color-border)' }}>Quick Start</h2>

      <Step number="1" title="Search for an entity" description="Enter a company name, UEI, CAGE code, or federal award ID in the search bar on the home page. Results pull from 6 federal data sources.">
        <Link href="/" style={{ fontSize: 13, color: 'var(--color-accent)', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          Go to search <ArrowRight size={12} />
        </Link>
      </Step>

      <Step number="2" title="Launch an investigation" description="Click 'New Research' on the Investigate page. Provide a title and seed identifier. The system will run 6 pipeline steps automatically:">
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          {[
            { step: 'Entity Resolution', desc: 'Links UEI, CAGE, names across datasets' },
            { step: 'Evidence Retrieval', desc: 'Pulls contracts, filings, press releases' },
            { step: 'Graph Building', desc: 'Maps entity relationships and networks' },
            { step: 'Anomaly Detection', desc: 'Flags unusual patterns in awards' },
            { step: 'Case Composition', desc: 'Generates cited claims from evidence' },
            { step: 'Auditor Gate', desc: 'Reviews claims for hallucinations' },
          ].map((s, i) => (
            <div key={s.step} style={{ display: 'flex', gap: 10, padding: '8px 14px', borderBottom: i < 5 ? '1px solid var(--color-border)' : 'none', fontSize: 13 }}>
              <span style={{ fontWeight: 600, minWidth: 140 }}>{s.step}</span>
              <span style={{ color: 'var(--color-text-muted)' }}>{s.desc}</span>
            </div>
          ))}
        </div>
      </Step>

      <Step number="3" title="Review the dossier" description="Each case produces a dossier with three types of results:">
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
          <span className="badge badge-finding" style={{ padding: '4px 10px' }}>Findings — verified facts with citations</span>
          <span className="badge badge-risk_signal" style={{ padding: '4px 10px' }}>Risk Signals — patterns that warrant attention</span>
          <span className="badge badge-hypothesis" style={{ padding: '4px 10px' }}>Hypotheses — unconfirmed patterns</span>
        </div>
        <p style={{ fontSize: 13, color: 'var(--color-text-muted)', lineHeight: 1.5 }}>
          Click any claim to expand its supporting citations. Each citation links to the source artifact with an excerpt.
        </p>
      </Step>

      <Step number="4" title="Export and share" description="Export the dossier as JSON from the case detail page. Use 'Share' to copy a direct link. The pack hash guarantees the dossier hasn't been tampered with." />

      {/* Navigation */}
      <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16, marginTop: 40, paddingBottom: 8, borderBottom: '1px solid var(--color-border)' }}>Navigation</h2>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10, marginBottom: 32 }}>
        {[
          { icon: Search, label: 'Investigate', desc: 'Search entities, launch research', href: '/' },
          { icon: FolderOpen, label: 'Cases', desc: 'View all investigations', href: '/cases' },
          { icon: Database, label: 'Sources', desc: 'Data connector health', href: '/sources' },
          { icon: FileText, label: 'About', desc: 'How CivicProof works', href: '/about' },
        ].map((item) => (
          <Link key={item.href} href={item.href} className="card" style={{ padding: 14, textDecoration: 'none', color: 'inherit', display: 'flex', gap: 12, alignItems: 'center' }}>
            <item.icon size={18} style={{ color: 'var(--color-accent)', flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>{item.label}</div>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{item.desc}</div>
            </div>
          </Link>
        ))}
      </div>

      {/* Data Sources */}
      <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16, paddingBottom: 8, borderBottom: '1px solid var(--color-border)' }}>Data Sources</h2>
      <p style={{ fontSize: 13, color: 'var(--color-text-secondary)', lineHeight: 1.6, marginBottom: 16 }}>
        CivicProof queries these 6 publicly accessible federal data sources:
      </p>
      <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 32 }}>
        {[
          { name: 'USAspending.gov', desc: 'Federal award data — contracts, grants, direct payments', rate: '5 RPS' },
          { name: 'DOJ Press Releases', desc: 'Department of Justice enforcement actions and settlements', rate: '4 RPS' },
          { name: 'SEC EDGAR', desc: 'Public company filings — 10-K, 10-Q, 8-K', rate: '10 RPS' },
          { name: 'Oversight.gov', desc: 'Inspector General reports across federal agencies', rate: '2 RPS' },
          { name: 'SAM.gov', desc: 'System for Award Management — entity registrations', rate: '4 RPS' },
          { name: 'OpenFEC', desc: 'Federal Election Commission — campaign finance data', rate: '1000/hr' },
        ].map((s, i) => (
          <div key={s.name} style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 14px', borderBottom: i < 5 ? '1px solid var(--color-border)' : 'none', fontSize: 13 }}>
            <div>
              <div style={{ fontWeight: 600, color: 'var(--color-text)' }}>{s.name}</div>
              <div style={{ color: 'var(--color-text-muted)', marginTop: 2 }}>{s.desc}</div>
            </div>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-text-muted)', whiteSpace: 'nowrap', paddingLeft: 16 }}>{s.rate}</span>
          </div>
        ))}
      </div>

      {/* Trust & Transparency */}
      <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16, paddingBottom: 8, borderBottom: '1px solid var(--color-border)' }}>Trust & Transparency</h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 32 }}>
        {[
          { icon: Eye, title: 'Full Audit Trail', desc: 'Every pipeline decision is logged — which agent ran, what data was queried, and what was decided.' },
          { icon: Shield, title: 'Auditor Gate', desc: 'An independent AI auditor reviews every claim for hallucinations and unsupported assertions before the dossier is published.' },
          { icon: Zap, title: 'Deterministic Replay', desc: 'Pack hashes verify that running the same inputs produces the same outputs. Every dossier is reproducible.' },
          { icon: Download, title: 'Export Everything', desc: 'Download the complete dossier as JSON. All data is yours — nothing locked behind a paywall.' },
        ].map((item) => (
          <div key={item.title} style={{ display: 'flex', gap: 12, fontSize: 13 }}>
            <item.icon size={16} style={{ color: 'var(--color-accent)', flexShrink: 0, marginTop: 2 }} />
            <div>
              <span style={{ fontWeight: 600 }}>{item.title}:</span>
              <span style={{ color: 'var(--color-text-secondary)', marginLeft: 4 }}>{item.desc}</span>
            </div>
          </div>
        ))}
      </div>

      <div style={{ padding: '14px 16px', borderRadius: 8, background: 'var(--color-warning-muted)', border: '1px solid rgba(245,158,11,0.2)', fontSize: 12, color: 'var(--color-warning)', lineHeight: 1.6 }}>
        CivicProof produces risk signals and hypotheses — not accusations. All findings require independent verification before any action is taken. This is not a government website.
      </div>
    </div>
  );
}
