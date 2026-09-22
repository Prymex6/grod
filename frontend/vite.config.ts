import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
// vitest/config re-exports Vite's defineConfig and adds the `test` section.
import { defineConfig } from 'vitest/config';

const API_TARGET = 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // The console talks to the API on the same origin, so proxy it in development.
    proxy: {
      // The slash matters: without it the rule would also catch console
      // routes that merely start with "api", such as /apis.
      // ws: the terminal of a workspace talks over a WebSocket.
      '/api/': { target: API_TARGET, changeOrigin: true, ws: true },
      '/.well-known': { target: API_TARGET, changeOrigin: true },
      // Published sites and Git over HTTP live outside the API prefix.
      '/-': { target: API_TARGET, changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
