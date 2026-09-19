// Copies the synthetic contract fixture into static/data/v1 so `bun run dev`,
// the build and the e2e smoke have a bundle to read. static/data/ is
// git-ignored: the real bundle is produced by the engine export, never committed.
//
// Usage: bun run fixture [--force]
import { cpSync, existsSync, readFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const source = join(root, 'e2e', 'fixtures', 'bundle', 'v1');
const target = join(root, 'static', 'data', 'v1');
const force = process.argv.includes('--force');

const bundleId = (dir) => {
	try {
		return JSON.parse(readFileSync(join(dir, 'manifest.json'), 'utf8')).bundle_id ?? null;
	} catch {
		return null;
	}
};

if (!existsSync(join(source, 'manifest.json'))) {
	console.error(`fixture: no bundle found at ${source}`);
	process.exit(1);
}

const current = existsSync(target) ? bundleId(target) : null;
if (current && current !== bundleId(source) && !force) {
	console.error(
		`fixture: ${target} holds another bundle (${current.slice(0, 12)}). ` +
			'Re-run with --force to replace it with the synthetic fixture.'
	);
	process.exit(1);
}

rmSync(target, { recursive: true, force: true });
cpSync(source, target, { recursive: true });
console.log(`fixture: copied synthetic bundle ${bundleId(target)?.slice(0, 12)} -> static/data/v1`);
