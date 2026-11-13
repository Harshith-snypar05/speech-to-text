"use client";
import { useState } from "react";
import type { AdminAnalytics, AdminSessionItem, AdminUserItem } from "@/lib/types";
import { cn } from "@/lib/utils";

interface AdminChartsProps {
  analytics: AdminAnalytics;
  sessions: AdminSessionItem[];
  users?: AdminUserItem[];
}

export function AdminCharts({ analytics, sessions }: AdminChartsProps) {
  const [hoveredDay, setHoveredDay] = useState<{ day: string; date: string; minutes: number; count: number } | null>(null);

  // Compute last 7 days transcription activity from sessions
  const last7Days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (6 - i));
    const dayLabel = d.toLocaleDateString(undefined, { weekday: "short" });
    const dateStr = d.toISOString().split("T")[0];

    // Find sessions that started on this date
    const daySessions = sessions.filter((s) => {
      if (!s.started_at) return false;
      const sDate = new Date(s.started_at * 1000).toISOString().split("T")[0];
      return sDate === dateStr;
    });

    const totalSecs = daySessions.reduce((acc, curr) => acc + (curr.duration_seconds || 0), 0);
    const totalMinutes = Math.round(totalSecs / 60);

    return {
      day: dayLabel,
      date: dateStr,
      minutes: totalMinutes,
      count: daySessions.length,
    };
  });

  const maxMinutes = Math.max(1, ...last7Days.map((d) => d.minutes));

  // Compute session duration buckets
  const durationBuckets = [
    { label: "< 2 min", count: 0, color: "bg-emerald-500" },
    { label: "2–10 min", count: 0, color: "bg-primary" },
    { label: "10–30 min", count: 0, color: "bg-violet" },
    { label: "30+ min", count: 0, color: "bg-amber-500" },
  ];

  sessions.forEach((s) => {
    const mins = (s.duration_seconds || 0) / 60;
    if (mins < 2) durationBuckets[0].count++;
    else if (mins < 10) durationBuckets[1].count++;
    else if (mins < 30) durationBuckets[2].count++;
    else durationBuckets[3].count++;
  });

  const totalBucketSessions = Math.max(1, sessions.length);

  // User distribution calculation for Donut Chart
  const totalUsers = Math.max(1, analytics.users.total);
  const verifiedPct = Math.round((analytics.users.verified / totalUsers) * 100);
  const unverifiedPct = Math.round(
    ((analytics.users.total - analytics.users.verified) / totalUsers) * 100
  );
  const disabledPct = Math.round((analytics.users.disabled / totalUsers) * 100);

  // Pro vs Free calculation
  const proPct = Math.round((analytics.subscriptions.pro / totalUsers) * 100);
  const freePct = 100 - proPct;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* 1. 7-Day Transcription Volume Bar Chart */}
      <div className="rounded-2xl border border-line bg-surface p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-ink">Daily Transcription Activity</h3>
            <p className="text-xs text-ink-2">Minutes recorded across the last 7 days</p>
          </div>
          <div className="text-right">
            <span className="text-sm font-bold text-primary">
              {hoveredDay ? `${hoveredDay.minutes} min` : `${Math.round(analytics.sessions.total_seconds / 60)} min total`}
            </span>
            <div className="text-[10px] text-ink-3">
              {hoveredDay ? `${hoveredDay.count} sessions on ${hoveredDay.day}` : "hover for details"}
            </div>
          </div>
        </div>

        {/* SVG & HTML Bar Chart */}
        <div className="pt-4 pb-2">
          <div className="h-44 flex items-end justify-between gap-2 sm:gap-4 px-2 border-b border-line">
            {last7Days.map((d) => {
              const heightPct = Math.max(8, Math.round((d.minutes / maxMinutes) * 100));
              const isHovered = hoveredDay?.date === d.date;

              return (
                <div
                  key={d.date}
                  className="flex-1 flex flex-col items-center h-full justify-end group cursor-pointer"
                  onMouseEnter={() => setHoveredDay(d)}
                  onMouseLeave={() => setHoveredDay(null)}
                >
                  <div className="w-full max-w-[42px] relative flex flex-col items-center justify-end h-full">
                    {/* Tooltip badge */}
                    {isHovered && (
                      <div className="absolute -top-9 z-10 whitespace-nowrap rounded-md bg-ink px-2 py-0.5 text-[10px] font-semibold text-surface shadow-md">
                        {d.minutes} min ({d.count} sess)
                      </div>
                    )}
                    {/* Bar with gradient */}
                    <div
                      style={{ height: `${heightPct}%` }}
                      className={cn(
                        "w-full rounded-t-lg transition-all duration-200",
                        isHovered
                          ? "bg-gradient-to-t from-primary to-violet shadow-lg shadow-primary/30"
                          : d.minutes > 0
                          ? "bg-primary/80 hover:bg-primary"
                          : "bg-surface-alt/70"
                      )}
                    />
                  </div>
                  <span
                    className={cn(
                      "mt-2 text-[11px] font-medium transition-colors",
                      isHovered ? "text-primary font-bold" : "text-ink-2"
                    )}
                  >
                    {d.day}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* 2. User Accounts & Plan Distribution */}
      <div className="rounded-2xl border border-line bg-surface p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-ink">User & Subscription Breakdown</h3>
            <p className="text-xs text-ink-2">Distribution of account tiers and verification</p>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-violet/10 text-violet">
            {analytics.users.total} Total Users
          </span>
        </div>

        {/* Subscription Ratio Progress */}
        <div className="space-y-2 pt-1">
          <div className="flex justify-between text-xs font-medium">
            <span className="flex items-center gap-1.5 text-primary">
              <span className="size-2 rounded-full bg-primary" /> Pro Plan ({analytics.subscriptions.pro})
            </span>
            <span className="flex items-center gap-1.5 text-ink-2">
              Free Plan ({analytics.subscriptions.free}) <span className="size-2 rounded-full bg-line" />
            </span>
          </div>

          <div className="h-3.5 w-full rounded-full bg-surface-alt overflow-hidden flex">
            <div
              style={{ width: `${Math.max(5, proPct)}%` }}
              className="h-full bg-gradient-to-r from-violet to-primary transition-all duration-300"
              title={`Pro: ${proPct}%`}
            />
            <div
              style={{ width: `${freePct}%` }}
              className="h-full bg-line transition-all duration-300"
              title={`Free: ${freePct}%`}
            />
          </div>
        </div>

        {/* Account Status Tiles */}
        <div className="grid grid-cols-3 gap-3 pt-2">
          <div className="rounded-xl border border-line/60 bg-surface-alt/30 p-3 text-center">
            <div className="text-xs text-ink-2 font-medium">Verified</div>
            <div className="text-xl font-bold text-success mt-1">{analytics.users.verified}</div>
            <div className="text-[10px] text-ink-3 mt-0.5">{verifiedPct}% of users</div>
          </div>

          <div className="rounded-xl border border-line/60 bg-surface-alt/30 p-3 text-center">
            <div className="text-xs text-ink-2 font-medium">Unverified</div>
            <div className="text-xl font-bold text-warning mt-1">
              {Math.max(0, analytics.users.total - analytics.users.verified)}
            </div>
            <div className="text-[10px] text-ink-3 mt-0.5">{unverifiedPct}% pending</div>
          </div>

          <div className="rounded-xl border border-line/60 bg-surface-alt/30 p-3 text-center">
            <div className="text-xs text-ink-2 font-medium">Disabled</div>
            <div className="text-xl font-bold text-error mt-1">{analytics.users.disabled}</div>
            <div className="text-[10px] text-ink-3 mt-0.5">{disabledPct}% restricted</div>
          </div>
        </div>

        {/* 3. Session Duration Distribution */}
        <div className="pt-2 border-t border-line space-y-2">
          <div className="text-xs font-semibold text-ink-2 uppercase tracking-wider">
            Session Length Distribution
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {durationBuckets.map((b) => {
              const pct = Math.round((b.count / totalBucketSessions) * 100);
              return (
                <div key={b.label} className="rounded-lg border border-line bg-surface-alt/20 p-2 text-center">
                  <div className="flex items-center justify-center gap-1.5 text-xs text-ink-2">
                    <span className={cn("size-2 rounded-full", b.color)} /> {b.label}
                  </div>
                  <div className="text-base font-bold text-ink mt-0.5">{b.count}</div>
                  <div className="text-[10px] text-ink-3">{pct}%</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
