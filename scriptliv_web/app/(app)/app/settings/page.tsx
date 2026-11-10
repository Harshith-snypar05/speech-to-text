"use client";
import Link from "next/link";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Badge, Button, Card, Field, Notice, Spinner, inputCls } from "@/components/ui";
import { PaymentBanner } from "@/components/payment-banner";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtMoney } from "@/lib/format";
import type { BillingDetails, Delivery, PaymentMethod, PaymentRow, Settings, Subscription } from "@/lib/types";

const errText = (e: unknown) => (e instanceof ApiError ? e.message : "That did not work. Try again.");

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <Card className="space-y-4">
      <div><h2 className="font-semibold">{title}</h2>{hint && <p className="text-sm text-ink-2">{hint}</p>}</div>
      {children}
    </Card>
  );
}

function DeliveryNote({ d }: { d: Delivery | null }) {
  if (!d) return null;
  if (d.delivery === "email") return <Notice tone="success" title="Verification email sent">Open the link in it to confirm.</Notice>;
  if (d.delivery === "dev" && d.dev_token)
    return <Notice tone="info" title="Test environment: email is not sent"><Link className="font-medium text-primary underline" href={`/verify-email?token=${encodeURIComponent(d.dev_token)}`}>Open the verification link</Link></Notice>;
  return <Notice tone="warning" title="We could not send the email">Email delivery is not available right now. Try again later.</Notice>;
}

function Account() {
  const { token, user, refresh } = useAuth();
  const [name, setName] = useState(user?.name ?? "");
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [del, setDel] = useState<Delivery | null>(null);
  if (!user || !token) return null;

  const saveName = async () => { try { await api.updateName(token, name.trim()); await refresh(); setMsg({ ok: true, text: "Name saved." }); } catch (e) { setMsg({ ok: false, text: errText(e) }); } };
  const changeEmail = async (ev: React.FormEvent) => {
    ev.preventDefault();
    try { setDel(await api.changeEmail(token, email.trim(), pw)); setEmail(""); setPw(""); await refresh(); setMsg(null); } catch (e) { setMsg({ ok: false, text: errText(e) }); }
  };
  const resend = async () => { try { setDel(await api.resendVerification(token)); setMsg(null); } catch (e) { setMsg({ ok: false, text: errText(e) }); } };

  return (
    <Section title="Account details">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span>{user.email}</span>
        <Badge tone={user.email_verified ? "success" : "warning"}>{user.email_verified ? "Verified" : "Not verified"}</Badge>
      </div>
      {user.pending_email && (
        <Notice tone="info" title={`Waiting to confirm ${user.pending_email}`}>
          Your sign-in email changes after you open the link we sent. <button className="font-medium text-primary underline" onClick={resend}>Send it again</button>
        </Notice>
      )}
      {!user.email_verified && !user.pending_email && <Button variant="outline" size="sm" onClick={resend}>Resend verification email</Button>}
      <DeliveryNote d={del} />
      <form onSubmit={(e) => { e.preventDefault(); void saveName(); }} className="flex items-end gap-2">
        <div className="flex-1"><Field label="Name"><input value={name} maxLength={80} required onChange={(e) => setName(e.target.value)} className={inputCls} /></Field></div>
        <Button type="submit" variant="outline" disabled={!name.trim() || name.trim() === user.name}>Save</Button>
      </form>
      <form onSubmit={changeEmail} className="grid gap-3 border-t border-line pt-4 sm:grid-cols-2">
        <Field label="New email"><input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} autoComplete="off" /></Field>
        <Field label="Current password"><input type="password" required value={pw} onChange={(e) => setPw(e.target.value)} className={inputCls} autoComplete="current-password" /></Field>
        <div className="sm:col-span-2"><Button type="submit" variant="outline">Change email</Button></div>
      </form>
      {msg && <Notice tone={msg.ok ? "success" : "error"} title={msg.text} />}
    </Section>
  );
}

