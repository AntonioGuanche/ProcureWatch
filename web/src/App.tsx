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

  if (loading) {
    return <div className="loading">Chargement…</div>;
  }

  if (!user) {
    if (showForgot) {
      return <ForgotPassword onBack={() => setShowForgot(false)} />;
    }
    return <Login onForgotPassword={() => setShowForgot(true)} />;
  }

  return null; // Authenticated — handled by parent
}

function ResetPasswordPage() {
  const navigate = useNavigate();
  return <ResetPassword onBack={() => navigate("/")} />;
}

function AppRoutes() {
  const { user, loading, logout } = useAuth();

  if (loading) {
    return <div className="loading">Chargement…</div>;
  }

  return (
    <Routes>
      {/* Password reset is always accessible (even when logged out) */}
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      {!user ? (
        <Route path="*" element={<AuthGate />} />
      ) : (
        <Route
          path="*"
          element={
            <div className="app-layout">
              <header className="app-header">
                <div className="header-brand">
                  <span className="brand-name">ProcureWatch</span>
                </div>
                <nav className="header-nav">
                  <NavLink to="/dashboard" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                    Dashboard
                  </NavLink>
                  <NavLink to="/search" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                    Rechercher
                  </NavLink>
                  <NavLink to="/watchlists" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                    Watchlists
                  </NavLink>
                </nav>
                <div className="header-user">
                  <span className="user-name">{user.name}</span>
                  <button onClick={logout} className="btn-logout" title="Déconnexion">↪</button>
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
