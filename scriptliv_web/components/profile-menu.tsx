"use client";
import { CreditCard, LogOut, Settings } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import type { User } from "@/lib/types";
import { cn } from "@/lib/utils";

const initial = (u: User) => ((u.name || u.email || "?").trim()[0] ?? "?").toUpperCase();

/** Round avatar in the navbar. Opens a menu with Settings, My plans and Log out. Email lives here, not in the bar. */
export function ProfileMenu({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);

  const item = "flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm text-ink transition-colors hover:bg-violet/10 hover:text-violet";

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-label="Account menu"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "grid size-10 place-items-center rounded-full bg-gradient-to-br from-violet to-primary text-sm font-semibold text-white transition-shadow hover:shadow-[0_0_0_3px] hover:shadow-violet/30",
          open && "shadow-[0_0_0_3px] shadow-violet/40",
        )}
      >
        {initial(user)}
      </button>
      {open && (
        <div id={menuId} role="menu" className="absolute right-0 top-[calc(100%+10px)] z-40 w-64 rounded-2xl border border-line bg-surface p-2 shadow-xl backdrop-blur-md">
          <div className="px-3 pb-2 pt-1.5">
            {user.name && <div className="truncate text-sm font-semibold">{user.name}</div>}
            <div className="truncate text-xs text-ink-2" title={user.email}>{user.email}</div>
          </div>
          <div className="my-1 h-px bg-line" />
          <Link role="menuitem" href="/app/settings" onClick={() => setOpen(false)} className={item}><Settings className="size-4" aria-hidden /> Settings</Link>
          <Link role="menuitem" href="/app/plans" onClick={() => setOpen(false)} className={item}><CreditCard className="size-4" aria-hidden /> My plans</Link>
          <div className="my-1 h-px bg-line" />
          <button type="button" role="menuitem" onClick={() => { setOpen(false); onSignOut(); }} className={item}><LogOut className="size-4" aria-hidden /> Log out</button>
        </div>
      )}
    </div>
  );
}
