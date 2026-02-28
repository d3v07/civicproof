'use client';

import { Shield, Eye, FileText, GitBranch } from 'lucide-react';

export default function AboutPage() {
  return (
    <div style={{ maxWidth: 640, margin: '0 auto', paddingTop: 40 }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 8 }}>About CivicProof</h1>
      <p style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.7, marginBottom: 32 }}>
        CivicProof is an open-source research tool that analyzes publicly available federal spending data.
        It retrieves evidence from 6 government data sources, maps entity relationships, and surfaces risk signals — all with full citation and audit trails.
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 32 }}>
        {[
          { icon: Eye, title: 'Transparency', desc: 'Every claim is cited to source artifacts. Every pipeline step is logged. Pack hashes verify deterministic replay.' },
          { icon: Shield, title: 'Not Accusations', desc: 'Findings are risk signals and hypotheses, not accusations. All results require independent corroboration before action.' },
          { icon: FileText, title: '6 Federal Sources', desc: 'USAspending, DOJ Press Releases, SEC EDGAR, Oversight.gov, SAM.gov, and OpenFEC — all accessed via public APIs.' },
          { icon: GitBranch, title: 'Open Source', desc: 'Built with FastAPI, Next.js, PostgreSQL, Redis. Deployed on GCP Cloud Run with Terraform IaC.' },
        ].map((item) => (
          <div key={item.title} className="card" style={{ padding: 16, display: 'flex', gap: 14 }}>
            <div style={{ width: 36, height: 36, borderRadius: 8, background: 'var(--accent-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <item.icon size={16} style={{ color: 'var(--accent)' }} />
            </div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{item.title}</div>
              <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.5 }}>{item.desc}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6 }}>
        CivicProof is not affiliated with any government agency. This tool processes only publicly available data accessible through official government APIs.
      </div>
    </div>
  );
}
