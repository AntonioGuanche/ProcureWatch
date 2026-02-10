import { useEffect, useState } from "react";
import { useParams, useSearchParams, Link, useNavigate } from "react-router-dom";
import { getWatchlist, previewWatchlist, newSinceWatchlist, refreshWatchlist } from "../api";
import type { Watchlist, Notice } from "../types";
import { Toast } from "../components/Toast";

function formatDate(s: string | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

function chipList(items: string[], label: string): string {
  if (!items || items.length === 0) return "";
  return `${label}: ${items.join(", ")}`;
}

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

  const setTab = (t: Tab) => {
    navigate(`/watchlists/${id}?tab=${t}`, { replace: true });
  };

  useEffect(() => {
    if (!id) return;
    getWatchlist(id).then(setWatchlist).catch(() => setToast("Failed to load watchlist"));
  }, [id]);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    const fn = tab === "new" ? newSinceWatchlist : previewWatchlist;
    fn(id, page, pageSize)
      .then((res) => {
        setNotices(res.items);
        setTotal(res.total);
      })
      .catch(() => setToast("Failed to load notices"))
      .finally(() => setLoading(false));
  }, [id, tab, page, pageSize]);

  const handleRefresh = async () => {
    if (!id) return;
    setRefreshing(true);
    try {
      await refreshWatchlist(id);
      setToast("Refresh completed");
      getWatchlist(id).then(setWatchlist);
      const fn = tab === "new" ? newSinceWatchlist : previewWatchlist;
      const res = await fn(id, page, pageSize);
      setNotices(res.items);
      setTotal(res.total);
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  };

  if (!watchlist) return <p>Loading watchlist…</p>;

  // Build filter summary
  const filters = [
    chipList(watchlist.keywords, "Mots-clés"),
    chipList(watchlist.cpv_prefixes, "CPV"),
    chipList(watchlist.countries, "Pays"),
    chipList(watchlist.nuts_prefixes, "NUTS"),
  ].filter(Boolean);

  return (
    <>
      <h1>{watchlist.name}</h1>
      <div className="card">
        <div className="wl-filters">
          {filters.length > 0 ? (
            <p>
              <strong>Filtres :</strong>{" "}
              {filters.map((f, i) => (
                <span key={i} className="filter-badge">{f}</span>
              ))}
            </p>
          ) : (
            <p><strong>Filtres :</strong> <em>Aucun filtre — matche toutes les notices</em></p>
          )}
        </div>
        <p>
          Dernier refresh : {formatDate(watchlist.last_refresh_at)} | Notify : {watchlist.notify_email ?? "—"} | {watchlist.enabled ? "✅ Active" : "⏸️ Désactivée"}
        </p>
        <p>
          <Link to="/watchlists" className="btn">← Back to list</Link>
          <Link to={`/watchlists/${id}/edit`} className="btn">Edit</Link>
          <button onClick={handleRefresh} disabled={refreshing} className="btn primary">
            {refreshing ? "Refreshing…" : "Refresh now"}
          </button>
        </p>
      </div>
      <div className="tabs">
        <button
          className={tab === "preview" ? "active" : ""}
          onClick={() => setTab("preview")}
        >
          Preview
        </button>
        <button
          className={tab === "new" ? "active" : ""}
          onClick={() => setTab("new")}
        >
          New since last notified
        </button>
      </div>
      {loading ? (
        <p>Loading notices…</p>
      ) : (
        <>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Published</th>
                  <th>Title</th>
                  <th>Buyer</th>
                  <th>CPV</th>
                  <th>Deadline</th>
                  <th>URL</th>
                </tr>
              </thead>
              <tbody>
                {notices.map((n) => (
                  <tr key={n.id}>
                    <td>{formatDate(n.publication_date)}</td>
                    <td>{n.title}</td>
                    <td>{n.organisation_names ? Object.values(n.organisation_names)[0] ?? "—" : "—"}</td>
                    <td>{n.cpv_main_code ?? "—"}</td>
                    <td>{formatDate(n.deadline)}</td>
                    <td>
                      {n.url ? (
                        <a href={n.url} target="_blank" rel="noopener noreferrer">
                          Link
                        </a>
                      ) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {total === 0 && <p>No notices.</p>}
          {total > pageSize && (
            <div className="pagination">
              <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</button>
              <span>Page {page} of {Math.ceil(total / pageSize)} ({total} total)</span>
              <button disabled={page >= Math.ceil(total / pageSize)} onClick={() => setPage((p) => p + 1)}>Next</button>
            </div>
          )}
        </>
      )}
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </>
  );
}
