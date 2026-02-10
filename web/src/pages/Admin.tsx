import { useEffect, useState } from "react";
import { getDashboardOverview, getDashboardTopCpv, getDashboardHealth, getAdminStats, getAdminUsers } from "../api";
import type { DashboardOverview, DashboardTopCpv, DashboardHealth } from "../types";

interface AdminStats { users: { total: number; active: number }; watchlists: { total: number; enabled: number }; favorites_total: number; }
interface AdminUser { id: string; email: string; name: string; is_admin: boolean; is_active: boolean; created_at: string | null; }

function fmtDate(s: string | null): string {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString("fr-BE", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return s; }
}

export function Admin() {
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [health, setHealth] = useState<DashboardHealth | null>(null);
  const [topCpv, setTopCpv] = useState<DashboardTopCpv | null>(null);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      getDashboardOverview().then(setOverview).catch(() => {}),
      getDashboardHealth().then(setHealth).catch(() => {}),
      getDashboardTopCpv(10, false).then(setTopCpv).catch(() => {}),
      getAdminStats().then(setStats).catch((e) => setError(e?.message || "Accès refusé")),
      getAdminUsers().then(setUsers).catch(() => {}),
    ]);
  }, []);

  if (error) return (
    <div className="page">
      <h1>Administration</h1>
      <div className="alert alert-error">{error}</div>
    </div>
  );

  return (
    <div className="page">
      <h1>Administration</h1>
      <p className="page-subtitle">Vue d'ensemble du système ProcureWatch</p>

      {/* KPI Cards */}
      <div className="admin-kpi-grid">
        <div className="admin-kpi">
          <span className="admin-kpi-value">{overview?.total_notices?.toLocaleString("fr-BE") ?? "…"}</span>
          <span className="admin-kpi-label">Notices totales</span>
        </div>
        <div className="admin-kpi accent">
          <span className="admin-kpi-value">{overview?.active_notices?.toLocaleString("fr-BE") ?? "…"}</span>
          <span className="admin-kpi-label">Opportunités ouvertes</span>
        </div>
        <div className="admin-kpi">
          <span className="admin-kpi-value">{overview?.expiring_7d ?? "…"}</span>
          <span className="admin-kpi-label">Expirent sous 7j</span>
        </div>
        <div className="admin-kpi">
          <span className="admin-kpi-value">{stats?.users?.total ?? "…"}</span>
          <span className="admin-kpi-label">Utilisateurs</span>
        </div>
        <div className="admin-kpi">
          <span className="admin-kpi-value">{stats?.watchlists?.enabled ?? "…"}</span>
          <span className="admin-kpi-label">Veilles actives</span>
        </div>
        <div className="admin-kpi">
          <span className="admin-kpi-value">{stats?.favorites_total ?? "…"}</span>
          <span className="admin-kpi-label">Favoris totaux</span>
        </div>
      </div>

      <div className="admin-grid">
        {/* Sources breakdown */}
        <div className="admin-card">
          <h2>Répartition par source</h2>
          {overview?.by_source && Object.entries(overview.by_source).map(([src, cnt]) => (
            <div key={src} className="admin-bar-row">
              <span className="admin-bar-label">
                <span className={`source-badge ${src.includes("BOSA") ? "bosa" : "ted"}`}>{src.includes("BOSA") ? "BOSA" : "TED"}</span>
              </span>
              <div className="admin-bar-track">
                <div className="admin-bar-fill" style={{ width: `${overview.total_notices ? Math.round((cnt / overview.total_notices) * 100) : 0}%` }} />
              </div>
              <span className="admin-bar-count">{cnt.toLocaleString("fr-BE")}</span>
            </div>
          ))}
        </div>

        {/* Data quality */}
        <div className="admin-card">
          <h2>Qualité des données</h2>
          {health?.field_fill_rates_pct && (
            <div className="admin-health-grid">
              {Object.entries(health.field_fill_rates_pct).map(([label, pctVal]) => (
                <div key={label} className="admin-health-item">
                  <div className="admin-health-header">
                    <span>{label}</span>
                    <span className="admin-health-pct">{Math.round(pctVal)}%</span>
                  </div>
                  <div className="admin-bar-track">
                    <div className={`admin-bar-fill ${pctVal > 70 ? 'good' : pctVal > 40 ? 'ok' : 'bad'}`}
                      style={{ width: `${Math.round(pctVal)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
          {health?.freshness && (
            <div style={{ marginTop: "1rem", fontSize: ".82rem", color: "var(--gray-500)" }}>
              Dernière publication : {fmtDate(health.freshness.newest_publication_date)}
              {health.freshness.hours_since_last_import != null && (
                <> · Import il y a {Math.round(health.freshness.hours_since_last_import)}h</>
              )}
            </div>
          )}
        </div>

        {/* Top CPV */}
        <div className="admin-card">
          <h2>Top 10 Secteurs CPV</h2>
          {topCpv?.data?.map((c, i) => (
            <div key={c.code} className="admin-cpv-row">
              <span className="admin-cpv-rank">#{i + 1}</span>
              <code className="cpv-code">{c.code}</code>
              <span className="admin-cpv-desc">{c.label || "—"}</span>
              <span className="admin-cpv-count">{c.count}</span>
            </div>
          ))}
        </div>

        {/* Import stats */}
        <div className="admin-card">
          <h2>Historique imports</h2>
          {health?.imports && Object.entries(health.imports).map(([src, info]) => (
            <div key={src} style={{ marginBottom: ".75rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: ".25rem" }}>
                <span className={`source-badge ${src.includes("BOSA") ? "bosa" : "ted"}`}>{src.includes("BOSA") ? "BOSA" : "TED"}</span>
                <span style={{ fontSize: ".8rem", color: "var(--gray-500)" }}>{info.run_count} exécutions</span>
              </div>
              <div style={{ fontSize: ".82rem", color: "var(--gray-600)" }}>
                Créés : {info.total_created} · Mis à jour : {info.total_updated} · Erreurs : {info.total_errors}
              </div>
              <div style={{ fontSize: ".78rem", color: "var(--gray-400)" }}>
                Dernier run : {fmtDate(info.last_run)}
              </div>
            </div>
          ))}
        </div>

        {/* Users */}
        <div className="admin-card" style={{ gridColumn: "1 / -1" }}>
          <h2>Utilisateurs ({users.length})</h2>
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Nom</th>
                  <th>Email</th>
                  <th>Inscrit le</th>
                  <th>Statut</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>{u.name} {u.is_admin && <span className="tag tag-primary">Admin</span>}</td>
                    <td>{u.email}</td>
                    <td>{fmtDate(u.created_at)}</td>
                    <td><span className={`tag ${u.is_active ? "tag-success" : "tag-muted"}`}>{u.is_active ? "Actif" : "Inactif"}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
