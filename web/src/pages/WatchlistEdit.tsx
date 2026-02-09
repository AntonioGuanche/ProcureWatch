import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getWatchlist, updateWatchlist } from "../api";
import type { Watchlist, WatchlistUpdate } from "../types";
import { WatchlistForm } from "./WatchlistForm";
import { Toast } from "../components/Toast";

export function WatchlistEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [wl, setWl] = useState<Watchlist | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getWatchlist(id)
      .then(setWl)
      .catch((e) => setToast(e instanceof Error ? e.message : "Erreur"))
      .finally(() => setLoading(false));
  }, [id]);

  const handleSubmit = async (payload: import("../types").WatchlistCreate | WatchlistUpdate) => {
    if (!id) return;
    try {
      await updateWatchlist(id, payload as WatchlistUpdate);
      navigate(`/watchlists/${id}`);
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Erreur de mise à jour");
    }
  };

  if (loading) return <div className="loading">Chargement…</div>;
  if (!wl) return <div className="alert alert-error">Veille introuvable</div>;

  return (
    <div className="page">
      <div className="page-header">
        <h1>Modifier « {wl.name} »</h1>
      </div>
      <div className="card" style={{ maxWidth: 600 }}>
        <WatchlistForm initial={wl} onSubmit={handleSubmit} onCancel={() => navigate(`/watchlists/${id}`)} />
      </div>
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
