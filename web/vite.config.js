import { defineConfig } from "vitest/config";
import { svelte } from "@sveltejs/vite-plugin-svelte";

const backendPort = process.env.LIGHTERBIRD_PORT || 6006;

export default defineConfig({
  plugins: [svelte({ compilerOptions: { dev: true } })],
  server: {
    port: 6005,
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
  resolve: {
    conditions: ["browser", "module", "import", "default"],
  },
  ssr: {
    noExternal: ["svelte", "@sveltejs/vite-plugin-svelte"],
    resolve: {
      conditions: ["browser", "module", "import", "default"],
    },
  },
  test: {
    include: ["src/**/*.test.js"],
    environment: "jsdom",
    globals: true,
    server: {
      deps: {
        inline: ["svelte", "@sveltejs/vite-plugin-svelte"],
      },
    },
    transformMode: {
      web: ["**/*.svelte"],
    },
  },
});
