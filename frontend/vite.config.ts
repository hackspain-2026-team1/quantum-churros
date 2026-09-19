import { defineConfig } from 'vite';

export default defineConfig({
	server: {
		proxy: {
			'/api': {
				target: process.env.VITE_API_PROXY ?? 'http://api:8000',
				changeOrigin: true,
			},
		},
	},
});
