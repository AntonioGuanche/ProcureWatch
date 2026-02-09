import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createWatchlist } from "../api";
import type { WatchlistCreate } from "../types";
import { WatchlistForm } from "./WatchlistForm";
import { Toast } from "../components/Toast";

export function WatchlistNew() {
  const navigate = useNavigate();
  const [toast, setToast] = useState<string | null>(null);

  const handleSubmit = async (payload: WatchlistCreate | import("../types").WatchlistUpdate) => {
    try {
      const w = await createWatchlist(payload as WatchlistCreate);
      navigate(`/watchlists/${w.id}`);
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Erreur lors de la création");
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1>Nouvelle veille</h1>
        <p className="page-subtitle">Configurez les critères de votre veille marchés publics</p>
      </div>
      <div className="card" style={{ maxWidth: 600 }}>
        <WatchlistForm onSubmit={handleSubmit} onCancel={() => navigate("/watchlists")} />
      </div>
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
