import { BrowserRouter, Routes, Route, NavLink, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { Dashboard } from "./pages/Dashboard";
import { Search } from "./pages/Search";
import { WatchlistList } from "./pages/WatchlistList";
import { WatchlistNew } from "./pages/WatchlistNew";
import { WatchlistDetail } from "./pages/WatchlistDetail";
import { WatchlistEdit } from "./pages/WatchlistEdit";
import { Login } from "./pages/Login";

function AppRoutes() {
  const { user, loading, logout } = useAuth();

  if (loading) {
    return <div className="loading">Chargement…</div>;
  }

  if (!user) {
    return <Login />;
  }

  return (
    <div className="app-layout">
      <header className="app-header">
        <div className="header-brand">
          <span className="logo">📡</span>
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
        <span>ProcureWatch — Veille marchés publics BE + EU</span>
      </footer>
    </div>
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
