import { useEffect, useState, useCallback, useRef } from "react";
import { searchNotices, getFacets, getFavoriteIds, addFavorite, removeFavorite, getTranslationExpansion, type SearchParams, type TranslationExpansion } from "../api";
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

/**
 * Column sort configuration.
 * Each sortable column maps to its desc and asc backend sort keys.
 */
const COLUMN_SORTS: Record<string, { desc: string; asc: string }> = {
  publication: { desc: "date_desc", asc: "date_asc" },
  deadline:    { desc: "deadline_desc", asc: "deadline" },
  value:       { desc: "value_desc", asc: "value_asc" },
  award:       { desc: "award_desc", asc: "award_asc" },
  cpv:         { desc: "cpv_desc", asc: "cpv_asc" },
  source:      { desc: "source_desc", asc: "source_asc" },
};

/** Determine which column + direction is currently active */
function parseSort(sort: string): { col: string | null; dir: "asc" | "desc" } {
  for (const [col, keys] of Object.entries(COLUMN_SORTS)) {
    if (sort === keys.desc) return { col, dir: "desc" };
    if (sort === keys.asc)  return { col, dir: "asc" };
  }
  if (sort === "relevance") return { col: null, dir: "desc" };
  return { col: "publication", dir: "desc" }; // default
}

/** Sort arrow indicator */
function SortArrow({ col, currentSort }: { col: string; currentSort: string }) {
  const { col: activeCol, dir } = parseSort(currentSort);
  if (activeCol !== col) return <span className="sort-arrow inactive">⇅</span>;
  return <span className="sort-arrow active">{dir === "desc" ? "↓" : "↑"}</span>;
}

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

  // Translation preview — debounced
  const [translations, setTranslations] = useState<TranslationExpansion | null>(null);
  const translationTimer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => {
    clearTimeout(translationTimer.current);
    const trimmed = q.trim();
    if (!trimmed || trimmed.length < 2) { setTranslations(null); return; }
    translationTimer.current = setTimeout(() => {
      getTranslationExpansion(trimmed)
        .then((t) => {
          if (t.expanded_count > t.original_count) setTranslations(t);
          else setTranslations(null);
        })
        .catch(() => setTranslations(null));
    }, 400);
    return () => clearTimeout(translationTimer.current);
  }, [q]);

  const doSearch = useCallback(async (p: number, sortOverride?: string) => {
    const effectiveSort = sortOverride ?? sort;
    setLoading(true);
    setError(null);
    setPage(p);
    try {
      const params: SearchParams = { page: p, page_size: pageSize, sort: effectiveSort };
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

  /** Handle column header click: toggle direction or switch column */
  const handleColumnSort = (col: string) => {
    const keys = COLUMN_SORTS[col];
    if (!keys) return;
    const { col: activeCol, dir } = parseSort(sort);
    let newSort: string;
    if (activeCol === col) {
      // Toggle direction
      newSort = dir === "desc" ? keys.asc : keys.desc;
    } else {
      // New column — default to desc (most useful first)
      newSort = keys.desc;
    }
    setSort(newSort);
    doSearch(1, newSort);
  };

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
              <option key={f.code} value={f.code}>{f.code} — {f.label || "?"} ({f.count})</option>
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
          {results && <span className="results-count">{results.total.toLocaleString("fr-BE")} résultat{results.total !== 1 ? "s" : ""}</span>}
        </div>

        {translations && (
          <div className="translation-bar">
            <span className="translation-label">🌐 Recherche étendue :</span>
            {translations.expanded
              .filter((t) => !translations.original.map(o => o.toLowerCase()).includes(t.toLowerCase()))
              .map((t) => (
                <span key={t} className="translation-tag">{t}</span>
              ))}
          </div>
        )}
      </form>

      {error && <div className="alert alert-error">{error}</div>}
      {loading && !results && <div className="loading">Chargement…</div>}

      {results && results.items.length > 0 && (
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: "3%" }}></th>
                <th style={{ width: "30%" }}>Titre</th>
                <th className="th-sortable" style={{ width: "8%" }} onClick={() => handleColumnSort("cpv")}>
                  CPV <SortArrow col="cpv" currentSort={sort} />
                </th>
                <th className="th-sortable" style={{ width: "7%" }} onClick={() => handleColumnSort("source")}>
                  Source <SortArrow col="source" currentSort={sort} />
                </th>
                <th className="th-sortable" style={{ width: "10%" }} onClick={() => handleColumnSort("publication")}>
                  Publication <SortArrow col="publication" currentSort={sort} />
                </th>
                <th className="th-sortable" style={{ width: "12%" }} onClick={() => handleColumnSort("deadline")}>
                  Deadline <SortArrow col="deadline" currentSort={sort} />
                </th>
                <th className="th-sortable" style={{ width: "10%" }} onClick={() => handleColumnSort("value")}>
                  Valeur est. <SortArrow col="value" currentSort={sort} />
                </th>
                <th className="th-sortable" style={{ width: "10%" }} onClick={() => handleColumnSort("award")}>
                  Attribution <SortArrow col="award" currentSort={sort} />
                </th>
              </tr>
            </thead>
            <tbody>
              {results.items.map((n) => {
                const isAwarded = !!(n.award_winner_name || n.award_value);
                return (
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
                      {isAwarded && (
                        <span className="tag tag-awarded" title={n.award_winner_name || "Attribué"}>Attribué</span>
                      )}
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
                    <td className="nowrap">
                      {n.award_value ? (
                        <span className="award-cell" title={n.award_winner_name || undefined}>
                          {fmtValue(n.award_value)}
                        </span>
                      ) : n.award_winner_name ? (
                        <span className="award-cell award-winner-only" title={n.award_winner_name}>
                          {n.award_winner_name.length > 20 ? n.award_winner_name.slice(0, 20) + "…" : n.award_winner_name}
                        </span>
                      ) : "—"}
                    </td>
                  </tr>
                );
              })}
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
