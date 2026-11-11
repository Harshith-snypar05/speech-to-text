/**
 * One place that turns anything that can go wrong into a sentence a person can act on.
 * Rule: say what happened in plain words, then what to do next. Never show codes, stack traces or "undefined".
 */

/** Used when the API gave no usable message (proxy error page, dropped connection, unexpected status). */
export function fallbackForStatus(status: number): string {
  if (status === 0) return "We can't reach ScriptLiv. Check your internet connection and try again.";
  if (status === 401) return "Your session has expired. Please sign in again.";
  if (status === 403) return "You don't have permission to do that.";
  if (status === 404) return "We couldn't find that. It may have been moved or deleted.";
  if (status === 408 || status === 504) return "That took too long. Please try again.";
  if (status === 413) return "That is too large to send. Try something smaller.";
  if (status === 429) return "Too many attempts. Wait a few minutes, then try again.";
  if (status >= 500) return "ScriptLiv is having a problem on our side. Nothing was lost; please try again in a moment.";
  return "Something went wrong. Please try again.";
}

/** API error -> message. A server message is kept only when it came with a real code (those are written to be read). */
export function apiMessage(status: number, code: string | undefined, message: string | undefined): string {
  if (code === "invalid_token" && status === 401) return "Your session has expired. Please sign in again.";
  if (code === "unauthenticated") return "Please sign in to continue.";
  if (status >= 502 && status <= 504 && !code) return "ScriptLiv is temporarily unavailable. Please try again in a moment.";
  if (message && code && code !== "error") return message;
  return fallbackForStatus(status);
}

/** Microphone / browser failures from getUserMedia and friends. */
export function micMessage(raw: string | undefined): string {
  const t = (raw ?? "").toLowerCase();
  if (t.includes("notallowed") || t.includes("permission") || t.includes("denied")) return "Microphone access is blocked. Allow the microphone in your browser's address bar, then try again.";
  if (t.includes("notfound") || t.includes("devicesnotfound") || t.includes("requested device")) return "No microphone was found. Plug one in or choose another input, then try again.";
  if (t.includes("notreadable") || t.includes("could not start") || t.includes("in use")) return "Your microphone is busy. Close other apps that use it, then try again.";
  if (t.includes("secure") || t.includes("https")) return "Recording needs a secure (https) connection.";
  return "We couldn't start your microphone. Check it is connected and allowed, then try again.";
}

export interface CloseNotice { title: string; body: string; tone: "error" | "warning" | "info"; link?: { href: string; label: string } }

/** Live connection closed by the relay: `code` is the WebSocket close code, `reason` its reason text. */
export function closeNotice(code: number | string, reason = ""): CloseNotice {
  const c = String(code);
  const plans = { href: "/app/plans", label: "See plans and add-ons" };
  if (c === "4403") return { tone: "warning", title: "Verify your email to record", body: "Transcription turns on once your email address is verified. Open the link we emailed you, or resend it from Settings.", link: { href: "/app/settings", label: "Open Settings" } };
  if (c === "4409") return { tone: "info", title: "Recording continued on another connection", body: "A newer connection took over this session, for example after a network change. Your transcript so far is saved." };
  if (c === "4402") {
    if (reason === "session_limit") return { tone: "warning", title: "Free sessions are limited to 30 minutes", body: "This session reached the 30-minute limit and was stopped. Your transcript is saved. Start a new session to keep going, or upgrade to Pro for longer sessions.", link: plans };
    if (reason === "allowance_reserved") return { tone: "warning", title: "Your minutes are in use by another recording", body: "Another recording on your account is using your remaining minutes. Stop it, then start again." };
    if (reason === "payment_required") return { tone: "error", title: "Payment required", body: "Your last payment failed, so paid minutes and add-ons are paused. Update your payment method or retry the payment.", link: plans };
    if (reason === "personal_limit") return { tone: "error", title: "You reached your personal limit", body: "Recording stopped at the limit you set in Settings. Raise it there to continue.", link: { href: "/app/settings", label: "Open Settings" } };
    return { tone: "error", title: "You are out of minutes", body: "Recording stopped when your minutes ran out. Nothing was recorded past your balance. Add minutes or upgrade to continue.", link: plans };
  }
  if (c === "4400") return { tone: "error", title: "Recording could not start", body: "The connection was set up incorrectly. Refresh the page and try again." };
  if (c === "1013") return { tone: "warning", title: "We're at capacity right now", body: "Too many people are transcribing at the moment. Wait a minute and try again." };
  if (reason === "billing_unavailable") return { tone: "error", title: "We couldn't check your minutes", body: "ScriptLiv couldn't reach the account service. Nothing was recorded. Please try again in a moment." };
  if (reason === "session_taken") return { tone: "error", title: "That session belongs to another account", body: "Start a new session instead." };
  return { tone: "error", title: "Your sign-in may have expired", body: "The connection was refused. Sign in again, then try recording.", link: { href: "/login", label: "Sign in" } };
}
