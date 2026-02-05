import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listWatchlists, deleteWatchlist, refreshWatchlist } from "../api";
import type { Watchlist } from "../types";
import { Toast } from "../components/Toast";

function formatDate(s: string | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
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
      setToast(e instanceof Error ? e.message : "Failed to load watchlists");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [page]);

  const handleRefresh = async (id: string) => {
    setRefreshingId(id);
    try {
      await refreshWatchlist(id);
      setToast("Refresh completed");
      load();
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Refresh failed");
    } finally {
      setRefreshingId(null);
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`Delete watchlist "${name}"?`)) return;
    try {
      await deleteWatchlist(id);
      setToast("Deleted");
      load();
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Delete failed");
    }
  };

  return (
    <>
      <h1>Watchlists</h1>
      <p>
        <Link to="/watchlists/new" className="btn primary">Create watchlist</Link>
      </p>
      {loading ? (
        <p>Loading…</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Enabled</th>
                <th>Term</th>
                <th>CPV</th>
                <th>Buyer</th>
                <th>Procedure</th>
                <th>Country</th>
                <th>Lang</th>
                <th>Last refresh</th>
                <th>Last notified</th>
                <th>Notify email</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((w) => (
                <tr key={w.id}>
                  <td>{w.name}</td>
                  <td>{w.is_enabled ? "Yes" : "No"}</td>
                  <td>{w.term ?? "—"}</td>
                  <td>{w.cpv_prefix ?? "—"}</td>
                  <td>{w.buyer_contains ?? "—"}</td>
                  <td>{w.procedure_type ?? "—"}</td>
                  <td>{w.country}</td>
                  <td>{w.language ?? "—"}</td>
                  <td>{formatDate(w.last_refresh_at)}</td>
                  <td>{formatDate(w.last_notified_at)}</td>
                  <td>{w.notify_email ?? "—"}</td>
                  <td>
                    <Link to={`/watchlists/${w.id}?tab=preview`} className="btn">Preview</Link>
                    <Link to={`/watchlists/${w.id}?tab=new`} className="btn">New</Link>
                    <button
                      onClick={() => handleRefresh(w.id)}
                      disabled={refreshingId === w.id}
                    >
                      {refreshingId === w.id ? "…" : "Refresh now"}
                    </button>
                    <Link to={`/watchlists/${w.id}/edit`} className="btn">Edit</Link>
                    <button onClick={() => handleDelete(w.id, w.name)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {total > pageSize && (
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</button>
          <span>Page {page} of {Math.ceil(total / pageSize)} ({total} total)</span>
          <button disabled={page >= Math.ceil(total / pageSize)} onClick={() => setPage((p) => p + 1)}>Next</button>
        </div>
      )}
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </>
  );
}
