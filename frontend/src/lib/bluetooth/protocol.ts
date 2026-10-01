/**
 * BitChat message protocol codec for NeighbourGood.
 *
 * Encodes NG-specific data (emergency tickets, crisis votes, etc.) as
 * JSON payloads inside standard BitChat broadcast messages so native
 * BitChat nodes relay them without modification.
 *
 * Packet format (simplified for gateway leaf-node usage):
 *   [1 byte type] [1 byte TTL] [4 bytes message ID] [2 bytes payload length] [N bytes payload]
 *
 * We use type 0x01 = broadcast message.
 * Payload is UTF-8 encoded JSON prefixed with "ng:" to identify NeighbourGood messages.
 *
 * Fragment packet format (type 0x02):
 *   Standard 8-byte header, then payload:
 *   [4 bytes original msgId] [1 byte fragmentIndex] [1 byte totalFragments] [N bytes fragment data]
 *
 * Packets larger than one BLE write are split with fragmentPacket() on send and
 * put back together by a FragmentReassembler on receive (bounded memory,
 * incomplete sets dropped after a timeout).
 *
 * This module has no imports so it can be unit-tested under plain Node.
 */

const PACKET_TYPE_BROADCAST = 0x01;
const PACKET_TYPE_FRAGMENT = 0x02;
const DEFAULT_TTL = 7;
const NG_PREFIX = 'ng:';

/** Default BLE MTU minus ATT header (3 bytes) minus BitChat header (8 bytes). */
const DEFAULT_MAX_PAYLOAD = 174;

/** Fragment overhead: originalMsgId(4) + index(1) + total(1) = 6 bytes. */
const FRAGMENT_HEADER_SIZE = 6;

/** Incomplete fragment sets are dropped after this many milliseconds. */
export const FRAGMENT_TIMEOUT_MS = 15_000;
/** Most fragments one message may be split into (bounds per-set memory). */
export const MAX_FRAGMENTS_PER_MESSAGE = 128;
/** Most incomplete sets buffered at once; the oldest is evicted beyond this. */
export const MAX_PENDING_FRAGMENT_SETS = 32;
/** Most bytes buffered across all incomplete sets. */
export const MAX_BUFFERED_FRAGMENT_BYTES = 512 * 1024;

export type NGMeshMessageType =
	| 'emergency_ticket'
	| 'ticket_comment'
	| 'crisis_vote'
	| 'crisis_status'
	| 'direct_message'
	| 'heartbeat'
	| 'resource_request'
	| 'resource_offer'
	| 'location_checkin'
	| 'ack';

export interface NGMeshMessage {
	ng: 1;
	type: NGMeshMessageType;
	community_id: number;
	sender_name: string;
	ts: number;
	id: string;
	data: Record<string, unknown>;
	/** Signature fields (see signing.ts); absent on unsigned messages. */
	author_user_id?: number;
	key_id?: string;
	sig?: string;
}

export interface MeshTicketData {
	title: string;
	description: string;
	ticket_type: 'request' | 'offer' | 'emergency_ping';
	urgency: 'low' | 'medium' | 'high' | 'critical';
	/** Same UUID as the REST create of this ticket, so the server never duplicates it. */
	client_id?: string;
}

export interface MeshCommentData {
	ticket_mesh_id: string;
	body: string;
}

export interface MeshVoteData {
	vote_type: 'activate' | 'deactivate';
}

export interface MeshCrisisStatusData {
	new_mode: 'blue' | 'red';
}

export interface MeshDirectMessageData {
	recipient_id: number;
	body: string;
}

export interface MeshResourceData {
	title: string;
	description: string;
	category: string;
	quantity?: number;
}

export interface MeshCheckinData {
	lat: number;
	lng: number;
	status: 'safe' | 'need_help' | 'evacuating';
	note?: string;
}

export interface MeshAckData {
	/** The message ID being acknowledged. */
	ack_for: string;
}

const encoder = new TextEncoder();
const decoder = new TextDecoder();

