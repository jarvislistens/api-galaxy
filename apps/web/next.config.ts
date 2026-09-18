import type { NextConfig } from "next";

const apiOrigin = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8099";

const config: NextConfig = {
  reactStrictMode: true,
  // The browser talks to /api/* on its own origin and Next proxies to the Python
  // backend. That keeps CORS out of the picture entirely and means the app works
  // unchanged whether the backend is on localhost or behind a tunnel.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
  },
  eslint: { ignoreDuringBuilds: false },
  typescript: { ignoreBuildErrors: false },
};

export default config;
