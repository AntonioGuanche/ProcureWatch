import { useState } from "react";

interface ForgotPasswordProps {
  onBack: () => void;
}

export function ForgotPassword({ onBack }: ForgotPasswordProps) {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await fetch("/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Erreur");
      }
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-header">
          <h1>ProcureWatch</h1>
          <p>Réinitialisation du mot de passe</p>
        </div>

        {sent ? (
          <div className="auth-success">
            <div className="alert alert-success">
              Si un compte existe avec cet email, un lien de réinitialisation a été envoyé.
              Vérifiez votre boîte de réception.
            </div>
            <button onClick={onBack} className="btn-primary auth-submit" style={{ marginTop: "1rem" }}>
              Retour à la connexion
            </button>
          </div>
        ) : (
          <>
            {error && <div className="alert alert-error">{error}</div>}
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label>Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="votre@email.com"
                  required
                />
              </div>
              <button type="submit" className="btn-primary auth-submit" disabled={loading}>
                {loading ? "Envoi…" : "Envoyer le lien"}
              </button>
            </form>
            <div className="auth-forgot">
              <button onClick={onBack} className="btn-link">
                ← Retour à la connexion
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
