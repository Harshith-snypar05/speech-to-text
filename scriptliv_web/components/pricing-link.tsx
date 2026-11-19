"use client";
import Link from "next/link";
import { useOffer } from "@/lib/offer";

/** "Pricing" link that disappears while the inaugural offer runs (no plans are shown then). */
export function PricingLink({ className }: { className?: string }) {
  const offer = useOffer();
  if (!offer || offer.active) return null;
  return <Link href="/pricing" className={className}>Pricing</Link>;
}
