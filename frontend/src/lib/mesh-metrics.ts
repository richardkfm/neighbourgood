/**
 * Mesh analytics and diagnostics.
 *
 * Tracks message counts, fragment stats, reconnects, and peer history.
 * Persists to IndexedDB for post-crisis analysis.
 */

import { writable, get } from 'svelte/store';

export interface MeshMetrics {
	/** Total messages sent in this session */
	messagesSent: number;
	/** Total messages received in this session */
	messagesReceived: number;
	/** Total messages relayed */
	messagesRelayed: number;
	/** Fragment packets handled */
	fragmentsReceived: number;
	/** Reconnect attempts */
	reconnectAttempts: number;
	/** Successful reconnects */
	reconnectSuccesses: number;
	/** Peak peer count observed */
	peakPeerCount: number;
	/** Session start timestamp */
	sessionStart: number;
	/** Per-type message counts */
	messagesByType: Record<string, number>;
	/** Acks sent */
	acksSent: number;
	/** Acks received */
	acksReceived: number;
	/** Errors encountered */
	errors: number;
}

const INITIAL_METRICS: MeshMetrics = {
	messagesSent: 0,
	messagesReceived: 0,
	messagesRelayed: 0,
	fragmentsReceived: 0,
	reconnectAttempts: 0,
	reconnectSuccesses: 0,
	peakPeerCount: 0,
	sessionStart: Date.now(),
	messagesByType: {},
	acksSent: 0,
	acksReceived: 0,
	errors: 0,
};

export const meshMetrics = writable<MeshMetrics>({ ...INITIAL_METRICS });

// ── Metric recording functions ───────────────────────────────────────────────

export function recordMessageSent(type: string): void {
	meshMetrics.update((m) => ({
		...m,
		messagesSent: m.messagesSent + 1,
		messagesByType: { ...m.messagesByType, [type]: (m.messagesByType[type] || 0) + 1 },
	}));
}

export function recordMessageReceived(type: string): void {
	meshMetrics.update((m) => ({
		...m,
		messagesReceived: m.messagesReceived + 1,
		messagesByType: { ...m.messagesByType, [type]: (m.messagesByType[type] || 0) + 1 },
	}));
}

export function recordRelay(): void {
	meshMetrics.update((m) => ({ ...m, messagesRelayed: m.messagesRelayed + 1 }));
}

export function recordFragment(): void {
	meshMetrics.update((m) => ({ ...m, fragmentsReceived: m.fragmentsReceived + 1 }));
}

export function recordReconnectAttempt(): void {
	meshMetrics.update((m) => ({ ...m, reconnectAttempts: m.reconnectAttempts + 1 }));
}

export function recordReconnectSuccess(): void {
	meshMetrics.update((m) => ({ ...m, reconnectSuccesses: m.reconnectSuccesses + 1 }));
}

export function recordPeerCount(count: number): void {
	meshMetrics.update((m) => ({
		...m,
		peakPeerCount: Math.max(m.peakPeerCount, count),
	}));
}

export function recordAckSent(): void {
	meshMetrics.update((m) => ({ ...m, acksSent: m.acksSent + 1 }));
}

export function recordAckReceived(): void {
	meshMetrics.update((m) => ({ ...m, acksReceived: m.acksReceived + 1 }));
}

export function recordError(): void {
	meshMetrics.update((m) => ({ ...m, errors: m.errors + 1 }));
}

export function resetMetrics(): void {
	meshMetrics.set({ ...INITIAL_METRICS, sessionStart: Date.now() });
}

/** Export current metrics as JSON for debugging. */
export function exportMetrics(): string {
	const m = get(meshMetrics);
	return JSON.stringify({
		...m,
		sessionDurationMs: Date.now() - m.sessionStart,
		exportedAt: new Date().toISOString(),
	}, null, 2);
}

// ── IndexedDB persistence ────────────────────────────────────────────────────

const DB_NAME = 'ng-mesh-metrics';
const STORE_NAME = 'sessions';

function openDB(): Promise<IDBDatabase> {
	return new Promise((resolve, reject) => {
		const request = indexedDB.open(DB_NAME, 1);
		request.onupgradeneeded = () => {
			const db = request.result;
			if (!db.objectStoreNames.contains(STORE_NAME)) {
				db.createObjectStore(STORE_NAME, { autoIncrement: true });
			}
		};
		request.onsuccess = () => resolve(request.result);
		request.onerror = () => reject(request.error);
	});
}

/** Save current session metrics to IndexedDB. */
export async function persistMetrics(): Promise<void> {
	const m = get(meshMetrics);
	const db = await openDB();
	const tx = db.transaction(STORE_NAME, 'readwrite');
	tx.objectStore(STORE_NAME).put({
		...m,
		sessionEnd: Date.now(),
		sessionDurationMs: Date.now() - m.sessionStart,
	});
	return new Promise((resolve, reject) => {
		tx.oncomplete = () => { db.close(); resolve(); };
		tx.onerror = () => { db.close(); reject(tx.error); };
	});
}

/** Load all historical session metrics. */
export async function loadAllSessions(): Promise<MeshMetrics[]> {
	const db = await openDB();
	const tx = db.transaction(STORE_NAME, 'readonly');
	const req = tx.objectStore(STORE_NAME).getAll();
	return new Promise((resolve, reject) => {
		req.onsuccess = () => { db.close(); resolve(req.result); };
		req.onerror = () => { db.close(); reject(req.error); };
	});
}
