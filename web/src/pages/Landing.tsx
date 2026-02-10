import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

interface CpvSuggestion {
  code: string;
  label: string;
}

interface AnalysisResult {
  url: string;
  company_name: string | null;
  meta_description: string | null;
  keywords: string[];
  suggested_cpv: CpvSuggestion[];
  raw_word_count: number;
}

export default function Landing() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [selectedKeywords, setSelectedKeywords] = useState<Set<string>>(new Set());
  const resultRef = useRef<HTMLDivElement>(null);

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const resp = await fetch("/api/public/analyze-website", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim() }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Erreur d'analyse");
      setResult(data);
      // Auto-select top 8 keywords
      setSelectedKeywords(new Set(data.keywords.slice(0, 8)));
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 200);
    } catch (err: any) {
      setError(err.message || "Impossible d'analyser ce site");
    } finally {
      setLoading(false);
    }
  };

  const toggleKeyword = (kw: string) => {
    setSelectedKeywords((prev) => {
      const next = new Set(prev);
      if (next.has(kw)) next.delete(kw);
      else next.add(kw);
      return next;
    });
  };

  const handleCreateWatchlist = () => {
    const kws = Array.from(selectedKeywords);
    const cpvs = result?.suggested_cpv?.map((c) => c.code) || [];
    // Store in sessionStorage for after signup
    sessionStorage.setItem("pw_onboarding", JSON.stringify({
      keywords: kws,
      cpv_codes: cpvs,
      company_name: result?.company_name || "",
      source_url: result?.url || "",
    }));
    if (user) {
      navigate("/watchlists/new");
    } else {
      navigate("/signup");
    }
  };

  return (
    <div className="landing">
      {/* ─── Header ─── */}
      <header className="landing-header">
        <div className="landing-header-inner">
          <span className="landing-brand">ProcureWatch</span>
          <div className="landing-header-actions">
            {user ? (
              <button className="btn-landing-primary" onClick={() => navigate("/dashboard")}>
                Mon tableau de bord →
              </button>
            ) : (
              <>
                <button className="btn-landing-ghost" onClick={() => navigate("/login")}>Connexion</button>
                <button className="btn-landing-primary" onClick={() => navigate("/signup")}>Essai gratuit</button>
              </>
            )}
          </div>
        </div>
      </header>

      {/* ─── Hero ─── */}
      <section className="landing-hero">
        <div className="landing-hero-inner">
          <div className="hero-badge">🇧🇪 🇪🇺 Belgique &amp; Europe</div>
          <h1>Ne ratez plus aucun marché public</h1>
          <p className="hero-subtitle">
            ProcureWatch centralise les appels d'offres belges (BOSA) et européens (TED) 
            et vous alerte automatiquement sur les opportunités qui correspondent à votre activité.
          </p>

          {/* ─── Analyzer Tool ─── */}
          <div className="analyzer-card">
            <div className="analyzer-header">
              <div className="analyzer-icon">🔍</div>
              <div>
                <h2>Découvrez vos opportunités en 10 secondes</h2>
                <p>Entrez l'URL de votre site web — on détecte vos mots-clés métier et les marchés correspondants.</p>
              </div>
            </div>

            <form onSubmit={handleAnalyze} className="analyzer-form">
              <div className="analyzer-input-row">
                <input
                  type="text"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://www.votre-entreprise.be"
                  className="analyzer-input"
                  disabled={loading}
                />
                <button type="submit" className="btn-analyze" disabled={loading || !url.trim()}>
                  {loading ? (
                    <span className="spinner-inline" />
                  ) : (
                    "Analyser"
                  )}
                </button>
              </div>
              {error && <div className="analyzer-error">{error}</div>}
            </form>
          </div>
        </div>
      </section>

      {/* ─── Analysis Results ─── */}
      {result && (
        <section className="landing-results" ref={resultRef}>
          <div className="landing-results-inner">
            {result.company_name && (
              <div className="result-company">
                <span className="result-company-label">Entreprise détectée :</span>
                <span className="result-company-name">{result.company_name}</span>
              </div>
            )}

            <div className="result-grid">
              {/* Keywords */}
              <div className="result-card">
                <h3>🏷️ Mots-clés détectés</h3>
                <p className="result-hint">Cliquez pour sélectionner/désélectionner les mots-clés pertinents pour votre veille.</p>
                <div className="keyword-chips">
                  {result.keywords.map((kw) => (
                    <button
                      key={kw}
                      className={`keyword-chip ${selectedKeywords.has(kw) ? "selected" : ""}`}
                      onClick={() => toggleKeyword(kw)}
                    >
                      {selectedKeywords.has(kw) && <span className="chip-check">✓ </span>}
                      {kw}
                    </button>
                  ))}
                </div>
              </div>

              {/* CPV Suggestions */}
              {result.suggested_cpv.length > 0 && (
                <div className="result-card">
                  <h3>📋 Codes CPV suggérés</h3>
                  <p className="result-hint">Catégories de marchés publics qui correspondent à votre activité.</p>
                  <div className="cpv-list">
                    {result.suggested_cpv.map((cpv) => (
                      <div key={cpv.code} className="cpv-item">
                        <span className="cpv-code">{cpv.code}</span>
                        <span className="cpv-label">{cpv.label}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* CTA */}
            <div className="result-cta">
              <p className="result-cta-text">
                <strong>{selectedKeywords.size} mot(s)-clé(s)</strong> sélectionné(s)
                {result.suggested_cpv.length > 0 && (
                  <> + <strong>{result.suggested_cpv.length} code(s) CPV</strong></>
                )}
              </p>
              <button className="btn-create-watchlist" onClick={handleCreateWatchlist} disabled={selectedKeywords.size === 0}>
                {user ? "Créer ma veille avec ces mots-clés →" : "Créer mon compte et ma première veille →"}
              </button>
              <p className="result-cta-sub">Gratuit • Sans engagement • Alertes par email</p>
            </div>
          </div>
        </section>
      )}

      {/* ─── How It Works ─── */}
      <section className="landing-steps">
        <div className="landing-steps-inner">
          <h2>Comment ça marche ?</h2>
          <div className="steps-grid">
            <div className="step-card">
              <div className="step-number">1</div>
              <div className="step-icon">🌐</div>
              <h3>Analysez votre site</h3>
              <p>Entrez l'URL de votre entreprise. Notre outil détecte automatiquement vos mots-clés métier.</p>
            </div>
            <div className="step-card">
              <div className="step-number">2</div>
              <div className="step-icon">🔔</div>
              <h3>Créez votre veille</h3>
              <p>Affinez les mots-clés, choisissez vos zones géographiques, et activez les alertes email.</p>
            </div>
            <div className="step-card">
              <div className="step-number">3</div>
              <div className="step-icon">🎯</div>
              <h3>Remportez des marchés</h3>
              <p>Recevez chaque jour les nouvelles opportunités. Accédez aux documents et déposez vos offres.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Stats ─── */}
      <section className="landing-stats">
        <div className="landing-stats-inner">
          <div className="stat-item">
            <div className="stat-number">3 900+</div>
            <div className="stat-label">Marchés référencés</div>
          </div>
          <div className="stat-item">
            <div className="stat-number">2</div>
            <div className="stat-label">Sources (BOSA + TED)</div>
          </div>
          <div className="stat-item">
            <div className="stat-number">24h</div>
            <div className="stat-label">Délai d'alerte</div>
          </div>
          <div className="stat-item">
            <div className="stat-number">Gratuit</div>
            <div className="stat-label">Pour démarrer</div>
          </div>
        </div>
      </section>

      {/* ─── Features ─── */}
      <section className="landing-features">
        <div className="landing-features-inner">
          <h2>Tout ce qu'il faut pour trouver vos marchés</h2>
          <div className="features-grid">
            <div className="feature-item">
              <div className="feature-icon">🇧🇪</div>
              <h3>Marchés belges</h3>
              <p>Tous les avis du portail e-Procurement (BOSA), mis à jour quotidiennement.</p>
            </div>
            <div className="feature-item">
              <div className="feature-icon">🇪🇺</div>
              <h3>Marchés européens</h3>
              <p>Les appels d'offres TED couvrant la Belgique, France, Luxembourg et toute l'UE.</p>
            </div>
            <div className="feature-item">
              <div className="feature-icon">📧</div>
              <h3>Alertes email</h3>
              <p>Recevez un résumé des nouveaux marchés correspondant à vos veilles, directement dans votre boîte mail.</p>
            </div>
            <div className="feature-item">
              <div className="feature-icon">📄</div>
              <h3>Documents inclus</h3>
              <p>Accédez aux cahiers des charges et documents d'appels d'offres directement depuis la plateforme.</p>
            </div>
            <div className="feature-item">
              <div className="feature-icon">⭐</div>
              <h3>Favoris</h3>
              <p>Marquez les marchés intéressants et retrouvez-les facilement depuis votre tableau de bord.</p>
            </div>
            <div className="feature-item">
              <div className="feature-icon">🔍</div>
              <h3>Recherche avancée</h3>
              <p>Filtrez par mots-clés, codes CPV, zones NUTS, types de procédures, dates et montants.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ─── CTA Final ─── */}
      <section className="landing-final-cta">
        <div className="landing-final-inner">
          <h2>Prêt à trouver vos prochains marchés ?</h2>
          <p>Créez votre compte gratuitement et recevez vos premières alertes aujourd'hui.</p>
          {user ? (
            <button className="btn-landing-primary btn-lg" onClick={() => navigate("/dashboard")}>
              Accéder à mon tableau de bord →
            </button>
          ) : (
            <button className="btn-landing-primary btn-lg" onClick={() => navigate("/signup")}>
              Commencer gratuitement →
            </button>
          )}
        </div>
      </section>

      {/* ─── Footer ─── */}
      <footer className="landing-footer">
        <div className="landing-footer-inner">
          <span className="landing-brand-sm">ProcureWatch</span>
          <span className="landing-footer-text">Veille des marchés publics — Belgique &amp; Europe</span>
          <span className="landing-footer-text">© 2026 ProcureWatch</span>
        </div>
      </footer>
    </div>
  );
}
