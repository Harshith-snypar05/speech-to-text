"use client";
import { Check, Copy, Link2, Link2Off, Mic, RotateCcw, Square } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Waveform } from "@/components/waveform";
import { Badge, Button, Card, Notice, inputCls } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { config, isWsConfigured } from "@/lib/config";
import { LiveClient, newSessionId, type LiveState } from "@/lib/live-client";
import { fmtDuration } from "@/lib/format";
import { closeNotice, micMessage } from "@/lib/friendly-errors";
import { cn } from "@/lib/utils";

const absolute = (u: string) => (u.startsWith("http") ? u : `${location.origin}${u.startsWith("/") ? "" : "/"}${u}`);

const LABEL: Record<LiveState, { text: string; tone: "neutral" | "success" | "error" | "warning" | "info" | "primary" }> = {
  idle: { text: "Ready", tone: "neutral" },
  "requesting-mic": { text: "Waiting for microphone permission", tone: "info" },
  "mic-denied": { text: "Microphone blocked", tone: "error" },
  connecting: { text: "Connecting to ScriptLiv", tone: "info" },
  "backend-unavailable": { text: "Backend unavailable", tone: "error" },
  live: { text: "Recording", tone: "success" },
  reconnecting: { text: "Reconnecting", tone: "warning" },
  "connection-failed": { text: "Connection lost", tone: "error" },
  unauthorized: { text: "Access refused", tone: "error" },
  stopping: { text: "Finishing", tone: "info" },
  stopped: { text: "Session saved", tone: "neutral" },
  error: { text: "Error", tone: "error" },
};

