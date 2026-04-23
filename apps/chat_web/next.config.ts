import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "export",
  basePath: "/app",
  trailingSlash: true,
};

export default nextConfig;
