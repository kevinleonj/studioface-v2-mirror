import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  output: "export",                 // static files -> Firebase Hosting
  images: { unoptimized: true },    // no image optimisation server in a static export
  trailingSlash: true,
};
export default nextConfig;
