/**
 * Mesh message signatures (format v1) — must match backend/app/services/mesh_signing.py.
 *
 *   signing input = UTF-8("NG-MESH-SIG-V1\n" + canonicalJson({
 *                     author_user_id, community_id, data, id, ts, type }))
 *   signature     = ECDSA P-256 / SHA-256, IEEE P1363 (r || s, 64 bytes), base64url, no padding
 *   key_id        = base64url(SHA-256(SubjectPublicKeyInfo DER)), no padding (43 chars)
 *
 * canonicalJson: no whitespace; object keys sorted by code point (= UTF-8 byte
 * order); strings escaped like JSON.stringify (\" \\ \b \t \n \f \r, other
 * U+0000–U+001F as \u00xx), lone surrogates rejected; numbers finite, integral
 * values within ±(2^53−1), formatted by Number.prototype.toString (so -0 → "0");
 * nesting deeper than 32 levels rejected.
 *
 * Pure module (only WebCrypto): unit-tested with `npm test` under Node.
 */

export const SIGNING_PREFIX = 'NG-MESH-SIG-V1\n';
export const REGISTRATION_PREFIX = 'NG-MESH-KEY-V1\n';
const MAX_DEPTH = 32;

export class CanonicalizationError extends Error {}

function compareCodePoints(a: string, b: string): number {
	const ai = a[Symbol.iterator]();
	const bi = b[Symbol.iterator]();
	for (;;) {
		const x = ai.next();
		const y = bi.next();
		if (x.done || y.done) return x.done ? (y.done ? 0 : -1) : 1;
		const d = x.value.codePointAt(0)! - y.value.codePointAt(0)!;
		if (d !== 0) return d;
	}
}

function canonicalString(value: string): string {
	// Lone surrogates cannot be encoded as UTF-8 (the server rejects them too)
	if (/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(value)) {
		throw new CanonicalizationError('string is not well-formed Unicode');
	}
	return JSON.stringify(value);
}

function canonicalNumber(value: number): string {
	if (!Number.isFinite(value)) throw new CanonicalizationError('non-finite number');
	if (Number.isInteger(value) && !Number.isSafeInteger(value)) {
		throw new CanonicalizationError('integer outside the safe range');
	}
	return String(value);
}

export function canonicalJson(value: unknown, depth = 0): string {
	if (depth > MAX_DEPTH) throw new CanonicalizationError('nesting too deep');
	if (value === null) return 'null';
	if (value === true) return 'true';
	if (value === false) return 'false';
	if (typeof value === 'number') return canonicalNumber(value);
	if (typeof value === 'string') return canonicalString(value);
	if (Array.isArray(value)) {
		return '[' + value.map((v) => canonicalJson(v, depth + 1)).join(',') + ']';
	}
	if (typeof value === 'object') {
		const obj = value as Record<string, unknown>;
		const keys = Object.keys(obj).sort(compareCodePoints);
		return (
			'{' +
			keys.map((k) => canonicalString(k) + ':' + canonicalJson(obj[k], depth + 1)).join(',') +
			'}'
		);
	}
	throw new CanonicalizationError(`unsupported type ${typeof value}`);
}

export interface SignedFields {
	type: string;
	community_id: number;
	ts: number;
	id: string;
	data: Record<string, unknown>;
	author_user_id: number;
}

export function signingInput(f: SignedFields): Uint8Array {
	const payload = {
		author_user_id: f.author_user_id,
		community_id: f.community_id,
		data: f.data,
		id: f.id,
		ts: f.ts,
		type: f.type
	};
	return new TextEncoder().encode(SIGNING_PREFIX + canonicalJson(payload));
}

export function registrationInput(userId: number, keyId: string): Uint8Array {
	return new TextEncoder().encode(`${REGISTRATION_PREFIX}${userId}\n${keyId}`);
}

// ── Encoding ─────────────────────────────────────────────────────────────────

export function b64urlEncode(bytes: ArrayBuffer | Uint8Array): string {
	const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
	let bin = '';
	for (const b of u8) bin += String.fromCharCode(b);
	return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function b64urlDecode(text: string): Uint8Array {
	const std = text.replace(/-/g, '+').replace(/_/g, '/');
	const bin = atob(std + '='.repeat((4 - (std.length % 4)) % 4));
	const out = new Uint8Array(bin.length);
	for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
	return out;
}

const ECDSA = { name: 'ECDSA', hash: 'SHA-256' } as const;

/** Copy into a fresh ArrayBuffer (WebCrypto typings reject SharedArrayBuffer-backed views). */
function buf(bytes: Uint8Array): ArrayBuffer {
	return bytes.slice().buffer as ArrayBuffer;
}

export async function computeKeyId(spki: ArrayBuffer | Uint8Array): Promise<string> {
	const data = spki instanceof Uint8Array ? buf(spki) : spki;
	return b64urlEncode(await crypto.subtle.digest('SHA-256', data));
}

export async function signBytes(privateKey: CryptoKey, message: Uint8Array): Promise<string> {
	return b64urlEncode(await crypto.subtle.sign(ECDSA, privateKey, buf(message)));
}

export async function verifyBytes(
	publicKey: CryptoKey,
	signature: string,
	message: Uint8Array
): Promise<boolean> {
	try {
		return await crypto.subtle.verify(ECDSA, publicKey, buf(b64urlDecode(signature)), buf(message));
	} catch {
		return false;
	}
}

export async function signFields(privateKey: CryptoKey, fields: SignedFields): Promise<string> {
	return signBytes(privateKey, signingInput(fields));
}
