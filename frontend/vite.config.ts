import { defineConfig } from 'vite';

export default defineConfig({
	server: {
		host: process.env.VITE_HOST ?? '0.0.0.0',
		port: Number(process.env.VITE_PORT ?? 3000),
		proxy: {
			'/api': {
				target: process.env.VITE_API_PROXY ?? 'http://api:8000',
				changeOrigin: true,
			},
		},
	},
});
