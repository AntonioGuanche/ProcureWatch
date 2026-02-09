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
    try {
      const res = await listWatchlists(page, pageSize);
      setItems(res.items);
      setTotal(res.total);
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Impossible de charger les veilles");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [page]);

  const handleRefresh = async (id: string) => {
    setRefreshingId(id);
    try {
      const r = await refreshWatchlist(id);
      setToast(`Refresh terminé : ${r.imported_new_total} nouveaux`);
      load();
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Erreur refresh");
    } finally {
      setRefreshingId(null);
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`Supprimer la veille « ${name} » ?`)) return;
    try {
      await deleteWatchlist(id);
      setToast("Veille supprimée");
      load();
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Erreur suppression");
    }
  };

  return (
    <div className="page">
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
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
                  <span className={`tag ${w.is_enabled ? "tag-success" : "tag-muted"}`}>
                    {w.is_enabled ? "Active" : "Désactivée"}
                  </span>
                </div>
                <div className="wl-actions">
                  <button
                    onClick={() => handleRefresh(w.id)}
                    disabled={refreshingId === w.id}
                    title="Rafraîchir"
                  >
                    {refreshingId === w.id ? "⏳" : "🔄"}
                  </button>
                  <Link to={`/watchlists/${w.id}/edit`} className="btn" title="Modifier">✏️</Link>
                  <button onClick={() => handleDelete(w.id, w.name)} title="Supprimer">🗑️</button>
                </div>
              </div>

              <div className="wl-card-tags">
                {w.term && <span className="tag tag-default">{w.term}</span>}
                {w.cpv_prefix && <span className="tag tag-default">CPV {w.cpv_prefix}</span>}
                {w.country && <span className="tag tag-default">{w.country}</span>}
                {w.buyer_contains && <span className="tag tag-default">{w.buyer_contains}</span>}
              </div>

              <div className="wl-card-meta">
                <span>Dernier refresh : {fmtDate(w.last_refresh_at)}</span>
                {w.notify_email && <span>📧 {w.notify_email}</span>}
              </div>

              <div className="wl-card-links">
                <Link to={`/watchlists/${w.id}?tab=preview`}>Voir les résultats →</Link>
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
