import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listWatchlists, deleteWatchlist, refreshWatchlist } from "../api";
import type { Watchlist } from "../types";
import { Toast } from "../components/Toast";

function fmtDate(s: string | null): string {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString("fr-BE", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return s; }
}

export function WatchlistList() {
  const [items, setItems] = useState<Watchlist[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<string | null>(null);
  const [refreshingId, setRefreshingId] = useState<string | null>(null);
  const pageSize = 25;

  const load = async () => {
    setLoading(true);
    try { const res = await listWatchlists(page, pageSize); setItems(res.items); setTotal(res.total); }
    catch (e) { setToast(e instanceof Error ? e.message : "Impossible de charger les veilles"); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [page]);

  const handleRefresh = async (id: string) => {
    setRefreshingId(id);
    try {
      const r = await refreshWatchlist(id);
      setToast(`Refresh terminé : ${r.matched} résultats, ${r.added} ajoutés`);
      load();
    } catch (e) { setToast(e instanceof Error ? e.message : "Erreur refresh"); }
    finally { setRefreshingId(null); }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`Supprimer la veille « ${name} » ?`)) return;
    try { await deleteWatchlist(id); setToast("Veille supprimée"); load(); }
    catch (e) { setToast(e instanceof Error ? e.message : "Erreur suppression"); }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Mes Veilles</h1>
          <p className="page-subtitle">Gérez vos veilles et recevez des alertes.</p>
        </div>
        <Link to="/watchlists/new" className="btn-primary" style={{ textDecoration: "none" }}>
          + Nouvelle veille
        </Link>
      </div>

      {loading ? (
        <div className="loading">Chargement…</div>
      ) : items.length === 0 ? (
        <div className="empty-state">
          <p>Aucune veille configurée</p>
          <Link to="/watchlists/new" className="btn-primary" style={{ marginTop: ".75rem", display: "inline-block", textDecoration: "none" }}>
            Créer votre première veille
          </Link>
        </div>
      ) : (
        <div className="wl-grid">
          {items.map((w) => (
            <div key={w.id} className="wl-card">
              <div className="wl-card-header">
                <div>
                  <h3 className="wl-name">{w.name}</h3>
                  <span className={`tag ${w.enabled ? "tag-success" : "tag-muted"}`}>
                    {w.enabled ? "Active" : "Désactivée"}
                  </span>
                </div>
                <div className="wl-actions">
                  <button
                    className="btn-sm btn-outline"
                    onClick={() => handleRefresh(w.id)}
                    disabled={refreshingId === w.id}
                    title="Rafraîchir"
                  >
                    {refreshingId === w.id ? (
                      <svg className="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
                    ) : (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                      </svg>
                    )}
                    <span>Refresh</span>
                  </button>
                  <Link to={`/watchlists/${w.id}/edit`} className="btn-sm btn-outline" title="Modifier">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
                      <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                    <span>Modifier</span>
                  </Link>
                  <button
                    className="btn-sm btn-outline danger"
                    onClick={() => handleDelete(w.id, w.name)}
                    title="Supprimer"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                    </svg>
                  </button>
                </div>
              </div>

              <div className="wl-card-tags">
                {w.keywords.map((k, i) => <span key={`kw-${i}`} className="tag tag-default">{k}</span>)}
                {w.cpv_prefixes.map((c, i) => <span key={`cpv-${i}`} className="tag tag-default">CPV {c}</span>)}
                {w.countries.map((c, i) => <span key={`co-${i}`} className="tag tag-default">{c}</span>)}
                {w.nuts_prefixes.map((n, i) => <span key={`nuts-${i}`} className="tag tag-default">NUTS {n}</span>)}
              </div>

              <div className="wl-card-meta">
                <span>Dernier refresh : {fmtDate(w.last_refresh_at)}</span>
                {w.notify_email && <span>📧 {w.notify_email}</span>}
              </div>

              <div className="wl-card-links">
                <Link to={`/watchlists/${w.id}?tab=preview`} className="btn-sm btn-primary-outline">
                  Voir les résultats →
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}

      {total > pageSize && (
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>← Précédent</button>
          <span>Page {page} / {Math.ceil(total / pageSize)}</span>
          <button disabled={page >= Math.ceil(total / pageSize)} onClick={() => setPage((p) => p + 1)}>Suivant →</button>
        </div>
      )}

      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
