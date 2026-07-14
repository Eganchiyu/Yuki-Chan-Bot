import { defineConfig } from 'vite';
import path from 'path';

export default defineConfig({
  root: '.',
  publicDir: 'public',
  base: './',
  resolve: {
    alias: {
      '@framework': path.resolve(__dirname, 'src/WebSDK/Framework/src'),
      '@cubismsdksamples': path.resolve(__dirname, 'src/WebSDK/src'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
  },
});
