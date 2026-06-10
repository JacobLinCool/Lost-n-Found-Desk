import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  build: {
    // Build directly into the directory the FastAPI app serves, so a single
    // `pnpm run build` (or `make init`) refreshes the deployed SPA with no
    // manual copy step. emptyOutDir is required because ../static is outside
    // the Vite project root.
    outDir: '../static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:7860',
      '/gradio_api': 'http://127.0.0.1:7860',
      '/config': 'http://127.0.0.1:7860',
      '/health': 'http://127.0.0.1:7860',
    },
  },
});
