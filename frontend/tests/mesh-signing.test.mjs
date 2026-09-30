// Mesh message signing (format v1). Run: npm test  (node --test, Node >= 22.18 strips TS types)
// The test vector is shared with backend/tests/test_mesh_signing.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import {
	canonicalJson,
	signingInput,
	registrationInput,
	computeKeyId,
	b64urlDecode,
	b64urlEncode,
	signFields,
	verifyBytes,
	CanonicalizationError
} from '../src/lib/bluetooth/signing.ts';

const VECTOR = {
	spki:
		'MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEUl9KvnTu5X-wkKzPd5AW6xPknX1iyUuE2pUzPF5NdTD_' +
		'3gr9_nioxag13oYcS1eQnX2x2DKDbazA7cjJ6UyXtw',
	keyId: '3H_Ue8LOIqm7abYuhd694bThLhod9RHeqXtTZZgZn9U',
	dataJson:
		'{"title":"Water needed \\"urgently\\"","description":"Line1\\nLine2\\t\\u0001 caf\\u00e9 ' +
		'\\ud83d\\ude00 \\\\ end","urgency":"high","ticket_type":"request","lat":52.52,"lng":-13.405,' +
		'"tiny":0.000001,"tinier":1e-7,"count":5,"neg":-0,"big":9007199254740991,' +
		'"float":0.30000000000000004,"flags":[true,false,null],"nested":{"z":1,"a":{"b":[]},' +
		'"\\u00e9":"e-acute","Z":"upper","aa":2}}',
	fields: {
		type: 'emergency_ticket',
		community_id: 7,
		ts: 1790000000123,
		id: '3f1c2d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f',
		author_user_id: 42
	},
	canonical:
		'NG-MESH-SIG-V1\n{"author_user_id":42,"community_id":7,"data":{"big":9007199254740991,' +
		'"count":5,"description":"Line1\\nLine2\\t\\u0001 café 😀 \\\\ end","flags":[true,false,null],' +
		'"float":0.30000000000000004,"lat":52.52,"lng":-13.405,"neg":0,"nested":{"Z":"upper",' +
		'"a":{"b":[]},"aa":2,"z":1,"é":"e-acute"},"ticket_type":"request","tinier":1e-7,' +
		'"tiny":0.000001,"title":"Water needed \\"urgently\\"","urgency":"high"},' +
		'"id":"3f1c2d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f","ts":1790000000123,"type":"emergency_ticket"}',
	sha256: '6a18f6ff3ac6771a9ebc955680f394476a0de9348405029b65a18e687278e8b8',
	sig: 'HewX0900UtZ6ZxshaoSbja2SSDOjqn3NcKyVsFhNJBoLWmg4F4tE_9FvYqAOhBfmp29aV-Nye7h2rt73qWiZVg',
	regProofUser42:
		'BGbXOGZ08qqQLksg-0ntsE1wZUyHeVWX0H9sC4obHeKDzf7J4uJhb82Bb-NCu1-bucHeu9K79T9IrQyr0lDR_w'
};

const vectorFields = () => ({ ...VECTOR.fields, data: JSON.parse(VECTOR.dataJson) });

async function vectorPublicKey() {
	const spki = b64urlDecode(VECTOR.spki);
	return crypto.subtle.importKey('spki', spki, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['verify']);
}

test('canonical form matches the shared vector', () => {
	const input = signingInput(vectorFields());
	assert.equal(new TextDecoder().decode(input), VECTOR.canonical);
	assert.equal(createHash('sha256').update(input).digest('hex'), VECTOR.sha256);
});

test('key_id is the SHA-256 of the SPKI', async () => {
	assert.equal(await computeKeyId(b64urlDecode(VECTOR.spki)), VECTOR.keyId);
});

test('vector signatures verify, and fail after tampering', async () => {
	const key = await vectorPublicKey();
	assert.equal(await verifyBytes(key, VECTOR.sig, signingInput(vectorFields())), true);
	assert.equal(await verifyBytes(key, VECTOR.regProofUser42, registrationInput(42, VECTOR.keyId)), true);
	const tampered = { ...vectorFields(), author_user_id: 43 };
	assert.equal(await verifyBytes(key, VECTOR.sig, signingInput(tampered)), false);
	assert.equal(await verifyBytes(key, 'not-base64!', signingInput(vectorFields())), false);
});

test('sign and verify round trip with a fresh key', async () => {
	const kp = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, false, [
		'sign',
		'verify'
	]);
	const fields = { ...vectorFields(), id: 'x-1' };
	const sig = await signFields(kp.privateKey, fields);
	assert.equal(b64urlDecode(sig).length, 64); // IEEE P1363 r || s
	assert.equal(await verifyBytes(kp.publicKey, sig, signingInput(fields)), true);
});

test('canonical values', () => {
	const cases = [
		[0.1, '0.1'],
		[1e-7, '1e-7'],
		[0.000001, '0.000001'],
		[1.5e-10, '1.5e-10'],
		[-0, '0'],
		[5.0, '5'],
		[-13.405, '-13.405'],
		[2 ** 53 - 1, '9007199254740991'],
		['\x7f ', '"\x7f "'],
		[{ b: 1, a: 2, B: 3 }, '{"B":3,"a":2,"b":1}'],
		// Code point order (UTF-8 byte order), not UTF-16 code unit order
		[{ '\u{1F600}': 1, '￿': 2 }, '{"￿":2,"\u{1F600}":1}']
	];
	for (const [value, expected] of cases) assert.equal(canonicalJson(value), expected);
});

test('canonical rejects values the server rejects', () => {
	let deep = [];
	for (let i = 0; i < 40; i++) deep = [deep];
	for (const bad of [NaN, Infinity, 2 ** 53, 1e21, '\ud800', undefined, () => 1, deep]) {
		assert.throws(() => canonicalJson(bad), CanonicalizationError);
	}
});

test('base64url round trip', () => {
	const bytes = new Uint8Array([0, 251, 255, 1, 2]);
	assert.deepEqual(b64urlDecode(b64urlEncode(bytes)), bytes);
});
