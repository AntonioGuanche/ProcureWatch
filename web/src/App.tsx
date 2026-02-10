import { useState } from "react";
import { BrowserRouter, Routes, Route, NavLink, Navigate, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { Dashboard } from "./pages/Dashboard";
import { Search } from "./pages/Search";
import { WatchlistList } from "./pages/WatchlistList";
import { WatchlistNew } from "./pages/WatchlistNew";
import { WatchlistDetail } from "./pages/WatchlistDetail";
import { WatchlistEdit } from "./pages/WatchlistEdit";
import { Login } from "./pages/Login";
import { ForgotPassword } from "./pages/ForgotPassword";
import { ResetPassword } from "./pages/ResetPassword";

function AuthGate() {
  const { user, loading } = useAuth();
  const [showForgot, setShowForgot] = useState(false);
  if (loading) return <div className="loading">Chargement…</div>;
  if (!user) {
    if (showForgot) return <ForgotPassword onBack={() => setShowForgot(false)} />;
    return <Login onForgotPassword={() => setShowForgot(true)} />;
  }
  return null;
}

function ResetPasswordPage() {
  const navigate = useNavigate();
  return <ResetPassword onBack={() => navigate("/")} />;
}

function AppRoutes() {
  const { user, loading, logout } = useAuth();
  if (loading) return <div className="loading">Chargement…</div>;

  return (
    <Routes>
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      {!user ? (
        <Route path="*" element={<AuthGate />} />
      ) : (
        <Route
          path="*"
          element={
            <div className="app-layout">
              <header className="app-header">
                <div className="header-left">
                  <NavLink to="/dashboard" className="brand-name">ProcureWatch</NavLink>
                </div>
                <nav className="header-nav">
                  <NavLink to="/dashboard" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
                    Accueil
                  </NavLink>
                  <NavLink to="/search" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                    Rechercher
                  </NavLink>
                  <NavLink to="/watchlists" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>
                    Veilles
                  </NavLink>
                </nav>
                <div className="header-right">
                  <span className="user-name">{user.name}</span>
                  <button onClick={logout} className="btn-sm btn-outline" title="Déconnexion">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
                    </svg>
                  </button>
                </div>
              </header>

              <main className="app-main">
                <Routes>
                  <Route path="/" element={<Navigate to="/dashboard" replace />} />
                  <Route path="/dashboard" element={<Dashboard />} />
                  <Route path="/search" element={<Search />} />
                  <Route path="/watchlists" element={<WatchlistList />} />
                  <Route path="/watchlists/new" element={<WatchlistNew />} />
                  <Route path="/watchlists/:id" element={<WatchlistDetail />} />
                  <Route path="/watchlists/:id/edit" element={<WatchlistEdit />} />
                  <Route path="*" element={<Navigate to="/dashboard" replace />} />
                </Routes>
              </main>

              <footer className="app-footer">
                <span>ProcureWatch — Veille des marchés publics</span>
              </footer>
            </div>
          }
        />
      )}
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
