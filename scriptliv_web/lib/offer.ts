"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export interface Offer { active: boolean; until: number | null; minutes: number | null }

let cached: Promise<Offer> | null = null;
function load(): Promise<Offer> {
  cached ??= api.plans()
    .then((p) => ({ active: !!p.promo_active, until: p.promo_until ?? null, minutes: p.promo_allowance_minutes ?? null }))
    .catch(() => { cached = null; return { active: false, until: null, minutes: null }; });
  return cached;
}

/** Inaugural offer state from the public /v1/plans. null until known. While `active`, plans and prices are hidden. */
export function useOffer(): Offer | null {
  const [offer, setOffer] = useState<Offer | null>(null);
  useEffect(() => { let on = true; void load().then((o) => { if (on) setOffer(o); }); return () => { on = false; }; }, []);
  return offer;
}
