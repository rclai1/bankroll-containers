import type { NextConfig } from "next";

const apiOrigin =
  process.env.BACKEND_URL ??
  (process.env.NODE_ENV === "production"
    ? "https://bankroll-tau.vercel.app"
    : "http://localhost:8000");

const nextConfig: NextConfig = {
  /* config options here */
  output: "standalone",
  reactCompiler: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/auth/:path*",
        destination: `${apiOrigin}/auth/:path*`,
      },
      {
        source: "/api/blackjack/:path*",
        destination: `${apiOrigin}/:path*`,
      },
      {
        source: "/api/shop/:path*",
        destination: `${apiOrigin}/shop/:path*`,
      },
      {
        source: "/api/shop",
        destination: `${apiOrigin}/shop`,
      },
    ];
  },
};

export default nextConfig;
