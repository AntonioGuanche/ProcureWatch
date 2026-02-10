import { useEffect, useState } from "react";
import { getDashboardOverview, getDashboardTopCpv, getDashboardHealth, getAdminStats, getAdminUsers } from "../api";

interface Overview { total_notices: number; open_opportunities: number; expiring_7d: number; sources: Record<string, number>; }
interface Health { total: number; with_description: number; with_deadline: number; with_cpv: number; with_nuts: number; with_url: number; with_value: number; }
interface TopCpv { items: Array<{ cpv_code: string; description: string | null; count: number }>; }
interface AdminStats { users: { total: number; active: number }; watchlists: { total: number; enabled: number }; favorites_total: number; }
interface AdminUser { id: string; email: string; name: string; is_admin: boolean; is_active: boolean; created_at: string | null; }

function fmtDate(s: string | null): string {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString("fr-BE", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return s; }
}

function pct(n: number, total: number): string {
  if (total === 0) return "0%";
  return Math.round((n / total) * 100) + "%";
}

export function Admin() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [topCpv, setTopCpv] = useState<TopCpv | null>(null);
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
          <span className="admin-kpi-value">{overview?.open_opportunities?.toLocaleString("fr-BE") ?? "…"}</span>
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
          {overview?.sources && Object.entries(overview.sources).map(([src, cnt]) => (
            <div key={src} className="admin-bar-row">
              <span className="admin-bar-label">
                <span className={`source-badge ${src.includes("BOSA") ? "bosa" : "ted"}`}>{src.includes("BOSA") ? "BOSA" : "TED"}</span>
              </span>
              <div className="admin-bar-track">
                <div className="admin-bar-fill" style={{ width: pct(cnt, overview.total_notices) }} />
              </div>
              <span className="admin-bar-count">{cnt.toLocaleString("fr-BE")}</span>
            </div>
          ))}
        </div>

        {/* Data quality */}
        <div className="admin-card">
          <h2>Qualité des données</h2>
          {health && (
            <div className="admin-health-grid">
              {([
                ["Description", health.with_description],
                ["Deadline", health.with_deadline],
                ["CPV", health.with_cpv],
                ["NUTS", health.with_nuts],
                ["URL", health.with_url],
                ["Valeur estimée", health.with_value],
              ] as [string, number][]).map(([label, val]) => (
                <div key={label} className="admin-health-item">
                  <div className="admin-health-header">
                    <span>{label}</span>
                    <span className="admin-health-pct">{pct(val, health.total)}</span>
                  </div>
                  <div className="admin-bar-track">
                    <div className={`admin-bar-fill ${Number(pct(val, health.total).replace('%','')) > 70 ? 'good' : Number(pct(val, health.total).replace('%','')) > 40 ? 'ok' : 'bad'}`}
                      style={{ width: pct(val, health.total) }} />
                  </div>
                  <span className="admin-health-count">{val.toLocaleString("fr-BE")} / {health.total.toLocaleString("fr-BE")}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Top CPV */}
        <div className="admin-card">
          <h2>Top 10 Secteurs CPV</h2>
          {topCpv?.items?.map((c, i) => (
            <div key={c.cpv_code} className="admin-cpv-row">
              <span className="admin-cpv-rank">#{i + 1}</span>
              <code className="cpv-code">{c.cpv_code}</code>
              <span className="admin-cpv-desc">{c.description || "—"}</span>
              <span className="admin-cpv-count">{c.count}</span>
            </div>
          ))}
        </div>

        {/* Users */}
        <div className="admin-card">
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
