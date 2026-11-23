import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import { join, relative } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { canChangeAdminRole, canToggleDisabled, mayLoadAdminData } from "../lib/admin-access";
import { ApiError, api } from "../lib/api";

const ROOT = join(__dirname, "..");
const authState = vi.hoisted(() => ({ value: { token: null as string | null, user: null as unknown, ready: true } }));
const apiCalls = vi.hoisted(() => ({ list: [] as string[] }));

vi.mock("@/lib/auth", () => ({ useAuth: () => authState.value }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: () => {} }) }));
vi.mock("@/lib/api", async (orig) => {
  const real = await orig<typeof import("../lib/api")>();
  const spy = (name: string) => () => {
    apiCalls.list.push(name);
    return new Promise(() => {});
  };
  return { ...real, api: { ...real.api, adminAnalytics: spy("analytics"), adminUsers: spy("users"), adminSessions: spy("sessions"),
    adminUpdateUser: spy("update"), adminDeleteSession: spy("delete") } };
});

function sources(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (["node_modules", ".next", "tests", ".git"].includes(name)) continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) sources(p, out);
    else if (/\.(tsx?|mjs|json|md)$/.test(name) && !/package(-lock)?\.json$|tsbuildinfo/.test(name)) out.push(p);
  }
  return out;
}

describe("/app/admin is gone, /app/control-room is the only admin page", () => {
  it("has no app/admin route directory and has the control-room page", () => {
    expect(existsSync(join(ROOT, "app/(app)/app/admin"))).toBe(false);
    expect(existsSync(join(ROOT, "app/(app)/app/control-room/page.tsx"))).toBe(true);
  });

  it("nothing in the source links to or references /app/admin", () => {
    const hits = sources(ROOT)
      .filter((f) => /\/app\/admin(?![\w-])/.test(readFileSync(f, "utf8")))
      .map((f) => relative(ROOT, f));
    expect(hits).toEqual([]);
  });

  it("the navigation entry points reach /app/control-room", () => {
    for (const f of ["app/(app)/layout.tsx", "components/profile-menu.tsx"]) {
      expect(readFileSync(join(ROOT, f), "utf8")).toContain("/app/control-room");
    }
  });

  it("the sitemap and robots do not advertise the admin page", () => {
    const listed = sources(ROOT).filter((f) => /(sitemap|robots)\.(ts|tsx)$/.test(f));
    for (const f of listed) expect(readFileSync(f, "utf8")).not.toMatch(/control-room|\/app\/admin/);
  });

  it("everything under /app/* is served noindex", () => {
    const cfg = readFileSync(join(ROOT, "next.config.ts"), "utf8");
    expect(cfg).toMatch(/\/app\/:path\*/);
    expect(cfg).toContain("noindex, nofollow");
  });
});

describe("control-room serves only a static shell", () => {
  beforeEach(() => {
    apiCalls.list.length = 0;
  });
  afterEach(() => vi.restoreAllMocks());

  const render = async () => {
    const mod = await import("../app/(app)/app/control-room/page");
    return renderToStaticMarkup(createElement(mod.default));
  };
  const adminData = /Revoke Admin|Make Admin|Disable Account|Total Users|@example\.com|<table/i;

  it.each([
    ["signed out", { token: null, user: null, ready: true }],
    ["auth still loading", { token: null, user: null, ready: false }],
    ["ordinary signed-in user", { token: "t", user: { email: "ann@example.com", is_admin: false }, ready: true }],
    ["administrator", { token: "t", user: { email: "boss@example.com", is_admin: true }, ready: true }],
  ])("server HTML for %s contains no admin data and makes no admin API call", async (_name, state) => {
    authState.value = state;
    const html = await render();
    expect(html).not.toMatch(adminData);
    expect(apiCalls.list).toEqual([]);
  });

  it("the page module holds no list of administrator emails", () => {
    const src = readFileSync(join(ROOT, "app/(app)/app/control-room/page.tsx"), "utf8");
    expect(src).not.toMatch(/SUPERADMINS/);
    expect(src).not.toMatch(/[\w.+-]+@[\w-]+\.[a-z]{2,}/i);
  });
});

