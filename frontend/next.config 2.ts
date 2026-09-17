import type { NextConfig } from "next";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  // Proxy the API and rendered videos so the browser only ever talks to one origin.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API}/api/:path*` },
      { source: "/media/:path*", destination: `${API}/media/:path*` },
    ];
  },
};

export default config;
