import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

const proxy: RequestHandler = async ({ fetch, params, request, url }) => {
	const upstream = new URL(
		`/api/${params.path}${url.search}`,
		env.API_URL ?? 'http://127.0.0.1:8000'
	);
	const headers = new Headers(request.headers);
	headers.delete('host');
	const body =
		request.method === 'GET' || request.method === 'HEAD' ? undefined : await request.arrayBuffer();
	return fetch(upstream, { method: request.method, headers, body });
};

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
