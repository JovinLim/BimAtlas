import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		proxy: {
			// Proxy /api/* to the backend to avoid ERR_ALPN_NEGOTIATION_FAILED
			// (browser/antivirus TLS inspection can break direct localhost:8000 requests)
			'/api': {
				target: 'http://localhost:8000',
				changeOrigin: true,
				rewrite: (path) => path.replace(/^\/api/, ''),
				secure: false,
				ws: true,
			}
		}
	}
});
