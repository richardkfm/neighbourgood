/**
 * Mesh networking store — manages BLE connection state and message routing
 * for offline crisis communication via BitChat gateway.
 */

import { writable, derived, get } from 'svelte/store';
import { t } from 'svelte-i18n';
import {
	isBluetoothSupported,
	scanForBitchatNode,
	connectToNode,
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
	decodeNGMessageWithTTL,
	createNGMessage,
	createBitchatPacket,
	fragmentPacket,
	isFragmentPacket,
	FragmentReassembler,
	validateNGMessage,
	type NGMeshMessage,
	type MeshTicketData,
	type MeshVoteData,
	type MeshResourceData,
	type MeshCheckinData
} from '$lib/bluetooth/protocol';
import { api } from '$lib/api';
import { user } from '$lib/stores/auth';
import type { MeshSyncResult } from '$lib/types';
import { putMessage, deleteMessages, loadMessages, clearMessages } from '$lib/mesh-db';
import {
	saveOfflineTicket,
	addCommentToTicket,
	deleteOfflineTickets,
	clearOfflineTickets,
	type OfflineTicket,
	type OfflineTicketComment
} from '$lib/mesh-triage-db';
import { signMeshMessage } from '$lib/mesh-keys';

export type MeshStatus = 'disconnected' | 'scanning' | 'connecting' | 'connected' | 'reconnecting';

// ── Stores ────────────────────────────────────────────────────────────────────

export const meshStatus = writable<MeshStatus>('disconnected');
export const meshDeviceName = writable<string | null>(null);
export const meshMessages = writable<NGMeshMessage[]>([]);
export const meshPeers = writable<Set<string>>(new Set());

export const meshIsSupported = derived(meshStatus, () => isBluetoothSupported());
export const meshPeerCount = derived(meshPeers, (peers) => peers.size);

/** Whether to relay received messages to expand mesh range. Opt-in to save battery. */
export const meshRelayEnabled = writable<boolean>(false);
/** Count of messages relayed in this session. */
export const meshRelayCount = writable<number>(0);

/** Ack status for sent messages: message ID → 'pending' | 'acked' */
export const meshAckStatus = writable<Map<string, 'pending' | 'acked'>>(new Map());

// Deduplication: track seen message IDs (sliding window of last 500)
const seenIds = new Set<string>();
const MAX_SEEN = 500;

/** Puts fragmented packets (larger than one BLE write) back together. */
const reassembler = new FragmentReassembler();

let unsubMessage: (() => void) | null = null;
let unsubDisconnect: (() => void) | null = null;

const MAX_RECONNECT_ATTEMPTS = 3;
const RECONNECT_BASE_DELAY_MS = 1000;

/** Heartbeats announce this device to nearby peers while the mesh page is open. */
export const HEARTBEAT_INTERVAL_MS = 30_000;
let heartbeatTimer: ReturnType<typeof setInterval> | null = null;

// Messages that are persisted server-side get signed; heartbeats/acks are not synced
const UNSIGNED_TYPES = new Set(['heartbeat', 'ack']);

// ── Actions ───────────────────────────────────────────────────────────────────

/** Connect to a nearby BitChat node. Prompts the user with Chrome device picker. */
export async function connectToMesh(): Promise<void> {
	if (!isBluetoothSupported()) {
		throw new Error(get(t)('mesh.not_supported'));
	}

	try {
		meshStatus.set('scanning');
		const device = await scanForBitchatNode();

		meshStatus.set('connecting');
		await connectToNode(device);

		meshDeviceName.set(getDeviceName());
		meshStatus.set('connected');

		await restoreMeshMessages();

		subscribeToEvents();
	} catch (err) {
		meshStatus.set('disconnected');
		meshDeviceName.set(null);
		cleanup();
		throw err;
	}
}

/**
 * Recover messages persisted to IndexedDB by a previous session, and remember
 * their IDs so the same messages re-delivered over the mesh are not queued twice.
 */
