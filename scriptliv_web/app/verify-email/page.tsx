"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { AuthShell } from "@/components/auth-shell";
import { Button, Notice, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function Verify() {
  const token = useSearchParams().get("token");
  const { refresh, token: session } = useAuth();
  const [state, setState] = useState<"working" | "ok" | "bad">(token ? "working" : "bad");
  const [msg, setMsg] = useState("This link is missing its token.");
  const done = useRef(false);
  const router = useRouter();

  useEffect(() => {
    if (!token || done.current) return;
    done.current = true; // the token is single-use; React strict mode must not spend it twice
    api.verifyEmail(token)
      .then(() => { setState("ok"); if (session) void refresh(); })
      .catch((e) => { setState("bad"); setMsg(e instanceof ApiError ? e.message : "Could not verify. Try again."); });
  }, [token, session, refresh]);

  // verified: send the user back to the sign-in page (verifying never signs anyone in)
  useEffect(() => {
    if (state !== "ok") return;
    const t = setTimeout(() => router.replace("/login"), 2000);
    return () => clearTimeout(t);
  }, [state, router]);

  return (
    <AuthShell title="Confirm your email" footer={<Link href="/login" className="font-medium text-primary">Sign in</Link>}>
      {state === "working" && <div className="flex items-center gap-3 text-sm"><Spinner /> Verifying…</div>}
      {state === "ok" && (
        <div className="space-y-4">
          <Notice tone="success" title="Email confirmed">Your email address is verified. Taking you to sign in…</Notice>
          <Link href="/login" className="block"><Button size="lg" className="w-full">Sign in</Button></Link>
        </div>
      )}
      {state === "bad" && <Notice tone="error" title="Could not confirm your email">{msg} Sign in with your email and password to request a new link.</Notice>}
    </AuthShell>
  );
}

export default function VerifyEmailPage() {
  return <Suspense><Verify /></Suspense>;
}
