import type { HandleClientError } from '@sveltejs/kit';
import { BundleError } from '$lib/xray/bundle.js';

// Loads throw BundleError when a bundle file is missing or breaks the contract;
// its Spanish message is what the error pages show.
export const handleError: HandleClientError = ({ error, message }) => {
	console.error(error);
	if (error instanceof BundleError) return { message: error.message };
	return { message };
};
