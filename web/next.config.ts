import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: process.env.VERCEL ? undefined : "standalone",  // standalone is for the Docker image; Vercel traces itself
  reactStrictMode: true,
  poweredByHeader: false,
  turbopack: { root: path.resolve(__dirname) },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
};

export default nextConfig;
