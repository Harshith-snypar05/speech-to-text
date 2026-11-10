import { LiveTranscriptParser } from "./transcript-parser";

/**
 * Live transcription client: browser mic -> AudioWorklet (16 kHz mono PCM16) -> relay WebSocket.
 *
 * "live" is only reported once BOTH the microphone is capturing AND the socket is open; the UI must never show a
 * recording state before that. On an unexpected drop the SAME session id is reused (no new session) with capped
 * exponential backoff; the mic keeps capturing, audio produced during the gap is not buffered and is counted in
 * `lostAudioMs` so the UI can say so honestly.
 */
export type LiveState =
  | "idle" | "requesting-mic" | "mic-denied" | "connecting" | "backend-unavailable"
  | "live" | "reconnecting" | "connection-failed" | "unauthorized" | "stopping" | "stopped" | "error";

export interface LiveOptions {
  wsUrl: string;
  sessionId: string;
  token: string;
  micDeviceId?: string;
  maxRetries?: number;
  connectTimeoutMs?: number;
  workletUrl?: string;
}

export interface LiveHandlers {
  onState: (s: LiveState, detail?: string) => void;
  onPartial: (text: string) => void;
  onFinal: (text: string) => void;
  /** optional: a refined version of an earlier final (match it by `original`) */
  onRefine?: (original: string, refined: string) => void;
  /** real RMS level 0..1 of the most recent ~100 ms of captured audio */
  onLevel: (rms: number) => void;
}

const TERMINAL_CLOSE = new Set([4400, 4401, 4402, 4403, 4409]);

export class LiveClient {
  private ws: WebSocket | null = null;
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  private parser = new LiveTranscriptParser();
  private gen = 0;
  private userStopped = false;
  private retries = 0;
  private partial = "";
  private gapStart: number | null = null;
  state: LiveState = "idle";
  lostAudioMs = 0;
  reconnects = 0;

  constructor(private o: LiveOptions, private h: LiveHandlers) {}

  private set(s: LiveState, detail?: string) {
    this.state = s;
    this.h.onState(s, detail);
  }

