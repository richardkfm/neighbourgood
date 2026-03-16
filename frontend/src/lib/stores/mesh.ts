/**
 * Mesh networking store — manages BLE connection state and message routing
 * for offline crisis communication via BitChat gateway.
 */

import { writable, derived, get } from 'svelte/store';
import {
	isBluetoothSupported,
	scanForBitchatNode,
	connectToNode,
	disconnect as bleDisconnect,
	forgetDevice,
	hasLastDevice,
	reconnectToLastDevice,
	sendMessage,
	onMessage,
	onDisconnect,
	getDeviceName
} from '$lib/bluetooth/connection';
import {
	encodeNGMessage,
	decodeNGMessage,
	createNGMessage,
	type NGMeshMessage,
	type NGMeshMessageType,
	type MeshTicketData,
	type MeshVoteData,
	type MeshResourceData
} from '$lib/bluetooth/protocol';
import { persistMessages, loadMessages, clearMessages } from '$lib/mesh-db';

export type MeshStatus = 'disconnected' | 'scanning' | 'connecting' | 'connected' | 'reconnecting';

// ── Stores ────────────────────────────────────────────────────────────────────

export const meshStatus = writable<MeshStatus>('disconnected');
export const meshDeviceName = writable<string | null>(null);
export const meshMessages = writable<NGMeshMessage[]>([]);
export const meshPeers = writable<Set<string>>(new Set());

export const meshIsSupported = derived(meshStatus, () => isBluetoothSupported());
export const meshPeerCount = derived(meshPeers, (peers) => peers.size);

// Deduplication: track seen message IDs (sliding window of last 500)
const seenIds = new Set<string>();
const MAX_SEEN = 500;

let unsubMessage: (() => void) | null = null;
let unsubDisconnect: (() => void) | null = null;

const MAX_RECONNECT_ATTEMPTS = 3;
const RECONNECT_BASE_DELAY_MS = 1000;

// ── Actions ───────────────────────────────────────────────────────────────────

/** Connect to a nearby BitChat node. Prompts the user with Chrome device picker. */
export async function connectToMesh(): Promise<void> {
	if (!isBluetoothSupported()) {
		throw new Error('Web Bluetooth not supported');
	}

	try {
		meshStatus.set('scanning');
		const device = await scanForBitchatNode();

		meshStatus.set('connecting');
		await connectToNode(device);

		meshDeviceName.set(getDeviceName());
		meshStatus.set('connected');

		// Recover any persisted messages from a previous session
		try {
			const persisted = await loadMessages();
			if (persisted.length > 0) {
				meshMessages.update((msgs) => {
					const existingIds = new Set(msgs.map((m) => m.id));
					const newMsgs = persisted.filter((m) => !existingIds.has(m.id));
					return [...msgs, ...newMsgs];
				});
			}
		} catch {
			// IndexedDB unavailable — continue without recovery
		}

		subscribeToEvents();
	} catch (err) {
		meshStatus.set('disconnected');
		meshDeviceName.set(null);
		cleanup();
		throw err;
	}
}

/** Disconnect from the current BitChat node (manual — prevents auto-reconnect). */
export function disconnectFromMesh(): void {
	forgetDevice();
	meshStatus.set('disconnected');
	meshDeviceName.set(null);
	cleanup();
}

/** Send an NG message through the BLE mesh. */
export async function sendViaMesh(msg: NGMeshMessage): Promise<void> {
	const packet = encodeNGMessage(msg);
	await sendMessage(packet);
	// Track our own message to avoid processing it as incoming
	addSeenId(msg.id);
}

/** Broadcast an emergency ticket through the mesh. */
export async function broadcastEmergencyTicket(
	communityId: number,
	senderName: string,
	ticket: MeshTicketData
): Promise<NGMeshMessage> {
	const msg = createNGMessage('emergency_ticket', communityId, senderName, ticket as unknown as Record<string, unknown>);
	await sendViaMesh(msg);
	return msg;
}

/** Broadcast a crisis vote through the mesh. */
export async function broadcastCrisisVote(
	communityId: number,
	senderName: string,
	vote: MeshVoteData
): Promise<NGMeshMessage> {
	const msg = createNGMessage('crisis_vote', communityId, senderName, vote as unknown as Record<string, unknown>);
	await sendViaMesh(msg);
	return msg;
}

