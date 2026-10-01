/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />

import { build, files, version } from '$service-worker';

declare const self: ServiceWorkerGlobalScope;

// One cache per build version — old caches are deleted on activate.
const STATIC_CACHE = `ng-static-${version}`;
// API cache is kept across versions (serves stale data when offline).
const API_CACHE = 'ng-api-v1';

// All SvelteKit build chunks + everything in /static
const PRECACHE_ASSETS = [...build, ...files];

// ── Install: precache all static + build assets ──────────────────────────────

self.addEventListener('install', (event) => {
	event.waitUntil(
		caches
			.open(STATIC_CACHE)
			.then((cache) => cache.addAll(PRECACHE_ASSETS))
			// Activate immediately — don't wait for existing tabs to close.
			.then(() => self.skipWaiting())
	);
});

// ── Activate: delete old static caches (previous build versions) ─────────────

self.addEventListener('activate', (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) =>
				Promise.all(
					keys
						// Remove old versioned static caches but keep the API cache.
						.filter((k) => k.startsWith('ng-static-') && k !== STATIC_CACHE)
						.map((k) => caches.delete(k))
				)
			)
			// Take control of all open tabs immediately.
			.then(() => self.clients.claim())
	);
});

// ── Fetch: route-based caching strategies ────────────────────────────────────

self.addEventListener('fetch', (event) => {
	const { request } = event;
	const url = new URL(request.url);

	// Only handle GET from the same origin.
	if (request.method !== 'GET') return;
	if (url.origin !== self.location.origin) return;

	// API requests: network-first, fall back to cached response when offline.
	if (url.pathname.startsWith('/api/')) {
		event.respondWith(apiNetworkFirst(request));
		return;
	}

	// Precached build/static assets: cache-first (they have hashed names).
	if (PRECACHE_ASSETS.includes(url.pathname)) {
		event.respondWith(cacheFirst(request, STATIC_CACHE));
		return;
	}

	// SvelteKit page navigations: network-first, branded offline fallback.
	if (request.mode === 'navigate') {
		event.respondWith(navigationNetworkFirst(request));
		return;
	}
});

// ── Strategy helpers ─────────────────────────────────────────────────────────

/** Cache-first: return cached version, fetch from network only on miss. */
async function cacheFirst(request: Request, cacheName: string): Promise<Response> {
	const cached = await caches.match(request, { cacheName });
	if (cached) return cached;
	const response = await fetch(request);
	const cache = await caches.open(cacheName);
	cache.put(request, response.clone());
	return response;
}

/**
 * Network-first for API: try the network, cache successful responses,
 * serve stale cache on failure. Returns a 503 if nothing is cached.
 *
 * Cached responses carry an `X-Served-From: offline-cache` header so
 * the application can detect that it is viewing stale data.
 */
async function apiNetworkFirst(request: Request): Promise<Response> {
	const cache = await caches.open(API_CACHE);
	try {
		const response = await fetch(request);
		if (response.ok) {
			cache.put(request, response.clone());
		}
		return response;
	} catch {
		const cached = await cache.match(request);
		if (cached) {
			// Re-emit with an extra header so the app knows this is stale data.
			const headers = new Headers(cached.headers);
			headers.set('X-Served-From', 'offline-cache');
			return new Response(cached.body, {
				status: cached.status,
				statusText: cached.statusText,
				headers
			});
		}
		return new Response(JSON.stringify({ detail: 'You are offline' }), {
			status: 503,
			headers: { 'Content-Type': 'application/json' }
		});
	}
}

/**
 * Network-first for page navigations: try network, serve the offline
 * fallback page when the network is unavailable.
 */
async function navigationNetworkFirst(request: Request): Promise<Response> {
	try {
		return await fetch(request);
	} catch {
		const offline = await caches.match('/offline.html');
		return offline ?? new Response('Offline', { status: 503 });
	}
}

// ── Background Sync: flush offline queue when connectivity returns ────────────
//
// Only one side replays: when a tab is open the job is handed to it (it owns
// the localStorage queue). Otherwise the worker replays from the Cache mirror
// and records every request it handled in DONE_CACHE_KEY, so the next tab
// drops those entries instead of sending them a second time, and shows the
// ones the server refused.

const QUEUE_CACHE = 'ng-offline-queue';
const QUEUE_CACHE_KEY = '/_internal/offline-queue';
const DONE_CACHE_KEY = '/_internal/offline-queue-done';
const MAX_RETRIES = 5;