function Password() {
  const { token, setToken } = useAuth();
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    if (next.length < 8) { setMsg({ ok: false, text: "New password must be at least 8 characters." }); return; }
    try {
      const r = await api.changePassword(token, cur, next);
      await setToken(r.token); // other devices are signed out; this one keeps going
      setCur(""); setNext(""); setMsg({ ok: true, text: "Password changed. Other devices were signed out." });
    } catch (x) { setMsg({ ok: false, text: errText(x) }); }
  }
  return (
    <Section title="Password">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <Field label="Current password"><input type="password" required value={cur} onChange={(e) => setCur(e.target.value)} className={inputCls} autoComplete="current-password" /></Field>
        <Field label="New password" hint="At least 8 characters."><input type="password" required minLength={8} value={next} onChange={(e) => setNext(e.target.value)} className={inputCls} autoComplete="new-password" /></Field>
        <div className="sm:col-span-2"><Button type="submit" variant="outline">Change password</Button></div>
      </form>
      {msg && <Notice tone={msg.ok ? "success" : "error"} title={msg.text} />}
    </Section>
  );
}

function Preferences() {
  const { settings, saveSettings } = useAuth();
  const [langs, setLangs] = useState<string[]>(["en"]);
  const [err, setErr] = useState<string | null>(null);
  const { token } = useAuth();
  useEffect(() => { if (token) api.settings(token).then((r) => setLangs(r.supported_languages)).catch(() => {}); }, [token]);
  if (!settings) return null;
  const save = async (p: Partial<Settings>) => { setErr(null); try { await saveSettings(p); } catch (e) { setErr(errText(e)); } };
  const themes: Settings["theme"][] = ["light", "dark", "system"];
  return (
    <Section title="Preferences">
      <div>
        <div className="text-sm font-medium">Theme</div>
        <div role="radiogroup" aria-label="Theme" className="mt-2 inline-flex rounded-full border border-line p-1">
          {themes.map((t) => (
            <button key={t} role="radio" aria-checked={settings.theme === t} onClick={() => save({ theme: t })}
              className={"rounded-full px-4 py-1.5 text-sm font-medium capitalize " + (settings.theme === t ? "bg-lavender text-primary" : "text-ink-2 hover:text-ink")}>{t}</button>
          ))}
        </div>
      </div>
      <Field label="Language">
        <select value={settings.language} onChange={(e) => save({ language: e.target.value })} className={inputCls}>
          {langs.map((l) => <option key={l} value={l}>{l === "en" ? "English" : l}</option>)}
        </select>
      </Field>
      <label className="flex items-start justify-between gap-4">
        <span><span className="block text-sm font-medium">Prevent auto-lock while transcribing</span><span className="block text-sm text-ink-2">Keeps the screen awake during a live session so recording is not interrupted.</span></span>
        <input type="checkbox" checked={settings.prevent_auto_lock} onChange={(e) => save({ prevent_auto_lock: e.target.checked })} className="mt-1 size-5 accent-[var(--color-primary)]" />
      </label>
      {err && <Notice tone="error" title={err} />}
    </Section>
  );
}

