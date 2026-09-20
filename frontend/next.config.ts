import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static files, copied into the API image by the Dockerfile and served by FastAPI
  // at "/" (docs/DECISIONS.md: one Cloud Run service, no separate hosting product).
  output: "export",
  images: { unoptimized: true }, // no image optimisation server in a static export
  trailingSlash: true,
  // Without this Next walks up past the repo and picks a stray package-lock.json out
  // of the home directory, then warns on every build.
  turbopack: { root: path.join(__dirname) },
};

export default nextConfig;
