import { useState } from "react";
import { useSearchParams } from "react-router-dom";

interface ResetPasswordProps {
  onBack: () => void;
}

export function ResetPassword({ onBack }: ResetPasswordProps) {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password !== confirm) {
      setError("Les mots de passe ne correspondent pas");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Erreur");
      }
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <div className="auth-header">
            <h1>ProcureWatch</h1>
          </div>
          <div className="alert alert-error">Lien invalide. Veuillez refaire une demande.</div>
          <button onClick={onBack} className="btn-primary auth-submit" style={{ marginTop: "1rem" }}>
            Retour à la connexion
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-header">
          <h1>ProcureWatch</h1>
          <p>Nouveau mot de passe</p>
        </div>

        {done ? (
          <div className="auth-success">
            <div className="alert alert-success">
              Mot de passe modifié avec succès !
            </div>
            <button onClick={onBack} className="btn-primary auth-submit" style={{ marginTop: "1rem" }}>
              Se connecter
            </button>
          </div>
        ) : (
          <>
            {error && <div className="alert alert-error">{error}</div>}
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label>Nouveau mot de passe</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="8 caractères minimum"
                  required
                  minLength={8}
                />
              </div>
              <div className="form-group">
                <label>Confirmer</label>
                <input
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  placeholder="Confirmez le mot de passe"
                  required
                  minLength={8}
                />
              </div>
              <button type="submit" className="btn-primary auth-submit" disabled={loading}>
                {loading ? "Modification…" : "Modifier le mot de passe"}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
