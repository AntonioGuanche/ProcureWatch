import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

interface CpvSuggestion { code: string; label: string }
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
  const [customKw, setCustomKw] = useState("");
  const [allKeywords, setAllKeywords] = useState<string[]>([]);
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    setLoading(true); setError(""); setResult(null);
    try {
      const resp = await fetch("/api/public/analyze-website", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim() }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Erreur d'analyse");
      setResult(data);
      setAllKeywords(data.keywords);
      // Auto-select all detected keywords (they're already filtered for relevance)
      setSelectedKeywords(new Set(data.keywords));
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 200);
    } catch (err: any) {
      setError(err.message || "Impossible d'analyser ce site");
    } finally { setLoading(false); }
  };

  const toggleKeyword = (kw: string) => {
    setSelectedKeywords(prev => {
      const next = new Set(prev);
      next.has(kw) ? next.delete(kw) : next.add(kw);
      return next;
    });
  };

  const addCustomKeyword = () => {
    const kw = customKw.trim().toLowerCase();
    if (kw && kw.length >= 2 && !allKeywords.includes(kw)) {
      setAllKeywords(prev => [...prev, kw]);
      setSelectedKeywords(prev => new Set([...prev, kw]));
      setCustomKw("");
    }
  };

  const handleCustomKwKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") { e.preventDefault(); addCustomKeyword(); }
  };

  const handleCreateWatchlist = () => {
    const kws = Array.from(selectedKeywords);
    const cpvs = result?.suggested_cpv?.map(c => c.code) || [];
    sessionStorage.setItem("pw_onboarding", JSON.stringify({
      keywords: kws, cpv_codes: cpvs,
      company_name: result?.company_name || "", source_url: result?.url || "",
    }));
    navigate(user ? "/watchlists/new" : "/login");
  };

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  const faqs = [
    { q: "Qu'est-ce qu'une watchlist ?", a: "Une watchlist est un ensemble de critères (mots-clés, codes CPV, régions) qui définissent les marchés publics pertinents pour votre activité. ProcureWatch surveille en continu les nouvelles publications et vous alerte dès qu'un marché correspond." },
    { q: "Quelles sources sont couvertes ?", a: "Nous centralisons les avis du portail belge e-Procurement (BOSA) et du Tenders Electronic Daily (TED) de l'Union européenne. Cela couvre la quasi-totalité des marchés publics belges et européens." },
    { q: "L'outil est-il vraiment gratuit ?", a: "Le plan Explorer est gratuit et permet d'accéder à la base de données, de faire des recherches et de créer une watchlist. Les plans payants ajoutent les alertes email, plus de watchlists et des fonctionnalités avancées." },
    { q: "Puis-je annuler à tout moment ?", a: "Oui, aucun engagement. Vous pouvez annuler ou changer de plan à tout moment depuis votre profil." },
  ];

  return (
    <div className="ld">
      {/* ─── Sticky Nav ─── */}
      <nav className="ld-nav">
        <div className="ld-nav-inner">
          <span className="ld-logo" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="#10b981" strokeWidth="2.5"/><path d="M8 12l3 3 5-6" stroke="#10b981" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            ProcureWatch
          </span>
          <div className="ld-nav-links">
            <button className="ld-nav-link" onClick={() => scrollTo("features")}>Fonctionnalités</button>
            <button className="ld-nav-link" onClick={() => scrollTo("pricing")}>Tarifs</button>
            {user ? (
              <button className="ld-btn-primary" onClick={() => navigate("/dashboard")}>Mon tableau de bord</button>
            ) : (
              <>
                <button className="ld-nav-link" onClick={() => navigate("/login")}>Connexion</button>
                <button className="ld-btn-primary" onClick={() => navigate("/login")}>Démarrer gratuitement</button>
              </>
            )}
          </div>
        </div>
      </nav>

      {/* ─── Hero ─── */}
      <section className="ld-hero">
        <div className="ld-hero-inner">
          <div className="ld-hero-text">
            <h1>Ne ratez plus aucun<br/><span className="ld-gradient-text">marché public</span></h1>
            <p className="ld-hero-sub">
              Recevez des alertes personnalisées pour les marchés publics belges et européens. 
              Concentrez-vous sur vos offres, pas sur la recherche.
            </p>
            <div className="ld-hero-actions">
              <button className="ld-btn-primary ld-btn-lg" onClick={() => scrollTo("analyzer")}>
                Analyser mon site gratuitement
              </button>
              <button className="ld-btn-outline ld-btn-lg" onClick={() => scrollTo("how")}>
                Comment ça marche ?
              </button>
            </div>
          </div>
          <div className="ld-hero-visual">
            <div className="ld-mockup">
              <div className="ld-mockup-bar">
                <span className="ld-dot red"/><span className="ld-dot yellow"/><span className="ld-dot green"/>
                <span className="ld-mockup-url">app.procurewatch.eu</span>
              </div>
              <div className="ld-mockup-body">
                <div className="ld-mock-sidebar">
                  <div className="ld-mock-menu-item active">Dashboard</div>
                  <div className="ld-mock-menu-item">Rechercher</div>
                  <div className="ld-mock-menu-item">Veilles</div>
                </div>
                <div className="ld-mock-content">
                  <div className="ld-mock-row header"><span>Titre</span><span>Source</span><span>Date</span><span>Statut</span></div>
                  <div className="ld-mock-row"><span>Entretien espaces verts commune…</span><span className="ld-tag bosa">BOSA</span><span>10/02</span><span className="ld-tag new">Nouveau</span></div>
                  <div className="ld-mock-row"><span>Travaux de voirie — Lot 3</span><span className="ld-tag ted">TED</span><span>09/02</span><span className="ld-tag new">Nouveau</span></div>
                  <div className="ld-mock-row"><span>Fourniture mobilier de bureau</span><span className="ld-tag ted">TED</span><span>08/02</span><span className="ld-tag open">Ouvert</span></div>
                  <div className="ld-mock-row"><span>Nettoyage bâtiments admin.</span><span className="ld-tag bosa">BOSA</span><span>07/02</span><span className="ld-tag open">Ouvert</span></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Trust Bar ─── */}
      <section className="ld-trust">
        <div className="ld-trust-inner">
          <div className="ld-trust-item">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            Pensé pour artisans &amp; PME
          </div>
          <div className="ld-trust-item">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>
            Sources 🇧🇪 + 🇪🇺 centralisées
          </div>
          <div className="ld-trust-item">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            Mise en place en 5 minutes
          </div>
        </div>
      </section>

      {/* ─── Analyzer Tool ─── */}
      <section className="ld-analyzer" id="analyzer">
        <div className="ld-analyzer-inner">
          <div className="ld-section-label">Outil gratuit</div>
          <h2>Découvrez vos marchés publics en 10 secondes</h2>
          <p className="ld-section-sub">Entrez l'URL de votre site web — notre outil détecte vos mots-clés métier et identifie les catégories de marchés publics correspondantes.</p>

          <form onSubmit={handleAnalyze} className="ld-analyze-form">
            <div className="ld-analyze-row">
              <input type="text" value={url} onChange={e => setUrl(e.target.value)}
                placeholder="https://www.votre-entreprise.be" className="ld-analyze-input" disabled={loading} />
              <button type="submit" className="ld-btn-primary ld-btn-lg" disabled={loading || !url.trim()}>
                {loading ? <span className="ld-spinner" /> : "Analyser"}
              </button>
            </div>
            {error && <div className="ld-error">{error}</div>}
          </form>
        </div>
      </section>

      {/* ─── Results ─── */}
      {result && (
        <section className="ld-results" ref={resultRef}>
          <div className="ld-results-inner">
            {result.company_name && (
              <div className="ld-result-company">
                Analyse de <strong>{result.company_name}</strong>
              </div>
            )}

            <div className="ld-result-grid">
              <div className="ld-result-card">
                <h3>Mots-clés détectés</h3>
                <p className="ld-hint">Cliquez pour sélectionner/désélectionner. Les mots en vert sont pré-sélectionnés car pertinents pour les marchés publics.</p>
                <div className="ld-chips">
                  {allKeywords.map(kw => (
                    <button key={kw} className={`ld-chip ${selectedKeywords.has(kw) ? "on" : ""}`}
                      onClick={() => toggleKeyword(kw)}>
                      {selectedKeywords.has(kw) && <span>✓ </span>}{kw}
                    </button>
                  ))}
                </div>
                <div className="ld-add-kw">
                  <input type="text" value={customKw} onChange={e => setCustomKw(e.target.value)}
                    onKeyDown={handleCustomKwKey}
                    placeholder="Ajouter un mot-clé…" className="ld-add-kw-input" />
                  <button type="button" onClick={addCustomKeyword} className="ld-add-kw-btn"
                    disabled={!customKw.trim()}>+ Ajouter</button>
                </div>
              </div>

              {result.suggested_cpv.length > 0 && (
                <div className="ld-result-card">
                  <h3>Codes CPV suggérés</h3>
                  <p className="ld-hint">Catégories de marchés publics correspondant à votre activité.</p>
                  <div className="ld-cpv-list">
                    {result.suggested_cpv.map(cpv => (
                      <div key={cpv.code} className="ld-cpv-item">
                        <span className="ld-cpv-code">{cpv.code}</span>
                        <span>{cpv.label}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="ld-result-cta">
              <p><strong>{selectedKeywords.size}</strong> mot(s)-clé(s) sélectionné(s)
                {result.suggested_cpv.length > 0 && <> + <strong>{result.suggested_cpv.length}</strong> code(s) CPV</>}
              </p>
              <button className="ld-btn-primary ld-btn-lg" onClick={handleCreateWatchlist}
                disabled={selectedKeywords.size === 0}>
                {user ? "Créer ma veille avec ces mots-clés →" : "Créer mon compte et ma première veille →"}
              </button>
              <span className="ld-sub-text">Gratuit · Sans engagement · Alertes par email</span>
            </div>
          </div>
        </section>
      )}

      {/* ─── Features ─── */}
      <section className="ld-features" id="features">
        <div className="ld-features-inner">
          <div className="ld-section-label">Fonctionnalités</div>
          <h2>Tout ce qu'il vous faut</h2>
          <p className="ld-section-sub">ProcureWatch centralise la veille marchés publics pour que vous puissiez vous concentrer sur vos offres.</p>

          <div className="ld-feat-grid">
            <div className="ld-feat-card">
              <div className="ld-feat-icon">🔔</div>
              <h3>Alertes intelligentes</h3>
              <p>Recevez des notifications pour les marchés qui correspondent à vos critères, par email ou dans l'app.</p>
            </div>
            <div className="ld-feat-card">
              <div className="ld-feat-icon">🇧🇪🇪🇺</div>
              <h3>Multi-sources</h3>
              <p>BOSA (Belgique) + TED (Europe) centralisés. Plus besoin de vérifier plusieurs portails chaque jour.</p>
            </div>
            <div className="ld-feat-card">
              <div className="ld-feat-icon">⚡</div>
              <h3>Gain de temps</h3>
              <p>Économisez 2 à 3 heures par jour de veille manuelle. Focus sur la rédaction de vos offres.</p>
            </div>
            <div className="ld-feat-card">
              <div className="ld-feat-icon">📄</div>
              <h3>Documents inclus</h3>
              <p>Accédez directement aux cahiers des charges et documents d'appel d'offres depuis la plateforme.</p>
            </div>
            <div className="ld-feat-card">
              <div className="ld-feat-icon">🔍</div>
              <h3>Recherche avancée</h3>
              <p>Filtrez par mots-clés, codes CPV, zones NUTS, types de procédures, dates et montants.</p>
            </div>
            <div className="ld-feat-card">
              <div className="ld-feat-icon">⭐</div>
              <h3>Favoris &amp; suivi</h3>
              <p>Marquez les marchés intéressants et suivez leur évolution depuis votre tableau de bord.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ─── How it works ─── */}
      <section className="ld-how" id="how">
        <div className="ld-how-inner">
          <h2>Comment ça marche ?</h2>
          <div className="ld-steps">
            <div className="ld-step">
              <div className="ld-step-num">1</div>
              <h3>Créez votre veille</h3>
              <p>Définissez vos critères : mots-clés, secteur, région. Ou laissez notre outil analyser votre site web.</p>
            </div>
            <div className="ld-step-arrow">→</div>
            <div className="ld-step">
              <div className="ld-step-num">2</div>
              <h3>ProcureWatch surveille</h3>
              <p>Nos algorithmes scannent BOSA et TED en continu et identifient les marchés qui vous correspondent.</p>
            </div>
            <div className="ld-step-arrow">→</div>
            <div className="ld-step">
              <div className="ld-step-num">3</div>
              <h3>Recevez vos alertes</h3>
              <p>Par email ou dans l'app, avec les détails, documents et liens directs vers les portails officiels.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Pricing ─── */}
      <section className="ld-pricing" id="pricing">
        <div className="ld-pricing-inner">
          <div className="ld-section-label">Tarifs</div>
          <h2>Des tarifs simples et transparents</h2>
          <p className="ld-section-sub">Commencez gratuitement, évoluez quand vous êtes prêt.</p>

          <div className="ld-price-grid">
            <div className="ld-price-card">
              <div className="ld-price-name">Explorer</div>
              <div className="ld-price-amount">Gratuit</div>
              <ul className="ld-price-features">
                <li>Accès à la base &amp; recherche</li>
                <li>1 watchlist</li>
                <li>Résultats dans l'app (sans email)</li>
                <li>Historique 7 jours</li>
              </ul>
              <button className="ld-btn-outline ld-btn-full" onClick={() => navigate("/login")}>Démarrer gratuitement</button>
            </div>
            <div className="ld-price-card popular">
              <div className="ld-popular-badge">Le plus populaire</div>
              <div className="ld-price-name">Pro</div>
              <div className="ld-price-amount">29€<span>/mois</span></div>
              <ul className="ld-price-features">
                <li>Jusqu'à 10 watchlists</li>
                <li>Notifications email (instant + digest)</li>
                <li>AI summary : résumé + points clés</li>
                <li>Historique 90 jours</li>
              </ul>
              <button className="ld-btn-primary ld-btn-full" onClick={() => navigate("/login")}>Passer en Pro</button>
            </div>
            <div className="ld-price-card">
              <div className="ld-price-name">Business</div>
              <div className="ld-price-amount">Sur devis</div>
              <ul className="ld-price-features">
                <li>Watchlists illimitées</li>
                <li>Multi-utilisateurs + rôles</li>
                <li>Intégrations (Slack/CRM) + exports</li>
                <li>Onboarding &amp; support prioritaire</li>
              </ul>
              <button className="ld-btn-outline ld-btn-full" onClick={() => window.location.href = "mailto:hello@procurewatch.eu"}>Nous contacter</button>
            </div>
          </div>
        </div>
      </section>

      {/* ─── FAQ ─── */}
      <section className="ld-faq" id="faq">
        <div className="ld-faq-inner">
          <h2>Questions fréquentes</h2>
          <div className="ld-faq-list">
            {faqs.map((faq, i) => (
              <div key={i} className={`ld-faq-item ${openFaq === i ? "open" : ""}`}>
                <button className="ld-faq-q" onClick={() => setOpenFaq(openFaq === i ? null : i)}>
                  {faq.q}
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                    className="ld-faq-arrow"><polyline points="6 9 12 15 18 9"/></svg>
                </button>
                {openFaq === i && <div className="ld-faq-a">{faq.a}</div>}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Final CTA ─── */}
      <section className="ld-final-cta">
        <div className="ld-final-inner">
          <h2>Prêt à trouver vos prochains marchés ?</h2>
          <p>Rejoignez les entreprises qui utilisent ProcureWatch pour ne plus rater aucune opportunité.</p>
          <button className="ld-btn-primary ld-btn-lg" onClick={() => user ? navigate("/dashboard") : navigate("/login")}>
            {user ? "Accéder à mon tableau de bord →" : "Commencer gratuitement →"}
          </button>
        </div>
      </section>

      {/* ─── Footer ─── */}
      <footer className="ld-footer">
        <div className="ld-footer-inner">
          <div className="ld-footer-left">
            <span className="ld-logo-sm">ProcureWatch</span>
          </div>
          <div className="ld-footer-links">
            <button onClick={() => scrollTo("features")}>Fonctionnalités</button>
            <button onClick={() => scrollTo("pricing")}>Tarifs</button>
            <button onClick={() => navigate("/login")}>Connexion</button>
            <button onClick={() => navigate("/login")}>Créer un compte</button>
          </div>
        </div>
        <div className="ld-footer-bottom">
          <span>© 2026 ProcureWatch. Tous droits réservés.</span>
        </div>
      </footer>
    </div>
  );
}
