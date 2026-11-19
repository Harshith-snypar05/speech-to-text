"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight, LogOut, Pencil } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Badge, Button, Card, Field, Notice, Progress, Spinner, Stat, inputCls } from "@/components/ui";
import { PaymentBanner } from "@/components/payment-banner";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useOffer } from "@/lib/offer";
import { fmtDate, fmtMinutes, fmtSecs } from "@/lib/format";
import type { BillingDetails, Delivery, PaymentMethod, Settings, Subscription, UsageSummary } from "@/lib/types";

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

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-label={title} className="w-full max-w-md space-y-4 rounded-[var(--radius-card)] border border-line bg-surface p-6 shadow-xl">
        <h2 className="text-lg font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  );
}

/** One tappable settings line: label left, value / chevron right. */
function Row({ label, value, onClick, href, tone, trailing, chevron }: {
  label: string; value?: ReactNode; onClick?: () => void; href?: string; tone?: "danger" | "primary"; trailing?: ReactNode; chevron?: boolean;
}) {
  const cls = "flex w-full items-center justify-between gap-3 py-3 text-left text-sm " + (onClick || href ? "hover:text-primary " : "");
  const color = tone === "danger" ? "text-error" : tone === "primary" ? "text-primary" : "";
  const inner = (
    <>
      <span className={"font-medium " + color}>{label}</span>
      <span className="flex min-w-0 items-center gap-2 text-ink-2">
        {value != null && <span className="truncate">{value}</span>}
        {trailing}
        {chevron && <ChevronRight className="-mr-1 size-5 shrink-0" aria-hidden />}
      </span>
    </>
  );
  if (href) return <Link href={href} className={cls}>{inner}</Link>;
  if (onClick) return <button type="button" onClick={onClick} className={cls}>{inner}</button>;
  return <div className={cls}>{inner}</div>;
}

function Account() {
  const { token, user, refresh } = useAuth();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(user?.name ?? "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [del, setDel] = useState<Delivery | null>(null);
  if (!user || !token) return null;

  const saveName = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setBusy(true);
    try { await api.updateName(token, name.trim()); await refresh(); setEditing(false); setMsg({ ok: true, text: "Name saved." }); }
    catch (e) { setMsg({ ok: false, text: errText(e) }); }
    setBusy(false);
  };
  const resend = async () => { try { setDel(await api.resendVerification(token)); setMsg(null); } catch (e) { setMsg({ ok: false, text: errText(e) }); } };

  return (
    <Section title="Account details">
      <div className="divide-y divide-line">
        <Row label="Name" value={user.name || "-"} onClick={() => { setName(user.name ?? ""); setMsg(null); setEditing(true); }}
          trailing={<Pencil className="size-4 text-primary" aria-label="Edit name" />} />
        <Row label="Email" value={user.email} trailing={<Badge tone={user.email_verified ? "success" : "warning"}>{user.email_verified ? "Verified" : "Not verified"}</Badge>} />
      </div>
      {user.pending_email && (
        <Notice tone="info" title={`Waiting to confirm ${user.pending_email}`}>
          Your sign-in email changes after you open the link we sent. <button className="font-medium text-primary underline" onClick={resend}>Send it again</button>
        </Notice>
      )}
      {!user.email_verified && !user.pending_email && <Button variant="outline" size="sm" onClick={resend}>Resend verification email</Button>}
      <DeliveryNote d={del} />
      {msg && <Notice tone={msg.ok ? "success" : "error"} title={msg.text} />}
      {editing && (
        <Modal title="Edit name" onClose={() => setEditing(false)}>
          <form onSubmit={saveName} className="space-y-4">
            <Field label="Name"><input autoFocus value={name} maxLength={80} required onChange={(e) => setName(e.target.value)} className={inputCls} /></Field>
            {msg && !msg.ok && <Notice tone="error" title={msg.text} />}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
              <Button type="submit" disabled={busy || !name.trim()}>{busy ? "Saving..." : "Save"}</Button>
            </div>
          </form>
        </Modal>
      )}
    </Section>
  );
}

