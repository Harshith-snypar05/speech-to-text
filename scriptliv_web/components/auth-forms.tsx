"use client";
import Link from "next/link";
import { useState } from "react";
import { CheckEmail } from "@/components/check-email";
import { Button, Field, Notice, inputCls } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export type AuthFormProps = {
  /** sign-in succeeded */
  onSignedIn: () => void;
  /** leave the popup without signing in (e.g. following the forgot-password link) */
  onClose: () => void;
  onSwitch: (m: "login" | "register") => void;
};

function Heading({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-5 pr-8">
      <h2 id="auth-title" className="text-2xl font-bold tracking-tight">{title}</h2>
      {subtitle && <p className="mt-1 text-sm text-ink-2">{subtitle}</p>}
    </div>
  );
}

export function LoginForm({ onSignedIn, onClose, onSwitch }: AuthFormProps) {
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [unverified, setUnverified] = useState<string | null>(null);
  const [devToken, setDevToken] = useState<string | undefined>();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await signIn(email.trim(), password);
      onSignedIn();
    } catch (x) {
      if (x instanceof ApiError && x.code === "email_not_verified") { setUnverified(email.trim()); return; }
      setErr(x instanceof ApiError ? x.message : "Sign-in failed. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (unverified) {
    return (
      <>
        <Heading title="Verify your email first" subtitle="This account is not verified yet." />
        <CheckEmail email={unverified} devToken={devToken} onDevToken={setDevToken} onSignIn={() => setUnverified(null)} />
      </>
    );
  }

  return (
    <>
      <Heading title="Welcome back" subtitle="Sign in to your ScriptLiv account." />
      <form onSubmit={submit} className="space-y-4">
        <Field label="Email">
          <input type="email" required autoFocus autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Password">
          <input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className={inputCls} />
        </Field>
        <div className="text-right text-sm"><Link href="/forgot-password" onClick={onClose} className="font-medium text-primary">Forgot password?</Link></div>
        {err && <Notice tone="error" title={err} />}
        <Button type="submit" size="lg" className="w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
      </form>
      <p className="mt-5 text-center text-sm text-ink-2">New to ScriptLiv? <button type="button" onClick={() => onSwitch("register")} className="font-medium text-primary">Create an account</button></p>
    </>
  );
}

export function RegisterForm({ onSwitch }: AuthFormProps) {
  const { signUp } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sent, setSent] = useState<{ email: string; devToken?: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < 8) { setErr("Password must be at least 8 characters."); return; }
    setBusy(true);
    setErr(null);
    try {
      const r = await signUp(name.trim(), email.trim(), password);
      setSent({ email: r.user.email, devToken: r.verification?.dev_token });
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : "Could not create the account. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <>
        <Heading title="Verify your email" subtitle="One more step before you can sign in." />
        <CheckEmail email={sent.email} devToken={sent.devToken} onDevToken={(t) => setSent({ ...sent, devToken: t })} onSignIn={() => onSwitch("login")} />
      </>
    );
  }

  return (
    <>
      <Heading title="Create your account" subtitle="Start with 300 free minutes every month. No card needed." />
      <form onSubmit={submit} className="space-y-4">
        <Field label="Name">
          <input required autoFocus maxLength={80} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Email">
          <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Password" hint="At least 8 characters.">
          <input type="password" required minLength={8} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className={inputCls} />
        </Field>
        {err && <Notice tone="error" title={err} />}
        <Button type="submit" size="lg" className="w-full" disabled={busy}>{busy ? "Creating account…" : "Create account"}</Button>
        <p className="text-xs text-ink-3">By creating an account you agree to our <Link href="/terms" target="_blank" className="font-medium text-primary underline">Terms &amp; Conditions</Link> and <Link href="/privacy" target="_blank" className="font-medium text-primary underline">Privacy Policy</Link>.</p>
      </form>
      <p className="mt-5 text-center text-sm text-ink-2">Already have an account? <button type="button" onClick={() => onSwitch("login")} className="font-medium text-primary">Sign in</button></p>
    </>
  );
}
