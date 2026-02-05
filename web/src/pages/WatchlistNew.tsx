import { useNavigate } from "react-router-dom";
import { createWatchlist } from "../api";
import type { WatchlistCreate } from "../types";
import { WatchlistForm } from "./WatchlistForm";

export function WatchlistNew() {
  const navigate = useNavigate();

  const handleSubmit = async (payload: WatchlistCreate | import("../types").WatchlistUpdate) => {
    const w = await createWatchlist(payload as WatchlistCreate);
    navigate(`/watchlists/${w.id}`);
  };

  return (
    <>
      <h1>Create watchlist</h1>
      <div className="card">
        <WatchlistForm onSubmit={handleSubmit} onCancel={() => navigate("/watchlists")} />
      </div>
    </>
  );
}
