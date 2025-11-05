import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  experimental: {
    optimizePackageImports: [
      "react",
      "react-dom",
      "next/navigation",
      "next/link"
    ]
  }
};

export default nextConfig;

