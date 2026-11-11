"use client";
import { OpenAuthModal } from "@/components/auth-modal";

// Sign-in is a popup now; this route (used by old links and redirects) opens it over the home page.
export default function LoginPage() {
  return <OpenAuthModal mode="login" />;
}
