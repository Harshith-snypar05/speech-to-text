"use client";
import { Smartphone } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Logo, ThemeToggle } from "@/components/brand";
import { Badge, Card, Copyright, Notice, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { config } from "@/lib/config";
import { fmtTime } from "@/lib/format";
import { LiveTranscriptParser } from "@/lib/transcript-parser";
import type { SharedView } from "@/lib/types";

function resolveViewerWsUrl(): string {
  if (config.wsUrl) return config.wsUrl;
  if (typeof window === "undefined") return "";
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}`;
}

/** Public, read-only transcript. No sign-in; viewers connect to the relay for live transcription. */
export default function SharedPage() {
  const { token } = useParams<{ token: string }>();
  const [v, setV] = useState<SharedView | null>(null);
  const [finals, setFinals] = useState<string[]>([]);
  const [partial, setPartial] = useState("");
  const [isLive, setIsLive] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const scroller = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const isLiveRef = useRef(false);
  isLiveRef.current = isLive;

  // Auto-scroll the inner transcript box whenever finals or partial change
  useEffect(() => {
    scroller.current?.scrollTo({ top: 1e9, behavior: "smooth" });
  }, [finals, partial]);

  // Load session metadata from the API
  useEffect(() => {
    let stop = false;
    let pollTimer: ReturnType<typeof setTimeout>;

    async function loadMeta() {
      try {
        const r = await api.shared(token);
        if (stop) return;
        setV(r);
        setIsLive(r.live);
        setErr(null);

        // If no WebSocket connected yet, seed finals from API
        if (!wsRef.current) {
          setFinals(r.transcript || []);
        }

        // If session is still live, poll periodically as a backup
        if (r.live) {
          pollTimer = setTimeout(loadMeta, 5000);
        }
      } catch (e) {
        if (stop) return;
        if (e instanceof ApiError && e.status === 404) {
          setErr("This link is not available. The owner may have stopped sharing it.");
          return;
        }
        setErr("Connection problem. Retrying…");
        pollTimer = setTimeout(loadMeta, 4000);
      }
    }

    void loadMeta();
    return () => {
      stop = true;
      clearTimeout(pollTimer);
    };
  }, [token]);

  // Connect to the WebSocket relay for real-time live transcription
  useEffect(() => {
    const sessionId = v?.session_id;
    if (!sessionId || !isLive) return;

    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout>;
    const parser = new LiveTranscriptParser();

    function connectWs() {
      if (cancelled || !sessionId) return;
      try {
        const wsBase = resolveViewerWsUrl();
        if (!wsBase) return;
        const u = new URL(wsBase, window.location.href);
        u.searchParams.set("role", "viewer");
        u.searchParams.set("session", sessionId);

        const ws = new WebSocket(u.toString());
        wsRef.current = ws;

        ws.onopen = () => {
          if (cancelled) {
            ws.close();
            return;
          }
          // The relay replays all historical finals upon connection; reset to prevent duplicates
          parser.reset();
          setFinals([]);
          setPartial("");
        };

        ws.onmessage = (ev) => {
          if (typeof ev.data !== "string") return;
          parser.parse(ev.data, {
            onFinal: (t) => {
              setPartial("");
              setFinals((f) => [...f, t]);
            },
            onPartial: (t) => {
              setPartial(t);
            },
            onRefine: (o, r) => {
              setFinals((f) => {
                const i = f.lastIndexOf(o);
                return i < 0 ? f : f.map((x, k) => (k === i ? r : x));
              });
            },
            onEnded: () => {
              setIsLive(false);
              setPartial("");
            },
          });
        };

        ws.onclose = () => {
          wsRef.current = null;
          // Reconnect if session is still reported as live
          if (!cancelled && isLiveRef.current) {
            retryTimer = setTimeout(connectWs, 2000);
          }
        };

        ws.onerror = () => {
          try {
            ws.close();
          } catch {
            /* ignore */
          }
        };
      } catch {
        if (!cancelled && isLiveRef.current) {
          retryTimer = setTimeout(connectWs, 3000);
        }
      }
    }

    connectWs();

    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      if (wsRef.current) {
        try {
          wsRef.current.close(1000);
        } catch {
          /* ignore */
        }
        wsRef.current = null;
      }
    };
  }, [v?.session_id, isLive]);

  return (
    <div className="mx-auto flex h-dvh max-h-dvh w-full max-w-2xl flex-col overflow-hidden px-4 py-3 sm:py-4">
      <header className="flex-shrink-0 mb-3 flex items-center justify-between">
        <Logo className="h-7 w-auto sm:h-8" />
        <ThemeToggle />
      </header>

      {err && (
        <div className="flex-shrink-0 mb-3">
          <Notice tone={v ? "warning" : "error"} title={err} />
        </div>
      )}

      {!v && !err && (
        <div className="flex flex-1 items-center justify-center">
          <Spinner />
        </div>
      )}

      {v && (
        <main className="flex flex-1 min-h-0 flex-col gap-3">
          <div className="flex-shrink-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-lg sm:text-xl font-semibold">{v.title || "Shared transcript"}</h1>
              {isLive ? (
                <Badge tone="success">
                  <span className="size-1.5 animate-pulse rounded-full bg-current" />
                  Live
                </Badge>
              ) : (
                <Badge tone="neutral">Ended</Badge>
              )}
            </div>
            <p className="text-xs text-ink-2">{fmtTime(v.started_at)}</p>
          </div>

          {/* Transcript Box statically fills the remaining device screen height (no dynamic expanding, no page scrolling) */}
          <Card className="flex flex-1 min-h-0 flex-col p-0 overflow-hidden">
            <div className="flex-shrink-0 flex items-center justify-between border-b border-line px-4 sm:px-5 py-2.5 sm:py-3 text-sm font-medium">
              <span>Live transcript</span>
              {isLive ? (
                <span className="flex items-center gap-1.5 text-xs text-success">
                  <span className="size-1.5 animate-pulse rounded-full bg-current" /> Live
                </span>
              ) : (
                <span className="text-xs text-ink-3">Ended</span>
              )}
            </div>
            <div
              ref={scroller}
              className="flex-1 min-h-0 overflow-y-auto px-4 sm:px-5 py-3 sm:py-4"
              aria-live="polite"
            >
              {finals.length === 0 && !partial ? (
                <p className="text-sm text-ink-3">
                  {isLive ? "Waiting for speech… text appears here as the speaker talks." : "Nothing was transcribed in this session."}
                </p>
              ) : (
                <>
                  {finals.map((t, i) => (
                    <p key={i} className="mb-2 leading-relaxed text-ink">
                      {t}
                    </p>
                  ))}
                  {partial && (
                    <p className="italic leading-relaxed text-ink-3" data-testid="partial">
                      {partial}
                    </p>
                  )}
                </>
              )}
            </div>
          </Card>

          <Card className="flex-shrink-0 flex flex-wrap items-center justify-between gap-2 bg-lavender/50 px-3.5 py-2 sm:px-4 sm:py-2.5">
            <div className="flex items-center gap-2.5 text-xs sm:text-sm">
              <Smartphone className="size-4 sm:size-5 text-primary flex-shrink-0" />
              <span>Read this on your phone with the ScriptLiv app.</span>
            </div>
            <div className="flex gap-2 text-xs sm:text-sm font-medium">
              <a href={v.app_links.deep_link} className="rounded-full border border-primary px-3 py-1 text-primary">
                Open in app
              </a>
              {v.app_links.android_store && (
                <a href={v.app_links.android_store} className="rounded-full border border-line px-3 py-1">
                  Google Play
                </a>
              )}
              {v.app_links.ios_store && (
                <a href={v.app_links.ios_store} className="rounded-full border border-line px-3 py-1">
                  App Store
                </a>
              )}
            </div>
          </Card>
        </main>
      )}

      <Copyright className="flex-shrink-0 mt-2 text-center text-xs" />
    </div>
  );
}