export async function restoreMeshMessages(): Promise<void> {
	try {
		// Re-validate: rows persisted by an older build may be malformed
		const persisted = (await loadMessages())
			.map((m) => validateNGMessage(m))
			.filter((m): m is NGMeshMessage => m !== null)
			// IndexedDB returns rows ordered by ID; restore arrival order
			.sort((a, b) => a.ts - b.ts);
		if (persisted.length === 0) return;
		for (const m of persisted) addSeenId(m.id);
		meshMessages.update((msgs) => {
			const existingIds = new Set(msgs.map((m) => m.id));
			const newMsgs = persisted.filter((m) => !existingIds.has(m.id));
			return newMsgs.length > 0 ? [...msgs, ...newMsgs] : msgs;
		});
	} catch {
		// IndexedDB unavailable — continue without recovery
	}
}

/** The server accepts at most this many messages per /mesh/sync request. */
const MESH_SYNC_BATCH_SIZE = 100;

/**
 * Upload queued mesh messages to the server in batches (a single request with
 * more than 100 messages is rejected outright). Only the messages that were
 * actually sent and not reported as failed are removed from the queue —
 * anything received while the request was in flight, and anything the server
 * reported as failed, is kept. Confirmed tickets are also removed from the
 * offline triage view (they are on the server now). Returns null when there
 * was nothing to sync.
 */
export async function syncMeshMessagesToServer(): Promise<MeshSyncResult | null> {
	const sending = get(meshMessages);
	if (sending.length === 0) return null;

	const total: MeshSyncResult = { synced: 0, verified: 0, duplicates: 0, errors: 0, rejected: 0 };
	const failed = new Set<string>();
	let lastBatchEnd = 0;
	try {
		for (let i = 0; i < sending.length; i += MESH_SYNC_BATCH_SIZE) {
			const batch = sending.slice(i, i + MESH_SYNC_BATCH_SIZE);
			const result = await api<MeshSyncResult>('/mesh/sync', {
				method: 'POST',
				body: { messages: batch },
				auth: true
			});
			total.synced += result.synced;
			total.verified = (total.verified ?? 0) + (result.verified ?? 0);
			total.duplicates += result.duplicates;
			total.errors += result.errors;
			total.rejected = (total.rejected ?? 0) + (result.rejected ?? 0);
			if (result.errors > 0) {
				if (result.failed_ids) {
					result.failed_ids.forEach((id) => failed.add(id));
				} else {
					// Older server without per-message results: keep the whole batch
					batch.forEach((m) => failed.add(m.id));
				}
			}
			lastBatchEnd = i + batch.length;
		}
	} finally {
		// Even if a later batch failed (network/HTTP error), drop what was confirmed
		const confirmed = sending.slice(0, lastBatchEnd).filter((m) => !failed.has(m.id));
		if (confirmed.length > 0) {
			removeMeshMessages(confirmed.map((m) => m.id));
			const tickets = confirmed.filter((m) => m.type === 'emergency_ticket').map((m) => m.id);
			deleteOfflineTickets(tickets).catch(() => {});
		}
	}
	return total;
}

/** Remove specific messages (e.g. after they were synced) from the queue. */
export function removeMeshMessages(ids: string[]): void {
	const drop = new Set(ids);
	meshMessages.set(get(meshMessages).filter((m) => !drop.has(m.id)));
	deleteMessages(ids).catch(() => {});
	notifyServiceWorker();
}

/** Disconnect from the current BitChat node (manual — prevents auto-reconnect). */
export function disconnectFromMesh(): void {
	stopHeartbeat();
	forgetDevice();
	meshStatus.set('disconnected');
	meshDeviceName.set(null);
	cleanup();
}

/** Write one packet, split into MTU-sized fragments when it does not fit one write. */
async function sendPacket(packet: Uint8Array): Promise<void> {
	for (const part of fragmentPacket(packet)) {
		await sendMessage(part);
	}
}

/**
 * Send an NG message through the BLE mesh. Messages the server will store are
 * signed with this browser's key first, so relays cannot alter them and the
 * server attributes them to their author. Returns the message as sent.
 */
