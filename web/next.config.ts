import type { NextConfig } from "next";

// Static export: the Jarvis Python process serves web/out/ on 127.0.0.1:3003, so there is no Node at runtime.
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
