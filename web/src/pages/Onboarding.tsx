import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { createWatchlist } from "../api";
import type { WatchlistCreate } from "../types";

/**
 * Post-signup onboarding wizard — shown when user has 0 watchlists.
 * 3 steps: Sector → Keywords & Region → Preview & Create
 */

// ── Predefined sectors with CPV codes and suggested keywords ──────
const SECTORS = [
  {
    id: "it",
    icon: "💻",
    name: "IT & Logiciel",
    description: "Développement, infra, cloud, cybersécurité",
    cpv: ["72000000", "48000000", "30200000"],
    keywords: ["logiciel", "software", "développement", "informatique", "cloud", "cybersécurité", "SaaS", "application web"],
  },
  {
    id: "construction",
    icon: "🏗️",
    name: "Construction & BTP",
    description: "Travaux, rénovation, voirie, HVAC",
    cpv: ["45000000"],
    keywords: ["construction", "rénovation", "bâtiment", "travaux", "HVAC", "voirie", "génie civil"],
  },
  {
    id: "consulting",
    icon: "📊",
    name: "Conseil & Études",
    description: "Management, audit, stratégie, formation",
    cpv: ["79000000", "73000000", "80000000"],
    keywords: ["conseil", "consultance", "audit", "étude", "formation", "stratégie", "management"],
  },
  {
    id: "communication",
    icon: "📢",
    name: "Communication & Marketing",
    description: "Agences, design, événementiel, impression",
    cpv: ["79340000", "79800000", "22000000", "79950000"],
    keywords: ["communication", "marketing", "graphisme", "événement", "impression", "publicité", "design"],
  },
  {
    id: "cleaning",
    icon: "🧹",
    name: "Nettoyage & Facility",
    description: "Entretien, espaces verts, sécurité",
    cpv: ["90900000", "90600000", "77300000", "79710000"],
    keywords: ["nettoyage", "entretien", "facility management", "espaces verts", "sécurité", "gardiennage"],
  },
  {
    id: "health",
    icon: "🏥",
    name: "Santé & Médical",
    description: "Fournitures médicales, pharma, laboratoire",
    cpv: ["33000000", "85000000"],
    keywords: ["médical", "santé", "pharmaceutique", "laboratoire", "hôpital", "dispositif médical"],
  },
  {
    id: "food",
    icon: "🍽️",
    name: "Alimentation & Catering",
    description: "Restauration collective, fournitures alimentaires",
    cpv: ["55000000", "15000000"],
    keywords: ["alimentation", "catering", "restauration", "repas", "traiteur", "collectivité"],
  },
  {
    id: "transport",
    icon: "🚛",
    name: "Transport & Logistique",
    description: "Transport, déménagement, courrier, véhicules",
    cpv: ["60000000", "34000000", "64000000"],
    keywords: ["transport", "logistique", "déménagement", "véhicule", "flotte", "courrier", "livraison"],
  },
];

// ── Belgian regions ──
const REGIONS = [
  { code: "BE1", name: "Bruxelles-Capitale", emoji: "🏙️" },
  { code: "BE2", name: "Flandre", emoji: "🦁" },
  { code: "BE3", name: "Wallonie", emoji: "🐓" },
];

interface PreviewNotice {
  title: string;
  authority: string | null;
  cpv: string | null;
  source: string | null;
  publication_date: string | null;
  deadline: string | null;
}