/** Create a new NG mesh message with auto-generated ID and timestamp. */
export function createNGMessage(
	type: NGMeshMessageType,
	communityId: number,
	senderName: string,
	data: Record<string, unknown>
): NGMeshMessage {
	return {
		ng: 1,
		type,
		community_id: communityId,
		sender_name: senderName,
		ts: Date.now(),
		id: crypto.randomUUID(),
		data
	};
}

/** Encode an NG message into a BitChat-compatible binary packet. */
export function encodeNGMessage(msg: NGMeshMessage): Uint8Array {
	const json = NG_PREFIX + JSON.stringify(msg);
	const payloadBytes = encoder.encode(json);
	return createBitchatPacket(payloadBytes, DEFAULT_TTL);
}

export interface DecodedNGMessage {
	message: NGMeshMessage;
	ttl: number;
}

/** Decode incoming BLE data into an NG message, or null if not NG format. */
export function decodeNGMessage(raw: DataView): NGMeshMessage | null {
	const result = decodeNGMessageWithTTL(raw);
	return result?.message ?? null;
}

/** Decode incoming BLE data into an NG message with TTL info for relay. */
export function decodeNGMessageWithTTL(raw: DataView): DecodedNGMessage | null {
	const parsed = parseBitchatPacket(raw);
	if (!parsed) return null;

	const text = decoder.decode(parsed.payload);
	if (!text.startsWith(NG_PREFIX)) return null;

	try {
		const message = validateNGMessage(JSON.parse(text.slice(NG_PREFIX.length)));
		return message ? { message, ttl: parsed.ttl } : null;
	} catch {
		return null;
	}
}

const NG_MESSAGE_TYPES: ReadonlySet<string> = new Set<NGMeshMessageType>([
	'emergency_ticket',
	'ticket_comment',
	'crisis_vote',
	'crisis_status',
	'direct_message',
	'heartbeat',
	'resource_request',
	'resource_offer',
	'location_checkin',
	'ack'
]);

/**
 * Validate and normalise an untrusted decoded JSON value into an NGMeshMessage.
 * Anything any nearby BLE device broadcasts ends up here, so a missing or
 * wrongly typed field must never reach the UI (a message without `data` used to
 * crash the mesh pages on every render) or the server sync payload.
 * Returns null when the value is not a usable NG message.
 */
export function validateNGMessage(obj: unknown): NGMeshMessage | null {
	if (typeof obj !== 'object' || obj === null || Array.isArray(obj)) return null;
	const o = obj as Record<string, unknown>;
	if (o.ng !== 1) return null;
	if (typeof o.type !== 'string' || !NG_MESSAGE_TYPES.has(o.type)) return null;
	if (typeof o.id !== 'string' || o.id.length === 0 || o.id.length > 100) return null;
	if (typeof o.community_id !== 'number' || !Number.isInteger(o.community_id)) return null;
	const data =
		typeof o.data === 'object' && o.data !== null && !Array.isArray(o.data)
			? (o.data as Record<string, unknown>)
			: {};
	const msg: NGMeshMessage = {
		ng: 1,
		type: o.type as NGMeshMessageType,
		community_id: o.community_id,
		sender_name: typeof o.sender_name === 'string' ? o.sender_name.slice(0, 100) : 'Unknown',
		ts: typeof o.ts === 'number' && Number.isFinite(o.ts) ? o.ts : Date.now(),
		id: o.id,
		data
	};
	// Keep signature fields untouched (relays and the server verify them) but
	// only when well-formed; the server treats anything else as unsigned anyway
	if (
		typeof o.author_user_id === 'number' &&
		Number.isSafeInteger(o.author_user_id) &&
		o.author_user_id > 0 &&
		typeof o.key_id === 'string' &&
		o.key_id.length <= 64 &&
		typeof o.sig === 'string' &&
		o.sig.length <= 200
	) {
		msg.author_user_id = o.author_user_id;
		msg.key_id = o.key_id;
		msg.sig = o.sig;
	}
	return msg;
}

