import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../auth";
import { createCheckout } from "../api";

/**
 * Public /pricing page — accessible with or without login.
 * - Monthly/Annual toggle with savings displayed
 * - Stripe Checkout integration for logged-in users
 * - Redirect to /login for anonymous users (with return intent)
 * - Full feature comparison table
 * - FAQ section
 * - Reuses Landing page design system (ld-* classes)
 */

const PLANS = [
  {
    key: "free",
    name: "Découverte",
    priceMonthly: 0,
    priceAnnualMonthly: 0,
    tagline: "Pour explorer les marchés publics",
    features: [
      "1 veille active",
      "10 résultats par veille",
      "Sources TED + BOSA",
      "Recherche full-text trilingue",
      "Historique 30 jours",
    ],
    cta: "Démarrer gratuitement",
    popular: false,
  },
  {
    key: "pro",
    name: "Pro",
    priceMonthly: 49,
    priceAnnualMonthly: 39,
    tagline: "Pour les indépendants et PME actives",
    features: [
      "5 veilles actives",
      "Résultats illimités",
      "Digest email quotidien",
      "20 résumés IA / mois",
      "Export CSV",
      "Historique 1 an",
      "Support prioritaire",
    ],
    cta: "Passer en Pro",
    popular: true,
  },
  {
    key: "business",
    name: "Business",
    priceMonthly: 149,
    priceAnnualMonthly: 119,
    tagline: "Pour les équipes et soumissionnaires réguliers",
    features: [
      "Veilles illimitées",
      "Alertes temps réel",
      "Résumés IA illimités",
      "Accès API complet",
      "Jusqu'à 5 utilisateurs",
      "Historique 3 ans",
      "Support dédié",
    ],
    cta: "Passer en Business",
    popular: false,
  },
];

const COMPARISON_ROWS: Array<{
  label: string;
  free: string;
  pro: string;
  business: string;
  category?: boolean;
}> = [
  { label: "Veilles & alertes", free: "", pro: "", business: "", category: true },
  { label: "Nombre de veilles", free: "1", pro: "5", business: "Illimité" },
  { label: "Résultats par veille", free: "10", pro: "Illimité", business: "Illimité" },
  { label: "Digest email quotidien", free: "—", pro: "✓", business: "✓" },
  { label: "Alertes temps réel", free: "—", pro: "—", business: "✓" },
  { label: "Données & recherche", free: "", pro: "", business: "", category: true },
  { label: "Sources TED + BOSA", free: "✓", pro: "✓", business: "✓" },
  { label: "Recherche trilingue FR/NL/EN", free: "✓", pro: "✓", business: "✓" },
  { label: "Historique", free: "30 jours", pro: "1 an", business: "3 ans" },
  { label: "Export CSV", free: "—", pro: "✓", business: "✓" },
  { label: "Intelligence & IA", free: "", pro: "", business: "", category: true },
  { label: "Résumés IA", free: "—", pro: "20 / mois", business: "Illimité" },
  { label: "Analyse de documents PDF", free: "—", pro: "✓", business: "✓" },
  { label: "Onboarding par URL", free: "✓", pro: "✓", business: "✓" },
  { label: "Équipe & intégration", free: "", pro: "", business: "", category: true },
  { label: "Utilisateurs", free: "1", pro: "1", business: "5" },
  { label: "Accès API", free: "—", pro: "—", business: "✓" },
  { label: "Support prioritaire", free: "—", pro: "✓", business: "✓" },
];

const FAQS = [
  {
    q: "Puis-je vraiment commencer gratuitement ?",
    a: "Oui. Le plan Découverte est gratuit, sans carte bancaire. Vous pouvez créer une veille, rechercher des marchés et consulter les résultats immédiatement.",
  },
  {
    q: "Puis-je changer de plan ou annuler à tout moment ?",
    a: "Absolument. Aucun engagement. Vous pouvez passer d'un plan à l'autre ou annuler à tout moment depuis votre profil. En cas d'annulation, vous gardez l'accès jusqu'à la fin de la période payée.",
  },
  {
    q: "Le plan annuel est-il vraiment moins cher ?",
    a: "Oui, le plan annuel offre une réduction de 20% par rapport au paiement mensuel. Vous payez l'équivalent de 10 mois pour 12 mois d'accès.",
  },
  {
    q: "Quelles sont les méthodes de paiement acceptées ?",
    a: "Nous acceptons les cartes bancaires (Visa, Mastercard, Bancontact) via Stripe. La facturation est automatique et vous recevez une facture par email chaque mois ou chaque année.",
  },
  {
    q: "Mes données sont-elles sécurisées ?",
    a: "Oui. Vos données sont hébergées en Europe, les paiements sont gérés par Stripe (certifié PCI DSS) et toutes les communications sont chiffrées en HTTPS.",
  },
  {
    q: "Qu'est-ce que le digest email ?",
    a: "Chaque matin, vous recevez un email récapitulant les nouveaux marchés publics qui correspondent à vos veilles : titre, autorité adjudicatrice, deadline, montant estimé et lien vers le dossier. Tout est scannable en 15 secondes.",
  },
];