export default function Onboarding() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [step, setStep] = useState(1);

  // Step 1: Sector
  const [selectedSector, setSelectedSector] = useState<string | null>(null);

  // Step 2: Keywords & Region
  const [keywords, setKeywords] = useState<string[]>([]);
  const [selectedKeywords, setSelectedKeywords] = useState<Set<string>>(new Set());
  const [customKw, setCustomKw] = useState("");
  const [selectedRegions, setSelectedRegions] = useState<Set<string>>(new Set());
  const [cpvCodes, setCpvCodes] = useState<string[]>([]);

  // Step 3: Preview & Create
  const [watchlistName, setWatchlistName] = useState("");
  const [preview, setPreview] = useState<{ total_matches: number; sample: PreviewNotice[] } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  // When sector is selected, populate keywords
  useEffect(() => {
    if (!selectedSector) return;
    const sector = SECTORS.find((s) => s.id === selectedSector);
    if (sector) {
      setKeywords(sector.keywords);
      setSelectedKeywords(new Set(sector.keywords));
      setCpvCodes(sector.cpv);
      setWatchlistName(`Veille ${sector.name}`);
    }
  }, [selectedSector]);

  // Fetch preview when moving to step 3
  useEffect(() => {
    if (step !== 3) return;
    fetchPreview();
  }, [step]);

  const fetchPreview = async () => {
    const kws = Array.from(selectedKeywords);
    if (kws.length === 0 && cpvCodes.length === 0) return;
    setPreviewLoading(true);
    try {
      const resp = await fetch("/api/public/preview-matches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keywords: kws, cpv_codes: cpvCodes }),
      });
      if (resp.ok) {
        setPreview(await resp.json());
      }
    } catch { /* ignore */ }
    finally { setPreviewLoading(false); }
  };

  const addCustomKeyword = () => {
    const kw = customKw.trim().toLowerCase();
    if (!kw || keywords.includes(kw)) { setCustomKw(""); return; }
    setKeywords((prev) => [...prev, kw]);
    setSelectedKeywords((prev) => new Set(prev).add(kw));
    setCustomKw("");
  };

  const toggleKeyword = (kw: string) => {
    setSelectedKeywords((prev) => {
      const next = new Set(prev);
      if (next.has(kw)) next.delete(kw);
      else next.add(kw);
      return next;
    });
  };

  const toggleRegion = (code: string) => {
    setSelectedRegions((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  const handleCreate = async () => {
    setCreating(true);
    setError("");
    try {
      const payload: WatchlistCreate = {
        name: watchlistName || "Ma première veille",
        keywords: Array.from(selectedKeywords),
        cpv_prefixes: cpvCodes,
        nuts_prefixes: Array.from(selectedRegions),
        enabled: true,
        notify_email: user?.email || null,
      };
      const w = await createWatchlist(payload);
      // Mark onboarding as done
      sessionStorage.setItem("pw_onboarding_done", "1");
      navigate(`/watchlists/${w.id}`, { replace: true });
    } catch (e: any) {
      setError(e.message || "Erreur lors de la création");
      setCreating(false);
    }
  };

  const canGoStep2 = selectedSector !== null;
  const canGoStep3 = selectedKeywords.size > 0;

  return (
    <div className="ob-root">
      <div className="ob-container">
        {/* Header */}
        <div className="ob-header">
          <div className="ob-brand">🔍 ProcureWatch</div>
          <div className="ob-steps">
            <div className={`ob-step-dot ${step >= 1 ? "active" : ""}`}>1</div>
            <div className="ob-step-line" />
            <div className={`ob-step-dot ${step >= 2 ? "active" : ""}`}>2</div>
            <div className="ob-step-line" />
            <div className={`ob-step-dot ${step >= 3 ? "active" : ""}`}>3</div>
          </div>
          <button className="ob-skip" onClick={() => { sessionStorage.setItem("pw_onboarding_done", "1"); navigate("/dashboard"); }}>
            Passer →
          </button>
        </div>

        {/* ── Step 1: Sector ── */}
        {step === 1 && (
          <div className="ob-step">
            <div className="ob-step-header">
              <h1>Bienvenue{user?.name ? `, ${user.name.split(" ")[0]}` : ""} !</h1>
              <p>Dans quel secteur cherchez-vous des marchés publics ?</p>
            </div>
            <div className="ob-sector-grid">
              {SECTORS.map((s) => (
                <button
                  key={s.id}
                  className={`ob-sector-card ${selectedSector === s.id ? "selected" : ""}`}
                  onClick={() => setSelectedSector(s.id)}
                >
                  <span className="ob-sector-icon">{s.icon}</span>
                  <span className="ob-sector-name">{s.name}</span>
                  <span className="ob-sector-desc">{s.description}</span>
                </button>
              ))}
            </div>
            <div className="ob-actions">
              <button className="ld-btn-primary ld-btn-lg" disabled={!canGoStep2} onClick={() => setStep(2)}>
                Continuer →
              </button>
            </div>
          </div>
        )}

        {/* ── Step 2: Keywords & Region ── */}
        {step === 2 && (
          <div className="ob-step">
            <div className="ob-step-header">
              <h1>Affinez vos critères</h1>
              <p>Sélectionnez les mots-clés pertinents et votre zone géographique.</p>
            </div>

            <div className="ob-section">
              <h3>Mots-clés</h3>
              <p className="ob-section-hint">Cliquez pour activer/désactiver. Ajoutez les vôtres ci-dessous.</p>
              <div className="ob-keyword-pills">
                {keywords.map((kw) => (
                  <button
                    key={kw}
                    className={`ob-pill ${selectedKeywords.has(kw) ? "active" : ""}`}
                    onClick={() => toggleKeyword(kw)}
                  >
                    {kw}
                  </button>
                ))}
              </div>
              <div className="ob-add-kw">
                <input
                  type="text"
                  placeholder="Ajouter un mot-clé…"
                  value={customKw}
                  onChange={(e) => setCustomKw(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addCustomKeyword())}
                />
                <button className="ld-btn-outline" onClick={addCustomKeyword} disabled={!customKw.trim()}>
                  Ajouter
                </button>
              </div>
            </div>

            <div className="ob-section">
              <h3>Région</h3>
              <p className="ob-section-hint">Optionnel — laissez vide pour toute la Belgique + Europe.</p>
              <div className="ob-region-cards">
                {REGIONS.map((r) => (
                  <button
                    key={r.code}
                    className={`ob-region-card ${selectedRegions.has(r.code) ? "selected" : ""}`}
                    onClick={() => toggleRegion(r.code)}
                  >
                    <span className="ob-region-emoji">{r.emoji}</span>
                    <span>{r.name}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="ob-actions">
              <button className="ld-btn-outline" onClick={() => setStep(1)}>← Retour</button>
              <button className="ld-btn-primary ld-btn-lg" disabled={!canGoStep3} onClick={() => setStep(3)}>
                Voir les résultats →
              </button>
            </div>
          </div>
        )}

        {/* ── Step 3: Preview & Create ── */}
        {step === 3 && (
          <div className="ob-step">
            <div className="ob-step-header">
              <h1>Votre veille est prête !</h1>
              <p>Voici un aperçu des marchés qui correspondent à vos critères.</p>
            </div>

            {/* Watchlist name */}
            <div className="ob-section">
              <h3>Nom de votre veille</h3>
              <input
                type="text"
                className="ob-name-input"
                value={watchlistName}
                onChange={(e) => setWatchlistName(e.target.value)}
                placeholder="Ma veille marchés publics"
              />
            </div>

            {/* Summary */}
            <div className="ob-summary">
              <div className="ob-summary-item">
                <span className="ob-summary-label">Mots-clés</span>
                <span className="ob-summary-value">
                  {Array.from(selectedKeywords).slice(0, 5).join(", ")}
                  {selectedKeywords.size > 5 && ` +${selectedKeywords.size - 5}`}
                </span>
              </div>
              <div className="ob-summary-item">
                <span className="ob-summary-label">Codes CPV</span>
                <span className="ob-summary-value">{cpvCodes.join(", ") || "—"}</span>
              </div>
              <div className="ob-summary-item">
                <span className="ob-summary-label">Régions</span>
                <span className="ob-summary-value">
                  {selectedRegions.size > 0
                    ? Array.from(selectedRegions).map((c) => REGIONS.find((r) => r.code === c)?.name).join(", ")
                    : "Toute la Belgique + Europe"}
                </span>
              </div>
            </div>

            {/* Preview */}
            <div className="ob-section">
              <h3>
                Aperçu des marchés
                {preview && !previewLoading && (
                  <span className="ob-match-count">{preview.total_matches} résultat{preview.total_matches !== 1 ? "s" : ""}</span>
                )}
              </h3>
              {previewLoading && <div className="ob-preview-loading">Recherche en cours…</div>}
              {!previewLoading && preview && preview.sample.length > 0 && (
                <div className="ob-preview-list">
                  {preview.sample.slice(0, 5).map((n, i) => (
                    <div key={i} className="ob-preview-card">
                      <div className="ob-preview-title">{n.title}</div>
                      <div className="ob-preview-meta">
                        {n.authority && <span>🏢 {n.authority}</span>}
                        {n.source && <span className="ob-preview-source">{n.source}</span>}
                        {n.deadline && <span>⏰ {new Date(n.deadline).toLocaleDateString("fr-BE")}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {!previewLoading && preview && preview.sample.length === 0 && (
                <div className="ob-preview-empty">
                  Pas encore de résultats pour ces critères. Pas d'inquiétude — votre veille est active et vous serez notifié dès qu'un marché correspondant sera publié.
                </div>
              )}
            </div>

            {error && <div className="ob-error">{error}</div>}

            <div className="ob-actions">
              <button className="ld-btn-outline" onClick={() => setStep(2)}>← Modifier</button>
              <button className="ld-btn-primary ld-btn-lg" onClick={handleCreate} disabled={creating}>
                {creating ? "Création…" : "Créer ma veille et commencer →"}
              </button>
            </div>

            <p className="ob-digest-hint">
              Vous recevrez votre premier digest email {user?.plan === "free" ? "cette semaine" : "demain matin"} avec les marchés correspondants.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
