import type { AdminUserItem } from "./types";

/**
 * What the control room lets an administrator attempt. These only decide which buttons are enabled: the API is the
 * authority and refuses protected accounts itself (403 protected_account), so this must never be the only check.
 * `protected` is computed by the API (administrators and the signed-in caller); the page holds no list of its own.
 */
type Target = Pick<AdminUserItem, "protected" | "disabled">;

/** Grant or revoke administrator rights. Protected accounts cannot be demoted (and are already administrators). */
export function canChangeAdminRole(u: Target): boolean {
  return !u.protected;
}

/** Disable or re-enable. A protected account cannot be disabled, but one that is already disabled can be re-enabled. */
export function canToggleDisabled(u: Target): boolean {
  return !u.protected || u.disabled;
}

/** Admin data is requested only for a signed-in administrator; everyone else never triggers an admin API call. */
export function mayLoadAdminData(s: { ready: boolean; token: string | null; user: { is_admin?: boolean } | null }): boolean {
  return s.ready && !!s.token && !!s.user?.is_admin;
}
