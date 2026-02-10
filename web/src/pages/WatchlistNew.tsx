import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { createWatchlist } from "../api";
import type { WatchlistCreate, Watchlist } from "../types";
import { WatchlistForm } from "./WatchlistForm";
import { Toast } from "../components/Toast";

export function WatchlistNew() {
  const navigate = useNavigate();
  const [toast, setToast] = useState<string | null>(null);
  const [prefill, setPrefill] = useState<Partial<Watchlist> | null>(null);

  // Check for onboarding data from landing page analyzer
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem("pw_onboarding");
      if (raw) {
        const data = JSON.parse(raw);
        setPrefill({
          name: data.company_name ? `Veille ${data.company_name}` : "Ma première veille",
          keywords: data.keywords || [],
          cpv_prefixes: data.cpv_codes || [],
          enabled: true,
        } as Partial<Watchlist>);
        sessionStorage.removeItem("pw_onboarding");
      }
    } catch { /* ignore */ }
  }, []);

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
        <p className="page-subtitle">
          {prefill ? "Nous avons pré-rempli les mots-clés détectés sur votre site. Ajustez si besoin !" : "Configurez les critères de votre veille marchés publics"}
        </p>
      </div>
      <div className="card" style={{ maxWidth: 600 }}>
        <WatchlistForm
          initial={prefill as any}
          onSubmit={handleSubmit}
          onCancel={() => navigate("/watchlists")}
        />
      </div>
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
