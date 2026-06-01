import type { NextConfig } from "next";

const isTauri = process.env.TAURI_ENV_PLATFORM !== undefined;
const isDev = process.env.NODE_ENV === "development";

const nextConfig: NextConfig = {
  ...(isTauri ? { output: "export" } : {}),
  
  ...(!isTauri || isDev ? {
    async rewrites() {
      return [
        {
          source: "/dashboard.html",
          destination: "/dashboard",
        },
        {
          source: "/dashboard/:tab(portfolio|signals|advisor|breakdown|history)",
          destination: "/dashboard",
        },
      ];
    },
  } : {}),
};

export default nextConfig;
