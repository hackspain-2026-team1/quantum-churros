import { defineConfig } from '@playwright/test';

// BASE_URL points the smoke test at a deployed site; without it the static
// build is served locally from whatever bundle sits in static/data/v1
// (the synthetic fixture when there is none).
const baseURL = process.env.BASE_URL;

export default defineConfig({
	use: { baseURL: baseURL ?? 'http://127.0.0.1:4173', locale: 'es-ES' },
	webServer: baseURL
		? undefined
		: {
				command:
					'(test -f static/data/v1/manifest.json || bun run fixture) && XRAY_TARGET=static bun run build && bun run preview -- --host 127.0.0.1 --port 4173',
				url: 'http://127.0.0.1:4173',
				timeout: 180_000,
				reuseExistingServer: true
			},
	testDir: 'e2e'
});
