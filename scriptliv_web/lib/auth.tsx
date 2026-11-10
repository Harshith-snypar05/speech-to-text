"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError } from "./api";
import type { AuthResult, RegisterResult, Settings, User } from "./types";

/**
 * Customer auth for the ScriptLiv API. The bearer token is kept in localStorage so a refresh or a new tab stays signed in
 * (there are no device or login limits). It is never put in a URL or logged. The server decides what the token may do.
 * Settings (theme, auto-lock, language, limits) are loaded once here and kept in sync with the backend.
 */
interface AuthCtx {
  token: string | null;
  user: User | null;
  settings: Settings | null;
  ready: boolean;
  signIn: (email: string, password: string) => Promise<AuthResult>;
  /** creates the account only; it does NOT sign in (the email must be verified first) */
  signUp: (name: string, email: string, password: string) => Promise<RegisterResult>;
  signOut: () => void;
  /** replace the stored token (used after a password change, which revokes every other session) */
  setToken: (t: string) => Promise<void>;
  refresh: () => Promise<void>;
  saveSettings: (patch: Partial<Settings>) => Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);
const KEY = "scriptliv.session";

const read = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
const write = (v: string | null) => { try { if (v) localStorage.setItem(KEY, v); else localStorage.removeItem(KEY); } catch { /* private mode */ } };

export function applyTheme(theme: Settings["theme"]) {
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  try { localStorage.setItem("sl-theme", theme); } catch { /* ignore */ }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTok] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [ready, setReady] = useState(false);

  const signOut = useCallback(() => { write(null); setTok(null); setUser(null); setSettings(null); }, []);

  const load = useCallback(async (t: string) => {
    try {
      const [u, s] = await Promise.all([api.me(t), api.settings(t)]);
      setUser(u); setSettings(s.settings); setTok(t);
      applyTheme(s.settings.theme);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) signOut();
      else { setTok(t); } // API unreachable: keep the token, pages show their own error
    }
  }, [signOut]);

  useEffect(() => {
    const t = read();
    void (t ? load(t) : Promise.resolve()).finally(() => setReady(true));
  }, [load]);

  const accept = useCallback(async (r: AuthResult) => { write(r.token); await load(r.token); return r; }, [load]);
  const signIn = useCallback(async (email: string, password: string) => accept(await api.login(email, password)), [accept]);
  const signUp = useCallback(async (name: string, email: string, password: string) => api.register(name, email, password), []);
  const setToken = useCallback(async (t: string) => { write(t); await load(t); }, [load]);
  const refresh = useCallback(async () => { if (token) await load(token); }, [token, load]);

  const saveSettings = useCallback(async (patch: Partial<Settings>) => {
    if (!token) return;
    const r = await api.saveSettings(token, patch);
    setSettings(r.settings);
    if (patch.theme) applyTheme(r.settings.theme);
  }, [token]);

  const value = useMemo(
    () => ({ token, user, settings, ready, signIn, signUp, signOut, setToken, refresh, saveSettings }),
    [token, user, settings, ready, signIn, signUp, signOut, setToken, refresh, saveSettings],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
