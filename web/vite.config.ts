import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "https://web-production-4d5c0.up.railway.app",
        changeOrigin: true,
        secure: true,
      },
    },
  },
});