export default function Pricing() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [annual, setAnnual] = useState(false);
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  const handleChoosePlan = async (planKey: string) => {
    setError("");
    if (planKey === "free") {
      navigate(user ? "/dashboard" : "/login");
      return;
    }
    if (!user) {
      // Store intent and redirect to login
      sessionStorage.setItem("pw_pricing_intent", JSON.stringify({ plan: planKey, interval: annual ? "year" : "month" }));
      navigate("/login");
      return;
    }
    // Logged in → create Stripe checkout
    setLoadingPlan(planKey);
    try {
      const { checkout_url } = await createCheckout(planKey, annual ? "year" : "month");
      window.location.href = checkout_url;
    } catch (err: any) {
      setError(err.message || "Erreur lors de la création du paiement.");
      setLoadingPlan(null);
    }
  };

  const savingsPercent = 20; // annual discount

  return (
    <div className="ld-root">
      {/* ── Nav bar ── */}
      <header className="pricing-nav">
        <div className="pricing-nav-inner">
          <Link to="/" className="pricing-brand">
            <span className="pricing-brand-icon">🔍</span> ProcureWatch
          </Link>
          <div className="pricing-nav-right">
            {user ? (
              <Link to="/dashboard" className="ld-btn-outline" style={{ padding: "0.45rem 1.2rem", fontSize: "0.85rem" }}>
                Mon tableau de bord
              </Link>
            ) : (
              <>
                <Link to="/login" className="pricing-nav-link">Connexion</Link>
                <Link to="/login" className="ld-btn-primary" style={{ padding: "0.45rem 1.2rem", fontSize: "0.85rem" }}>
                  Créer un compte
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="pricing-hero">
        <div className="ld-section-label">Tarifs</div>
        <h1>Des tarifs simples et transparents</h1>
        <p className="ld-section-sub">
          Commencez gratuitement. Évoluez quand vous êtes prêt.
          <br />
          <strong style={{ color: "var(--ld-teal)" }}>Aucun engagement — annulez à tout moment.</strong>
        </p>

        {/* Toggle */}
        <div className="pricing-toggle">
          <span className={!annual ? "active" : ""}>Mensuel</span>
          <button
            className={`pricing-toggle-switch ${annual ? "on" : ""}`}
            onClick={() => setAnnual(!annual)}
            aria-label="Basculer entre mensuel et annuel"
          >
            <span className="pricing-toggle-knob" />
          </button>
          <span className={annual ? "active" : ""}>
            Annuel
            <span className="pricing-toggle-badge">-{savingsPercent}%</span>
          </span>
        </div>
      </section>

      {/* ── Plan cards ── */}
      <section className="ld-pricing" style={{ paddingTop: "1rem" }}>
        <div className="ld-pricing-inner">
          {error && (
            <div style={{
              background: "#fef2f2", color: "#dc2626", padding: "0.75rem 1rem",
              borderRadius: "8px", marginBottom: "1rem", fontSize: "0.9rem", textAlign: "center",
            }}>
              {error}
            </div>
          )}
          <div className="ld-price-grid">
            {PLANS.map((plan) => {
              const price = annual ? plan.priceAnnualMonthly : plan.priceMonthly;
              const annualTotal = plan.priceAnnualMonthly * 12;
              const isCurrentPlan = user && user.plan === plan.key;
              const isLoading = loadingPlan === plan.key;

              return (
                <div key={plan.key} className={`ld-price-card ${plan.popular ? "popular" : ""}`}>
                  {plan.popular && <div className="ld-popular-badge">Le plus populaire</div>}
                  <div className="ld-price-name">{plan.name}</div>
                  <div className="pricing-tagline">{plan.tagline}</div>

                  {plan.priceMonthly === 0 ? (
                    <div className="ld-price-amount">Gratuit</div>
                  ) : (
                    <>
                      <div className="ld-price-amount">
                        {price}€<span>/mois</span>
                      </div>
                      {annual && (
                        <div className="ld-price-annual">
                          Facturé {annualTotal}€/an · Économisez {(plan.priceMonthly * 12) - annualTotal}€
                        </div>
                      )}
                      {!annual && (
                        <div className="ld-price-annual">
                          ou {plan.priceAnnualMonthly}€/mois en annuel
                        </div>
                      )}
                    </>
                  )}

                  <ul className="ld-price-features">
                    {plan.features.map((f, i) => (
                      <li key={i}>{f}</li>
                    ))}
                  </ul>

                  {isCurrentPlan ? (
                    <button className="ld-btn-outline ld-btn-full" disabled style={{ opacity: 0.6 }}>
                      Plan actuel
                    </button>
                  ) : (
                    <button
                      className={`${plan.popular ? "ld-btn-primary" : "ld-btn-outline"} ld-btn-full`}
                      onClick={() => handleChoosePlan(plan.key)}
                      disabled={isLoading}
                    >
                      {isLoading ? "Redirection…" : plan.cta}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Feature comparison table ── */}
      <section className="pricing-comparison">
        <div className="pricing-comparison-inner">
          <h2>Comparaison détaillée des plans</h2>
          <div className="pricing-table-wrap">
            <table className="pricing-table">
              <thead>
                <tr>
                  <th></th>
                  <th>Découverte</th>
                  <th className="pricing-table-highlight">Pro</th>
                  <th>Business</th>
                </tr>
              </thead>
              <tbody>
                {COMPARISON_ROWS.map((row, i) =>
                  row.category ? (
                    <tr key={i} className="pricing-table-category">
                      <td colSpan={4}>{row.label}</td>
                    </tr>
                  ) : (
                    <tr key={i}>
                      <td className="pricing-table-label">{row.label}</td>
                      <td>{row.free === "✓" ? <span className="pricing-check">✓</span> : row.free === "—" ? <span className="pricing-dash">—</span> : row.free}</td>
                      <td className="pricing-table-highlight">{row.pro === "✓" ? <span className="pricing-check">✓</span> : row.pro === "—" ? <span className="pricing-dash">—</span> : row.pro}</td>
                      <td>{row.business === "✓" ? <span className="pricing-check">✓</span> : row.business === "—" ? <span className="pricing-dash">—</span> : row.business}</td>
                    </tr>
                  )
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ── FAQ ── */}
      <section className="ld-faq" id="faq">
        <div className="ld-faq-inner">
          <h2>Questions fréquentes</h2>
          <div className="ld-faq-list">
            {FAQS.map((faq, i) => (
              <div key={i} className={`ld-faq-item ${openFaq === i ? "open" : ""}`}>
                <button className="ld-faq-q" onClick={() => setOpenFaq(openFaq === i ? null : i)}>
                  {faq.q}
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                    className="ld-faq-arrow"><polyline points="6 9 12 15 18 9" /></svg>
                </button>
                {openFaq === i && <div className="ld-faq-a">{faq.a}</div>}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Final CTA ── */}
      <section className="pricing-final-cta">
        <h2>Prêt à ne plus rater d'opportunité ?</h2>
        <p>Rejoignez les PME qui utilisent ProcureWatch pour surveiller les marchés publics en Belgique et en Europe.</p>
        <div style={{ display: "flex", gap: "1rem", justifyContent: "center", flexWrap: "wrap" }}>
          <button className="ld-btn-primary ld-btn-lg" onClick={() => navigate(user ? "/dashboard" : "/login")}>
            Démarrer gratuitement
          </button>
          <Link to="/" className="ld-btn-outline ld-btn-lg">
            Découvrir ProcureWatch
          </Link>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="pricing-footer">
        <span>ProcureWatch — Veille des marchés publics · Belgique & Europe</span>
        <div style={{ marginTop: "0.5rem" }}>
          <Link to="/" style={{ color: "var(--ld-gray-400)", fontSize: "0.82rem" }}>Accueil</Link>
          <span style={{ margin: "0 0.5rem", color: "var(--ld-gray-400)" }}>·</span>
          <Link to="/login" style={{ color: "var(--ld-gray-400)", fontSize: "0.82rem" }}>Connexion</Link>
        </div>
      </footer>
    </div>
  );
}
