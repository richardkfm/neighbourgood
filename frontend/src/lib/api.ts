/**
 * Thin wrapper around fetch for talking to the backend API.
 * All paths are prefixed with /api which the Vite dev proxy rewrites to the backend.
 */

import { get } from 'svelte/store';
import { token } from '$lib/stores/auth';
import { isOnline, enqueueRequest } from '$lib/stores/offline';

const BASE = '/api';

interface OfflineOptions {
	/** Human-readable label shown in the offline queue UI. */
	label: string;
	/** Value to return immediately when the request is queued. Defaults to undefined. */
	fallback?: unknown;
}

interface RequestOptions {
	method?: string;
	body?: unknown;
	auth?: boolean;
	/** If provided, queues the request when offline instead of throwing. */
	offline?: OfflineOptions;
	/** Use SvelteKit's load-scoped fetch when calling from a `load` function. */
	fetch?: typeof fetch;
}

export async function api<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
	const { method = 'GET', body, auth = false, offline, fetch: fetchFn = fetch } = opts;

	// Queue the request if offline and the caller opted in
	if (offline && !get(isOnline)) {
		const authToken = auth ? get(token) : null;
		enqueueRequest({ method, path, body, authToken, label: offline.label });
		return offline.fallback as T;
	}

	const headers: Record<string, string> = {};

	if (body) {
		headers['Content-Type'] = 'application/json';
	}
	if (auth) {
		const t = get(token);
		if (t) headers['Authorization'] = `Bearer ${t}`;
	}

	const res = await fetchFn(`${BASE}${path}`, {
		method,
		headers,
		body: body ? JSON.stringify(body) : undefined
	});

	if (res.status === 401 && auth) {
		await handleUnauthorized();
		throw new Error('Session expired');
	}

	if (!res.ok) {
		const err = await res.json().catch(() => ({ detail: res.statusText }));

		// Handle Pydantic validation errors (detail is an array of objects)
		let errorMsg = '';
		if (Array.isArray(err.detail)) {
			// Pydantic prefixes custom validator messages with "Value error, "
			errorMsg = err.detail
				.map((e: any) => (e.msg ? String(e.msg).replace(/^Value error, /, '') : e.toString()))
				.join('; ');
		} else if (typeof err.detail === 'string') {
			errorMsg = err.detail;
		} else if (err.detail) {
			errorMsg = err.detail.toString();
		}

		throw new Error(errorMsg || `Request failed: ${res.status}`);
	}

	if (res.status === 204) return undefined as T;
	return res.json();
}

/**
 * Clear auth state and redirect to /login. Called on 401 from any authenticated
 * request so an expired token doesn't cause silent failures across the app.
 * Uses dynamic imports to avoid SSR cycles on initial module load.
 */
async function handleUnauthorized(): Promise<void> {
	if (typeof window === 'undefined') return;
	try {
		const { logout } = await import('$lib/stores/auth');
		// An expired session is usually followed by the same person signing in
		// again; offline data is wiped if a different account signs in instead.
		await logout({ keepOfflineData: true });
	} catch {
		// Auth store not available; fall through to redirect.
	}
	try {
		const { goto } = await import('$app/navigation');
		await goto('/login');
	} catch {
		// Navigation not available (SSR / test); fall through.
	}
}

/**
 * Upload a file (multipart/form-data) to the backend.
 */
export async function apiUpload<T = unknown>(path: string, file: File): Promise<T> {
	const headers: Record<string, string> = {};
	// Fall back to localStorage in case the store hasn't synced yet after SSR hydration.
	const t = get(token) ?? (typeof localStorage !== 'undefined' ? localStorage.getItem('ng_token') : null);
	if (t) headers['Authorization'] = `Bearer ${t}`;

	const formData = new FormData();
	formData.append('file', file);

	const res = await fetch(`${BASE}${path}`, {
		method: 'POST',
		headers,
		body: formData
	});

	if (res.status === 401 && t) {
		await handleUnauthorized();
		throw new Error('Session expired');
	}

	if (!res.ok) {
		const err = await res.json().catch(() => ({ detail: res.statusText }));

		// Handle Pydantic validation errors (detail is an array of objects)
		let errorMsg = '';
		if (Array.isArray(err.detail)) {
			errorMsg = err.detail.map((e: any) => e.msg || e.toString()).join('; ');
		} else if (typeof err.detail === 'string') {
			errorMsg = err.detail;
		} else if (err.detail) {
			errorMsg = err.detail.toString();
		}

		throw new Error(errorMsg || `Upload failed: ${res.status}`);
	}

	return res.json();
}
