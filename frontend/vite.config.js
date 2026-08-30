import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Proxy API calls to the FastAPI backend during dev.
    proxy: {
      "/upload": "http://localhost:8000",
      "/score": "http://localhost:8000",
      "/rewrite": "http://localhost:8000",
      "/redflags": "http://localhost:8000",
      "/jdmatch": "http://localhost:8000",
      "/generate": "http://localhost:8000",
      "/rescore": "http://localhost:8000",
      "/original": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
