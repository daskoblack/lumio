import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base: './' -> chemins d'assets relatifs, indispensable car pywebview charge
// le index.html buildé depuis le disque (file://), pas depuis une racine web.
export default defineConfig({
  plugins: [react()],
  base: './',
  server: { port: 5173, strictPort: true },
})
