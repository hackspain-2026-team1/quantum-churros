import { defineConfig } from '@playwright/test';

export default defineConfig({
	use: { baseURL: 'http://127.0.0.1:4173' },
	webServer: [
		{
			command: 'cd .. && uv run --package quantum-churros-api uvicorn app.main:app --port 8000',
			port: 8000,
			reuseExistingServer: true
		},
		{
			command: 'bun run build && bun run preview -- --host 127.0.0.1 --port 4173',
			url: 'http://127.0.0.1:4173'
		}
	],
	testDir: 'e2e'
});
