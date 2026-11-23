"use client";
import {
  Activity,
  Clock,
  CreditCard,
  ExternalLink,
  Mic,
  PlusCircle,
  Radio,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserCheck,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminCharts } from "@/components/admin-charts";
import { Badge, Button, Card, Notice, PaginationControls, Spinner, inputCls } from "@/components/ui";
import { canChangeAdminRole, canToggleDisabled, mayLoadAdminData } from "@/lib/admin-access";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDuration, fmtTime } from "@/lib/format";
import type { AdminAnalytics, AdminSessionItem, AdminUserItem } from "@/lib/types";
import { cn } from "@/lib/utils";

type Tab = "overview" | "users" | "sessions";

export default function AdminPage() {
  const { token, user, ready } = useAuth();
  const router = useRouter();

  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [analytics, setAnalytics] = useState<AdminAnalytics | null>(null);
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [sessions, setSessions] = useState<AdminSessionItem[]>([]);
  const [search, setSearch] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Pagination states (Options: 10, 20, 30, 40, 50)
  const [userPage, setUserPage] = useState(1);
  const [userPageSize, setUserPageSize] = useState(10);
  const [sessionPage, setSessionPage] = useState(1);
  const [sessionPageSize, setSessionPageSize] = useState(10);

  // User Management Modal state
  const [selectedUser, setSelectedUser] = useState<AdminUserItem | null>(null);
  const [savingUser, setSavingUser] = useState(false);
  const [bonusMinutes, setBonusMinutes] = useState<number | "">("");

  // Load all dashboard data
  const loadData = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setErr(null);
    try {
      const [an, us, ss] = await Promise.all([
        api.adminAnalytics(token),
        api.adminUsers(token),
        api.adminSessions(token, 200),
      ]);
      setAnalytics(an);
      setUsers(us.users || []);
      setSessions(ss.sessions || []);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setErr("Access denied. Admin privileges required.");
      } else {
        setErr(e instanceof Error ? e.message : "Failed to load admin data");
      }
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (ready && token) {
      if (!mayLoadAdminData({ ready, token, user: { is_admin: user?.is_admin } })) {
        setErr("Access denied. Admin privileges required.");
        setLoading(false);
        return;
      }
      void loadData();
    }
  }, [ready, token, user?.is_admin, loadData]);

  // Handle User Privileges & Access Save
  const handleSaveUser = async (patch: {
    is_admin?: boolean;
    disabled?: boolean;
    email_verified?: boolean;
    plan?: string;
    grant_addon_minutes?: number;
  }) => {
    if (!token || !selectedUser) return;
    setSavingUser(true);
    try {
      const updated = await api.adminUpdateUser(token, selectedUser.id, patch);
      setUsers((prev) => prev.map((u) => (u.id === selectedUser.id ? { ...u, ...updated } : u)));
      setSelectedUser((prev) => (prev ? { ...prev, ...updated } : null));
      setSuccessMsg(`Updated settings for ${selectedUser.email}`);
      setTimeout(() => setSuccessMsg(null), 3500);
      setBonusMinutes("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to update user");
    } finally {
      setSavingUser(false);
    }
  };

  // Handle Session Deletion
  const handleDeleteSession = async (sessionId: string) => {
    if (!token || !confirm("Are you sure you want to permanently delete this session and its transcript?")) return;
    try {
      await api.adminDeleteSession(token, sessionId);
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
      setSuccessMsg("Session deleted successfully.");
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to delete session");
    }
  };

  if (!ready || (loading && !analytics)) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Spinner />
      </div>
    );
  }

  if (!user?.is_admin) {
    return (
      <div className="mx-auto max-w-lg py-12">
        <Card className="text-center p-8 space-y-4">
          <div className="mx-auto grid size-12 place-items-center rounded-full bg-error/10 text-error">
            <ShieldAlert className="size-6" />
          </div>
          <h1 className="text-xl font-semibold">Admin Access Required</h1>
          <p className="text-sm text-ink-2">
            Your account ({user?.email}) does not have administrator privileges.
          </p>
          <Button onClick={() => router.push("/app")}>Return to Dashboard</Button>
        </Card>
      </div>
    );
  }

  const filteredUsers = users.filter(
    (u) =>
      u.email.toLowerCase().includes(search.toLowerCase()) ||
      u.name.toLowerCase().includes(search.toLowerCase())
  );

  // Paginated slices
  const paginatedUsers = filteredUsers.slice((userPage - 1) * userPageSize, userPage * userPageSize);
  const paginatedSessions = sessions.slice((sessionPage - 1) * sessionPageSize, sessionPage * sessionPageSize);

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight">Admin Dashboard</h1>
            <Badge tone="primary">
              <ShieldCheck className="size-3.5 mr-1 inline" />
              Full Access
            </Badge>
          </div>
          <p className="text-sm text-ink-2 mt-0.5">
            Signed in as superadmin <span className="font-medium text-ink">{user.email}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadData} disabled={loading}>
            <RefreshCw className={cn("size-3.5 mr-1.5", loading && "animate-spin")} /> Refresh
          </Button>
        </div>
      </div>

      {err && <Notice tone="error" title={err} />}
      {successMsg && <Notice tone="success" title={successMsg} />}

      {/* Navigation Tabs */}
      <div className="flex border-b border-line gap-2 text-sm font-medium">
        <button
          onClick={() => setTab("overview")}
          className={cn(
            "flex items-center gap-2 px-4 py-2.5 border-b-2 transition-colors",
            tab === "overview"
              ? "border-primary text-primary font-semibold"
              : "border-transparent text-ink-2 hover:text-ink"
          )}
        >
          <Activity className="size-4" /> Overview & Analytics
        </button>
        <button
          onClick={() => setTab("users")}
          className={cn(
            "flex items-center gap-2 px-4 py-2.5 border-b-2 transition-colors",
            tab === "users"
              ? "border-primary text-primary font-semibold"
              : "border-transparent text-ink-2 hover:text-ink"
          )}
        >
          <Users className="size-4" /> Users & Access Control ({users.length})
        </button>
        <button
          onClick={() => setTab("sessions")}
          className={cn(
            "flex items-center gap-2 px-4 py-2.5 border-b-2 transition-colors",
            tab === "sessions"
              ? "border-primary text-primary font-semibold"
              : "border-transparent text-ink-2 hover:text-ink"
          )}
        >
          <Radio className="size-4" /> Platform Sessions ({sessions.length})
        </button>
      </div>

      {/* TAB 1: OVERVIEW & ANALYTICS */}
      {tab === "overview" && analytics && (
        <div className="space-y-6">
          {/* Key Metric Stat Cards */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card className="p-5 space-y-1">
              <div className="flex items-center justify-between text-ink-2 text-xs font-semibold uppercase tracking-wider">
                Total Users
                <Users className="size-4 text-primary" />
              </div>
              <div className="text-3xl font-bold">{analytics.users.total}</div>
              <div className="flex items-center gap-2 text-xs text-ink-2 pt-1">
                <span className="text-success font-medium">{analytics.users.verified} verified</span> •{" "}
                <span>{analytics.users.admins} admins</span>
              </div>
            </Card>

            <Card className="p-5 space-y-1">
              <div className="flex items-center justify-between text-ink-2 text-xs font-semibold uppercase tracking-wider">
                Total Transcribed
                <Clock className="size-4 text-violet" />
              </div>
              <div className="text-3xl font-bold">{analytics.sessions.total_hours} hrs</div>
              <div className="text-xs text-ink-2 pt-1">
                across <span className="font-medium text-ink">{analytics.sessions.total} sessions</span>
              </div>
            </Card>

            <Card className="p-5 space-y-1">
              <div className="flex items-center justify-between text-ink-2 text-xs font-semibold uppercase tracking-wider">
                Active Pro Plans
                <CreditCard className="size-4 text-indigo-500" />
              </div>
              <div className="text-3xl font-bold">{analytics.subscriptions.pro}</div>
              <div className="text-xs text-ink-2 pt-1">
                {analytics.subscriptions.free} accounts on free tier
              </div>
            </Card>

            <Card className="p-5 space-y-1">
              <div className="flex items-center justify-between text-ink-2 text-xs font-semibold uppercase tracking-wider">
                Platform Revenue
                <span className="text-base font-bold text-emerald-500">₹</span>
              </div>
              <div className="text-3xl font-bold">₹{(analytics.revenue_inr ?? analytics.revenue_usd).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
              <div className="text-xs text-ink-2 pt-1">Total completed billing payments</div>
            </Card>
          </div>

          {/* Data Visualization Graphs (Admin Only) */}
          <AdminCharts analytics={analytics} sessions={sessions} users={users} />

          {/* System Health & Shortcuts */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Card className="p-5 lg:col-span-2 space-y-4">
              <h2 className="text-base font-semibold">Live System Health</h2>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
                <div className="rounded-xl border border-line bg-surface-alt/50 p-4">
                  <div className="text-xs text-ink-2">Live Sessions</div>
                  <div className="text-2xl font-bold mt-1 flex items-center gap-2">
                    {analytics.sessions.live}
                    {analytics.sessions.live > 0 && (
                      <span className="size-2 rounded-full bg-success animate-pulse" />
                    )}
                  </div>
                  <div className="text-xs text-ink-3 mt-1">Currently transcribing</div>
                </div>

                <div className="rounded-xl border border-line bg-surface-alt/50 p-4">
                  <div className="text-xs text-ink-2">Engine Architecture</div>
                  <div className="text-base font-semibold mt-1">Parakeet TDT</div>
                  <div className="text-xs text-success mt-1">Metal GPU Accelerated</div>
                </div>

                <div className="rounded-xl border border-line bg-surface-alt/50 p-4">
                  <div className="text-xs text-ink-2">Disabled Accounts</div>
                  <div className="text-2xl font-bold mt-1">{analytics.users.disabled}</div>
                  <div className="text-xs text-ink-3 mt-1">Access restricted</div>
                </div>
              </div>
            </Card>

            <Card className="p-5 space-y-3">
              <h2 className="text-base font-semibold">Admin Shortcuts</h2>
              <div className="space-y-2">
                <Button
                  variant="outline"
                  className="w-full justify-start text-xs"
                  onClick={() => setTab("users")}
                >
                  <UserCheck className="size-3.5 mr-2" /> Manage User Privileges
                </Button>
                <Button
                  variant="outline"
                  className="w-full justify-start text-xs"
                  onClick={() => setTab("sessions")}
                >
                  <Radio className="size-3.5 mr-2" /> View All Live Broadcasts
                </Button>
                <Link
                  href="/app/record"
                  className="block rounded-lg border border-line px-3 py-2 text-xs hover:bg-surface-alt text-ink"
                >
                  <Mic className="size-3.5 mr-2 inline" /> Open Live Recording Studio
                </Link>
              </div>
            </Card>
          </div>
        </div>
      )}

      {/* TAB 2: USERS & ACCESS CONTROL */}
      {tab === "users" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="relative w-full max-w-sm">
              <Search className="absolute left-3 top-2.5 size-4 text-ink-3" />
              <input
                type="text"
                placeholder="Search by name or email..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setUserPage(1);
                }}
                className={cn(inputCls, "pl-9 mt-0")}
              />
            </div>
            <div className="text-xs text-ink-2">
              {filteredUsers.length} total matching users
            </div>
          </div>

          <Card className="p-0 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line bg-surface-alt/60 text-xs font-semibold text-ink-2 uppercase tracking-wider">
                  <tr>
                    <th className="px-5 py-3">User</th>
                    <th className="px-4 py-3">Plan</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Sessions</th>
                    <th className="px-4 py-3">Transcribed</th>
                    <th className="px-4 py-3">Joined</th>
                    <th className="px-5 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {paginatedUsers.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-5 py-8 text-center text-ink-3">
                        No users found matching &quot;{search}&quot;
                      </td>
                    </tr>
                  ) : (
                    paginatedUsers.map((u) => (
                      <tr key={u.id} className="hover:bg-surface-alt/30 transition-colors">
                        <td className="px-5 py-3.5">
                          <div className="font-medium text-ink">{u.name || "Unnamed"}</div>
                          <div className="text-xs text-ink-2">{u.email}</div>
                        </td>
                        <td className="px-4 py-3.5">
                          <Badge tone={u.plan === "pro" ? "primary" : "neutral"}>
                            {u.plan.toUpperCase()}
                          </Badge>
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="flex flex-wrap gap-1">
                            {u.is_admin && <Badge tone="primary">Admin</Badge>}
                            {u.email_verified ? (
                              <Badge tone="success">Verified</Badge>
                            ) : (
                              <Badge tone="warning">Unverified</Badge>
                            )}
                            {u.disabled && <Badge tone="error">Disabled</Badge>}
                          </div>
                        </td>
                        <td className="px-4 py-3.5 tabular-nums text-ink-2">{u.total_sessions}</td>
                        <td className="px-4 py-3.5 tabular-nums font-medium text-ink">
                          {u.total_minutes} min
                        </td>
                        <td className="px-4 py-3.5 text-xs text-ink-2">
                          {u.created_at ? fmtDate(u.created_at) : "—"}
                        </td>
                        <td className="px-5 py-3.5 text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setSelectedUser(u)}
                          >
                            Manage Access
                          </Button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls for Users (10, 20, 30, 40, 50) */}
            <PaginationControls
              page={userPage}
              pageSize={userPageSize}
              total={filteredUsers.length}
              pageSizeOptions={[10, 20, 30, 40, 50]}
              onPageChange={setUserPage}
              onPageSizeChange={setUserPageSize}
            />
          </Card>
        </div>
      )}

      {/* TAB 3: PLATFORM SESSIONS */}
      {tab === "sessions" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">System-wide Broadcasts & Recordings</h2>
            <div className="text-xs text-ink-2">{sessions.length} total sessions</div>
          </div>

          <Card className="p-0 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line bg-surface-alt/60 text-xs font-semibold text-ink-2 uppercase tracking-wider">
                  <tr>
                    <th className="px-5 py-3">Session & Speaker</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Duration</th>
                    <th className="px-4 py-3">Share Link</th>
                    <th className="px-4 py-3">Started</th>
                    <th className="px-5 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {paginatedSessions.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-5 py-8 text-center text-ink-3">
                        No sessions recorded yet.
                      </td>
                    </tr>
                  ) : (
                    paginatedSessions.map((s) => (
                      <tr key={s.session_id} className="hover:bg-surface-alt/30 transition-colors">
                        <td className="px-5 py-3.5">
                          <div className="font-medium text-ink">{s.title}</div>
                          <div className="text-xs text-ink-3 font-mono">{s.session_id}</div>
                          <div className="text-xs text-ink-2 mt-0.5">{s.owner_email}</div>
                        </td>
                        <td className="px-4 py-3.5">
                          {s.live ? (
                            <Badge tone="success">
                              <span className="size-1.5 animate-pulse rounded-full bg-current mr-1 inline-block" />
                              Live
                            </Badge>
                          ) : (
                            <Badge tone="neutral">Saved</Badge>
                          )}
                        </td>
                        <td className="px-4 py-3.5 tabular-nums text-ink font-medium">
                          {fmtDuration(s.duration_seconds)}
                        </td>
                        <td className="px-4 py-3.5 text-xs">
                          {s.sharing ? (
                            <span className="text-primary font-medium">Public link active</span>
                          ) : (
                            <span className="text-ink-3">Private</span>
                          )}
                        </td>
                        <td className="px-4 py-3.5 text-xs text-ink-2">
                          {fmtTime(s.started_at)}
                        </td>
                        <td className="px-5 py-3.5 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <Link
                              href={`/app/history/${s.session_id}`}
                              className="rounded p-1 text-ink-2 hover:text-primary transition-colors"
                              title="View transcript"
                            >
                              <ExternalLink className="size-4" />
                            </Link>
                            <button
                              onClick={() => handleDeleteSession(s.session_id)}
                              className="rounded p-1 text-ink-2 hover:text-error transition-colors"
                              title="Delete session"
                            >
                              <Trash2 className="size-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls for Sessions (10, 20, 30, 40, 50) */}
            <PaginationControls
              page={sessionPage}
              pageSize={sessionPageSize}
              total={sessions.length}
              pageSizeOptions={[10, 20, 30, 40, 50]}
              onPageChange={setSessionPage}
              onPageSizeChange={setSessionPageSize}
            />
          </Card>
        </div>
      )}

      {/* USER ACCESS MANAGEMENT MODAL */}
      {selectedUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-lg p-6 space-y-5 shadow-2xl animate-in fade-in-50 zoom-in-95">
            <div className="flex items-start justify-between border-b border-line pb-4">
              <div>
                <h3 className="text-lg font-bold">Manage User Access</h3>
                <p className="text-xs text-ink-2 mt-0.5">{selectedUser.email}</p>
              </div>
              <button
                onClick={() => setSelectedUser(null)}
                className="rounded-lg p-1 text-ink-3 hover:text-ink"
              >
                <X className="size-5" />
              </button>
            </div>

            <div className="space-y-4 text-sm">
              {/* Role & Admin Privilege */}
              <div className="flex items-center justify-between rounded-xl border border-line p-3">
                <div>
                  <div className="font-semibold text-ink">Administrator Privileges</div>
                  <div className="text-xs text-ink-2">Grants full control over users & system settings</div>
                </div>
                <Button
                  size="sm"
                  variant={selectedUser.is_admin ? "danger" : "outline"}
                  disabled={savingUser || !canChangeAdminRole(selectedUser)}
                  onClick={() => handleSaveUser({ is_admin: !selectedUser.is_admin })}
                >
                  {selectedUser.is_admin ? "Revoke Admin" : "Make Admin"}
                </Button>
              </div>
              {selectedUser.protected && (
                <p className="text-xs text-ink-2">
                  Protected account: administrators and your own account cannot be demoted or disabled here.
                </p>
              )}

              {/* Plan Switcher */}
              <div className="flex items-center justify-between rounded-xl border border-line p-3">
                <div>
                  <div className="font-semibold text-ink">Subscription Plan</div>
                  <div className="text-xs text-ink-2">
                    Current: <span className="font-medium uppercase">{selectedUser.plan}</span>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant={selectedUser.plan === "free" ? "primary" : "outline"}
                    disabled={savingUser}
                    onClick={() => handleSaveUser({ plan: "free" })}
                  >
                    Free
                  </Button>
                  <Button
                    size="sm"
                    variant={selectedUser.plan === "pro" ? "primary" : "outline"}
                    disabled={savingUser}
                    onClick={() => handleSaveUser({ plan: "pro" })}
                  >
                    Pro
                  </Button>
                </div>
              </div>

              {/* Email Verification */}
              <div className="flex items-center justify-between rounded-xl border border-line p-3">
                <div>
                  <div className="font-semibold text-ink">Email Verification</div>
                  <div className="text-xs text-ink-2">
                    {selectedUser.email_verified ? "Email is verified" : "Account is unverified"}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant={selectedUser.email_verified ? "outline" : "primary"}
                  disabled={savingUser}
                  onClick={() => handleSaveUser({ email_verified: !selectedUser.email_verified })}
                >
                  {selectedUser.email_verified ? "Mark Unverified" : "Force Verify"}
                </Button>
              </div>

              {/* Grant Bonus Minutes */}
              <div className="rounded-xl border border-line p-3 space-y-2">
                <div className="font-semibold text-ink">Grant Bonus Transcription Minutes</div>
                <div className="text-xs text-ink-2">
                  Adds non-expiring transcription minutes directly to the customer&apos;s account.
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="number"
                    min="1"
                    placeholder="e.g. 60"
                    value={bonusMinutes}
                    onChange={(e) => setBonusMinutes(e.target.value ? Number(e.target.value) : "")}
                    className={cn(inputCls, "mt-0 flex-1")}
                  />
                  <Button
                    size="sm"
                    disabled={savingUser || !bonusMinutes || Number(bonusMinutes) <= 0}
                    onClick={() => handleSaveUser({ grant_addon_minutes: Number(bonusMinutes) })}
                  >
                    <PlusCircle className="size-3.5 mr-1" /> Grant
                  </Button>
                </div>
              </div>

              {/* Account Suspension */}
              <div className="flex items-center justify-between rounded-xl border border-error/30 bg-error/5 p-3">
                <div>
                  <div className="font-semibold text-error">Account Access</div>
                  <div className="text-xs text-ink-2">
                    {selectedUser.disabled
                      ? "Account is currently disabled"
                      : "Account has normal access"}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant={selectedUser.disabled ? "outline" : "danger"}
                  disabled={savingUser || !canToggleDisabled(selectedUser)}
                  onClick={() => handleSaveUser({ disabled: !selectedUser.disabled })}
                >
                  {selectedUser.disabled ? "Enable Account" : "Disable Account"}
                </Button>
              </div>
            </div>

            <div className="flex justify-end pt-2 border-t border-line">
              <Button variant="outline" onClick={() => setSelectedUser(null)}>
                Close
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
