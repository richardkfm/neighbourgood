// BLE packet fragmentation and bounded reassembly. Run: npm test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	createBitchatPacket,
	fragmentPacket,
	FragmentReassembler,
	isFragmentPacket,
	encodeNGMessage,
	decodeNGMessage,
	createNGMessage,
	FRAGMENT_TIMEOUT_MS,
	MAX_PENDING_FRAGMENT_SETS,
	MAX_FRAGMENTS_PER_MESSAGE
} from '../src/lib/bluetooth/protocol.ts';

const view = (u8) => new DataView(u8.buffer, u8.byteOffset, u8.byteLength);

function bigPacket(size) {
	const payload = new Uint8Array(size);
	for (let i = 0; i < size; i++) payload[i] = i % 251;
	return createBitchatPacket(payload);
}

/** Hand-build a fragment packet (for malicious inputs). */
function fragment(msgId, index, total, chunk = new Uint8Array([1, 2, 3])) {
	const payload = new Uint8Array(6 + chunk.length);
	payload.set(msgId, 0);
	payload[4] = index;
	payload[5] = total;
	payload.set(chunk, 6);
	const packet = createBitchatPacket(payload);
	packet[0] = 0x02;
	return packet;
}

test('small packets are not fragmented', () => {
	const packet = bigPacket(100);
	const parts = fragmentPacket(packet);
	assert.equal(parts.length, 1);
	assert.equal(parts[0], packet);
	assert.equal(isFragmentPacket(view(packet)), false);
});

test('large packets round-trip through fragmentation in any order', () => {
	const packet = bigPacket(2000);
	const parts = fragmentPacket(packet);
	assert.ok(parts.length > 1);
	for (const p of parts) {
		assert.ok(p.length <= 174 + 8, 'each fragment fits one BLE write');
		assert.equal(isFragmentPacket(view(p)), true);
	}
	const r = new FragmentReassembler();
	const shuffled = [...parts].reverse();
	let result = null;
	for (const p of shuffled) result = r.push(view(p)) ?? result;
	assert.deepEqual(result, packet);
	assert.equal(r.pendingSets, 0);
	assert.equal(r.pendingBytes, 0);
});

test('a signed NG message survives fragmentation', () => {
	const msg = createNGMessage('emergency_ticket', 3, 'Ana', {
		title: 'Need insulin',
		description: 'x'.repeat(1500),
		client_id: '8d0f7c4e-1111-4222-8333-944455556666'
	});
	Object.assign(msg, { author_user_id: 9, key_id: 'k'.repeat(43), sig: 's'.repeat(86) });
	const r = new FragmentReassembler();
	let full = null;
	for (const p of fragmentPacket(encodeNGMessage(msg))) full = r.push(view(p)) ?? full;
	const decoded = decodeNGMessage(view(full));
	assert.deepEqual(decoded, msg);
});

test('duplicate fragments are ignored', () => {
	const packet = bigPacket(600);
	const parts = fragmentPacket(packet);
	const r = new FragmentReassembler();
	assert.equal(r.push(view(parts[0])), null);
	assert.equal(r.push(view(parts[0])), null);
	let result = null;
	for (const p of parts.slice(1)) result = r.push(view(p)) ?? result;
	assert.deepEqual(result, packet);
});

test('incomplete sets are dropped after the timeout', () => {
	let now = 1000;
	const r = new FragmentReassembler(() => now);
	const parts = fragmentPacket(bigPacket(600));
	r.push(view(parts[0]));
	assert.equal(r.pendingSets, 1);
	now += FRAGMENT_TIMEOUT_MS + 1;
	r.expire();
	assert.equal(r.pendingSets, 0);
	assert.equal(r.pendingBytes, 0);
	// Late fragments start a new set rather than completing the stale one
	for (const p of parts.slice(1)) assert.equal(r.push(view(p)), null);
});

test('malicious fragment counts are refused', () => {
	const r = new FragmentReassembler();
	const id = new Uint8Array([1, 2, 3, 4]);
	assert.equal(r.push(view(fragment(id, 0, 0))), null); // zero fragments
	assert.equal(r.push(view(fragment(id, 0, 1))), null); // a "set" of one is not a fragment
	assert.equal(r.push(view(fragment(id, 5, 5))), null); // index out of range
	assert.equal(r.push(view(fragment(id, 0, MAX_FRAGMENTS_PER_MESSAGE + 1))), null); // too many
	assert.equal(r.pendingSets, 0);
	// A conflicting total for the same message ID drops the set
	r.push(view(fragment(id, 0, 3)));
	assert.equal(r.pendingSets, 1);
	assert.equal(r.push(view(fragment(id, 1, 4))), null);
	assert.equal(r.pendingSets, 1); // replaced by the new set of 4
	// Truncated / empty fragments
	assert.equal(r.push(view(new Uint8Array([2, 7, 0, 0, 0, 0, 0, 3, 1, 2]))), null);
});

test('memory is bounded: oldest sets are evicted', () => {
	const r = new FragmentReassembler();
	for (let i = 0; i < MAX_PENDING_FRAGMENT_SETS + 10; i++) {
		r.push(view(fragment(new Uint8Array([0, 0, i >> 8, i & 0xff]), 0, 100, new Uint8Array(160))));
	}
	assert.equal(r.pendingSets, MAX_PENDING_FRAGMENT_SETS);
	assert.ok(r.pendingBytes <= 512 * 1024);
});

test('oversized messages cannot be sent', () => {
	assert.throws(() => fragmentPacket(bigPacket(60000)));
});