  async start() {
    if (this.state !== "idle" && this.state !== "stopped" && this.state !== "mic-denied" && this.state !== "backend-unavailable" && this.state !== "error") return;
    this.userStopped = false;
    this.retries = 0;
    this.lostAudioMs = 0;
    this.reconnects = 0;
    this.parser.reset();
    const gen = ++this.gen;

    this.set("requesting-mic");
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, deviceId: this.o.micDeviceId ? { exact: this.o.micDeviceId } : undefined },
      });
    } catch (e) {
      this.set("mic-denied", e instanceof Error ? e.message : String(e));
      return;
    }
    if (gen !== this.gen) return this.releaseMic();

    this.set("connecting");
    try {
      await this.openSocket(gen);
    } catch {
      this.releaseMic();
      if (gen === this.gen) this.set("backend-unavailable");
      return;
    }
    if (gen !== this.gen) return this.releaseMic();

    try {
      await this.startCapture(gen);
    } catch (e) {
      this.closeSocket();
      this.releaseMic();
      this.set("error", e instanceof Error ? e.message : String(e));
      return;
    }
    if (gen === this.gen) this.set("live");
  }

  private url() {
    const u = new URL(this.o.wsUrl);
    u.searchParams.set("role", "speaker");
    u.searchParams.set("session", this.o.sessionId);
    u.searchParams.set("token", this.o.token);
    return u.toString();
  }

  private openSocket(gen: number): Promise<void> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(this.url());
      ws.binaryType = "arraybuffer";
      const timer = setTimeout(() => { ws.close(); reject(new Error("timeout")); }, this.o.connectTimeoutMs ?? 8000);
      ws.onopen = () => {
        clearTimeout(timer);
        if (gen !== this.gen) { ws.close(); return reject(new Error("superseded")); }
        this.ws = ws;
        ws.onmessage = (ev) => this.onMessage(ev);
        ws.onclose = (ev) => this.onClose(gen, ev);
        resolve();
      };
      ws.onerror = () => { /* onclose follows; initial failures surface via reject below */ };
      ws.onclose = (ev) => {
        clearTimeout(timer);
        if (TERMINAL_CLOSE.has(ev.code) && gen === this.gen) this.set("unauthorized", `${ev.code}:${ev.reason || ""}`);
        reject(new Error("closed " + ev.code));
      };
    });
  }

  private async startCapture(gen: number) {
    if (!this.stream) throw new Error("no microphone stream");
    const ctx = new AudioContext();
    this.ctx = ctx;
    await ctx.audioWorklet.addModule(this.o.workletUrl ?? "/pcm-worklet.js");
    if (gen !== this.gen) throw new Error("superseded");
    const src = ctx.createMediaStreamSource(this.stream);
    const node = new AudioWorkletNode(ctx, "pcm-processor", { numberOfInputs: 1, numberOfOutputs: 0, channelCount: 1 });
    node.port.onmessage = (ev: MessageEvent<{ pcm: ArrayBuffer; rms: number }>) => {
      this.h.onLevel(ev.data.rms);
      if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(ev.data.pcm);
      else this.lostAudioMs += 100; // mic still running while the socket is down: that audio is gone
    };
    src.connect(node);
    this.node = node;
    if (ctx.state === "suspended") await ctx.resume();
  }

  private onMessage(ev: MessageEvent) {
    if (typeof ev.data !== "string") return;
    this.parser.parse(ev.data, {
      onFinal: (t) => { this.partial = ""; this.h.onFinal(t); },
      onPartial: (t) => { this.partial = t; this.h.onPartial(t); },
      onEnded: () => { /* the relay never sends "ended" to the speaker itself */ },
      onRefine: (o, r) => this.h.onRefine?.(o, r),
    });
  }

  private onClose(gen: number, ev: CloseEvent) {
    this.ws = null;
    if (this.userStopped || gen !== this.gen) return;
    if (TERMINAL_CLOSE.has(ev.code)) {
      this.set("unauthorized", `${ev.code}:${ev.reason || ""}`);
      this.teardownCapture();
      return;
    }
    this.gapStart = Date.now();
    void this.retryLoop(gen);
  }

  private async retryLoop(gen: number) {
    while (!this.userStopped && gen === this.gen) {
      if (this.retries >= (this.o.maxRetries ?? 5)) {
        this.set("connection-failed");
        return;
      }
      this.retries++;
      this.set("reconnecting", `attempt ${this.retries}`);
      await new Promise((r) => setTimeout(r, Math.min(500 * 2 ** (this.retries - 1), 10000)));
      if (this.userStopped || gen !== this.gen) return;
      try {
        await this.openSocket(gen);
        this.retries = 0;
        this.reconnects++;
        this.parser.reset(); // a partial from before the drop will never get its final
        this.partial = "";
        this.h.onPartial("");
        this.gapStart = null;
        this.set("live");
        return;
      } catch {
        if (this.state === "unauthorized") { this.teardownCapture(); return; }
      }
    }
  }

  /** Manual retry after "connection-failed". Reuses the same session id. */
  retry() {
    if (this.state !== "connection-failed") return;
    this.retries = 0;
    void this.retryLoop(this.gen);
  }

  async stop() {
    if (this.state === "idle" || this.state === "stopped" || this.state === "stopping") return;
    this.userStopped = true;
    this.gen++;
    this.set("stopping");
    this.teardownCapture();
    // Give the relay's pause-triggered flush a moment to deliver the last utterance's final.
    if (this.ws && this.partial) {
      await new Promise<void>((resolve) => {
        const t = setTimeout(resolve, 2000);
        const poll = setInterval(() => { if (!this.partial) { clearTimeout(t); clearInterval(poll); resolve(); } }, 100);
        setTimeout(() => clearInterval(poll), 2100);
      });
    }
    this.closeSocket();
    this.set("stopped");
  }

  private closeSocket() {
    try { this.ws?.close(1000); } catch { /* already closed */ }
    this.ws = null;
  }

  private releaseMic() {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
  }

  private teardownCapture() {
    try { this.node?.disconnect(); } catch { /* ignore */ }
    this.node = null;
    void this.ctx?.close().catch(() => undefined);
    this.ctx = null;
    this.releaseMic();
  }
}

export function newSessionId(): string {
  const a = "abcdefghijklmnopqrstuvwxyz0123456789";
  const r = crypto.getRandomValues(new Uint8Array(12));
  return "sl-" + Array.from(r, (b) => a[b % a.length]).join("");
}
