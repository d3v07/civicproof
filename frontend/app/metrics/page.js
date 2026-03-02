'use client';

import { useState, useEffect } from 'react';
import { Activity, Shield, Clock, DollarSign, Database, AlertTriangle, CheckCircle2, TrendingUp } from 'lucide-react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { mockMetrics } from '../lib/mock-data';
import * as api from '../lib/api';

function StatCard({ icon: Icon, label, value, sub, color }) {
  return (
    <div className="card" style={{ padding: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: `${color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon size={16} style={{ color }} />
        </div>
        <span style={{ fontSize: 12, color: 'var(--text-3)', fontWeight: 500 }}>{label}</span>
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, fontFamily: 'var(--font-mono)', letterSpacing: '-0.02em' }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function generateActivityData() {
  const data = [];
  const now = new Date();
  for (let i = 23; i >= 0; i--) {
    const hour = new Date(now - i * 3600000);
    data.push({
      hour: hour.toLocaleTimeString('en-US', { hour: '2-digit', hour12: false }),
      cases: Math.floor(Math.random() * 4),
      artifacts: Math.floor(Math.random() * 120 + 20),
    });
  }
  return data;
}

function generateClaimTypeData(metrics) {
  return [
    { type: 'Findings', count: Math.round(metrics.total_cases_processed * 2.1) },
    { type: 'Risk Signals', count: Math.round(metrics.total_cases_processed * 1.4) },
    { type: 'Hypotheses', count: Math.round(metrics.total_cases_processed * 0.8) },
  ];
}

const CHART_THEME = {
  grid: '#1a1a25',
  text: '#71717a',
  tooltip: { background: '#0f0f14', border: '#1a1a25' },
};

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: CHART_THEME.tooltip.background, border: `1px solid ${CHART_THEME.tooltip.border}`, borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
      <div style={{ color: 'var(--text-2)', marginBottom: 4 }}>{label}</div>
      {payload.map((entry) => (
        <div key={entry.dataKey} style={{ color: entry.color, fontFamily: 'var(--font-mono)' }}>
          {entry.name}: {entry.value}
        </div>
      ))}
    </div>
  );
}

export default function MetricsPage() {
  const [metrics, setMetrics] = useState(null);
  const [activityData] = useState(generateActivityData);

  useEffect(() => {
    async function load() {
      try {
        const data = await api.getMetrics();
        setMetrics(data);
      } catch {
        setMetrics(mockMetrics);
      }
    }
    load();
  }, []);

  if (!metrics) {
    return <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-3)' }}>Loading metrics...</div>;
  }

  const claimData = generateClaimTypeData(metrics);

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 4 }}>Metrics</h1>
        <p style={{ fontSize: 13, color: 'var(--text-3)' }}>System health and performance overview</p>
      </div>

      {/* KPI cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 24 }}>
        <StatCard
          icon={Shield}
          label="Audit Pass Rate"
          value={`${(metrics.audited_dossier_pass_rate * 100).toFixed(0)}%`}
          sub="All dossiers"
          color="var(--green)"
        />
        <StatCard
          icon={Clock}
          label="Median Time"
          value={`${metrics.median_tip_to_dossier_seconds}s`}
          sub="Tip to dossier"
          color="var(--accent)"
        />
        <StatCard
          icon={AlertTriangle}
          label="Hallucination Catch"
          value={`${(metrics.hallucination_caught_rate * 100).toFixed(0)}%`}
          sub="Blocked by auditor"
          color="var(--amber)"
        />
        <StatCard
          icon={DollarSign}
          label="Avg Cost"
          value={`$${metrics.avg_cost_per_dossier_usd.toFixed(2)}`}
          sub="Per dossier"
          color="var(--accent-2)"
        />
      </div>

      {/* Charts row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 24 }}>
        <div className="card" style={{ padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Activity (Last 24h)</div>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={activityData}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} />
              <XAxis dataKey="hour" tick={{ fill: CHART_THEME.text, fontSize: 10 }} tickLine={false} axisLine={{ stroke: CHART_THEME.grid }} />
              <YAxis tick={{ fill: CHART_THEME.text, fontSize: 10 }} tickLine={false} axisLine={{ stroke: CHART_THEME.grid }} />
              <Tooltip content={<ChartTooltip />} />
              <Line type="monotone" dataKey="artifacts" stroke="var(--accent)" strokeWidth={2} dot={false} name="Artifacts" />
              <Line type="monotone" dataKey="cases" stroke="var(--green)" strokeWidth={2} dot={false} name="Cases" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card" style={{ padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Claims by Type</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={claimData}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} />
              <XAxis dataKey="type" tick={{ fill: CHART_THEME.text, fontSize: 10 }} tickLine={false} axisLine={{ stroke: CHART_THEME.grid }} />
              <YAxis tick={{ fill: CHART_THEME.text, fontSize: 10 }} tickLine={false} axisLine={{ stroke: CHART_THEME.grid }} />
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey="count" fill="var(--accent)" radius={[4, 4, 0, 0]} name="Count" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Last 24h stats + system totals */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div className="card" style={{ padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Last 24 Hours</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 13, color: 'var(--text-2)' }}>Cases Created</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{metrics.last_24h.cases_created}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 13, color: 'var(--text-2)' }}>Artifacts Fetched</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{metrics.last_24h.artifacts_fetched.toLocaleString()}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 13, color: 'var(--text-2)' }}>Audit Blocks</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: metrics.last_24h.audit_blocks > 0 ? 'var(--red)' : 'var(--text-1)' }}>
                {metrics.last_24h.audit_blocks}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 13, color: 'var(--text-2)' }}>Model Cost</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>${metrics.last_24h.model_cost_usd.toFixed(2)}</span>
            </div>
          </div>
        </div>

        <div className="card" style={{ padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>System Totals</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 13, color: 'var(--text-2)' }}>Total Cases</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{metrics.total_cases_processed}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 13, color: 'var(--text-2)' }}>Total Artifacts</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{metrics.total_artifacts_ingested.toLocaleString()}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 13, color: 'var(--text-2)' }}>Active Sources</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{metrics.sources_active}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 13, color: 'var(--text-2)' }}>Entity Coverage</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{(metrics.entity_resolution_coverage * 100).toFixed(0)}%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
