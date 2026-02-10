import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listFavorites, listWatchlists, getDashboardOverview, removeFavorite } from "../api";
import { useAuth } from "../auth";
import type { FavoriteItem, Watchlist, DashboardOverview } from "../types";
import { NoticeModal } from "../components/NoticeModal";


function orgName(names: Record<string, string> | null): string {
  if (!names) return "—";
  return names.fr || names.nl || names.en || Object.values(names)[0] || "—";
}

function deadlineTag(deadline: string | null) {
  if (!deadline) return null;
  const days = Math.ceil((new Date(deadline).getTime() - Date.now()) / 86400000);
  if (days < 0) return <span className="tag tag-muted">Expiré</span>;
  if (days <= 3) return <span className="tag tag-danger">{days}j</span>;
  if (days <= 7) return <span className="tag tag-warning">{days}j</span>;
  return <span className="tag tag-default">{days}j</span>;
}

export function Dashboard() {
  const { user } = useAuth();
  const [favorites, setFavorites] = useState<FavoriteItem[]>([]);
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [favIds, setFavIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    Promise.all([
      listFavorites(1, 10).catch(() => ({ items: [], total: 0, page: 1, page_size: 10 })),
      listWatchlists(1, 10).catch(() => ({ items: [], total: 0 })),
      getDashboardOverview().catch(() => null),
    ]).then(([favs, wls, ov]) => {
      setFavorites(favs.items);
      setFavIds(new Set(favs.items.map((f: FavoriteItem) => f.notice.id)));
      setWatchlists(wls.items);
      setOverview(ov);
    }).finally(() => setLoading(false));
  }, []);

  const handleRemoveFav = async (noticeId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await removeFavorite(noticeId);
      setFavorites((prev) => prev.filter((f) => f.notice.id !== noticeId));
      setFavIds((prev) => { const s = new Set(prev); s.delete(noticeId); return s; });
    } catch { /* ignore */ }
  };

  const handleModalFavToggle = (noticeId: string, favorited: boolean) => {
    if (favorited) {
      setFavIds((prev) => new Set(prev).add(noticeId));
    } else {
      setFavIds((prev) => { const s = new Set(prev); s.delete(noticeId); return s; });
      setFavorites((prev) => prev.filter((f) => f.notice.id !== noticeId));
    }
  };

  if (loading) return <div className="page"><div className="loading">Chargement…</div></div>;

  return (
    <div className="page">
      <div className="dash-welcome">
        <h1>Bonjour{user?.name ? `, ${user.name.split(" ")[0]}` : ""}</h1>
        <p className="page-subtitle">Votre tableau de bord ProcureWatch</p>
      </div>

      {/* Stats cards */}
      {overview && (
        <div className="dash-stats">
          <div className="stat-card">
            <div className="stat-value">{overview.total_notices.toLocaleString("fr-BE")}</div>
            <div className="stat-label">Marchés en base</div>
          </div>
          <div className="stat-card accent">
            <div className="stat-value">{overview.active_notices.toLocaleString("fr-BE")}</div>
            <div className="stat-label">Opportunités ouvertes</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{overview.expiring_7d}</div>
            <div className="stat-label">Expirent sous 7 jours</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{watchlists.length}</div>
            <div className="stat-label">Veilles actives</div>
          </div>
        </div>
      )}

      {/* Two-column layout */}
      <div className="dash-grid">
        {/* Favorites */}
        <div className="dash-section">
          <div className="dash-section-header">
            <h2>Mes favoris</h2>
            {favorites.length > 0 && <span className="badge">{favorites.length}</span>}
          </div>
          {favorites.length === 0 ? (
            <div className="empty-hint">
              <p>Aucun favori pour le moment.</p>
              <p>Cliquez sur l'étoile ★ dans la <Link to="/search">recherche</Link> pour suivre un marché.</p>
            </div>
          ) : (
            <div className="fav-list">
              {favorites.map((f) => (
                <div key={f.notice.id} className="fav-item clickable-row" onClick={() => setSelectedId(f.notice.id)}>
                  <div className="fav-info">
                    <div className="fav-title">{f.notice.title || "Sans titre"}</div>
                    <div className="fav-meta">
                      <span className={`source-badge small ${f.notice.source.includes("BOSA") ? "bosa" : "ted"}`}>
                        {f.notice.source.includes("BOSA") ? "BOSA" : "TED"}
                      </span>
                      <span>{orgName(f.notice.organisation_names)}</span>
                      {f.notice.deadline && <span>{deadlineTag(f.notice.deadline)}</span>}
                    </div>
                  </div>
                  <button
                    className="btn-icon small danger"
                    onClick={(e) => handleRemoveFav(f.notice.id, e)}
                    title="Retirer des favoris"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Watchlists */}
        <div className="dash-section">
          <div className="dash-section-header">
            <h2>Mes veilles</h2>
            <Link to="/watchlists/new" className="btn-sm btn-primary-outline">+ Nouvelle</Link>
          </div>
          {watchlists.length === 0 ? (
            <div className="empty-hint">
              <p>Aucune veille configurée.</p>
              <p>Créez une veille pour être alerté automatiquement.</p>
              <Link to="/watchlists/new" className="btn-primary" style={{ marginTop: ".5rem", display: "inline-block", textDecoration: "none", fontSize: ".85rem", padding: ".5rem 1rem" }}>
                Créer une veille
              </Link>
            </div>
          ) : (
            <div className="wl-dash-list">
              {watchlists.map((w) => (
                <Link key={w.id} to={`/watchlists/${w.id}?tab=preview`} className="wl-dash-item">
                  <div className="wl-dash-info">
                    <span className="wl-dash-name">{w.name}</span>
                    <span className={`tag small ${w.enabled ? "tag-success" : "tag-muted"}`}>
                      {w.enabled ? "Active" : "Inactive"}
                    </span>
                  </div>
                  <div className="wl-dash-tags">
                    {w.keywords.slice(0, 3).map((k, i) => (
                      <span key={i} className="tag tag-default small">{k}</span>
                    ))}
                    {w.keywords.length > 3 && <span className="tag tag-default small">+{w.keywords.length - 3}</span>}
                  </div>
                </Link>
              ))}
              <Link to="/watchlists" className="btn-link" style={{ marginTop: ".5rem", display: "inline-block" }}>
                Voir toutes les veilles →
              </Link>
            </div>
          )}
        </div>
      </div>

      {/* Quick search */}
      <div className="dash-cta">
        <Link to="/search" className="btn-primary" style={{ textDecoration: "none" }}>
          Rechercher des marchés publics →
        </Link>
      </div>

      {/* Modal */}
      {selectedId && (
        <NoticeModal
          noticeId={selectedId}
          isFavorited={favIds.has(selectedId)}
          onToggleFavorite={handleModalFavToggle}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  );
}
