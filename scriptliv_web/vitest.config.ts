import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Node environment (no DOM). `@/` mirrors the tsconfig path alias; the pages are compiled with the automatic JSX runtime, as Next does.
export default defineConfig({
  oxc: { jsx: { runtime: "automatic" } },
  resolve: { alias: { "@": fileURLToPath(new URL("./", import.meta.url)) } },
  test: { environment: "node", include: ["tests/**/*.test.{ts,tsx}"] },
});
