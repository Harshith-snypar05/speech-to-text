"use client";
import { X } from "lucide-react";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { LoginForm, RegisterForm } from "@/components/auth-forms";
import { useAuth } from "@/lib/auth";

export type AuthMode = "login" | "register";
type Ctx = { open: (m: AuthMode) => void; close: () => void };
const AuthModalCtx = createContext<Ctx>({ open: () => {}, close: () => {} });
export const useAuthModal = () => useContext(AuthModalCtx);

/** Sign-in and sign-up live in a popup over whatever page the visitor is on. /login and /register just open it. */
export function AuthModalProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<AuthMode | null>(null);
  const { token } = useAuth();
  const router = useRouter();
  const open = useCallback((m: AuthMode) => { if (token) router.push("/app"); else setMode(m); }, [token, router]);
  const close = useCallback(() => setMode(null), []);
  const value = useMemo(() => ({ open, close }), [open, close]);
  return (
    <AuthModalCtx.Provider value={value}>
      {children}
      {mode && <Dialog mode={mode} setMode={setMode} onClose={close} />}
    </AuthModalCtx.Provider>
  );
}

const FOCUSABLE = "a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]:not([tabindex='-1'])";

function Dialog({ mode, setMode, onClose }: { mode: AuthMode; setMode: (m: AuthMode) => void; onClose: () => void }) {
  const router = useRouter();
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const prevFocus = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key !== "Tab" || !panel.current) return;
      const f = Array.from(panel.current.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = prevOverflow; prevFocus?.focus?.(); };
  }, [onClose]);

  const signedIn = () => { onClose(); router.replace("/app"); };
  const props = { onSignedIn: signedIn, onClose, onSwitch: setMode };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto p-4" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div aria-hidden className="pointer-events-none fixed inset-0 bg-[#1b0f2f]/35 backdrop-blur-sm dark:bg-black/60" />
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby="auth-title" className="relative w-full max-w-sm rounded-[22px] border border-line bg-surface p-7 shadow-[var(--shadow)]">
        <button type="button" aria-label="Close" onClick={onClose} className="absolute right-4 top-4 grid size-8 place-items-center rounded-full text-ink-2 hover:bg-surface-alt hover:text-ink">
          <X className="size-4" aria-hidden />
        </button>
        {mode === "login" ? <LoginForm key="login" {...props} /> : <RegisterForm key="register" {...props} />}
      </div>
    </div>
  );
}

export function AuthTrigger({ mode, className, children }: { mode: AuthMode; className?: string; children: React.ReactNode }) {
  const { open } = useAuthModal();
  return <button type="button" onClick={() => open(mode)} className={className}>{children}</button>;
}

/** The legacy /login and /register routes: land on the home page with the popup open (or on /app if already signed in). */
export function OpenAuthModal({ mode }: { mode: AuthMode }) {
  const { open } = useAuthModal();
  const router = useRouter();
  const { ready, token } = useAuth();
  useEffect(() => {
    if (!ready) return;
    if (token) { router.replace("/app"); return; }
    router.replace("/");
    open(mode);
  }, [ready, token, mode, open, router]);
  return null;
}