function Limits() {
  const { settings, saveSettings } = useAuth();
  const [limit, setLimit] = useState(settings?.personal_limit_minutes?.toString() ?? "");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  if (!settings) return null;
  const save = async (p: Partial<Settings>) => { try { await saveSettings(p); setMsg({ ok: true, text: "Saved." }); } catch (e) { setMsg({ ok: false, text: errText(e) }); } };
  const levels = [50, 80, 100];
  const toggle = (n: number) => save({ warn_percents: settings.warn_percents.includes(n) ? settings.warn_percents.filter((x) => x !== n) : [...settings.warn_percents, n].sort((a, b) => a - b) });
  return (
    <Section title="Usage limits" hint="Warnings and an optional monthly cap of your own. Viewers of a shared transcript never count.">
      <label className="flex items-center justify-between gap-4 text-sm">
        <span className="font-medium">Warn me as I use my minutes</span>
        <input type="checkbox" checked={settings.usage_warnings} onChange={(e) => save({ usage_warnings: e.target.checked })} className="size-5 accent-[var(--color-primary)]" />
      </label>
      {settings.usage_warnings && (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Warn at">
          {levels.map((n) => (
            <button key={n} aria-pressed={settings.warn_percents.includes(n)} onClick={() => toggle(n)}
              className={"rounded-full border px-3 py-1 text-sm " + (settings.warn_percents.includes(n) ? "border-primary bg-lavender text-primary" : "border-line text-ink-2")}>{n}% used</button>
          ))}
        </div>
      )}
      <form onSubmit={(e) => { e.preventDefault(); void save({ personal_limit_minutes: limit.trim() ? Math.max(1, Math.floor(Number(limit))) : null }); }} className="flex items-end gap-2">
        <div className="flex-1"><Field label="Personal monthly limit (minutes)" hint="Blank means no personal limit. New sessions stop starting once you reach it.">
          <input inputMode="numeric" pattern="[0-9]*" value={limit} onChange={(e) => setLimit(e.target.value.replace(/\D/g, ""))} className={inputCls} placeholder="No limit" />
        </Field></div>
        <Button type="submit" variant="outline">Save</Button>
      </form>
      {msg && <Notice tone={msg.ok ? "success" : "error"} title={msg.text} />}
    </Section>
  );
}

