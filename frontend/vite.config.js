import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Local Docker flow serves built files from FastAPI at /static/ (backend/static).
  // Vercel Services serves the frontend from / — so use / base when building on Vercel.
  base: process.env.VERCEL ? "/" : "/static/",
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/static": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: process.env.VERCEL ? "dist" : "../backend/static",
    emptyOutDir: true,
  },
});
