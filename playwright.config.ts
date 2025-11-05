import { defineConfig } from '@playwright/test';

export default defineConfig({
  webServer: {
    command: 'pnpm dev',
    port: 3000,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  use: {
    baseURL: 'http://localhost:3000',
    viewport: { width: 390, height: 844 }, // mobile-like
  },
});

