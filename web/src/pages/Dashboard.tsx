import { useEffect, useState } from "react";
import {
  getDashboardOverview,
  getDashboardTrends,
  getDashboardTopCpv,
  getDashboardHealth,
} from "../api";
import type {
  DashboardOverview,
  DashboardTrends,
  DashboardTopCpv,
  DashboardHealth,
} from "../types";

function fmt(n: number): string {
  return n.toLocaleString("fr-BE");
}

export function Dashboard() {
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [trends, setTrends] = useState<DashboardTrends | null>(null);
  const [topCpv, setTopCpv] = useState<DashboardTopCpv | null>(null);
  const [health, setHealth] = useState<DashboardHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      getDashboardOverview(),
      getDashboardTrends(30, "day"),
      getDashboardTopCpv(10),
      getDashboardHealth(),
    ]).then(([ov, tr, cpv, hl]) => {
      setOverview(ov);
      setTrends(tr);
      setTopCpv(cpv);
      setHealth(hl);
    }).catch((e) => {
      setError(e instanceof Error ? e.message : "Erreur chargement");
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading">Chargement du dashboard…</div>;
  if (error) return <div className="alert alert-error">{error}</div>;
  if (!overview) return null;

  // Aggregate trends
  const trendByDate = new Map<string, number>();
  trends?.data.forEach((p) => trendByDate.set(p.date, (trendByDate.get(p.date) || 0) + p.count));
  const trendData = Array.from(trendByDate.entries())
    .map(([d, c]) => ({ date: d, count: c }))
    .sort((a, b) => a.date.localeCompare(b.date));
  const trendMax = Math.max(...trendData.map((d) => d.count), 1);

  const cpvMax = topCpv?.data.length ? topCpv.data[0].count : 1;

  const freshHours = health?.freshness.hours_since_last_import;

  return (
    <div className="page">
      <div className="page-header">
        <h1>Dashboard</h1>
        <p className="page-subtitle">Vue d'ensemble de vos données marchés publics</p>
      </div>

      {/* KPI row */}
      <div className="kpi-row">
        <div className="kpi-card">
          <div className="kpi-number">{fmt(overview.total_notices)}</div>
          <div className="kpi-label">Total avis</div>
          <div className="kpi-sub">
            {Object.entries(overview.by_source).map(([s, c]) => (
              <span key={s} className="kpi-source">
                <span className={`source-dot ${s.includes("BOSA") ? "bosa" : "ted"}`} />
                {s.includes("BOSA") ? "BOSA" : "TED"} {fmt(c)}
              </span>
            ))}
          </div>
        </div>
        <div className="kpi-card highlight">
          <div className="kpi-number">{fmt(overview.active_notices)}</div>
          <div className="kpi-label">Opportunités ouvertes</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-number">{fmt(overview.expiring_7d)}</div>
          <div className="kpi-label">Expirent sous 7 jours</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-number">{overview.added_7d}</div>
          <div className="kpi-label">Ajoutés (7j)</div>
          <div className="kpi-sub">{overview.added_24h} dernières 24h</div>
        </div>
      </div>

      <div className="grid-2col">
        {/* Trend chart */}
        <div className="card">
          <h3>Publications — 30 derniers jours</h3>
          <div className="sparkline">
            {trendData.slice(-30).map((d, i) => (
              <div
                key={i}
                className="spark-bar"
                style={{ height: `${Math.max((d.count / trendMax) * 100, 4)}%` }}
                title={`${d.date}: ${d.count}`}
              />
            ))}
          </div>
          {trends && (
            <div className="chart-legend">
              {Object.entries(trends.totals_by_source).map(([s, c]) => (
                <span key={s}><span className={`source-dot ${s.includes("BOSA") ? "bosa" : "ted"}`} /> {s.includes("BOSA") ? "BOSA" : "TED"}: {fmt(c)}</span>
              ))}
            </div>
          )}
        </div>

        {/* Top CPV */}
        <div className="card">
          <h3>Top secteurs (CPV)</h3>
          <div className="cpv-bars">
            {topCpv?.data.map((d) => (
              <div key={d.code} className="cpv-row">
                <span className="cpv-label">{d.code} {d.label}</span>
                <div className="cpv-track">
                  <div className="cpv-fill" style={{ width: `${(d.count / cpvMax) * 100}%` }} />
                </div>
                <span className="cpv-count">{fmt(d.count)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Data health */}
      {health && (
        <div className="card">
          <h3>Santé des données</h3>
          <div className="health-row">
            <div className="health-metric">
              <span className="health-key">Fraîcheur</span>
              <span className={
                freshHours == null ? "" :
                freshHours < 6 ? "text-success" :
                freshHours < 24 ? "text-warning" : "text-danger"
              }>
                {freshHours != null ? `${freshHours}h` : "N/A"}
              </span>
            </div>
            {Object.entries(health.field_fill_rates_pct).map(([field, pct]) => (
              <div key={field} className="health-metric">
                <span className="health-key">{field}</span>
                <div className="progress-track">
                  <div
                    className="progress-fill"
                    style={{
                      width: `${pct}%`,
                      background: pct > 80 ? "var(--green)" : pct > 50 ? "var(--amber)" : "var(--red)",
                    }}
                  />
                </div>
                <span className="health-val">{pct}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
