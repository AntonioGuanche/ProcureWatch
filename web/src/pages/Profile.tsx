import { useState, useEffect } from "react";
import { useAuth } from "../auth";
import { updateProfile, changePassword, deleteAccount, getSubscription, createCheckout, createPortalSession } from "../api";
import type { SubscriptionInfo } from "../api";
import { useNavigate } from "react-router-dom";

function EyeIcon({ show }: { show: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      {show ? (
        <><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></>
      ) : (
        <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></>
      )}
    </svg>
  );
}

export function Profile() {
  const { user, setUser, logout } = useAuth();
  const navigate = useNavigate();

  // Profile form
  const [name, setName] = useState(user?.name || "");
  const [email, setEmail] = useState(user?.email || "");
  const [profileMsg, setProfileMsg] = useState<string | null>(null);
  const [profileErr, setProfileErr] = useState<string | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);

  // Password form
  const [curPw, setCurPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [pwMsg, setPwMsg] = useState<string | null>(null);
  const [pwErr, setPwErr] = useState<string | null>(null);
  const [pwLoading, setPwLoading] = useState(false);

  // Delete
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [delLoading, setDelLoading] = useState(false);

  // Billing
  const [sub, setSub] = useState<SubscriptionInfo | null>(null);
  const [billingLoading, setBillingLoading] = useState(true);
  const [billingAction, setBillingAction] = useState(false);

  useEffect(() => {
    getSubscription()
      .then(setSub)
      .catch(() => {})
      .finally(() => setBillingLoading(false));
  }, []);

  const handleUpgrade = async (plan: string, interval: string) => {
    setBillingAction(true);
    try {
      const { checkout_url } = await createCheckout(plan, interval);
      window.location.href = checkout_url;
    } catch (err) {
      alert(err instanceof Error ? err.message : "Erreur");
      setBillingAction(false);
    }
  };

  const handleManage = async () => {
    setBillingAction(true);
    try {
      const { portal_url } = await createPortalSession();
      window.location.href = portal_url;
    } catch (err) {
      alert(err instanceof Error ? err.message : "Erreur");
      setBillingAction(false);
    }
  };

  const handleProfileSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileErr(null);
    setProfileMsg(null);
    setProfileLoading(true);
    try {
      const updated = await updateProfile({ name: name.trim(), email: email.trim() });
      setUser({ id: updated.id, email: updated.email, name: updated.name, is_admin: updated.is_admin });
      setProfileMsg("Profil mis à jour");
    } catch (err) {
      setProfileErr(err instanceof Error ? err.message : "Erreur");
    } finally {
      setProfileLoading(false);
    }
  };

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwErr(null);
    setPwMsg(null);
    if (newPw !== confirmPw) { setPwErr("Les mots de passe ne correspondent pas"); return; }
    setPwLoading(true);
    try {
      await changePassword({ current_password: curPw, new_password: newPw });
      setPwMsg("Mot de passe modifié");
      setCurPw(""); setNewPw(""); setConfirmPw("");
    } catch (err) {
      setPwErr(err instanceof Error ? err.message : "Erreur");
    } finally {
      setPwLoading(false);
    }
  };

  const handleDelete = async () => {
    setDelLoading(true);
    try {
      await deleteAccount();
      logout();
      navigate("/");
    } catch {
      setDelLoading(false);
    }
  };

  return (
    <div className="page">
      <h1>Mon Profil</h1>
      <p className="page-subtitle">Gérez vos informations et préférences.</p>

      <div className="profile-grid">
        {/* Account Info */}
        <div className="profile-card">
          <h2>Informations du compte</h2>
          <p className="card-subtitle">Vos données personnelles</p>

          {profileMsg && <div className="alert alert-success">{profileMsg}</div>}
          {profileErr && <div className="alert alert-error">{profileErr}</div>}

          <form onSubmit={handleProfileSave}>
            <div className="form-group">
              <label>Email</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="form-group">
              <label>Nom complet</label>
              <input type="text" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <button type="submit" className="btn-primary" disabled={profileLoading}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
              {profileLoading ? "Enregistrement…" : "Sauvegarder"}
            </button>
          </form>
        </div>

        {/* Password Change */}
        <div className="profile-card">
          <h2>Changer le mot de passe</h2>
          <p className="card-subtitle">Sécurisez votre compte</p>

          {pwMsg && <div className="alert alert-success">{pwMsg}</div>}
          {pwErr && <div className="alert alert-error">{pwErr}</div>}

          <form onSubmit={handlePasswordChange}>
            <div className="form-group">
              <label>Mot de passe actuel</label>
              <div className="input-with-icon">
                <input type={showPw ? "text" : "password"} value={curPw} onChange={(e) => setCurPw(e.target.value)} required />
                <button type="button" className="pw-toggle" onClick={() => setShowPw(!showPw)} tabIndex={-1}>
                  <EyeIcon show={showPw} />
                </button>
              </div>
            </div>
            <div className="form-group">
              <label>Nouveau mot de passe</label>
              <input type={showPw ? "text" : "password"} value={newPw} onChange={(e) => setNewPw(e.target.value)} required minLength={8} placeholder="8 caractères minimum" />
            </div>
            <div className="form-group">
              <label>Confirmer</label>
              <input type={showPw ? "text" : "password"} value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} required minLength={8} />
            </div>
            <button type="submit" className="btn-primary" disabled={pwLoading}>
              {pwLoading ? "Modification…" : "Modifier le mot de passe"}
            </button>
          </form>
        </div>

        {/* Subscription Plan */}
        <div className="profile-card">
          <h2>Abonnement</h2>
          <p className="card-subtitle">Votre plan actuel</p>

          {billingLoading ? (
            <p style={{ color: "#888" }}>Chargement…</p>
          ) : sub ? (
            <>
              <div className="plan-card">
                <div className="plan-info">
                  <strong>{sub.display_name}</strong>
                  <span className={`tag ${sub.effective_plan !== "free" && sub.status === "active" ? "tag-success" : sub.status === "past_due" ? "tag-warning" : sub.status === "canceled" ? "tag-muted" : "tag-success"}`}>
                    {sub.status === "active" ? "ACTIF" : sub.status === "past_due" ? "IMPAYÉ" : sub.status === "canceled" ? "ANNULÉ" : sub.status === "none" ? "ACTIF" : sub.status.toUpperCase()}
                  </span>
                </div>
                <p className="plan-desc">
                  {sub.limits.max_watchlists === -1
                    ? "Veilles illimitées"
                    : `${sub.limits.max_watchlists} veille${sub.limits.max_watchlists > 1 ? "s" : ""} incluse${sub.limits.max_watchlists > 1 ? "s" : ""}`}
                  {sub.limits.email_digest && " · Digest email"}
                  {sub.limits.csv_export && " · Export CSV"}
                  {sub.limits.api_access && " · Accès API"}
                </p>
                {sub.current_period_end && (
                  <p className="plan-desc" style={{ fontSize: ".8rem", marginTop: ".25rem" }}>
                    {sub.cancel_at_period_end
                      ? `Accès jusqu'au ${new Date(sub.current_period_end).toLocaleDateString("fr-FR")}`
                      : `Prochain renouvellement : ${new Date(sub.current_period_end).toLocaleDateString("fr-FR")}`}
                  </p>
                )}
              </div>

              <div style={{ marginTop: ".75rem", display: "flex", gap: ".5rem", flexWrap: "wrap" }}>
                {sub.effective_plan === "free" && (
                  <>
                    <button className="btn-sm btn-primary" onClick={() => handleUpgrade("pro", "month")} disabled={billingAction}>
                      {billingAction ? "Redirection…" : "Passer à Pro — 49€/mois"}
                    </button>
                    <button className="btn-sm btn-outline" onClick={() => handleUpgrade("business", "month")} disabled={billingAction}>
                      Business — 149€/mois
                    </button>
                  </>
                )}
                {sub.effective_plan === "pro" && (
                  <>
                    <button className="btn-sm btn-outline" onClick={handleManage} disabled={billingAction}>
                      {billingAction ? "Redirection…" : "Gérer mon abonnement"}
                    </button>
                    <button className="btn-sm btn-primary" onClick={() => handleUpgrade("business", "month")} disabled={billingAction}>
                      Passer à Business
                    </button>
                  </>
                )}
                {sub.effective_plan === "business" && (
                  <button className="btn-sm btn-outline" onClick={handleManage} disabled={billingAction}>
                    {billingAction ? "Redirection…" : "Gérer mon abonnement"}
                  </button>
                )}
              </div>
            </>
          ) : (
            <p style={{ color: "#888" }}>Impossible de charger les informations d'abonnement.</p>
          )}
        </div>

        {/* Danger Zone */}
        <div className="profile-card danger-zone">
          <h2>Zone de danger</h2>
          <p className="card-subtitle">Actions irréversibles</p>

          {!deleteConfirm ? (
            <button className="btn-sm btn-outline danger" onClick={() => setDeleteConfirm(true)}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
              Supprimer mon compte
            </button>
          ) : (
            <div className="delete-confirm">
              <p>Êtes-vous sûr ? Cette action est <strong>irréversible</strong>. Toutes vos données seront supprimées.</p>
              <div className="delete-actions">
                <button className="btn-sm btn-outline danger" onClick={handleDelete} disabled={delLoading}>
                  {delLoading ? "Suppression…" : "Confirmer la suppression"}
                </button>
                <button className="btn-sm btn-outline" onClick={() => setDeleteConfirm(false)}>Annuler</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
