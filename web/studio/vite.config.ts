import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  esbuild: { jsx: "automatic", jsxImportSource: "preact" },
  build: {
    outDir: "../../audio_smith/studio/static",
    emptyOutDir: true,
    target: "es2022",
    sourcemap: false,
  },
});
