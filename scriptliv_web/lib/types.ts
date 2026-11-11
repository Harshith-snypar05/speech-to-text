/** Shapes returned by the ScriptLiv API (/v1/*). Times are unix seconds. */
export interface User { id: string; name: string; email: string; email_verified: boolean; pending_email: string | null; created_at: number }
export interface Delivery { delivery: "email" | "dev" | "unavailable" | "failed"; dev_token?: string }
export interface AuthResult { token: string; user: User }
/** Sign-up never signs in: the account must verify its email first. */
export interface RegisterResult { verification_required: true; user: User; verification?: Delivery }

export interface Settings {
  theme: "light" | "dark" | "system";
  language: string;
  prevent_auto_lock: boolean;
  usage_warnings: boolean;
  warn_percents: number[];
  personal_limit_minutes: number | null;
}
export interface SettingsResponse { settings: Settings; supported_languages: string[] }

export interface Addon { id: string; minutes_total: number; remaining_seconds: number; expires_at: number }
export interface UsageSummary {
  plan: string; plan_name: string; period_start: number; reset_at: number;
  included_minutes: number; included_used_seconds: number; included_remaining_seconds: number; percent_used: number;
  addon_remaining_seconds: number; addon_used_seconds: number; addons: Addon[];
  total_remaining_seconds: number; warnings: { level: number; message: string }[]; cancel_at_period_end: boolean;
}
export interface UsageSession {
  session_id: string; started_at: number; ended_at: number | null;
  metered_seconds: number; included_seconds: number; addon_seconds: number; unbilled_overshoot_seconds: number;
}

export interface PlanInfo { id: string; name: string; included_minutes: number; price_usd_month: number; blurb: string; max_session_minutes?: number | null }
export interface Plans { plans: PlanInfo[]; addon: { minutes: number; price_usd: number; note: string }; purchasing_available: boolean }
export interface Subscription {
  plan: string; plan_name: string; status: string; period_start: number; renews_or_resets_at: number;
  cancel_at_period_end: boolean; access_ends_at: number | null; price_usd_month: number;
  payment?: PaymentIssue | null;
}
export interface PaymentIssue {
  state: string; access_restricted: boolean; message: string; failed_attempts: number; max_retries: number;
  next_attempt_at: number | null; can_retry: boolean; retry_in_seconds: number;
}
export interface PaymentMethod { brand?: string; last4?: string; exp_month?: number; exp_year?: number }
export interface PaymentRow { id: string; created_at: number; description: string; amount_cents: number; currency: string; status: string; receipt_url: string | null }
export interface BillingDetails { name?: string; company?: string; address?: string; country?: string; tax_id?: string }

export interface SessionItem {
  session_id: string; title: string; started_at: number | null; ended_at: number | null;
  sharing: boolean; share_url: string | null; transcript?: string[];
}
export interface SharedView {
  session_id: string; title: string; live: boolean; started_at: number | null; ended_at: number | null; transcript: string[];
  app_links: { deep_link: string; android_store: string | null; ios_store: string | null };
}
