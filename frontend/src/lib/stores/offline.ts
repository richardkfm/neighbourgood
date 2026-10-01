/**
 * Offline detection and request queuing store.
 *
 * Tracks connectivity via navigator.onLine + browser events.
 * Persists a queue of failed POST/PATCH requests to localStorage so they
 * can be replayed automatically when the device comes back online.
 *
 * The queue is mirrored to the Cache API for the service worker's Background
 * Sync. Only one side replays at a time: the service worker hands the job to
 * an open tab when there is one, and records what it replayed itself (in
 * DONE_CACHE_KEY) so the tab drops those entries instead of sending them again.
 */

import { writable, derived, get } from 'svelte/store';

export interface QueuedRequest {
	id: string;
	method: string;
	path: string;
	body: unknown;
	authToken: string | null;
	createdAt: string;
	/** Human-readable description shown in the UI. */
	label: string;
	/** Whether this request was also broadcast via BLE mesh. */
	meshSent?: boolean;
	/** Number of times this request has been retried on server/network errors. */
	retryCount?: number;
}

/** A queued request the server refused on replay (4xx), shown to the user. */
export interface ReplayFailure {
	id: string;
	label: string;
	status: number;
	detail: string;
}

/** What the service worker did with a queued request while no tab was open. */
interface ReplayOutcome {
	id: string;
	ok: boolean;
	status: number;
	label: string;
	detail?: string;
}

const MAX_RETRIES = 5;
const TOKEN_KEY = 'ng_token';

const QUEUE_KEY = 'ng_offline_queue';

function loadQueue(): QueuedRequest[] {
	if (typeof localStorage === 'undefined') return [];
	try {
		return JSON.parse(localStorage.getItem(QUEUE_KEY) ?? '[]');
	} catch {
		return [];
	}
}

// ── Stores ────────────────────────────────────────────────────────────────────

export const isOnline = writable(
	typeof navigator !== 'undefined' ? navigator.onLine : true
);

export const offlineQueue = writable<QueuedRequest[]>(loadQueue());

/** Requests the server refused when replayed; the layout shows them until dismissed. */
export const replayFailures = writable<ReplayFailure[]>([]);

export const QUEUE_CACHE = 'ng-offline-queue';
export const QUEUE_CACHE_KEY = '/_internal/offline-queue';
export const DONE_CACHE_KEY = '/_internal/offline-queue-done';

// Keep localStorage and Cache API in sync whenever the queue changes.
offlineQueue.subscribe((q) => {
	if (typeof localStorage !== 'undefined') {
		localStorage.setItem(QUEUE_KEY, JSON.stringify(q));
	}
	// Mirror to Cache API so the service worker can access the queue for Background Sync.
	if (typeof caches !== 'undefined') {
		caches.open(QUEUE_CACHE).then((cache) => {
			if (q.length > 0) {
				cache.put(
					QUEUE_CACHE_KEY,
					new Response(JSON.stringify(q), {
						headers: { 'Content-Type': 'application/json' }
					})
				);
			} else {
				cache.delete(QUEUE_CACHE_KEY);
			}
		}).catch(() => { /* Cache API unavailable — ignore */ });
	}
});

export const queueCount = derived(offlineQueue, (q) => q.length);

// ── Actions ───────────────────────────────────────────────────────────────────

/** Add a request to the offline queue. Returns the generated id. */
export function enqueueRequest(
	req: Omit<QueuedRequest, 'id' | 'createdAt'>,
	options?: { meshSent?: boolean }
): string {
	const id = crypto.randomUUID();
	offlineQueue.update((q) => [
		...q,
		{ ...req, id, createdAt: new Date().toISOString(), meshSent: options?.meshSent ?? false }
	]);
	return id;
}

/** Remove a specific request from the queue (e.g. user cancels it). */
export function removeFromQueue(id: string) {
	offlineQueue.update((q) => q.filter((r) => r.id !== id));
}

export function dismissReplayFailures() {
	replayFailures.set([]);
}

function reportFailures(failures: ReplayFailure[]) {
	if (failures.length > 0) replayFailures.update((f) => [...f, ...failures]);
}

async function errorDetail(res: Response): Promise<string> {
	try {
		const body = await res.json();
		if (typeof body?.detail === 'string') return body.detail;
		if (Array.isArray(body?.detail)) {
			return body.detail.map((e: { msg?: string }) => e?.msg ?? '').filter(Boolean).join('; ');
		}
	} catch {
		// not JSON
	}
	return res.statusText || `HTTP ${res.status}`;
}

/**
 * Drop the entries the service worker already replayed (while no tab was
 * open) and surface the ones it could not deliver. Call on startup and when
 * the service worker reports a flush.
 */
