export const fmtTime = (s: number | null | undefined) =>
  s == null ? "unavailable" : new Date(s * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });

export const fmtBytes = (n: number | null | undefined) => {
  if (n == null) return "unavailable";
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
};

/** 16 kHz mono PCM16 = 32000 bytes/s; only valid for audio recorded by this system. */
export const audioSeconds = (bytes: number) => bytes / 32000;

export const fmtDuration = (s: number | null | undefined) => {
  if (s == null) return "unavailable";
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
};

/** Shows null/undefined as "unavailable" so it is never mistaken for 0. */
export const num = (n: number | null | undefined, unit = "") => (n == null ? "unavailable" : `${n}${unit}`);

export function toCsv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return "";
  const keys = Object.keys(rows[0]);
  const esc = (v: unknown) => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [keys.join(","), ...rows.map((r) => keys.map((k) => esc(r[k])).join(","))].join("\n");
}

export function download(name: string, text: string, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Seconds -> "1h 05m" / "42m 10s" / "30s". */
export const fmtSecs = (s: number | null | undefined) => {
  if (s == null) return "unavailable";
  const t = Math.max(0, Math.floor(s));
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), sec = t % 60;
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : m ? `${m}m ${String(sec).padStart(2, "0")}s` : `${sec}s`;
};
export const fmtMinutes = (s: number | null | undefined) => (s == null ? "unavailable" : `${Math.floor(Math.max(0, s) / 60).toLocaleString()} min`);
export const fmtDate = (s: number | null | undefined) => (s == null ? "unavailable" : new Date(s * 1000).toLocaleDateString(undefined, { dateStyle: "medium" }));
export const fmtMoney = (cents: number, currency = "usd") => new Intl.NumberFormat(undefined, { style: "currency", currency: currency.toUpperCase() }).format(cents / 100);
