import type { NextConfig } from "next";

const apiTarget = (process.env.STUDY_BUDDY_API_URL ?? "http://127.0.0.1:8010").replace(/\/$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  // The dashboard is intentionally used from other devices on this LAN.
  // Next 16 otherwise blocks its dev client/HMR and leaves the rendered page
  // unhydrated, so buttons and upload handlers appear but never run.
  // Opened from other devices on this LAN. The Mac's IP is DHCP-assigned and
  // drifts, so allow the whole current subnet (plus the explicit IP as a
  // belt-and-braces fallback). Update these if the network changes.
  allowedDevOrigins: ["localhost", "127.0.0.1", "10.0.2.2", "10.50.75.40", "10.50.75.*"],
  experimental: {
    proxyClientMaxBodySize: "1000mb",
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiTarget}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