function Billing() {
  const { token } = useAuth();
  const [sub, setSub] = useState<Subscription | null>(null);
  const [avail, setAvail] = useState(true);
  const [pm, setPm] = useState<PaymentMethod | null>(null);
  const [pays, setPays] = useState<PaymentRow[]>([]);
  const [det, setDet] = useState<BillingDetails>({});
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const [s, m, p, d] = await Promise.all([api.subscription(token), api.paymentMethod(token), api.payments(token), api.billingDetails(token)]);
      setSub(s.subscription); setAvail(s.purchasing_available && m.available); setPm(m.payment_method); setPays(p.payments); setDet(d);
    } catch (e) { setMsg({ ok: false, text: errText(e) }); }
    setLoaded(true);
  }, [token]);
  useEffect(() => { void load(); }, [load]);

  if (!loaded) return <Card><Spinner /></Card>;
  const act = async (fn: () => Promise<Subscription>) => { try { setSub(await fn()); setConfirm(false); setMsg(null); } catch (e) { setMsg({ ok: false, text: errText(e) }); } };
  const portal = async () => { try { window.location.assign((await api.portal(token!)).url); } catch (e) { setMsg({ ok: false, text: errText(e) }); } };
  const paid = sub && sub.plan !== "basic";

  return (
    <>
      <Section title="Subscription">
        {sub?.payment && <PaymentBanner payment={sub.payment} onChanged={(n) => (n ? setSub(n) : void load())} />}
        {sub && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-lg font-semibold">{sub.plan_name}</span>
              <Badge tone={sub.payment ? (sub.payment.access_restricted ? "error" : "warning") : sub.cancel_at_period_end ? "warning" : "success"}>{sub.payment ? (sub.payment.access_restricted ? "Payment required" : "Payment failed") : sub.cancel_at_period_end ? "Cancelled" : "Active"}</Badge>
            </div>
            <p className="text-sm text-ink-2">
              {sub.cancel_at_period_end ? `You keep Pro access until ${fmtDate(sub.access_ends_at ?? sub.renews_or_resets_at)}. After that you move to Basic.`
                : paid ? `Renews ${fmtDate(sub.renews_or_resets_at)} · $${sub.price_usd_month}/month` : `Your free minutes reset ${fmtDate(sub.renews_or_resets_at)}.`}
            </p>
            <div className="flex flex-wrap gap-2">
              <Link href="/app/plans"><Button variant="outline">{paid ? "View plans and add-ons" : "Upgrade or buy minutes"}</Button></Link>
              {paid && sub.cancel_at_period_end && <Button onClick={() => act(() => api.resumePlan(token!))}>Keep my plan</Button>}
              {paid && !sub.cancel_at_period_end && !confirm && <Button variant="ghost" className="text-error" onClick={() => setConfirm(true)}>Cancel plan</Button>}
            </div>
            {confirm && sub && (
              <div className="rounded-xl border border-error/30 bg-error/10 p-3 text-sm">
                <p>Cancel Pro? You keep access until <b>{fmtDate(sub.renews_or_resets_at)}</b>, then move to Basic.</p>
                <div className="mt-2 flex gap-2"><Button variant="danger" size="sm" onClick={() => act(() => api.cancelPlan(token!))}>Cancel plan</Button><Button variant="ghost" size="sm" onClick={() => setConfirm(false)}>Keep it</Button></div>
              </div>
            )}
          </>
        )}
        {!avail && <Notice tone="info" title="Payments are not switched on yet">Plan purchases, payment methods and receipts appear here once billing is enabled.</Notice>}
        {msg && <Notice tone={msg.ok ? "success" : "error"} title={msg.text} />}
      </Section>

      <Section title="Payment method">
        {pm?.last4 ? (
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="capitalize">{pm.brand} ending {pm.last4} · expires {pm.exp_month}/{pm.exp_year}</span>
            <Button variant="outline" size="sm" onClick={portal}>Update</Button>
          </div>
        ) : <p className="text-sm text-ink-2">{avail ? "No card on file." : "Not available yet."}</p>}
      </Section>

      <Section title="Payment history">
        {pays.length === 0 ? <p className="text-sm text-ink-2">No payments yet.</p> : (
          <ul className="divide-y divide-line text-sm">
            {pays.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span>{fmtDate(p.created_at)} · {p.description}</span>
                <span className="flex items-center gap-3 tabular-nums">{fmtMoney(p.amount_cents, p.currency)} <Badge tone={p.status === "paid" ? "success" : "neutral"}>{p.status}</Badge>
                  {p.receipt_url && <a href={p.receipt_url} target="_blank" rel="noreferrer" className="text-primary underline">Receipt</a>}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Billing details" hint="Printed on your receipts.">
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={async (e) => { e.preventDefault(); try { setDet(await api.saveBillingDetails(token!, det)); setMsg({ ok: true, text: "Billing details saved." }); } catch (x) { setMsg({ ok: false, text: errText(x) }); } }}>
          {(["name", "company", "address", "country", "tax_id"] as const).map((k) => (
            <Field key={k} label={{ name: "Name", company: "Company", address: "Address", country: "Country", tax_id: "Tax ID" }[k]}>
              <input value={det[k] ?? ""} maxLength={200} onChange={(e) => setDet({ ...det, [k]: e.target.value })} className={inputCls} />
            </Field>
          ))}
          <div className="sm:col-span-2"><Button type="submit" variant="outline">Save billing details</Button></div>
        </form>
      </Section>
    </>
  );
}

function Microphone() {
  const [mics, setMics] = useState<MediaDeviceInfo[] | null>(null);
  const [mic, setMic] = useState("");
  useEffect(() => { try { setMic(localStorage.getItem("sl-mic") ?? ""); } catch { /* ignore */ } }, []);
  async function loadMics() {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      s.getTracks().forEach((t) => t.stop());
      setMics((await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput"));
    } catch { setMics([]); }
  }
  return (
    <Section title="Microphone" hint="Stored in this browser only.">
      {!mics ? <Button variant="outline" onClick={loadMics}>Choose microphone…</Button>
        : mics.length === 0 ? <Notice tone="warning" title="No microphone available or permission denied" />
        : (
          <select value={mic} aria-label="Microphone" onChange={(e) => { setMic(e.target.value); try { localStorage.setItem("sl-mic", e.target.value); } catch { /* ignore */ } }} className={inputCls + " mt-0"}>
            <option value="">System default</option>
            {mics.map((m) => <option key={m.deviceId} value={m.deviceId}>{m.label || "Microphone"}</option>)}
          </select>
        )}
    </Section>
  );
}

export default function SettingsPage() {
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <Account />
      <Password />
      <Preferences />
      <Limits />
      <Billing />
      <Microphone />
    </div>
  );
}
