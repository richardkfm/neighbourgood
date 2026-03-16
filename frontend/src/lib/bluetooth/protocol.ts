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
 */

const PACKET_TYPE_BROADCAST = 0x01;
const PACKET_TYPE_FRAGMENT = 0x02;
const DEFAULT_TTL = 7;
const NG_PREFIX = 'ng:';

/** Default BLE MTU minus ATT header (3 bytes) minus BitChat header (8 bytes). */
const DEFAULT_MAX_PAYLOAD = 174;

/** Fragment overhead: originalMsgId(4) + index(1) + total(1) = 6 bytes. */
const FRAGMENT_HEADER_SIZE = 6;

/** Stale fragment timeout in milliseconds. */
const FRAGMENT_TIMEOUT_MS = 10_000;

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
}

export interface MeshTicketData {
	title: string;
	description: string;
	ticket_type: 'request' | 'offer' | 'emergency_ping';
	urgency: 'low' | 'medium' | 'high' | 'critical';
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
		const obj = JSON.parse(text.slice(NG_PREFIX.length));
		if (obj.ng !== 1 || !obj.type || !obj.id) return null;
		return { message: obj as NGMeshMessage, ttl: parsed.ttl };
	} catch {
		return null;
	}
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

	if (totalFragments > 255) {
		throw new Error('Message too large to fragment (> 255 fragments)');
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

interface FragmentBuffer {
	fragments: (Uint8Array | null)[];
	total: number;
	received: number;
	createdAt: number;
}

const reassemblyBuffers = new Map<string, FragmentBuffer>();

/**
 * Process an incoming fragment packet. Returns the reassembled complete
 * packet when all fragments are received, or null if still waiting.
 */
export function defragmentPacket(raw: DataView): Uint8Array | null {
	const parsed = parseBitchatPacket(raw);
	if (!parsed) return null;

	// Only handle fragment packets
	if (parsed.type !== PACKET_TYPE_FRAGMENT) return null;

	if (parsed.payload.length < FRAGMENT_HEADER_SIZE) return null;

	// Extract fragment header
	const originalMsgId = Array.from(parsed.payload.slice(0, 4))
		.map((b) => b.toString(16).padStart(2, '0'))
		.join('');
	const fragmentIndex = parsed.payload[4];
	const totalFragments = parsed.payload[5];
	const chunk = parsed.payload.slice(FRAGMENT_HEADER_SIZE);

	if (fragmentIndex >= totalFragments || totalFragments === 0) return null;

	// Clean up stale buffers
	const now = Date.now();
	for (const [key, buf] of reassemblyBuffers) {
		if (now - buf.createdAt > FRAGMENT_TIMEOUT_MS) {
			reassemblyBuffers.delete(key);
		}
	}

	// Get or create buffer
	let buffer = reassemblyBuffers.get(originalMsgId);
	if (!buffer) {
		buffer = {
			fragments: new Array(totalFragments).fill(null),
			total: totalFragments,
			received: 0,
			createdAt: now
		};
		reassemblyBuffers.set(originalMsgId, buffer);
	}

	// Store fragment (ignore duplicates)
	if (buffer.fragments[fragmentIndex] === null) {
		buffer.fragments[fragmentIndex] = chunk;
		buffer.received++;
	}

	// Check if complete
	if (buffer.received === buffer.total) {
		reassemblyBuffers.delete(originalMsgId);

		// Concatenate all fragments
		const totalLength = buffer.fragments.reduce((sum, f) => sum + (f?.length ?? 0), 0);
		const result = new Uint8Array(totalLength);
		let offset = 0;
		for (const frag of buffer.fragments) {
			if (frag) {
				result.set(frag, offset);
				offset += frag.length;
			}
		}
		return result;
	}

	return null;
}

/**
 * Check if a raw BLE packet is a fragment (type 0x02).
 * Used by the connection manager to route packets correctly.
 */
export function isFragmentPacket(raw: DataView): boolean {
	return raw.byteLength >= 1 && raw.getUint8(0) === PACKET_TYPE_FRAGMENT;
}