/** Build a BitChat-compatible binary packet from a payload. */
export function createBitchatPacket(payload: Uint8Array, ttl: number = DEFAULT_TTL): Uint8Array {
	// Generate a random 4-byte message ID
	const msgId = new Uint8Array(4);
	crypto.getRandomValues(msgId);

	// Header: type(1) + TTL(1) + msgId(4) + length(2) = 8 bytes
	const header = new Uint8Array(8);
	header[0] = PACKET_TYPE_BROADCAST;
	header[1] = Math.min(ttl, 7);
	header.set(msgId, 2);
	// Payload length as big-endian uint16
	header[6] = (payload.length >> 8) & 0xff;
	header[7] = payload.length & 0xff;

	// Combine header + payload
	const packet = new Uint8Array(header.length + payload.length);
	packet.set(header, 0);
	packet.set(payload, header.length);
	return packet;
}

/** Parse a BitChat binary packet, extracting type, TTL, and payload. */
export function parseBitchatPacket(
	raw: DataView
): { type: number; ttl: number; payload: Uint8Array } | null {
	if (raw.byteLength < 8) return null;

	const type = raw.getUint8(0);
	const ttl = raw.getUint8(1);
	const payloadLength = raw.getUint16(6, false); // big-endian

	if (raw.byteLength < 8 + payloadLength) return null;

	const payload = new Uint8Array(raw.buffer, raw.byteOffset + 8, payloadLength);
	return { type, ttl, payload };
}

// ── Fragmentation ─────────────────────────────────────────────────────────────

/**
 * Split a packet into MTU-sized fragments if needed.
 * Returns an array of 1+ packets. If the packet fits in a single write,
 * returns the original packet in a single-element array.
 */
export function fragmentPacket(
	packet: Uint8Array,
	maxPayload: number = DEFAULT_MAX_PAYLOAD
): Uint8Array[] {
	if (packet.length <= maxPayload + 8) {
		// Fits in a single packet (maxPayload is for the payload portion)
		return [packet];
	}

	// Extract the original message ID from the packet header (bytes 2-5)
	const originalMsgId = packet.slice(2, 6);
	// The full data to fragment is the entire original packet
	const dataPerFragment = maxPayload - FRAGMENT_HEADER_SIZE;
	const totalFragments = Math.ceil(packet.length / dataPerFragment);

	if (totalFragments > MAX_FRAGMENTS_PER_MESSAGE) {
		throw new Error(`Message too large to send over the mesh (> ${MAX_FRAGMENTS_PER_MESSAGE} fragments)`);
	}

	const fragments: Uint8Array[] = [];

	for (let i = 0; i < totalFragments; i++) {
		const start = i * dataPerFragment;
		const end = Math.min(start + dataPerFragment, packet.length);
		const chunk = packet.slice(start, end);

		// Build fragment payload: originalMsgId(4) + index(1) + total(1) + chunk
		const fragPayload = new Uint8Array(FRAGMENT_HEADER_SIZE + chunk.length);
		fragPayload.set(originalMsgId, 0);
		fragPayload[4] = i;
		fragPayload[5] = totalFragments;
		fragPayload.set(chunk, FRAGMENT_HEADER_SIZE);

		// Wrap in a BitChat packet with type = FRAGMENT
		const fragMsgId = new Uint8Array(4);
		crypto.getRandomValues(fragMsgId);

		const header = new Uint8Array(8);
		header[0] = PACKET_TYPE_FRAGMENT;
		header[1] = DEFAULT_TTL;
		header.set(fragMsgId, 2);
		header[6] = (fragPayload.length >> 8) & 0xff;
		header[7] = fragPayload.length & 0xff;

		const fragPacket = new Uint8Array(8 + fragPayload.length);
		fragPacket.set(header, 0);
		fragPacket.set(fragPayload, 8);
		fragments.push(fragPacket);
	}

	return fragments;
}

interface FragmentSet {
	fragments: (Uint8Array | null)[];
	total: number;
	received: number;
	bytes: number;
	createdAt: number;
}

