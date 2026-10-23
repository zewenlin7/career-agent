import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Do not put backend URLs or credentials in `env`: Next exposes those at build time.
  poweredByHeader: false,
};
export default nextConfig;
