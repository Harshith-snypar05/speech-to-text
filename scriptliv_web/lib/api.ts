import { config } from "./config";
import { apiMessage } from "./friendly-errors";
import type {
  AuthResult, BillingDetails, RegisterResult, Delivery, PaymentMethod, PaymentRow, Plans, SessionItem, SettingsResponse, SharedView,
  Subscription, UsageSession, UsageSummary, User,
} from "./types";

/**
 * ScriptLiv API client. Same-origin by default: Next rewrites /sl/* to the API (SL_BACKEND_HTTP), so the browser needs
 * no CORS. Errors come back as {error:{code,message}}; `code` is stable, `message` is safe to show.
 */
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

const base = () => (config.slApiBase || "/sl").replace(/\/$/, "");

async function request<T>(path: string, opts: { method?: string; token?: string | null; body?: unknown } = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(base() + path, {
      method: opts.method ?? "GET",
      headers: { ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}), ...(opts.token ? { Authorization: `Bearer ${opts.token}` } : {}) },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "network", apiMessage(0, "network", undefined));
  }
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  try { data = await res.json(); } catch { /* non-JSON body */ }
  if (!res.ok) {
    const e = (data as { error?: { code?: string; message?: string } } | null)?.error;
    throw new ApiError(res.status, e?.code ?? "error", apiMessage(res.status, e?.code, e?.message));
  }
  return data as T;
}

const sid = (id: string) => encodeURIComponent(id);

export const api = {
  register: (name: string, email: string, password: string) => request<RegisterResult>("/v1/auth/register", { method: "POST", body: { name, email, password } }),
  login: (email: string, password: string) => request<AuthResult>("/v1/auth/login", { method: "POST", body: { email, password } }),
  resendVerificationPublic: (email: string) => request<{ status: string; message: string; dev_token?: string }>("/v1/auth/resend-verification", { method: "POST", body: { email } }),
  forgotPassword: (email: string) => request<{ status: string; message: string }>("/v1/auth/forgot-password", { method: "POST", body: { email } }),
  resetPassword: (token: string, new_password: string) => request<{ status: string; message: string }>("/v1/auth/reset-password", { method: "POST", body: { token, new_password } }),
  verifyEmail: (token: string) => request<{ user: User }>("/v1/auth/verify-email", { method: "POST", body: { token } }),
  me: (t: string) => request<{ user: User }>("/v1/me", { token: t }).then((r) => r.user),
  updateName: (t: string, name: string) => request<{ user: User }>("/v1/me", { method: "PATCH", token: t, body: { name } }).then((r) => r.user),
  changeEmail: (t: string, new_email: string, password: string) =>
    request<{ pending_email: string } & Delivery>("/v1/me/email", { method: "POST", token: t, body: { new_email, password } }),
  resendVerification: (t: string) => request<Delivery>("/v1/me/email/resend", { method: "POST", token: t }),
  changePassword: (t: string, current_password: string, new_password: string) =>
    request<{ token: string }>("/v1/me/password", { method: "POST", token: t, body: { current_password, new_password } }),

  settings: (t: string) => request<SettingsResponse>("/v1/settings", { token: t }),
  saveSettings: (t: string, patch: Partial<SettingsResponse["settings"]>) => request<SettingsResponse>("/v1/settings", { method: "PUT", token: t, body: patch }),

  usage: (t: string) => request<UsageSummary>("/v1/usage", { token: t }),
  usageSessions: (t: string) => request<{ sessions: UsageSession[] }>("/v1/usage/sessions", { token: t }).then((r) => r.sessions),

  plans: () => request<Plans>("/v1/plans"),
  subscription: (t: string) => request<{ subscription: Subscription; purchasing_available: boolean }>("/v1/subscription", { token: t }),
  checkout: (t: string, kind: "pro" | "addon") => request<{ url: string }>("/v1/billing/checkout", { method: "POST", token: t, body: { kind } }),
  retryPayment: (t: string) => request<{ result: string; subscription: Subscription }>("/v1/billing/retry-payment", { method: "POST", token: t }),
  portal: (t: string) => request<{ url: string }>("/v1/billing/portal", { method: "POST", token: t }),
  cancelPlan: (t: string) => request<{ subscription: Subscription }>("/v1/subscription/cancel", { method: "POST", token: t }).then((r) => r.subscription),
  resumePlan: (t: string) => request<{ subscription: Subscription }>("/v1/subscription/resume", { method: "POST", token: t }).then((r) => r.subscription),
  paymentMethod: (t: string) => request<{ available: boolean; payment_method: PaymentMethod | null }>("/v1/billing/payment-method", { token: t }),
  payments: (t: string) => request<{ available: boolean; payments: PaymentRow[] }>("/v1/billing/payments", { token: t }),
  billingDetails: (t: string) => request<{ details: BillingDetails }>("/v1/billing/details", { token: t }).then((r) => r.details),
  saveBillingDetails: (t: string, d: BillingDetails) => request<{ details: BillingDetails }>("/v1/billing/details", { method: "PUT", token: t, body: d }).then((r) => r.details),

  sessions: (t: string) => request<{ sessions: SessionItem[] }>("/v1/sessions", { token: t }).then((r) => r.sessions),
  session: (t: string, id: string) => request<SessionItem>(`/v1/sessions/${sid(id)}`, { token: t }),
  renameSession: (t: string, id: string, title: string) => request<SessionItem>(`/v1/sessions/${sid(id)}`, { method: "PATCH", token: t, body: { title } }),
  deleteSession: (t: string, id: string) => request<void>(`/v1/sessions/${sid(id)}`, { method: "DELETE", token: t }),
  share: (t: string, id: string) => request<SessionItem>(`/v1/sessions/${sid(id)}/share`, { method: "POST", token: t }),
  unshare: (t: string, id: string) => request<SessionItem>(`/v1/sessions/${sid(id)}/share`, { method: "DELETE", token: t }),
  shared: (token: string) => request<SharedView>(`/v1/shared/${encodeURIComponent(token)}`),
};
