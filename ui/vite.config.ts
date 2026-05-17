import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [
      react(),
      tailwindcss()
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
        crypto: 'crypto-browserify',
      },
    },
    css: {preprocessorOptions: {less: {javascriptEnabled: true},},},
    server: {
      // 修改为监听所有接口，而不是特定主机名
      host: '0.0.0.0',
      port: 3000,
      allowedHosts: true,
      proxy: {
        // 后端请求 (8080 端口)
        '/web': {
          target: env.BACKEND_URL || 'http://localhost:8080',
          changeOrigin: true,
        },
        '/data': {
          target: env.BACKEND_URL || 'http://localhost:8080',
          changeOrigin: true,
        },
        // 工具服务请求 (1601 端口)
        '/v1': {
          target: env.TOOL_URL || 'http://localhost:1601',
          changeOrigin: true,
        },
      },
    },
    define: {
      // 一定要序列化，否则打包时会报错
      SERVICE_BASE_URL: JSON.stringify(env.SERVICE_BASE_URL),
      BACKEND_URL: JSON.stringify(env.BACKEND_URL),
      TOOL_URL: JSON.stringify(env.TOOL_URL),
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
      minify: 'terser' as const,
      rollupOptions: {output: {inlineDynamicImports: true},},
      cssCodeSplit: false,
    },
  }
});