/** Password changes go through an emailed reset link, the same flow as "Forgot password" on the login page. */
function Password() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try { const r = await api.forgotPassword(email.trim()); setSent(r.message || "If that email has an account, a reset link is on its way."); }
    catch (x) { setErr(errText(x)); }
    setBusy(false);
  };
  return (
    <Section title="Security">
      <div className="divide-y divide-line">
        <Row label="Change password" chevron onClick={() => { setEmail(user?.email ?? ""); setSent(null); setErr(null); setOpen(true); }} />
      </div>
      {open && (
        <Modal title={sent ? "Check your email" : "Change password"} onClose={close}>
          {sent ? (
            <>
              <Notice tone="success" title={sent} />
              <div className="flex justify-end"><Button onClick={close}>Done</Button></div>
            </>
          ) : (
            <form onSubmit={send} className="space-y-4">
              <p className="text-sm text-ink-2">To keep your account safe we email you a link to choose a new password.</p>
              <Field label="Email"><input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} /></Field>
              {err && <Notice tone="error" title={err} />}
              <div className="flex justify-end gap-2">
                <Button type="button" variant="ghost" onClick={close}>Cancel</Button>
                <Button type="submit" disabled={busy}>{busy ? "Sending..." : "Send reset link"}</Button>
              </div>
            </form>
          )}
        </Modal>
      )}
    </Section>
  );
}


