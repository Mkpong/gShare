/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Served from the root: one SPA covers both the user console (/) and the admin console (/admin),
// with separate layouts.
export default defineConfig({
  base: '/',
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    proxy: {
      // In development, proxy /api to the backend; the bearer header passes through.
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Vendor code changes on dependency bumps, app code on every release: keeping them in
        // separate chunks lets the browser keep the (much larger) vendor half cached across deploys.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          // uplot is the one dependency with no React import, so it is safe to isolate. Everything
          // else stays in one vendor chunk: splitting React away from libraries that import it
          // (icons, i18n, zustand) let a dependent chunk evaluate before React had initialised and
          // took the login page down with "Cannot read properties of undefined (reading 'useState')".
          if (id.includes('uplot')) return 'uplot';
          return 'vendor';
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
});
