import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig(({ mode }) => {
  // Load .env from project root (one level up from frontend/)
  const env = loadEnv(mode, resolve(__dirname, '..'), '')

  const apiTarget = env.VITE_API_URL || 'http://localhost:8000'
  const wsTarget  = apiTarget.replace(/^http/, 'ws')

  return {
    plugins: [react()],

    // ── Dev server ──────────────────────────────────────────────
    server: {
      host:        '0.0.0.0',   // accessible from Waveshare LCD browser
      port:        5173,
      strictPort:  true,
      proxy: {
        '/api':    { target: apiTarget, changeOrigin: true },
        '/ws':     { target: wsTarget,  ws: true, changeOrigin: true },
        '/stream': { target: apiTarget, changeOrigin: true },
        '/health': { target: apiTarget, changeOrigin: true },
      },
    },

    // ── Preview server (vite preview) ───────────────────────────
    preview: {
      host: '0.0.0.0',
      port: 4173,
    },

    // ── Production build ────────────────────────────────────────
    build: {
      outDir:    'dist',
      emptyOutDir: true,

      // No source maps in production — keeps bundle small on RPi SD card
      sourcemap: false,

      // Explicit minification (esbuild is default and fastest on ARM)
      minify: 'esbuild',

      // Raise chunk size warning to 800 KB (Recharts is large)
      chunkSizeWarningLimit: 800,

      rollupOptions: {
        output: {
          // ── Manual chunk splitting ──────────────────────────
          // Splits vendor libs into separate cacheable chunks so that
          // the RPi browser only re-downloads what actually changed.
          manualChunks: {
            // React runtime — changes rarely
            'vendor-react': ['react', 'react-dom', 'react-router-dom'],

            // Charts — large, but rarely updated
            'vendor-charts': ['recharts'],

            // Icons — small but separate for caching
            'vendor-icons': ['lucide-react'],
          },

          // Deterministic filenames for long-term caching
          chunkFileNames:  'assets/js/[name]-[hash].js',
          entryFileNames:  'assets/js/[name]-[hash].js',
          assetFileNames:  'assets/[ext]/[name]-[hash].[ext]',
        },
      },

      // CSS code splitting — each lazy-loaded chunk gets its own CSS
      cssCodeSplit: true,

      // Target modern browsers only (RPi Chromium supports ES2020+)
      target: 'es2020',
    },

    // ── Define compile-time constants ───────────────────────────
    define: {
      __APP_VERSION__: JSON.stringify(
        process.env.npm_package_version || '2.0.0'
      ),
      __APP_ENV__: JSON.stringify(mode),
    },

    // ── Path aliases ────────────────────────────────────────────
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src'),
        '@components': resolve(__dirname, 'src/components'),
        '@pages':      resolve(__dirname, 'src/pages'),
        '@hooks':      resolve(__dirname, 'src/hooks'),
        '@services':   resolve(__dirname, 'src/services'),
      },
    },

    // ── Optimise deps (pre-bundling) ────────────────────────────
    optimizeDeps: {
      include: [
        'react',
        'react-dom',
        'react-router-dom',
        'recharts',
        'lucide-react',
        'clsx',
      ],
    },
  }
})
