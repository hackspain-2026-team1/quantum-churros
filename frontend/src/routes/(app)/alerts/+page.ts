import { loadAlerts, loadReceipt } from '$lib/xray/bundle.js';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
	const [file, abstentions] = await Promise.all([
		loadAlerts(fetch),
		// The receipt only adds what unlocks a standing abstention; the inbox works without it
		// and the receipt screen reports its own errors.
		loadReceipt(fetch)
			.then((receipt) => receipt.abstentions)
			.catch(() => null)
	]);
	return { alerts: file.alerts, abstentions };
};
