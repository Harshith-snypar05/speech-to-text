"use client";
import { Mic, RotateCcw, Square } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Waveform } from "@/components/waveform";
import { Badge, Button, Card, Notice } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { config, isWsConfigured } from "@/lib/config";
import { LiveClient, newSessionId, type LiveState } from "@/lib/live-client";
import { fmtDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

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
      {state === "mic-denied" && <Notice tone="error" title="Microphone access was blocked">Allow the microphone for this site in your browser settings, then try again.</Notice>}
      {state === "backend-unavailable" && <Notice tone="error" title="Could not reach the transcription backend">No audio was recorded. Check that the staging relay is running and try again.</Notice>}
      {state === "unauthorized" && <RefusedNotice detail={detail} />}
      {state === "error" && <Notice tone="error" title="Something went wrong" >{detail}</Notice>}
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
  const code = i < 0 ? d : d.slice(0, i);
  const reason = i < 0 ? "" : d.slice(i + 1);
  const plans = <Link href="/app/plans" className="font-medium text-primary underline">See plans and add-ons</Link>;
  if (code === "4403") return (
    <Notice tone="warning" title="Verify your email to record">
      Transcription is available once your email address is verified. <Link href="/app/settings" className="font-medium text-primary underline">Open Settings</Link>.
    </Notice>
  );
  if (code === "4409") return <Notice tone="info" title="Recording continued on another connection">This session was taken over by a newer connection (for example after a network change). Your transcript so far is saved.</Notice>;
  if (code === "4402") {
    if (reason === "allowance_reserved") return <Notice tone="warning" title="Your minutes are in use by another recording">Another recording on your account holds your remaining minutes. Finish or stop it, then start again.</Notice>;
    if (reason === "payment_required") return <Notice tone="error" title="Payment required">Your last payment failed, so paid minutes and add-ons are paused. Update your payment method or retry the payment. {plans}.</Notice>;
    if (reason === "personal_limit") return <Notice tone="error" title="You reached your personal limit">Recording stopped at the limit you set in Settings. Raise it there to continue.</Notice>;
    return <Notice tone="error" title="You are out of minutes">Recording stopped exactly when your minutes ran out; nothing was recorded past your balance. {plans}.</Notice>;
  }
  return <Notice tone="error" title="This connection was refused">Your sign-in may have expired. Sign in again.</Notice>;
}