// Written by the auth store; lets mesh sync authenticate without a queued request
const AUTH_CACHE = 'ng-auth';
const AUTH_CACHE_KEY = '/_internal/auth-token';

// Mesh sync constants
const MESH_DB_NAME = 'ng-mesh';
const MESH_STORE_NAME = 'messages';
const TRIAGE_DB_NAME = 'ng-mesh-triage';
const TRIAGE_STORE_NAME = 'tickets';

interface QueuedRequest {
	id: string;
	method: string;
	path: string;
	body: unknown;
	authToken: string | null;
	label: string;
	retryCount?: number;
}

interface ReplayOutcome {
	id: string;
	ok: boolean;
	status: number;
	label: string;
	detail?: string;
}

self.addEventListener('message', (event) => {
	if (event.data?.type === 'mesh-queue-updated') {
		// Register a Background Sync so mesh messages get flushed even if tab closes
		(self.registration as any).sync?.register?.('ng-mesh-sync').catch(() => {});
	}
});

self.addEventListener('sync', (event: ExtendableEvent) => {
	const tag = (event as any).tag;
	if (tag === 'ng-flush-queue') {
		event.waitUntil(flushOfflineQueue());
	} else if (tag === 'ng-mesh-sync') {
		event.waitUntil(flushMeshQueue());
	}
});

/** Ask open tabs to do the work instead; returns false when no tab is open. */
async function delegateToClient(type: string): Promise<boolean> {
	const clients = await self.clients.matchAll({ type: 'window' });
	for (const client of clients) client.postMessage({ type });
	return clients.length > 0;
}

async function detailOf(res: Response): Promise<string> {
	try {
		const body = await res.json();
		if (typeof body?.detail === 'string') return body.detail;
	} catch {
		// not JSON
	}
	return res.statusText || `HTTP ${res.status}`;
}

async function flushOfflineQueue(): Promise<void> {
	if (await delegateToClient('ng-flush-request')) return;

	const cache = await caches.open(QUEUE_CACHE);
	const response = await cache.match(QUEUE_CACHE_KEY);
	if (!response) return;

	let queue: QueuedRequest[];
	try {
		queue = await response.json();
	} catch {
		return;
	}
	if (!queue || queue.length === 0) return;

	const remaining: QueuedRequest[] = [];
	const outcomes: ReplayOutcome[] = [];

	for (const req of queue) {
		try {
			const headers: Record<string, string> = {};
			if (req.method !== 'DELETE') {
				headers['Content-Type'] = 'application/json';
			}
			if (req.authToken) {
				headers['Authorization'] = `Bearer ${req.authToken}`;
			}
			const res = await fetch(`/api${req.path}`, {
				method: req.method,
				headers,
				body: req.method !== 'DELETE' ? JSON.stringify(req.body) : undefined
			});

			if (res.ok) {
				outcomes.push({ id: req.id, ok: true, status: res.status, label: req.label });
			} else if (res.status >= 400 && res.status < 500) {
				// Client error — retrying won't help; the next tab tells the user
				outcomes.push({ id: req.id, ok: false, status: res.status, label: req.label, detail: await detailOf(res) });
			} else {
				const retries = (req.retryCount ?? 0) + 1;
				if (retries < MAX_RETRIES) {
					remaining.push({ ...req, retryCount: retries });
				} else {
					outcomes.push({ id: req.id, ok: false, status: res.status, label: req.label });
				}
			}
		} catch {
			const retries = (req.retryCount ?? 0) + 1;
			if (retries < MAX_RETRIES) {
				remaining.push({ ...req, retryCount: retries });
			} else {
				outcomes.push({ id: req.id, ok: false, status: 0, label: req.label });
			}
		}
	}

	// Record what was handled so a tab never replays it again
	let previous: ReplayOutcome[] = [];
	try {
		previous = (await (await cache.match(DONE_CACHE_KEY))?.json()) ?? [];
	} catch {
		previous = [];
	}
	await cache.put(
		DONE_CACHE_KEY,
		new Response(JSON.stringify([...previous, ...outcomes]), {
			headers: { 'Content-Type': 'application/json' }
		})
	);

	// Write back remaining items (or delete cache entry if empty)
	if (remaining.length > 0) {
		await cache.put(
			QUEUE_CACHE_KEY,
			new Response(JSON.stringify(remaining), {
				headers: { 'Content-Type': 'application/json' }
			})
		);
	} else {
		await cache.delete(QUEUE_CACHE_KEY);
	}

	// A tab may have opened meanwhile; it reconciles with DONE_CACHE_KEY
	const clients = await self.clients.matchAll();
	for (const client of clients) {
		client.postMessage({ type: 'ng-queue-flushed', remaining: remaining.length });
	}
}

