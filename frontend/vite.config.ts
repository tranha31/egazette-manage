import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// Dev: Vite (http://localhost:5173) chuyển tiếp /api sang backend, nên frontend và API cùng một origin,
// không cần CORS và đăng nhập Basic (nếu bật) hoạt động bình thường.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const target = env.VITE_PROXY_TARGET || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: { port: 5173, proxy: { "/api": { target, changeOrigin: false } } },
    preview: { port: 4173, proxy: { "/api": { target } } },
    test: { environment: "node" },
  };
});
