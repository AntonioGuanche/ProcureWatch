import { useEffect, useState, useCallback } from "react";
import { searchNotices, getFacets, getFavoriteIds, addFavorite, removeFavorite, type SearchParams } from "../api";
import type { NoticeSearchResponse, FacetsResponse } from "../types";
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
  { value: "relevance", label: "Pertinence" },
  { value: "deadline", label: "Deadline ↑" },
  { value: "deadline_desc", label: "Deadline ↓" },
  { value: "value_desc", label: "Valeur ↓" },
];

export function Search() {
  const [q, setQ] = useState("");
  const [cpv, setCpv] = useState("");
  const [nuts, setNuts] = useState("");
  const [source, setSource] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [sort, setSort] = useState("date_desc");
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const [results, setResults] = useState<NoticeSearchResponse | null>(null);
  const [facets, setFacets] = useState<FacetsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Favorites
  const [favIds, setFavIds] = useState<Set<string>>(new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    getFacets().then(setFacets).catch(() => {});
    getFavoriteIds().then((r) => setFavIds(new Set(r.notice_ids))).catch(() => {});
  }, []);

  const doSearch = useCallback(async (p: number) => {
    setLoading(true);
    setError(null);
    setPage(p);
    try {
      const params: SearchParams = { page: p, page_size: pageSize, sort };
      if (q.trim()) params.q = q.trim();
      if (cpv) params.cpv = cpv;
      if (nuts) params.nuts = nuts;
      if (source) params.source = source;
      if (activeOnly) params.active_only = true;
      const data = await searchNotices(params);
      setResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur de recherche");
    } finally {
      setLoading(false);
    }
  }, [q, cpv, nuts, source, activeOnly, sort, pageSize]);

  useEffect(() => { doSearch(1); }, []);

  const handleSubmit = (e: React.FormEvent) => { e.preventDefault(); doSearch(1); };

  const handleToggleFav = async (noticeId: string, e?: React.MouseEvent) => {
    if (e) { e.stopPropagation(); }
    const isFav = favIds.has(noticeId);
    try {
      if (isFav) {
        await removeFavorite(noticeId);
        setFavIds((prev) => { const s = new Set(prev); s.delete(noticeId); return s; });
      } else {
        await addFavorite(noticeId);
        setFavIds((prev) => new Set(prev).add(noticeId));
      }
    } catch { /* ignore */ }
  };

  const handleModalFavToggle = (noticeId: string, favorited: boolean) => {
    setFavIds((prev) => {
      const s = new Set(prev);
      if (favorited) s.add(noticeId); else s.delete(noticeId);
      return s;
    });
  };

  return (
    <div className="page">
      <h1>Rechercher</h1>
      <p className="page-subtitle">Recherchez et filtrez les marchés publics.</p>

      <form onSubmit={handleSubmit} className="search-form">
        <div className="filter-row">
          <input type="text" value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Rechercher par mot-clé…" className="filter-input" />
          <select value={cpv} onChange={(e) => setCpv(e.target.value)} className="filter-select">
            <option value="">Tous les CPV</option>
            {facets?.top_cpv_divisions.map((f) => (
              <option key={f.code} value={f.code}>{f.code} ({f.count})</option>
            ))}
          </select>
          <select value={nuts} onChange={(e) => setNuts(e.target.value)} className="filter-select">
            <option value="">Tous pays</option>
            {facets?.top_nuts_countries.map((f) => (
              <option key={f.code} value={f.code}>{f.code} ({f.count})</option>
            ))}
          </select>
          <div className="source-toggles">
            <button type="button" className={`source-btn ${source === "" ? "active" : ""}`} onClick={() => setSource("")}>Tous</button>
            <button type="button" className={`source-btn bosa ${source === "BOSA_EPROC" ? "active" : ""}`} onClick={() => setSource(source === "BOSA_EPROC" ? "" : "BOSA_EPROC")}>BOSA</button>
            <button type="button" className={`source-btn ted ${source === "TED_EU" ? "active" : ""}`} onClick={() => setSource(source === "TED_EU" ? "" : "TED_EU")}>TED</button>
          </div>
          <button type="submit" className="btn-primary" disabled={loading}>Rechercher</button>
        </div>

        <div className="filter-row-secondary">
          <label className="checkbox-label">
            <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} />
            Opportunités ouvertes uniquement
          </label>
          <div className="sort-control">
            <span>Trier par</span>
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          {results && <span className="results-count">{results.total.toLocaleString("fr-BE")} résultat{results.total !== 1 ? "s" : ""}</span>}
        </div>
      </form>

      {error && <div className="alert alert-error">{error}</div>}
      {loading && !results && <div className="loading">Chargement…</div>}

      {results && results.items.length > 0 && (
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: "3%" }}></th>
                <th style={{ width: "35%" }}>Titre</th>
                <th>CPV</th>
                <th>Source</th>
                <th>Publication</th>
                <th>Deadline</th>
                <th>Valeur</th>
              </tr>
            </thead>
            <tbody>
              {results.items.map((n) => (
                <tr key={n.id} className="clickable-row" onClick={() => setSelectedId(n.id)}>
                  <td onClick={(e) => e.stopPropagation()}>
                    <button
                      className={`btn-star ${favIds.has(n.id) ? "active" : ""}`}
                      onClick={(e) => handleToggleFav(n.id, e)}
                      title={favIds.has(n.id) ? "Retirer des favoris" : "Ajouter aux favoris"}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill={favIds.has(n.id) ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
                        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                      </svg>
                    </button>
                  </td>
                  <td>
                    <span className="notice-link">{n.title || "Sans titre"}</span>
                    {n.description && <p className="notice-desc">{n.description}</p>}
                  </td>
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

      {results && results.items.length === 0 && (
        <div className="empty-state">Aucun résultat trouvé. Essayez d'élargir vos critères.</div>
      )}

      {results && results.total_pages > 1 && (
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => doSearch(page - 1)}>← Précédent</button>
          <span>Page {results.page} / {results.total_pages}</span>
          <button disabled={page >= results.total_pages} onClick={() => doSearch(page + 1)}>Suivant →</button>
        </div>
      )}

      {/* Notice detail modal */}
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
