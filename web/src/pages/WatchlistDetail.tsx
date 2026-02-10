import { useEffect, useState, useCallback } from "react";
import { useParams, useSearchParams, Link, useNavigate } from "react-router-dom";
import { getWatchlist, previewWatchlist, newSinceWatchlist, refreshWatchlist, getFavoriteIds, addFavorite, removeFavorite } from "../api";
import type { Watchlist, Notice } from "../types";
import { Toast } from "../components/Toast";
import { NoticeModal } from "../components/NoticeModal";

function fmtDate(s: string | null): string {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString("fr-BE", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return s; }
}

function fmtValue(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("fr-BE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(v);
}

function orgName(names: Record<string, string> | null): string {
  if (!names) return "—";
  return names.fr || names.FR || names.nl || names.NL || names.en || names.default || Object.values(names)[0] || "—";
}

function deadlineTag(deadline: string | null) {
  if (!deadline) return null;
  const days = Math.ceil((new Date(deadline).getTime() - Date.now()) / 86400000);
  if (days < 0) return <span className="tag tag-muted">Expiré</span>;
  if (days <= 3) return <span className="tag tag-danger">{days}j</span>;
  if (days <= 7) return <span className="tag tag-warning">{days}j</span>;
  return <span className="tag tag-default">{days}j</span>;
}

const SORT_OPTIONS = [
  { value: "date_desc", label: "Plus récent" },
  { value: "date_asc", label: "Plus ancien" },
  { value: "deadline", label: "Deadline ↑" },
  { value: "deadline_desc", label: "Deadline ↓" },
  { value: "value_desc", label: "Valeur ↓" },
];

type Tab = "preview" | "new";

export function WatchlistDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const tabParam = (searchParams.get("tab") ?? "preview") as Tab;
  const tab: Tab = tabParam === "new" ? "new" : "preview";
  const [watchlist, setWatchlist] = useState<Watchlist | null>(null);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [favIds, setFavIds] = useState<Set<string>>(new Set());

  // Filters
  const [filterQ, setFilterQ] = useState("");
  const [filterSource, setFilterSource] = useState("");
  const [filterSort, setFilterSort] = useState("date_desc");
  const [filterActiveOnly, setFilterActiveOnly] = useState(false);

  const setTab = (t: Tab) => {
    setPage(1);
    navigate(`/watchlists/${id}?tab=${t}`, { replace: true });
  };

  useEffect(() => {
    if (!id) return;
    getWatchlist(id).then(setWatchlist).catch(() => setToast("Impossible de charger la veille"));
    getFavoriteIds().then((r) => setFavIds(new Set(r.notice_ids))).catch(() => {});
  }, [id]);

  const filters = { source: filterSource || undefined, q: filterQ || undefined, sort: filterSort, active_only: filterActiveOnly || undefined };

  const loadNotices = useCallback(async (p: number) => {
    if (!id) return;
    setLoading(true);
    try {
      const fn = tab === "new" ? newSinceWatchlist : previewWatchlist;
      const res = await fn(id, p, pageSize, filters);
      setNotices(res.items);
      setTotal(res.total);
    } catch { setToast("Impossible de charger les résultats"); }
    finally { setLoading(false); }
  }, [id, tab, pageSize, filterSource, filterQ, filterSort, filterActiveOnly]);

  useEffect(() => { loadNotices(page); }, [loadNotices, page]);

  const handleFilterSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    loadNotices(1);
  };

  const handleRefresh = async () => {
    if (!id) return;
    setRefreshing(true);
    try {
      const r = await refreshWatchlist(id);
      setToast(`Refresh terminé : ${r.matched} résultats, ${r.added} ajoutés`);
      getWatchlist(id).then(setWatchlist);
      loadNotices(page);
    } catch (e) { setToast(e instanceof Error ? e.message : "Erreur refresh"); }
    finally { setRefreshing(false); }
  };

  const handleToggleFav = async (noticeId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const isFav = favIds.has(noticeId);
    try {
      if (isFav) { await removeFavorite(noticeId); setFavIds((p) => { const s = new Set(p); s.delete(noticeId); return s; }); }
      else { await addFavorite(noticeId); setFavIds((p) => new Set(p).add(noticeId)); }
    } catch { /* ignore */ }
  };

  const handleModalFavToggle = (noticeId: string, favorited: boolean) => {
    setFavIds((p) => { const s = new Set(p); if (favorited) s.add(noticeId); else s.delete(noticeId); return s; });
  };

  if (!watchlist) return <div className="page"><div className="loading">Chargement…</div></div>;

  const criteriaLabels = [
    watchlist.keywords.length > 0 ? `Mots-clés: ${watchlist.keywords.join(", ")}` : "",
    watchlist.cpv_prefixes.length > 0 ? `CPV: ${watchlist.cpv_prefixes.join(", ")}` : "",
    watchlist.countries.length > 0 ? `Pays: ${watchlist.countries.join(", ")}` : "",
    watchlist.nuts_prefixes.length > 0 ? `NUTS: ${watchlist.nuts_prefixes.join(", ")}` : "",
  ].filter(Boolean);

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>{watchlist.name}</h1>
          <p className="page-subtitle">
            {criteriaLabels.length > 0
              ? criteriaLabels.map((f, i) => <span key={i} className="filter-badge">{f}</span>)
              : <em>Aucun filtre — matche toutes les notices</em>
            }
          </p>
        </div>
      </div>

      <div className="wl-detail-meta">
        <div className="wl-detail-info">
          <span>Dernier refresh : {fmtDate(watchlist.last_refresh_at)}</span>
          <span className="separator">|</span>
          {watchlist.notify_email && <><span>📧 {watchlist.notify_email}</span><span className="separator">|</span></>}
          <span className={`tag ${watchlist.enabled ? "tag-success" : "tag-muted"}`}>
            {watchlist.enabled ? "Active" : "Désactivée"}
          </span>
        </div>
        <div className="wl-detail-actions">
          <Link to="/watchlists" className="btn-sm btn-outline">← Retour</Link>
          <Link to={`/watchlists/${id}/edit`} className="btn-sm btn-outline">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
            Modifier
          </Link>
          <button className="btn-sm btn-primary-outline" onClick={handleRefresh} disabled={refreshing}>
            {refreshing ? (
              <><svg className="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg> Refresh…</>
            ) : (
              <><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg> Refresh</>
            )}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="wl-tabs">
        <button className={`wl-tab ${tab === "preview" ? "active" : ""}`} onClick={() => setTab("preview")}>
          Aperçu
        </button>
        <button className={`wl-tab ${tab === "new" ? "active" : ""}`} onClick={() => setTab("new")}>
          Nouveaux
        </button>
      </div>

      {/* Filter bar */}
      <form onSubmit={handleFilterSubmit} className="search-form" style={{ marginBottom: "1rem" }}>
        <div className="filter-row">
          <input type="text" value={filterQ} onChange={(e) => setFilterQ(e.target.value)}
            placeholder="Filtrer par mot-clé…" className="filter-input" />
          <div className="source-toggles">
            <button type="button" className={`source-btn ${filterSource === "" ? "active" : ""}`} onClick={() => { setFilterSource(""); setPage(1); }}>Tous</button>
            <button type="button" className={`source-btn bosa ${filterSource === "BOSA_EPROC" ? "active" : ""}`} onClick={() => { setFilterSource(filterSource === "BOSA_EPROC" ? "" : "BOSA_EPROC"); setPage(1); }}>BOSA</button>
            <button type="button" className={`source-btn ted ${filterSource === "TED_EU" ? "active" : ""}`} onClick={() => { setFilterSource(filterSource === "TED_EU" ? "" : "TED_EU"); setPage(1); }}>TED</button>
          </div>
          <button type="submit" className="btn-primary" disabled={loading}>Filtrer</button>
        </div>
        <div className="filter-row-secondary">
          <label className="checkbox-label">
            <input type="checkbox" checked={filterActiveOnly} onChange={(e) => { setFilterActiveOnly(e.target.checked); setPage(1); }} />
            Ouvertes uniquement
          </label>
          <div className="sort-control">
            <span>Trier par</span>
            <select value={filterSort} onChange={(e) => { setFilterSort(e.target.value); setPage(1); }}>
              {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <span className="results-count">{total.toLocaleString("fr-BE")} résultat{total !== 1 ? "s" : ""}</span>
        </div>
      </form>

      {loading ? (
        <div className="loading">Chargement…</div>
      ) : notices.length === 0 ? (
        <div className="empty-state">
          {tab === "new" ? "Aucun nouveau résultat depuis la dernière notification." : "Aucun résultat. Essayez de modifier les filtres ou de faire un Refresh."}
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: "3%" }}></th>
                <th style={{ width: "30%" }}>Titre</th>
                <th style={{ width: "13%" }}>Acheteur</th>
                <th style={{ width: "8%" }}>CPV</th>
                <th style={{ width: "7%" }}>Source</th>
                <th style={{ width: "11%" }}>Publication</th>
                <th style={{ width: "14%" }}>Deadline</th>
                <th style={{ width: "9%" }}>Valeur</th>
              </tr>
            </thead>
            <tbody>
              {notices.map((n) => (
                <tr key={n.id} className="clickable-row" onClick={() => setSelectedId(n.id)}>
                  <td onClick={(e) => e.stopPropagation()}>
                    <button className={`btn-star ${favIds.has(n.id) ? "active" : ""}`}
                      onClick={(e) => handleToggleFav(n.id, e)}
                      title={favIds.has(n.id) ? "Retirer des favoris" : "Ajouter aux favoris"}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill={favIds.has(n.id) ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
                        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                      </svg>
                    </button>
                  </td>
                  <td>
                    <span className="notice-link">{n.title || "Sans titre"}</span>
                    {n.description && <p className="notice-desc">{n.description}</p>}
                  </td>
                  <td className="truncate" title={orgName(n.organisation_names)}>{orgName(n.organisation_names)}</td>
                  <td><code className="cpv-code">{n.cpv_main_code || "—"}</code></td>
                  <td>
                    <span className={`source-badge ${n.source.includes("BOSA") ? "bosa" : "ted"}`}>
                      {n.source.includes("BOSA") ? "BOSA" : "TED"}
                    </span>
                  </td>
                  <td className="nowrap">{fmtDate(n.publication_date)}</td>
                  <td className="nowrap">{fmtDate(n.deadline)} {n.deadline && deadlineTag(n.deadline)}</td>
                  <td className="nowrap">{fmtValue(n.estimated_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>← Précédent</button>
          <span>Page {page} / {totalPages} ({total} résultats)</span>
          <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Suivant →</button>
        </div>
      )}

      {selectedId && (
        <NoticeModal noticeId={selectedId} isFavorited={favIds.has(selectedId)}
          onToggleFavorite={handleModalFavToggle} onClose={() => setSelectedId(null)} />
      )}

      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
