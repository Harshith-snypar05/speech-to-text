"use client";
import { OpenAuthModal } from "@/components/auth-modal";

// Sign-up is a popup now; this route (used by old links) opens it over the home page.
export default function RegisterPage() {
  return <OpenAuthModal mode="register" />;
}
