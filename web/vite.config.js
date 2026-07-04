import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

const backendPort = process.env.LIGHTERBIRD_PORT || 8000;

export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: `http://localhost:${backendPort}`,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
  },
});
