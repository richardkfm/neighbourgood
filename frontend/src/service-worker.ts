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

const QUEUE_CACHE = 'ng-offline-queue';
const QUEUE_CACHE_KEY = '/_internal/offline-queue';
const MAX_RETRIES = 5;

// Mesh sync constants
const MESH_DB_NAME = 'ng-mesh';
const MESH_STORE_NAME = 'messages';

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

async function flushOfflineQueue(): Promise<void> {
	const cache = await caches.open(QUEUE_CACHE);
	const response = await cache.match(QUEUE_CACHE_KEY);
	if (!response) return;

	let queue: Array<{
		id: string;
		method: string;
		path: string;
		body: unknown;
		authToken: string | null;
		label: string;
		retryCount?: number;
	}>;
	try {
		queue = await response.json();
	} catch {
		return;
	}
	if (!queue || queue.length === 0) return;

	const remaining: typeof queue = [];

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
				// Success — drop from queue
			} else if (res.status >= 400 && res.status < 500) {
				// Client error — drop (retrying won't help)
			} else {
				const retries = (req.retryCount ?? 0) + 1;
				if (retries < MAX_RETRIES) {
					remaining.push({ ...req, retryCount: retries });
				}
			}
		} catch {
			const retries = (req.retryCount ?? 0) + 1;
			if (retries < MAX_RETRIES) {
				remaining.push({ ...req, retryCount: retries });
			}
		}
	}

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

	// Notify all clients to refresh their queue store
	const clients = await self.clients.matchAll();
	for (const client of clients) {
		client.postMessage({ type: 'ng-queue-flushed', remaining: remaining.length });
	}
}

// ── Mesh Background Sync ──────────────────────────────────────────────────────

async function flushMeshQueue(): Promise<void> {
	// Read mesh messages from IndexedDB
	let messages: unknown[];
	try {
		messages = await readMeshMessagesFromIDB();
	} catch {
		return;
	}
	if (!messages || messages.length === 0) return;

	// Get auth token from the offline queue cache (piggybacking on existing pattern)
	// or from any queued request that has one
	let authToken: string | null = null;
	try {
		const queueCache = await caches.open(QUEUE_CACHE);
		const queueResp = await queueCache.match(QUEUE_CACHE_KEY);
		if (queueResp) {
			const queue = await queueResp.json();
			authToken = queue?.[0]?.authToken ?? null;
		}
	} catch {
		// No token available — can't sync without auth
	}

	if (!authToken) return;

	try {
		// The API accepts at most 100 messages per request. Only wipe the local
		// queue when every batch succeeded AND the server reported no per-message
		// errors — an HTTP 200 alone can still mean some messages were rejected.
		let allOk = true;
		for (let i = 0; i < messages.length; i += 100) {
			const res = await fetch('/api/mesh/sync', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${authToken}`
				},
				body: JSON.stringify({ messages: messages.slice(i, i + 100) })
			});
			if (!res.ok) {
				allOk = false;
				break;
			}
			const result = await res.json().catch(() => null);
			if (!result || result.errors !== 0) allOk = false;
		}

		if (allOk) {
			// Clear IndexedDB on success
			await clearMeshMessagesFromIDB();
			// Notify clients
			const clients = await self.clients.matchAll();
			for (const client of clients) {
				client.postMessage({ type: 'ng-mesh-synced' });
			}
		}
	} catch {
		// Network still unavailable — Background Sync will retry
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

function clearMeshMessagesFromIDB(): Promise<void> {
	return new Promise((resolve, reject) => {
		const request = indexedDB.open(MESH_DB_NAME, 1);
		request.onsuccess = () => {
			const db = request.result;
			try {
				const tx = db.transaction(MESH_STORE_NAME, 'readwrite');
				tx.objectStore(MESH_STORE_NAME).clear();
				tx.oncomplete = () => {
					db.close();
					resolve();
				};
				tx.onerror = () => {
					db.close();
					reject(tx.error);
				};
			} catch {
				db.close();
				resolve();
			}
		};
		request.onerror = () => reject(request.error);
	});
}
