import type { NextConfig } from "next";

const labApiBaseUrl = process.env.LAB_API_BASE_URL ?? "http://127.0.0.1:8000";
const staticExport = process.env.NEXT_OUTPUT_MODE === "export";

const nextConfig: NextConfig = staticExport
  ? { output: "export" }
  : {
      allowedDevOrigins: ["127.0.0.1"],
      async rewrites() {
        return [
          { source: "/health", destination: `${labApiBaseUrl}/health` },
          { source: "/api/:path*", destination: `${labApiBaseUrl}/api/:path*` },
        ];
      },
    };

export default nextConfig;
