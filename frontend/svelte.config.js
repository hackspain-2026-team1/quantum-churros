import { mdsvex } from 'mdsvex';
import adapterNode from '@sveltejs/adapter-node';
import adapterStatic from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

// The public demo is a static SPA that reads the export bundle from /data/v1.
// XRAY_TARGET=static (or a Vercel build) selects it; local dev keeps the node adapter.
const isStatic = process.env.XRAY_TARGET === 'static' || Boolean(process.env.VERCEL);

/** @type {import('@sveltejs/kit').Config} */
const config = {
	// Consult https://svelte.dev/docs/kit/integrations
	// for more information about preprocessors
	preprocess: [vitePreprocess(), mdsvex()],
	kit: {
		adapter: isStatic
			? adapterStatic({ pages: 'build', assets: 'build', fallback: '200.html' })
			: adapterNode(),
		alias: {
			'@/*': './src/lib/*'
		}
	},
	extensions: ['.svelte', '.svx']
};

export default config;