export async function reconcileWithServiceWorker(): Promise<void> {
	if (typeof caches === 'undefined') return;
	let outcomes: ReplayOutcome[] = [];
	try {
		const cache = await caches.open(QUEUE_CACHE);
		const res = await cache.match(DONE_CACHE_KEY);
		if (!res) return;
		outcomes = await res.json();
		await cache.delete(DONE_CACHE_KEY);
	} catch {
		return;
	}
	if (!Array.isArray(outcomes) || outcomes.length === 0) return;
	const handled = new Set(outcomes.map((o) => o.id));
	offlineQueue.update((q) => q.filter((r) => !handled.has(r.id)));
	reportFailures(
		outcomes
			.filter((o) => !o.ok && o.status >= 400 && o.status < 500)
			.map((o) => ({ id: o.id, label: o.label, status: o.status, detail: o.detail ?? '' }))
	);
}

let flushing: Promise<{ succeeded: number; failed: number; dropped: number }> | null = null;

/**
 * Attempt to replay all queued requests against the live API.
 * Successfully sent requests are removed from the queue.
 * Classifies failures: 401 retries with fresh token, other 4xx are dropped
 * and reported in `replayFailures`, 5xx/network errors retry up to
 * MAX_RETRIES times before being dropped. Concurrent calls share one run.
 */
export function flushQueue(): Promise<{ succeeded: number; failed: number; dropped: number }> {
	flushing ??= runFlush().finally(() => {
		flushing = null;
	});
	return flushing;
}

async function runFlush(): Promise<{ succeeded: number; failed: number; dropped: number }> {
	await reconcileWithServiceWorker();
	const queue = get(offlineQueue);
	if (queue.length === 0) return { succeeded: 0, failed: 0, dropped: 0 };

	let succeeded = 0;
	let failed = 0;
	let dropped = 0;
	const done = new Set<string>();
	const retry = new Map<string, QueuedRequest>();
	const failures: ReplayFailure[] = [];

	const send = (req: QueuedRequest, authToken: string | null) => {
		const headers: Record<string, string> = {};
		if (req.method !== 'DELETE') headers['Content-Type'] = 'application/json';
		if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
		return fetch(`/api${req.path}`, {
			method: req.method,
			headers,
			body: req.method !== 'DELETE' ? JSON.stringify(req.body) : undefined
		});
	};

	for (const req of queue) {
		try {
			let res = await send(req, req.authToken);
			if (res.status === 401) {
				// Token expired — try with the current live token
				const liveToken = typeof localStorage !== 'undefined' ? localStorage.getItem(TOKEN_KEY) : null;
				if (liveToken && liveToken !== req.authToken) res = await send(req, liveToken);
			}

			if (res.ok) {
				succeeded++;
				done.add(req.id);
			} else if (res.status >= 400 && res.status < 500) {
				// Client errors (422, 404, expired session…) — retrying won't help; tell the user
				dropped++;
				done.add(req.id);
				failures.push({ id: req.id, label: req.label, status: res.status, detail: await errorDetail(res) });
			} else {
				// 5xx server error — retry with a limit
				const retries = (req.retryCount ?? 0) + 1;
				if (retries >= MAX_RETRIES) {
					dropped++;
					done.add(req.id);
				} else {
					retry.set(req.id, { ...req, retryCount: retries });
					failed++;
				}
			}
		} catch {
			// Network error — retry with a limit
			const retries = (req.retryCount ?? 0) + 1;
			if (retries >= MAX_RETRIES) {
				dropped++;
				done.add(req.id);
			} else {
				retry.set(req.id, { ...req, retryCount: retries });
				failed++;
			}
		}
	}

	// Requests queued while this flush was running are kept
	offlineQueue.update((q) => q.filter((r) => !done.has(r.id)).map((r) => retry.get(r.id) ?? r));
	reportFailures(failures);
	return { succeeded, failed, dropped };
}

/** Empty the queue and its service-worker mirror (on logout). */
export async function clearOfflineQueue(): Promise<void> {
	offlineQueue.set([]);
	replayFailures.set([]);
	if (typeof caches === 'undefined') return;
	try {
		const cache = await caches.open(QUEUE_CACHE);
		await Promise.all([cache.delete(QUEUE_CACHE_KEY), cache.delete(DONE_CACHE_KEY)]);
	} catch {
		// Cache API unavailable
	}
}

/**
 * Register window online/offline listeners.
 * Call once from the root layout's onMount (browser-only).
 */
export function initOfflineTracking() {
	if (typeof window === 'undefined') return;
	window.addEventListener('online', () => isOnline.set(true));
	window.addEventListener('offline', () => isOnline.set(false));
}
