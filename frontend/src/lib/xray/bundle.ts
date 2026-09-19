// Cached readers for the static export bundle served under `${base}/data/v1/`.
//
// Every reader takes SvelteKit's `fetch`, zod-parses the file with contract.ts
// and caches the parsed result per bundle_id, so pages and components can call
// them freely. Nothing here invents data: a missing or invalid file is an error
// the UI has to show, except loadCompany, whose folder is optional in the contract.

import { base } from '$app/paths';
import { ZodError } from 'zod';
import {
	BUNDLE_FILES,
	parseBundleFile,
	type AlertsFile,
	type BundleFile,
	type BundleKind,
	type CompanyFile,
	type EvidenceFile,
	type GroupFile,
	type InvoicesDue,
	type Manifest,
	type Portfolio,
	type Receipt
} from './contract.js';

export type Fetch = typeof fetch;
export type BundleErrorKind = 'missing' | 'invalid' | 'network';

export const BUNDLE_ROOT = `${base}/data/v1`;

export class BundleError extends Error {
	readonly kind: BundleErrorKind;
	readonly path: string;
	readonly status: number;

	constructor(kind: BundleErrorKind, path: string, message: string, status = 0) {
		super(message);
		this.name = 'BundleError';
		this.kind = kind;
		this.path = path;
		this.status = status;
	}
}

let manifestPromise: Promise<Manifest> | null = null;
const cache = new Map<string, Promise<unknown>>();

/** Forget everything read so far; the next reader call fetches again. */
export function clearBundleCache(): void {
	manifestPromise = null;
	cache.clear();
}

async function readJson(fetcher: Fetch, path: string, version?: string): Promise<unknown> {
	const url = `${BUNDLE_ROOT}/${path}${version ? `?v=${version}` : ''}`;
	let response: Response;
	try {
		response = await fetcher(url, { headers: { accept: 'application/json' } });
	} catch (reason) {
		const detail = reason instanceof Error ? reason.message : String(reason);
		throw new BundleError('network', path, `No se pudo leer ${path}: ${detail}`);
	}
	// A static host with an SPA fallback answers 200 + HTML for a missing file.
	const type = response.headers.get('content-type') ?? '';
	if (response.status === 404 || (response.ok && type.includes('text/html'))) {
		throw new BundleError('missing', path, `El bundle no contiene ${path}`, 404);
	}
	if (!response.ok) {
		throw new BundleError(
			'network',
			path,
			`El servidor respondió ${response.status} al leer ${path}`,
			response.status
		);
	}
	try {
		return await response.json();
	} catch {
		throw new BundleError('invalid', path, `${path} no es JSON válido`, response.status);
	}
}

function parse<K extends BundleKind>(kind: K, path: string, data: unknown): BundleFile<K> {
	try {
		return parseBundleFile(kind, data);
	} catch (reason) {
		if (reason instanceof ZodError) {
			const issue = reason.issues[0];
			const where = issue?.path.length ? ` (${issue.path.join('.')})` : '';
			throw new BundleError(
				'invalid',
				path,
				`${path} no cumple el contrato ${kind}${where}: ${issue?.message ?? 'formato inesperado'}`
			);
		}
		throw reason;
	}
}

function cached<T>(key: string, read: () => Promise<T>): Promise<T> {
	const hit = cache.get(key) as Promise<T> | undefined;
	if (hit) return hit;
	const pending = read().catch((reason) => {
		cache.delete(key);
		throw reason;
	});
	cache.set(key, pending);
	return pending;
}

async function loadFile<K extends BundleKind>(
	fetcher: Fetch,
	kind: K,
	path: string
): Promise<BundleFile<K>> {
	const { bundle_id } = await loadManifest(fetcher);
	return cached(`${bundle_id}:${path}`, async () =>
		parse(kind, path, await readJson(fetcher, path, bundle_id.slice(0, 12)))
	);
}

/** The manifest names the bundle; every other file is cached under its bundle_id. */
export function loadManifest(fetcher: Fetch): Promise<Manifest> {
	if (!manifestPromise) {
		const path = BUNDLE_FILES.manifest;
		const pending = readJson(fetcher, path).then((data) => parse('manifest', path, data));
		pending.catch(() => {
			if (manifestPromise === pending) manifestPromise = null;
		});
		manifestPromise = pending;
	}
	return manifestPromise;
}

export function loadPortfolio(fetcher: Fetch): Promise<Portfolio> {
	return loadFile(fetcher, 'portfolio', BUNDLE_FILES.portfolio);
}

export function loadGroup(fetcher: Fetch, id: string): Promise<GroupFile> {
	return loadFile(fetcher, 'group', BUNDLE_FILES.group(id));
}

export function loadEvidence(fetcher: Fetch, id: string): Promise<EvidenceFile> {
	return loadFile(fetcher, 'evidence', BUNDLE_FILES.evidence(id));
}

/** Resolves to null when companies/{id}.json is absent: fall back to group.companies[]. */
export async function loadCompany(fetcher: Fetch, id: string): Promise<CompanyFile | null> {
	const path = BUNDLE_FILES.company(id);
	const { bundle_id } = await loadManifest(fetcher);
	return cached(`${bundle_id}:${path}`, async () => {
		try {
			return parse('company', path, await readJson(fetcher, path, bundle_id.slice(0, 12)));
		} catch (reason) {
			if (reason instanceof BundleError && reason.kind === 'missing') return null;
			throw reason;
		}
	});
}

export function loadAlerts(fetcher: Fetch): Promise<AlertsFile> {
	return loadFile(fetcher, 'alerts', BUNDLE_FILES.alerts);
}

export function loadReceipt(fetcher: Fetch): Promise<Receipt> {
	return loadFile(fetcher, 'receipt', BUNDLE_FILES.receipt);
}

/** Resolves to null when invoices_due.json is absent: older bundles have no reminders. */
export async function loadInvoicesDue(fetcher: Fetch): Promise<InvoicesDue | null> {
	const path = BUNDLE_FILES.invoices_due;
	const { bundle_id } = await loadManifest(fetcher);
	return cached(`${bundle_id}:${path}`, async () => {
		try {
			return parse('invoices_due', path, await readJson(fetcher, path, bundle_id.slice(0, 12)));
		} catch (reason) {
			if (reason instanceof BundleError && reason.kind === 'missing') return null;
			throw reason;
		}
	});
}