export async function sendViaMesh(msg: NGMeshMessage): Promise<NGMeshMessage> {
	const outgoing = UNSIGNED_TYPES.has(msg.type) ? msg : await signMeshMessage(msg, get(user)?.id);
	await sendPacket(encodeNGMessage(outgoing));
	// Track our own message to avoid processing it as incoming
	addSeenId(outgoing.id);

	// Track ack status for non-heartbeat, non-ack messages (stays 'pending' until acked)
	if (!UNSIGNED_TYPES.has(outgoing.type)) {
		meshAckStatus.update((m) => {
			const next = new Map(m);
			next.set(outgoing.id, 'pending');
			return next;
		});
	}
	return outgoing;
}

/** Broadcast an emergency ticket through the mesh. */
export async function broadcastEmergencyTicket(
	communityId: number,
	senderName: string,
	ticket: MeshTicketData
): Promise<NGMeshMessage> {
	return sendViaMesh(createNGMessage('emergency_ticket', communityId, senderName, { ...ticket }));
}

/** Broadcast a crisis vote through the mesh. */
export async function broadcastCrisisVote(
	communityId: number,
	senderName: string,
	vote: MeshVoteData
): Promise<NGMeshMessage> {
	return sendViaMesh(createNGMessage('crisis_vote', communityId, senderName, { ...vote }));
}

/** Broadcast a resource request through the mesh. */
export async function broadcastResourceRequest(
	communityId: number,
	senderName: string,
	resource: MeshResourceData
): Promise<NGMeshMessage> {
	return sendViaMesh(createNGMessage('resource_request', communityId, senderName, { ...resource }));
}

/** Broadcast a resource offer through the mesh. */
export async function broadcastResourceOffer(
	communityId: number,
	senderName: string,
	resource: MeshResourceData
): Promise<NGMeshMessage> {
	return sendViaMesh(createNGMessage('resource_offer', communityId, senderName, { ...resource }));
}

/** Broadcast a location check-in through the mesh. */
export async function broadcastCheckin(
	communityId: number,
	senderName: string,
	checkin: MeshCheckinData
): Promise<NGMeshMessage> {
	return sendViaMesh(createNGMessage('location_checkin', communityId, senderName, { ...checkin }));
}

/** Broadcast a heartbeat to announce presence. */
export async function broadcastHeartbeat(
	communityId: number,
	senderName: string
): Promise<void> {
	await sendViaMesh(createNGMessage('heartbeat', communityId, senderName, {}));
}

/**
 * Announce this device now and then every HEARTBEAT_INTERVAL_MS until
 * stopHeartbeat() (or a disconnect). Restarting replaces the previous timer.
 */
export function startHeartbeat(communityId: number, senderName: string): void {
	stopHeartbeat();
	const beat = () => {
		if (get(meshStatus) !== 'connected') return;
		broadcastHeartbeat(communityId, senderName).catch(() => {});
	};
	beat();
	heartbeatTimer = setInterval(beat, HEARTBEAT_INTERVAL_MS);
}

export function stopHeartbeat(): void {
	if (heartbeatTimer) {
		clearInterval(heartbeatTimer);
		heartbeatTimer = null;
	}
}

/** Clear all stored mesh messages (e.g. after syncing to server). */
export function clearMeshMessages(): void {
	meshMessages.set([]);
	clearMessages().catch(() => {});
	// Notify service worker that the queue is now empty
	notifyServiceWorker();
}

/**
 * Forget everything mesh-related on this device (on logout), so the next user
 * of the browser neither sees nor syncs the previous user's mesh data.
 */
export async function clearAllMeshData(): Promise<void> {
	disconnectFromMesh();
	meshMessages.set([]);
	meshPeers.set(new Set());
	meshAckStatus.set(new Map());
	meshRelayCount.set(0);
	seenIds.clear();
	reassembler.clear();
	await Promise.allSettled([clearMessages(), clearOfflineTickets()]);
}

/** Get current mesh messages snapshot. */
export function getMeshMessages(): NGMeshMessage[] {
	return get(meshMessages);
}

/** Toggle relay mode on/off. */
export function toggleRelay(): void {
	meshRelayEnabled.update((v) => !v);
}

/** Get relay stats. */
export function getRelayCount(): number {
	return get(meshRelayCount);
}

