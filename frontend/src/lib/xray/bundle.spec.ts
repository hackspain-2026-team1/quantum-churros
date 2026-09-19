import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { beforeEach, describe, expect, it } from 'vitest';
import {
	BUNDLE_ROOT,
	BundleError,
	clearBundleCache,
	loadAlerts,
	loadCompany,
	loadEvidence,
	loadGroup,
	loadManifest,
	loadPortfolio,
	loadReceipt
} from './bundle';

// Serves the synthetic contract fixture the way a static host serves /data/v1.
const root = fileURLToPath(new URL('../../../e2e/fixtures/bundle/v1/', import.meta.url));

function staticHost(options: { spaFallback?: boolean; without?: string } = {}) {
	const calls: string[] = [];
	const fetcher = (async (input: RequestInfo | URL) => {
		const url = new URL(String(input), 'http://bundle.test');
		calls.push(url.pathname);
		const path = url.pathname.slice(`${BUNDLE_ROOT}/`.length);
		const file = `${root}${path}`;
		const missing = !existsSync(file) || (options.without && path.startsWith(options.without));
		if (missing) {
			return options.spaFallback
				? new Response('<!doctype html>', { status: 200, headers: { 'content-type': 'text/html' } })
				: new Response('not found', { status: 404 });
		}
		return new Response(readFileSync(file, 'utf-8'), {
			status: 200,
			headers: { 'content-type': 'application/json' }
		});
	}) as typeof fetch;
	return { fetcher, calls };
}

describe('bundle readers', () => {
	beforeEach(() => clearBundleCache());

	it('parses every kind of file from /data/v1', async () => {
		const { fetcher } = staticHost();
		const manifest = await loadManifest(fetcher);
		const portfolio = await loadPortfolio(fetcher);
		const groupId = portfolio.groups[0].id;
		const group = await loadGroup(fetcher, groupId);
		const evidence = await loadEvidence(fetcher, groupId);
		const company = await loadCompany(fetcher, group.companies[0].id);
		const alerts = await loadAlerts(fetcher);
		const receipt = await loadReceipt(fetcher);

		expect(portfolio.months).toEqual(manifest.months);
		expect(group.id).toBe(groupId);
		expect(evidence.entity_id).toBe(groupId);
		expect(company?.group_id).toBe(groupId);
		expect(alerts.alerts).toHaveLength(manifest.counts.alerts);
		expect(receipt.params_hash).toBe(manifest.params_hash);
	});

	it('fetches each file once per bundle', async () => {
		const { fetcher, calls } = staticHost();
		const [first, second] = await Promise.all([loadPortfolio(fetcher), loadPortfolio(fetcher)]);
		await loadPortfolio(fetcher);

		expect(second).toBe(first);
		expect(calls.filter((path) => path.endsWith('/manifest.json'))).toHaveLength(1);
		expect(calls.filter((path) => path.endsWith('/portfolio.json'))).toHaveLength(1);
	});

	it('resolves a company to null when companies/ is absent, on 404 or on an SPA fallback', async () => {
		for (const spaFallback of [false, true]) {
			clearBundleCache();
			const { fetcher } = staticHost({ spaFallback, without: 'companies/' });
			const group = await loadGroup(fetcher, 'GROUP_T001');
			expect(await loadCompany(fetcher, group.companies[0].id)).toBeNull();
		}
	});

	it('reports a missing group as a BundleError and retries afterwards', async () => {
		const { fetcher, calls } = staticHost();
		await expect(loadGroup(fetcher, 'NOPE')).rejects.toMatchObject({
			name: 'BundleError',
			kind: 'missing',
			path: 'groups/NOPE.json'
		});
		await expect(loadGroup(fetcher, 'NOPE')).rejects.toBeInstanceOf(BundleError);
		expect(calls.filter((path) => path.endsWith('/groups/NOPE.json'))).toHaveLength(2);
	});

	it('rejects a file that breaks the contract', async () => {
		const fetcher = (async () =>
			new Response(JSON.stringify({ schema: 'xray-export-v1', kind: 'manifest' }), {
				status: 200,
				headers: { 'content-type': 'application/json' }
			})) as typeof fetch;
		await expect(loadManifest(fetcher)).rejects.toMatchObject({ kind: 'invalid' });
	});
});
