"use client";

/**
 * Authentication context.
 *
 * Holds the current user, exposes login/logout, and gates pages behind
 * `useRequireAuth`. The JWT itself lives in localStorage (see api.ts).
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken, setToken, type CurrentUser } from "./api";

interface AuthState {
  user: CurrentUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      setUser(await api.me());
    } catch {
      clearToken();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.login(username, password);
    setToken(res.access_token);
    setUser(await api.me());
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}

/**
 * Redirect to /login if the visitor is not authenticated.
 * Returns the loading flag so pages can show a spinner while resolving.
 */
export function useRequireAuth(adminOnly = false): { loading: boolean } {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login/");
    } else if (adminOnly && !user.is_admin) {
      router.replace("/");
    }
  }, [user, loading, adminOnly, router]);

  return { loading: loading || !user || (adminOnly && !user.is_admin) };
}
