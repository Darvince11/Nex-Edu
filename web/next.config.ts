import type { NextConfig } from "next";

const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const securityHeaders = [
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  },
];

const config: NextConfig = {
  // Browser tests build into their own folder, pointed at their own API (web/e2e/servers).
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // The API is served from this origin, so session cookies stay first-party,
  // CSRF works without CORS, and the CSP can restrict connect-src to 'self'.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*/` },
      { source: "/_allauth/:path*", destination: `${backend}/_allauth/:path*` },
    ];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default config;
