import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getWatchlist, updateWatchlist } from "../api";
import type { WatchlistUpdate } from "../types";
import { WatchlistForm } from "./WatchlistForm";

export function WatchlistEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [watchlist, setWatchlist] = useState<Awaited<ReturnType<typeof getWatchlist>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getWatchlist(id)
      .then(setWatchlist)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, [id]);

  const handleSubmit = async (payload: WatchlistUpdate) => {
    if (!id) return;
    await updateWatchlist(id, payload);
    navigate(`/watchlists/${id}`);
  };

  if (error) return <p>{error}</p>;
  if (!watchlist) return <p>Loading…</p>;

  return (
    <>
      <h1>Edit watchlist</h1>
      <div className="card">
        <WatchlistForm
          initial={watchlist}
          onSubmit={handleSubmit}
          onCancel={() => navigate(`/watchlists/${id}`)}
        />
      </div>
    </>
  );
}
