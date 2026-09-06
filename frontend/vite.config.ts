import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5273,
    strictPort: true,
    // Local-only tool: the frontend talks to the FastAPI backend through this proxy,
    // which keeps the browser on one origin and avoids CORS entirely in dev.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8100",
        changeOrigin: true,
      },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