export default function RecordPage() {
  const { token, user, settings } = useAuth();
  const wake = useRef<WakeLockSentinel | null>(null);
  const [state, setState] = useState<LiveState>("idle");
  const [detail, setDetail] = useState<string>();
  const [finals, setFinals] = useState<string[]>([]);
  const [partial, setPartial] = useState("");
  const [levels, setLevels] = useState<number[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [lost, setLost] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [shareBusy, setShareBusy] = useState(false);
  const [shareMsg, setShareMsg] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const client = useRef<LiveClient | null>(null);
  const t0 = useRef(0);
  const scroller = useRef<HTMLDivElement>(null);

  const busy = ["requesting-mic", "connecting", "live", "reconnecting", "stopping"].includes(state);

  useEffect(() => () => { void client.current?.stop(); }, []);

  // "Prevent auto-lock" setting: hold a screen wake lock while recording. Best effort; unsupported browsers just skip it.
  const wantWake = !!settings?.prevent_auto_lock && (state === "live" || state === "reconnecting");
  useEffect(() => {
    if (!wantWake || !("wakeLock" in navigator)) return;
    let cancelled = false;
    const grab = () => navigator.wakeLock.request("screen").then((l) => { if (cancelled) void l.release(); else wake.current = l; }).catch(() => { /* denied */ });
    void grab();
    const onVis = () => { if (document.visibilityState === "visible") void grab(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { cancelled = true; document.removeEventListener("visibilitychange", onVis); void wake.current?.release().catch(() => {}); wake.current = null; };
  }, [wantWake]);
  useEffect(() => { scroller.current?.scrollTo({ top: 1e9, behavior: "smooth" }); }, [finals, partial]);
  useEffect(() => {
    if (state !== "live") return;
    const i = setInterval(() => { setElapsed((Date.now() - t0.current) / 1000); setLost(client.current?.lostAudioMs ?? 0); }, 500);
    return () => clearInterval(i);
  }, [state]);

  const start = useCallback(async () => {
    if (!token || !isWsConfigured()) return;
    const id = newSessionId(); // one session per press; reconnects reuse it
    setSessionId(id);
    setFinals([]); setPartial(""); setLevels([]); setLost(0); setElapsed(0);
    setShareUrl(null); setShareMsg(null); setCopied(false);
    t0.current = Date.now();
    let micDeviceId: string | undefined;
    try { micDeviceId = localStorage.getItem("sl-mic") || undefined; } catch { /* ignore */ }
    const c = new LiveClient({ wsUrl: config.wsUrl, sessionId: id, token, micDeviceId }, {
      onState: (s, d) => { setState(s); setDetail(d); if (s === "stopped") setPartial(""); if (s === "stopped" || s === "connection-failed") setLost(c.lostAudioMs); },
      onPartial: setPartial,
      onFinal: (t) => setFinals((f) => [...f, t]),
      onRefine: (o, r) => setFinals((f) => { const i = f.lastIndexOf(o); return i < 0 ? f : f.map((x, k) => (k === i ? r : x)); }),
      onLevel: (r) => setLevels((l) => (l.length > 200 ? [...l.slice(-100), r] : [...l, r])),
    });
    client.current = c;
    await c.start();
  }, [token]);

  const stop = () => void client.current?.stop();

  // Live share link: the relay creates the session record when the first words arrive, so sharing before that returns 404.
  async function toggleShare() {
    if (!token || !sessionId) return;
    setShareBusy(true); setShareMsg(null);
    try {
      const r = shareUrl ? await api.unshare(token, sessionId) : await api.share(token, sessionId);
      setShareUrl(r.sharing && r.share_url ? absolute(r.share_url) : null);
    } catch (e) {
      setShareMsg(e instanceof ApiError && e.status === 404 ? "Start speaking first. The link works once the first words are transcribed." : e instanceof ApiError ? e.message : "Could not update sharing. Try again.");
    } finally { setShareBusy(false); }
  }
  async function copyShare() {
    if (!shareUrl) return;
    try { await navigator.clipboard.writeText(shareUrl); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { setShareMsg("Could not copy. Select the link and copy it by hand."); }
  }
  const unverified = !!user && !user.email_verified;
  const lbl = LABEL[state];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Record</h1>
        <div className="flex items-center gap-3">
          {state === "live" && <span className="tabular-nums text-sm text-ink-2">{fmtDuration(elapsed)}</span>}
          <Badge tone={lbl.tone}><span className={cn("size-1.5 rounded-full bg-current", state === "live" && "animate-pulse")} />{lbl.text}{state === "reconnecting" && detail ? ` (${detail})` : ""}</Badge>
        </div>
      </div>

      {unverified && (
        <Notice tone="warning" title="Verify your email to start recording">
          Recording, share links and purchases need a verified email address. <Link href="/app/settings" className="font-medium text-primary underline">Open Settings to verify</Link>.
        </Notice>
      )}
      {!isWsConfigured() && <Notice tone="warning" title="Live transcription is not configured">Set NEXT_PUBLIC_WS_URL in .env.local and restart the website.</Notice>}
      {state === "mic-denied" && <Notice tone="error" title="We can't use your microphone">{micMessage(detail)}</Notice>}
      {state === "backend-unavailable" && <Notice tone="error" title="We couldn't connect to ScriptLiv">Nothing was recorded. Check your internet connection and try again. If it keeps happening, wait a minute; the service may be restarting.</Notice>}
      {state === "unauthorized" && <RefusedNotice detail={detail} />}
      {state === "error" && <Notice tone="error" title="Recording stopped unexpectedly">Something interrupted the recording. Refresh the page and start again. Your transcript so far is saved.</Notice>}
      {state === "reconnecting" && <Notice tone="warning" title="Connection dropped, reconnecting to the same session">Speech while disconnected is not captured.</Notice>}
      {state === "connection-failed" && (
        <Notice tone="error" title="Could not reconnect">
          {sessionId && <>Your transcript so far is saved. </>}
          <Button size="sm" variant="outline" className="ml-1 mt-2" onClick={() => client.current?.retry()}><RotateCcw className="size-3" /> Retry same session</Button>
        </Notice>
      )}
      {lost > 0 && <Notice tone="warning" title={`About ${(lost / 1000).toFixed(1)} s of audio was not captured while offline`} />}

      <Card className="p-5">
        <Waveform levels={levels} active={state === "live"} />
        <div className="mt-5 flex flex-col items-center gap-2">
          {busy ? (
            <Button variant="danger" size="lg" onClick={stop} disabled={state === "stopping" || state === "requesting-mic" || state === "connecting"} className="h-16 w-16 rounded-full p-0" aria-label="Stop recording"><Square className="size-6" fill="currentColor" /></Button>
          ) : (
            <Button size="lg" onClick={start} disabled={!token || !isWsConfigured() || unverified} className="h-16 w-16 rounded-full p-0" aria-label="Start recording"><Mic className="size-7" /></Button>
          )}
          <div className="text-xs text-ink-2">{busy ? "Press to stop" : "Press to start"}</div>
        </div>
      </Card>

      {sessionId && (
        <Card className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="font-semibold">Share live</h2>
              <p className="text-sm text-ink-2">{shareUrl ? "Anyone with the link sees the transcript update live. They never use your minutes." : "Create a link so others can follow this transcript as you speak."}</p>
            </div>
            <Button variant={shareUrl ? "outline" : "primary"} onClick={toggleShare} disabled={shareBusy}>
              {shareUrl ? <><Link2Off className="size-4" /> Stop sharing</> : <><Link2 className="size-4" /> Share live link</>}
            </Button>
          </div>
          {shareMsg && <p role="status" className="text-sm text-warning">{shareMsg}</p>}
          {shareUrl && (
            <div className="flex gap-2">
              <input readOnly aria-label="Live share link" value={shareUrl} onFocus={(e) => e.currentTarget.select()} className={inputCls + " mt-0"} />
              <Button variant="outline" onClick={copyShare}>{copied ? <><Check className="size-4" /> Copied</> : <><Copy className="size-4" /> Copy</>}</Button>
            </div>
          )}
        </Card>
      )}

      <div className="grid gap-5 md:grid-cols-[1fr_260px]">
      <Card className="p-0">
        <div className="flex items-center justify-between border-b border-line px-5 py-3 text-sm font-medium">
          Live transcript
          {sessionId && state === "stopped" && <Link href={`/app/history/${sessionId}`} className="text-primary">Open in history</Link>}
        </div>
        <div ref={scroller} className="h-72 overflow-auto px-5 py-4" aria-live="polite">
          {finals.length === 0 && !partial && <p className="text-sm text-ink-3">{state === "live" ? "Listening. Start speaking." : "Your transcript appears here."}</p>}
          {finals.map((t, i) => <p key={i} className="mb-2 leading-relaxed text-ink">{t}</p>)}
          {partial && <p className="italic leading-relaxed text-ink-3" data-testid="partial">{partial}</p>}
        </div>
      </Card>
      <Card className="h-fit space-y-2 text-sm">
        <h2 className="font-semibold">Session info</h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
          <dt className="text-ink-2">Account</dt><dd className="truncate text-right" title={user?.email}>{user?.email ?? "unavailable"}</dd>
          <dt className="text-ink-2">Duration</dt><dd className="text-right tabular-nums">{sessionId ? fmtDuration(elapsed) : "—"}</dd>
          <dt className="text-ink-2">Segments</dt><dd className="text-right tabular-nums">{finals.length}</dd>
          <dt className="text-ink-2">Screen lock</dt><dd className="text-right">{settings?.prevent_auto_lock ? "Kept awake" : "Normal"}</dd>
        </dl>
        {sessionId && state === "stopped" && <Link href={`/app/history/${sessionId}`} className="block rounded-full border border-primary/40 px-3 py-2 text-center text-xs font-medium text-primary">Open transcript</Link>}
      </Card>
      </div>
    </div>
  );
}

/** Why the relay closed the connection (code:reason from live-client). */
function RefusedNotice({ detail }: { detail?: string }) {
  const d = detail ?? "";
  const i = d.indexOf(":");
  const n = closeNotice(i < 0 ? d : d.slice(0, i), i < 0 ? "" : d.slice(i + 1));
  return (
    <Notice tone={n.tone} title={n.title}>
      {n.body} {n.link && <Link href={n.link.href} className="font-medium text-primary underline">{n.link.label}</Link>}
    </Notice>
  );
}
