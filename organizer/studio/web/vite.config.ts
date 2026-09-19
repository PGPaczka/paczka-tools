import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

/**
 * Dev działa przez proxy, a nie przez CORS: przeglądarka widzi jedno źródło,
 * więc backend nie musi wpuszczać żadnego obcego originu. `just studio-dev`
 * podaje adres API w PACZKA_STUDIO_API (domyślnie port launchera).
 */
const api = process.env.PACZKA_STUDIO_API ?? 'http://127.0.0.1:8765';

export default defineConfig({
  plugins: [svelte()],
  server: {
    host: '127.0.0.1',
    proxy: { '/api': { target: api, changeOrigin: false } },
  },
  build: { outDir: 'dist', emptyOutDir: true },
  test: { environment: 'jsdom', include: ['src/**/*.test.ts'] },
});
