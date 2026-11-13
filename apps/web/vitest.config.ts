import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  test: {
    environment: 'happy-dom',
    include: ['test/**/*.test.ts'],
    setupFiles: ['test/support/setup.ts'],
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,vue}'],
      exclude: [
        // Bootstrap only: mounts the app and imports the stylesheet.
        'src/main.ts',
        // shadcn-vue primitives copied from the registry, not our code.
        'src/core/ui/**',
        // Generated from the server's OpenAPI schema; types only.
        'src/core/api/schema.d.ts',
      ],
      reporter: ['text', 'html'],
      thresholds: { lines: 95, statements: 95, functions: 92, branches: 92 },
    },
  },
})
