import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    // Pins the workspace root so Next/Turbopack doesn't infer a parent directory when
    // sibling lockfiles exist.
    root: import.meta.dirname,
  },
};

export default nextConfig;
