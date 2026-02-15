import { createContext, useContext, useState, useEffect, useCallback } from "react";
import type { ReactNode } from "react";

interface User {
  id: string;
  email: string;
  name: string;
  is_admin?: boolean;
  plan?: string;
}

interface AuthState {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<void>;
  logout: () => void;
  setUser: (user: User) => void;
}

const AuthContext = createContext<AuthState | null>(null);

const TOKEN_KEY = "pw_token";
const USER_KEY = "pw_user";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Restore from sessionStorage on mount
  useEffect(() => {
    const savedToken = sessionStorage.getItem(TOKEN_KEY);
    const savedUser = sessionStorage.getItem(USER_KEY);
    if (savedToken && savedUser) {
      try {
        setToken(savedToken);
        setUser(JSON.parse(savedUser));
      } catch {
        sessionStorage.removeItem(TOKEN_KEY);
        sessionStorage.removeItem(USER_KEY);
      }
    }
    setLoading(false);
  }, []);

  const saveAuth = (t: string, u: User) => {
    setToken(t);
    setUser(u);
    sessionStorage.setItem(TOKEN_KEY, t);
    sessionStorage.setItem(USER_KEY, JSON.stringify(u));
  };

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Erreur de connexion");
    }
    const data = await res.json();
    saveAuth(data.access_token, data.user);
  }, []);

  const register = useCallback(async (email: string, password: string, name?: string) => {
    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, name }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Erreur d'inscription");
    }
    const data = await res.json();
    saveAuth(data.access_token, data.user);
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
  }, []);

  const updateUser = useCallback((u: User) => {
    setUser(u);
    sessionStorage.setItem("pw_user", JSON.stringify(u));
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout, setUser: updateUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