/**
 * Reassembles fragment packets (type 0x02) into the original packet.
 *
 * Everything here comes from untrusted radios, so memory is bounded: at most
 * MAX_FRAGMENTS_PER_MESSAGE fragments per set, MAX_PENDING_FRAGMENT_SETS sets
 * and MAX_BUFFERED_FRAGMENT_BYTES in total (oldest set evicted first).
 * Incomplete sets are dropped after FRAGMENT_TIMEOUT_MS; duplicate fragments
 * are ignored; a fragment disagreeing with its set's fragment count drops the set.
 */
export class FragmentReassembler {
	private sets = new Map<string, FragmentSet>();
	private bufferedBytes = 0;
	private readonly now: () => number;
	private readonly timeoutMs: number;

	constructor(now: () => number = Date.now, timeoutMs: number = FRAGMENT_TIMEOUT_MS) {
		this.now = now;
		this.timeoutMs = timeoutMs;
	}

	/** Number of incomplete sets currently buffered. */
	get pendingSets(): number {
		return this.sets.size;
	}

	get pendingBytes(): number {
		return this.bufferedBytes;
	}

	/** Feed one received packet; returns the full packet once all fragments arrived. */
	push(raw: DataView): Uint8Array | null {
		const parsed = parseBitchatPacket(raw);
		if (!parsed || parsed.type !== PACKET_TYPE_FRAGMENT) return null;
		if (parsed.payload.length <= FRAGMENT_HEADER_SIZE) return null;

		const key = Array.from(parsed.payload.subarray(0, 4))
			.map((b) => b.toString(16).padStart(2, '0'))
			.join('');
		const index = parsed.payload[4];
		const total = parsed.payload[5];
		if (total < 2 || total > MAX_FRAGMENTS_PER_MESSAGE || index >= total) return null;
		// Copy: the DataView may point into a buffer the BLE stack reuses
		const chunk = parsed.payload.slice(FRAGMENT_HEADER_SIZE);

		this.expire();

		let set = this.sets.get(key);
		if (set && set.total !== total) {
			// Conflicting fragment count for the same message: drop the set
			this.drop(key);
			set = undefined;
		}
		if (!set) {
			set = { fragments: new Array(total).fill(null), total, received: 0, bytes: 0, createdAt: this.now() };
			this.sets.set(key, set);
			while (this.sets.size > MAX_PENDING_FRAGMENT_SETS) this.dropOldest();
		}
		if (set.fragments[index] !== null) return null; // duplicate

		set.fragments[index] = chunk;
		set.received++;
		set.bytes += chunk.length;
		this.bufferedBytes += chunk.length;
		while (this.bufferedBytes > MAX_BUFFERED_FRAGMENT_BYTES && this.sets.size > 0) {
			this.dropOldest();
		}
		if (!this.sets.has(key) || set.received < set.total) return null;

		this.drop(key);
		const result = new Uint8Array(set.bytes);
		let offset = 0;
		for (const frag of set.fragments) {
			result.set(frag!, offset);
			offset += frag!.length;
		}
		return result;
	}

	/** Drop incomplete sets older than the timeout. */
	expire(): void {
		const now = this.now();
		for (const [key, set] of this.sets) {
			if (now - set.createdAt > this.timeoutMs) this.drop(key);
		}
	}

	clear(): void {
		this.sets.clear();
		this.bufferedBytes = 0;
	}

	private drop(key: string): void {
		const set = this.sets.get(key);
		if (!set) return;
		this.bufferedBytes -= set.bytes;
		this.sets.delete(key);
	}

	private dropOldest(): void {
		// Map iterates in insertion order, i.e. oldest first
		const oldest = this.sets.keys().next();
		if (!oldest.done) this.drop(oldest.value);
	}
}

/**
 * Check if a raw BLE packet is a fragment (type 0x02).
 * Used by the connection manager to route packets correctly.
 */
export function isFragmentPacket(raw: DataView): boolean {
	return raw.byteLength >= 1 && raw.getUint8(0) === PACKET_TYPE_FRAGMENT;
}
