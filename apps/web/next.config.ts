import type { NextConfig } from "next";

const securityHeaders = [
  { key: "X-DNS-Prefetch-Control", value: "on" },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(self), microphone=(self), geolocation=(self)",
  },
];

const nextConfig: NextConfig = {
  transpilePackages: ["@ced/types", "@ced/ui"],
  experimental: {
    optimizePackageImports: ["lucide-react"],
  },
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
  async redirects() {
    return [
      { source: "/app", destination: "/dashboard", permanent: false },
      { source: "/register", destination: "/signup", permanent: false },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/v1/pdf/download/:fileId",
        destination: "/api/ced/pdf/download/:fileId",
      },
    ];
  },
};

export default nextConfig;