describe("unauthorized users cannot fetch admin data or run admin actions", () => {
  it("mayLoadAdminData is true only for a ready, signed-in administrator", () => {
    const admin = { is_admin: true };
    expect(mayLoadAdminData({ ready: true, token: "t", user: admin })).toBe(true);
    expect(mayLoadAdminData({ ready: false, token: "t", user: admin })).toBe(false);
    expect(mayLoadAdminData({ ready: true, token: null, user: admin })).toBe(false);
    expect(mayLoadAdminData({ ready: true, token: "t", user: { is_admin: false } })).toBe(false);
    expect(mayLoadAdminData({ ready: true, token: "t", user: {} })).toBe(false);
    expect(mayLoadAdminData({ ready: true, token: "t", user: null })).toBe(false);
  });

  it("the page's load effect goes through mayLoadAdminData", () => {
    const src = readFileSync(join(ROOT, "app/(app)/app/control-room/page.tsx"), "utf8");
    expect(src).toMatch(/if \(!mayLoadAdminData\(/);
  });

  describe("the API client sends the session token and surfaces the API's refusal", () => {
    const calls: { url: string; init: RequestInit }[] = [];
    beforeEach(() => {
      calls.length = 0;
      vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
        calls.push({ url: String(url), init });
        return new Response(JSON.stringify({ error: { code: "forbidden", message: "Admin privileges required." } }), {
          status: 403,
          headers: { "content-type": "application/json" },
        });
      });
    });
    afterEach(() => vi.unstubAllGlobals());

    // The mocked module above replaces api; take the real client for this group.
    const real = async () => (await vi.importActual<typeof import("../lib/api")>("../lib/api")).api;

    it("a 403 from list, update and delete is raised as ApiError, never swallowed into data", async () => {
      const a = await real();
      await expect(a.adminUsers("tok")).rejects.toMatchObject({ status: 403 });
      await expect(a.adminAnalytics("tok")).rejects.toBeInstanceOf(Error);
      await expect(a.adminUpdateUser("tok", "u1", { disabled: true })).rejects.toMatchObject({ status: 403 });
      await expect(a.adminDeleteSession("tok", "s1")).rejects.toMatchObject({ status: 403 });
      expect(calls.map((c) => c.init.method ?? "GET")).toEqual(["GET", "GET", "PATCH", "DELETE"]);
      for (const c of calls) expect(JSON.stringify(c.init.headers)).toContain("Bearer tok");
    });

    it("exports are the real ones", () => {
      expect(ApiError).toBeDefined();
      expect(api).toBeDefined();
    });
  });
});

describe("action buttons follow the backend `protected` field", () => {
  const u = (protectedFlag: boolean, disabled = false) => ({ protected: protectedFlag, disabled });

  it("revoke/make-admin is available only for unprotected accounts", () => {
    expect(canChangeAdminRole(u(false))).toBe(true);
    expect(canChangeAdminRole(u(true))).toBe(false);
    expect(canChangeAdminRole(u(true, true))).toBe(false);
  });

  it("disable is blocked for protected accounts, enable of a disabled protected account is allowed", () => {
    expect(canToggleDisabled(u(false))).toBe(true);
    expect(canToggleDisabled(u(false, true))).toBe(true);
    expect(canToggleDisabled(u(true))).toBe(false);
    expect(canToggleDisabled(u(true, true))).toBe(true);
  });

  it("the page wires both buttons to those helpers and to nothing else (no hardcoded identities)", () => {
    const src = readFileSync(join(ROOT, "app/(app)/app/control-room/page.tsx"), "utf8");
    expect(src).toMatch(/disabled=\{savingUser \|\| !canChangeAdminRole\(selectedUser\)\}/);
    expect(src).toMatch(/disabled=\{savingUser \|\| !canToggleDisabled\(selectedUser\)\}/);
    expect(src).not.toMatch(/selectedUser\.email\s*(===|!==|==|!=)/);
  });

  it("the shared type carries the API-computed flag", () => {
    expect(readFileSync(join(ROOT, "lib/types.ts"), "utf8")).toMatch(/protected: boolean;/);
  });
});