// ── Internals ─────────────────────────────────────────────────────────────────

function handlePacket(raw: DataView): void {
	let data = raw;
	if (isFragmentPacket(raw)) {
		const full = reassembler.push(raw);
		if (!full) return; // waiting for more fragments (or dropped)
		data = new DataView(full.buffer, full.byteOffset, full.byteLength);
	}

	const decoded = decodeNGMessageWithTTL(data);
	if (!decoded) return; // Not an NG message, ignore

	const { message: msg, ttl } = decoded;

	// Deduplicate
	if (seenIds.has(msg.id)) return;
	addSeenId(msg.id);

	if (msg.type === 'ack') {
		// Process incoming ack — mark our sent message as acknowledged
		const ackFor = msg.data?.ack_for;
		if (typeof ackFor === 'string') {
			meshAckStatus.update((m) => {
				if (m.has(ackFor)) {
					const next = new Map(m);
					next.set(ackFor, 'acked');
					return next;
				}
				return m;
			});
		}
	} else if (msg.type === 'heartbeat') {
		meshPeers.update((peers) => {
			const next = new Set(peers);
			next.add(msg.sender_name);
			return next;
		});
	} else {
		meshMessages.update((msgs) => [...msgs, msg]);
		// Persist to IndexedDB (fire-and-forget, one row per message)
		putMessage(msg).catch(() => {});
		notifyServiceWorker();

		// Persist emergency tickets/comments to offline triage DB
		if (msg.type === 'emergency_ticket') {
			const data = msg.data;
			const ticket: OfflineTicket = {
				id: msg.id,
				community_id: msg.community_id,
				sender_name: msg.sender_name,
				title: String(data.title || ''),
				description: String(data.description || ''),
				ticket_type: (data.ticket_type as OfflineTicket['ticket_type']) || 'request',
				urgency: (data.urgency as OfflineTicket['urgency']) || 'medium',
				ts: msg.ts,
				comments: []
			};
			saveOfflineTicket(ticket).catch(() => {});
		} else if (msg.type === 'ticket_comment') {
			const data = msg.data;
			const comment: OfflineTicketComment = {
				id: msg.id,
				sender_name: msg.sender_name,
				body: String(data.body || ''),
				ts: msg.ts
			};
			const ticketId = data.ticket_mesh_id;
			if (typeof ticketId === 'string' && ticketId) {
				addCommentToTicket(ticketId, comment).catch(() => {});
			}
		}

		// Auto-send ack for non-heartbeat messages
		sendAck(msg.community_id, msg.id);
	}

	// Multi-hop relay: re-broadcast with decremented TTL if enabled (skip acks)
	if (get(meshRelayEnabled) && ttl > 1 && msg.type !== 'ack') {
		relayMessage(msg, ttl - 1);
	}
}

function subscribeToEvents(): void {
	// Subscribe to incoming BLE messages
	unsubMessage = onMessage(handlePacket);

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
	reassembler.clear();
}

/** Send an acknowledgment for a received message. */
async function sendAck(communityId: number, ackForId: string): Promise<void> {
	try {
		const ackMsg = createNGMessage('ack', communityId, 'system', { ack_for: ackForId });
		await sendPacket(encodeNGMessage(ackMsg));
		addSeenId(ackMsg.id);
	} catch {
		// Ack send failed — not critical
	}
}

/** Re-broadcast a received message with decremented TTL for multi-hop relay. */
async function relayMessage(msg: NGMeshMessage, newTtl: number): Promise<void> {
	try {
		// Relayed unchanged, signature included, so the server can still verify it
		const json = 'ng:' + JSON.stringify(msg);
		const payloadBytes = new TextEncoder().encode(json);
		await sendPacket(createBitchatPacket(payloadBytes, newTtl));
		meshRelayCount.update((n) => n + 1);
	} catch {
		// Relay failed silently — not critical
	}
}

function notifyServiceWorker(): void {
	try {
		navigator.serviceWorker?.controller?.postMessage({ type: 'mesh-queue-updated' });
	} catch {
		// SW not available
	}
}
