import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // FastAPI serves the built site as static files, so there is no Next.js server.
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
