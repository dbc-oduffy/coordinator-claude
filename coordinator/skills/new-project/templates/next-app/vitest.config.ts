import { defineConfig } from "vitest/config";
import { resolve } from "node:path";

export default defineConfig({
  test: {
    environment: "node",
    include: ["test/**/*.test.ts"],
  },
  resolve: {
    alias: {
      // Mirror tsconfig `@/*` path mapping so test imports using `@/` resolve correctly.
      "@": resolve(import.meta.dirname, "./src"),
    },
  },
});
