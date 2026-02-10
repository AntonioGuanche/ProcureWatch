import { useState } from "react";
import { useSearchParams } from "react-router-dom";

interface ResetPasswordProps {
  onBack: () => void;
}

function EyeIcon({ show }: { show: boolean }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      {show ? (
        <>
          <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/>
          <path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/>
          <line x1="1" y1="1" x2="23" y2="23"/>
        </>
      ) : (
        <>
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
          <circle cx="12" cy="12" r="3"/>
        </>
      )}
    </svg>
  );
}

export function ResetPassword({ onBack }: ResetPasswordProps) {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) { setError("Les mots de passe ne correspondent pas"); return; }
    setLoading(true);
    try {
      const res = await fetch("/api/auth/reset-password", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Erreur"); }
      setDone(true);
    } catch (err) { setError(err instanceof Error ? err.message : "Erreur"); }
    finally { setLoading(false); }
  };

  if (!token) {
    return (
      <div className="auth-page"><div className="auth-card">
        <div className="auth-header"><h1>ProcureWatch</h1></div>
        <div className="alert alert-error">Lien invalide. Veuillez refaire une demande.</div>
        <button onClick={onBack} className="btn-primary auth-submit" style={{ marginTop: "1rem" }}>Retour</button>
      </div></div>
    );
  }

  return (
    <div className="auth-page"><div className="auth-card">
      <div className="auth-header"><h1>ProcureWatch</h1><p>Nouveau mot de passe</p></div>
      {done ? (
        <div>
          <div className="alert alert-success">Mot de passe modifié avec succès !</div>
          <button onClick={onBack} className="btn-primary auth-submit" style={{ marginTop: "1rem" }}>Se connecter</button>
        </div>
      ) : (
        <>
          {error && <div className="alert alert-error">{error}</div>}
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label>Nouveau mot de passe</label>
              <div className="input-with-icon">
                <input type={showPw ? "text" : "password"} value={password}
                  onChange={(e) => setPassword(e.target.value)} placeholder="8 caractères minimum" required minLength={8} />
                <button type="button" className="pw-toggle" onClick={() => setShowPw(!showPw)} tabIndex={-1}>
                  <EyeIcon show={showPw} />
                </button>
              </div>
            </div>
            <div className="form-group">
              <label>Confirmer</label>
              <div className="input-with-icon">
                <input type={showPw ? "text" : "password"} value={confirm}
                  onChange={(e) => setConfirm(e.target.value)} placeholder="Confirmez le mot de passe" required minLength={8} />
              </div>
            </div>
            <button type="submit" className="btn-primary auth-submit" disabled={loading}>
              {loading ? "Modification…" : "Modifier le mot de passe"}
            </button>
          </form>
        </>
      )}
    </div></div>
  );
}