// ── Mesh Background Sync ──────────────────────────────────────────────────────

async function readAuthToken(): Promise<string | null> {
	try {
		const res = await (await caches.open(AUTH_CACHE)).match(AUTH_CACHE_KEY);
		const body = res ? await res.json() : null;
		return typeof body?.token === 'string' ? body.token : null;
	} catch {
		return null;
	}
}

async function flushMeshQueue(): Promise<void> {
	if (await delegateToClient('ng-mesh-sync-request')) return;

	// Read mesh messages from IndexedDB
	let messages: Array<{ id: string; type: string }>;
	try {
		messages = (await readMeshMessagesFromIDB()) as Array<{ id: string; type: string }>;
	} catch {
		return;
	}
	if (!messages || messages.length === 0) return;

	// Logged out: nothing may be synced (logout also wipes the queue)
	const authToken = await readAuthToken();
	if (!authToken) return;

	const confirmed: string[] = [];
	const confirmedTickets: string[] = [];
	try {
		// The API accepts at most 100 messages per request. Messages the server
		// reported as failed stay queued; everything else in a batch that got
		// a response (synced, duplicate or refused by policy) is done.
		for (let i = 0; i < messages.length; i += 100) {
			const batch = messages.slice(i, i + 100);
			const res = await fetch('/api/mesh/sync', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${authToken}`
				},
				body: JSON.stringify({ messages: batch })
			});
			if (!res.ok) break;
			const result = await res.json().catch(() => null);
			if (!result) break;
			const failed = new Set<string>(
				Array.isArray(result.failed_ids) ? result.failed_ids : result.errors > 0 ? batch.map((m) => m.id) : []
			);
			for (const m of batch) {
				if (failed.has(m.id)) continue;
				confirmed.push(m.id);
				if (m.type === 'emergency_ticket') confirmedTickets.push(m.id);
			}
		}
	} catch {
		// Network still unavailable — Background Sync will retry
	}

	if (confirmed.length === 0) return;
	await deleteFromIDB(MESH_DB_NAME, MESH_STORE_NAME, confirmed).catch(() => {});
	await deleteFromIDB(TRIAGE_DB_NAME, TRIAGE_STORE_NAME, confirmedTickets).catch(() => {});
	const clients = await self.clients.matchAll();
	for (const client of clients) {
		client.postMessage({ type: 'ng-mesh-synced', ids: confirmed });
	}
}

function readMeshMessagesFromIDB(): Promise<unknown[]> {
	return new Promise((resolve, reject) => {
		const request = indexedDB.open(MESH_DB_NAME, 1);
		request.onupgradeneeded = () => {
			const db = request.result;
			if (!db.objectStoreNames.contains(MESH_STORE_NAME)) {
				db.createObjectStore(MESH_STORE_NAME, { keyPath: 'id' });
			}
		};
		request.onsuccess = () => {
			const db = request.result;
			try {
				const tx = db.transaction(MESH_STORE_NAME, 'readonly');
				const store = tx.objectStore(MESH_STORE_NAME);
				const getAll = store.getAll();
				getAll.onsuccess = () => {
					db.close();
					resolve(getAll.result);
				};
				getAll.onerror = () => {
					db.close();
					reject(getAll.error);
				};
			} catch {
				db.close();
				resolve([]);
			}
		};
		request.onerror = () => reject(request.error);
	});
}

/** Delete rows by key from an existing store (no-op if the database or store is missing). */
function deleteFromIDB(dbName: string, storeName: string, ids: string[]): Promise<void> {
	if (ids.length === 0) return Promise.resolve();
	return new Promise((resolve, reject) => {
		const request = indexedDB.open(dbName);
		request.onupgradeneeded = () => {
			// The database did not exist: nothing to delete. Abort so we don't
			// create it with a schema its owner module doesn't expect.
			request.transaction?.abort();
		};
		request.onsuccess = () => {
			const db = request.result;
			if (!db.objectStoreNames.contains(storeName)) {
				db.close();
				resolve();
				return;
			}
			const tx = db.transaction(storeName, 'readwrite');
			const store = tx.objectStore(storeName);
			for (const id of ids) store.delete(id);
			tx.oncomplete = () => {
				db.close();
				resolve();
			};
			tx.onerror = () => {
				db.close();
				reject(tx.error);
			};
		};
		request.onerror = () => resolve();
	});
}
