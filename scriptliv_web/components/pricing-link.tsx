"use client";
import Link from "next/link";
import { SHOW_SUBSCRIPTIONS } from "@/lib/features";
import { useOffer } from "@/lib/offer";

/** "Pricing" link. Hidden unless subscriptions are switched on, and while the inaugural offer runs. */
export function PricingLink({ className }: { className?: string }) {
  const offer = useOffer();
  if (!SHOW_SUBSCRIPTIONS || !offer || offer.active) return null;
  return <Link href="/pricing" className={className}>Pricing</Link>;
}