function Preferences() {
  const { settings, saveSettings } = useAuth();
  const [langs, setLangs] = useState<string[]>(["en"]);
  const [err, setErr] = useState<string | null>(null);
  const { token } = useAuth();
  useEffect(() => { if (token) api.settings(token).then((r) => setLangs(r.supported_languages)).catch(() => { }); }, [token]);
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

function Usage() {
  const { token } = useAuth();
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => { if (token) api.usage(token).then(setUsage).catch(() => setErr(true)); }, [token]);
  if (err) return <Notice tone="error" title="Could not load your usage" />;
  if (!usage) return <Card><Spinner /></Card>;
  const pct = usage.percent_used;
  if (usage.promo?.active) {
    const total = usage.promo.allowance_minutes ?? usage.included_minutes;
    return (
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">Inaugural offer: free minutes</h2>
          <Badge tone="success">Active</Badge>
        </div>
        <div className="mt-4"><Progress value={pct} tone={usage.total_remaining_seconds <= 0 ? "error" : pct >= 80 ? "warning" : "primary"} label="Free minutes used" /></div>
        <p className="mt-2 text-sm text-ink-2">
          {fmtSecs(usage.included_used_seconds)} of {total.toLocaleString()} min used · {fmtSecs(usage.total_remaining_seconds)} left
          {usage.promo.until ? `. The offer runs until ${fmtDate(usage.promo.until)}.` : "."} Only the person speaking uses minutes.
        </p>
      </Card>
    );
  }
  const tone = usage.total_remaining_seconds <= 0 ? "error" : pct >= 80 ? "warning" : "primary";
  return (
    <>
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2"><h2 className="font-semibold">{usage.plan_name} plan</h2>{usage.cancel_at_period_end && <Badge tone="warning">Ends {fmtDate(usage.reset_at)}</Badge>}</div>
          <span className="text-sm text-ink-2">{usage.cancel_at_period_end ? "Access ends" : "Resets"} {fmtDate(usage.reset_at)}</span>
        </div>
        <div className="mt-4"><Progress value={pct} tone={tone} label="Included minutes used" /></div>
        <p className="mt-2 text-sm text-ink-2">
          {fmtSecs(usage.included_used_seconds)} of {usage.included_minutes.toLocaleString()} min used · {fmtSecs(usage.included_remaining_seconds)} left
        </p>
      </Card>
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Included left" value={fmtMinutes(usage.included_remaining_seconds)} hint={`of ${usage.included_minutes.toLocaleString()} min`} />
        <Stat label="Add-on balance" value={fmtMinutes(usage.addon_remaining_seconds)} hint={usage.addons.length ? `Expires ${fmtDate(Math.min(...usage.addons.map((a) => a.expires_at)))}` : "None active"} />
        <Stat label="Total available" value={fmtMinutes(usage.total_remaining_seconds)} hint={`Resets ${fmtDate(usage.reset_at)}`} />
      </div>
      <p className="text-xs text-ink-2">Only the person speaking uses minutes. People watching a shared transcript never do.</p>
    </>
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

function Membership() {
  const { token } = useAuth();
  const offer = useOffer();
  const [sub, setSub] = useState<Subscription | null>(null);
  const [avail, setAvail] = useState(true);
  const [pm, setPm] = useState<PaymentMethod | null>(null);
  const [det, setDet] = useState<BillingDetails>({});
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const [s, m, d] = await Promise.all([api.subscription(token), api.paymentMethod(token), api.billingDetails(token)]);
      setSub(s.subscription); setAvail(s.purchasing_available && m.available); setPm(m.payment_method); setDet(d);
    } catch (e) { setMsg({ ok: false, text: errText(e) }); }
    setLoaded(true);
  }, [token]);
  useEffect(() => { void load(); }, [load]);

  if (!loaded || !offer) return <Card><Spinner /></Card>;
  if (offer.active) return null;   // no plans, payments or billing while the inaugural offer runs
  const portal = async () => { try { window.location.assign((await api.portal(token!)).url); } catch (e) { setMsg({ ok: false, text: errText(e) }); } };
  const paid = sub && sub.plan !== "basic";
  const price = sub ? (sub.price_display ?? (sub.price_inr_month ? `₹${sub.price_inr_month.toLocaleString()}${sub.tax_note ? ` ${sub.tax_note}` : ""}` : "₹999 + GST")) : "";
  const next = !sub ? "-" : !paid ? "None (free plan)" : sub.cancel_at_period_end ? `None (ends ${fmtDate(sub.access_ends_at ?? sub.renews_or_resets_at)})` : `${fmtDate(sub.renews_or_resets_at)} · ${price}`;
  const badge = sub ? (sub.payment ? (sub.payment.access_restricted ? "Payment required" : "Payment failed") : sub.cancel_at_period_end ? "Cancelled" : "Active") : "";
  const badgeTone = sub ? (sub.payment ? (sub.payment.access_restricted ? "error" : "warning") : sub.cancel_at_period_end ? "warning" : "success") : "neutral";

  return (
    <>
      <Section title="Membership details">
        {sub?.payment && <PaymentBanner payment={sub.payment} onChanged={(n) => (n ? setSub(n) : void load())} />}
        {sub && (
          <div className="divide-y divide-line">
            <Row label="Plan" value={sub.plan_name} trailing={<Badge tone={badgeTone}>{badge}</Badge>} />
            <Row label="Next payment" value={next} />
            <Row label="Payment method" value={pm?.last4 ? <span className="capitalize">{pm.brand} ending {pm.last4}</span> : paid ? "No card on file" : "-"}
              trailing={pm?.last4 ? <button type="button" onClick={portal} className="text-primary underline">Update</button> : undefined} />
            <Row label="Change plan" chevron href="/pricing" />
            <Row label="View payment history" chevron href="/app/settings/payments" />
          </div>
        )}
        {!avail && <Notice tone="info" title="Payments are not switched on yet">Plan purchases, payment methods and receipts appear here once billing is enabled.</Notice>}
        {msg && <Notice tone={msg.ok ? "success" : "error"} title={msg.text} />}
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

/** Help links: feature requests, connection troubleshooting and the legal pages. */
function Help() {
  return (
    <Section title="Help">
      <div className="divide-y divide-line">
        <Row label="Request a feature" chevron href="/app/settings/request-feature" />
        <Row label="Fix a connection issue" chevron href="/app/settings/connection-help" />
        <Row label="Privacy Policy" chevron href="/privacy" />
        <Row label="Terms & Conditions" chevron href="/terms" />
      </div>
    </Section>
  );
}

/** Account actions, shown just above Log out: cancel membership and delete account, each behind a confirmation. */
function AccountActions() {
  const { token, signOut } = useAuth();
  const router = useRouter();
  const [sub, setSub] = useState<Subscription | null>(null);
  const [dlg, setDlg] = useState<"cancel" | "delete" | null>(null);
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { if (token) api.subscription(token).then((r) => setSub(r.subscription)).catch(() => { }); }, [token]);
  if (!token) return null;
  const paid = sub && sub.plan !== "basic";
  const close = () => { setDlg(null); setPw(""); setErr(null); };

  const doCancel = async () => {
    setBusy(true); setErr(null);
    try { setSub(await api.cancelPlan(token)); setMsg({ ok: true, text: "Membership cancelled. You keep access until the period ends." }); close(); }
    catch (e) { setErr(errText(e)); }
    setBusy(false);
  };
  const keep = async () => { try { setSub(await api.resumePlan(token)); setMsg({ ok: true, text: "Membership kept." }); } catch (e) { setMsg({ ok: false, text: errText(e) }); } };
  const doDelete = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try { await api.deleteAccount(token, pw); signOut(); router.replace("/login"); return; }
    catch (x) { setErr(errText(x)); }
    setBusy(false);
  };

  return (
    <Card className="space-y-1">
      <div className="divide-y divide-line">
        {paid && (sub.cancel_at_period_end
          ? <Row label="Keep my membership" tone="primary" onClick={keep} />
          : <Row label="Cancel membership" tone="danger" onClick={() => { setErr(null); setDlg("cancel"); }} />)}
        <Row label="Delete account" tone="danger" onClick={() => { setErr(null); setDlg("delete"); }} />
      </div>
      {msg && <Notice tone={msg.ok ? "success" : "error"} title={msg.text} />}
      {dlg === "cancel" && sub && (
        <Modal title="Cancel membership?" onClose={close}>
          <p className="text-sm text-ink-2">You keep Pro until <b>{fmtDate(sub.renews_or_resets_at)}</b>. After that you move to the free Basic plan.</p>
          {err && <Notice tone="error" title={err} />}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={close}>Not now</Button>
            <Button variant="danger" disabled={busy} onClick={doCancel}>Cancel membership</Button>
          </div>
        </Modal>
      )}
      {dlg === "delete" && (
        <Modal title="Delete account?" onClose={close}>
          <form onSubmit={doDelete} className="space-y-4">
            <p className="text-sm text-ink-2">This permanently deletes your account, transcripts and usage. It cannot be undone.</p>
            <Field label="Your password"><input type="password" required autoFocus value={pw} onChange={(e) => setPw(e.target.value)} className={inputCls} autoComplete="current-password" /></Field>
            {err && <Notice tone="error" title={err} />}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={close}>Cancel</Button>
              <Button type="submit" variant="danger" disabled={busy || !pw}>{busy ? "Deleting..." : "Delete account"}</Button>
            </div>
          </form>
        </Modal>
      )}
    </Card>
  );
}

function LogoutButton() {
  const { signOut } = useAuth();
  const router = useRouter();
  return (
    <Button variant="outline" size="lg" className="w-full text-error" onClick={() => { signOut(); router.replace("/login"); }}>
      <LogOut className="size-4" aria-hidden /> Log out
    </Button>
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
      <Usage />
      <Limits />
      <Membership />
      <Microphone />
      <Help />
      <AccountActions />
      <LogoutButton />
    </div>
  );
}
