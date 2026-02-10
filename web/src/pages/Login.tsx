import { useState } from "react";
import { useAuth } from "../auth";

interface LoginProps {
  onForgotPassword?: () => void;
}

export function Login({ onForgotPassword }: LoginProps) {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, name || undefined);
      }
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
          <p>Veille des marchés publics</p>
        </div>

        <div className="auth-tabs">
          <button
            className={mode === "login" ? "auth-tab active" : "auth-tab"}
            onClick={() => { setMode("login"); setError(null); }}
          >
            Connexion
          </button>
          <button
            className={mode === "register" ? "auth-tab active" : "auth-tab"}
            onClick={() => { setMode("register"); setError(null); }}
          >
            Inscription
          </button>
        </div>

        {error && <div className="alert alert-error">{error}</div>}

        <form onSubmit={handleSubmit}>
          {mode === "register" && (
            <div className="form-group">
              <label>Nom</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Votre nom"
              />
            </div>
          )}
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
          <div className="form-group">
            <label>Mot de passe</label>
            <div className="input-with-icon">
              <input
                type={showPw ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={mode === "register" ? "8 caractères minimum" : ""}
                required
                minLength={mode === "register" ? 8 : undefined}
              />
              <button
                type="button"
                className="pw-toggle"
                onClick={() => setShowPw(!showPw)}
                tabIndex={-1}
                title={showPw ? "Masquer" : "Afficher"}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  {showPw ? (
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
              </button>
            </div>
          </div>
          <button type="submit" className="btn-primary auth-submit" disabled={loading}>
            {loading
              ? "Chargement…"
              : mode === "login"
              ? "Se connecter"
              : "Créer mon compte"}
          </button>
        </form>

        {mode === "login" && onForgotPassword && (
          <div className="auth-forgot">
            <button onClick={onForgotPassword} className="btn-link">
              Mot de passe oublié ?
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