/** Broadcast a resource request through the mesh. */
export async function broadcastResourceRequest(
	communityId: number,
	senderName: string,
	resource: MeshResourceData
): Promise<NGMeshMessage> {
	const msg = createNGMessage('resource_request', communityId, senderName, resource as unknown as Record<string, unknown>);
	await sendViaMesh(msg);
	return msg;
}

/** Broadcast a resource offer through the mesh. */
export async function broadcastResourceOffer(
	communityId: number,
	senderName: string,
	resource: MeshResourceData
): Promise<NGMeshMessage> {
	const msg = createNGMessage('resource_offer', communityId, senderName, resource as unknown as Record<string, unknown>);
	await sendViaMesh(msg);
	return msg;
}

/** Broadcast a heartbeat to announce presence. */
export async function broadcastHeartbeat(
	communityId: number,
	senderName: string
): Promise<void> {
	const msg = createNGMessage('heartbeat', communityId, senderName, {});
	await sendViaMesh(msg);
}

/** Clear all stored mesh messages (e.g. after syncing to server). */
export function clearMeshMessages(): void {
	meshMessages.set([]);
	clearMessages().catch(() => {});
	// Notify service worker that the queue is now empty
	notifyServiceWorker();
}

/** Get current mesh messages snapshot. */
export function getMeshMessages(): NGMeshMessage[] {
	return get(meshMessages);
}

// ── Internals ─────────────────────────────────────────────────────────────────

function subscribeToEvents(): void {
	// Subscribe to incoming BLE messages
	unsubMessage = onMessage((data: DataView) => {
		const msg = decodeNGMessage(data);
		if (!msg) return; // Not an NG message, ignore

		// Deduplicate
		if (seenIds.has(msg.id)) return;
		addSeenId(msg.id);

		if (msg.type === 'heartbeat') {
			meshPeers.update((peers) => {
				const next = new Set(peers);
				next.add(msg.sender_name);
				return next;
			});
		} else {
			meshMessages.update((msgs) => {
				const updated = [...msgs, msg];
				// Persist to IndexedDB (fire-and-forget)
				persistMessages(updated).catch(() => {});
				notifyServiceWorker();
				return updated;
			});
		}
	});

	// Handle unexpected disconnection — attempt auto-reconnect
	unsubDisconnect = onDisconnect(() => {
		cleanup();
		attemptReconnect();
	});
}

async function attemptReconnect(): Promise<void> {
	if (!hasLastDevice()) {
		meshStatus.set('disconnected');
		meshDeviceName.set(null);
		return;
	}

	meshStatus.set('reconnecting');

	for (let attempt = 0; attempt < MAX_RECONNECT_ATTEMPTS; attempt++) {
		const delay = RECONNECT_BASE_DELAY_MS * Math.pow(2, attempt);
		await sleep(delay);

		const success = await reconnectToLastDevice();
		if (success) {
			meshDeviceName.set(getDeviceName());
			meshStatus.set('connected');
			subscribeToEvents();
			return;
		}
	}

	// All retries failed
	forgetDevice();
	meshStatus.set('disconnected');
	meshDeviceName.set(null);
}

function sleep(ms: number): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

function addSeenId(id: string): void {
	if (seenIds.size >= MAX_SEEN) {
		// Remove oldest entries (Set iterates in insertion order)
		const iter = seenIds.values();
		const toRemove = seenIds.size - MAX_SEEN + 1;
		for (let i = 0; i < toRemove; i++) {
			seenIds.delete(iter.next().value!);
		}
	}
	seenIds.add(id);
}

function cleanup(): void {
	if (unsubMessage) {
		unsubMessage();
		unsubMessage = null;
	}
	if (unsubDisconnect) {
		unsubDisconnect();
		unsubDisconnect = null;
	}
}

function notifyServiceWorker(): void {
	try {
		navigator.serviceWorker?.controller?.postMessage({ type: 'mesh-queue-updated' });
	} catch {
		// SW not available
	}
}
