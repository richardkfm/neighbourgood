/**
 * Per-browser mesh signing keys.
 *
 * Each browser holds one ECDSA P-256 key pair per account. The private key is
 * generated non-extractable and kept (as a CryptoKey) in IndexedDB, so page
 * script can sign with it but never read it out. While online the public key is
 * registered with the server (POST /mesh/keys, with a proof-of-possession
 * signature); outgoing mesh messages are then signed so whoever relays and
 * syncs them, the server attributes them to their real author.
 */

import { api } from '$lib/api';
import type { NGMeshMessage } from '$lib/bluetooth/protocol';
import {
	b64urlEncode,
	computeKeyId,
	registrationInput,
	signBytes,
	signFields
} from '$lib/bluetooth/signing';

const DB_NAME = 'ng-mesh-keys';
const STORE = 'keys';

interface StoredKey {
	/** `user:<id>` */
	id: string;
	userId: number;
	keyId: string;
	privateKey: CryptoKey;
	publicKey: CryptoKey;
	spki: string;
	registered: boolean;
}

export interface MeshKeyInfo {
	key_id: string;
	device_name: string;
	public_key: string;
	created_at: string;
	last_used_at: string | null;
	revoked_at: string | null;
}

function openDB(): Promise<IDBDatabase> {
	return new Promise((resolve, reject) => {
		const req = indexedDB.open(DB_NAME, 1);
		req.onupgradeneeded = () => {
			if (!req.result.objectStoreNames.contains(STORE)) {
				req.result.createObjectStore(STORE, { keyPath: 'id' });
			}
		};
		req.onsuccess = () => resolve(req.result);
		req.onerror = () => reject(req.error);
	});
}

async function tx<T>(mode: IDBTransactionMode, fn: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
	const db = await openDB();
	return new Promise((resolve, reject) => {
		const t = db.transaction(STORE, mode);
		const req = fn(t.objectStore(STORE));
		t.oncomplete = () => {
			db.close();
			resolve(req.result);
		};
		t.onerror = () => {
			db.close();
			reject(t.error);
		};
	});
}

const loadKey = (userId: number) =>
	tx<StoredKey | undefined>('readonly', (s) => s.get(`user:${userId}`) as IDBRequest<StoredKey | undefined>);
const saveKey = (key: StoredKey) => tx('readwrite', (s) => s.put(key));

async function createKey(userId: number): Promise<StoredKey> {
	// extractable=false applies to the private key; the public key stays exportable
	const pair = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, false, [
		'sign',
		'verify'
	]);
	const spki = await crypto.subtle.exportKey('spki', pair.publicKey);
	const key: StoredKey = {
		id: `user:${userId}`,
		userId,
		keyId: await computeKeyId(spki),
		privateKey: pair.privateKey,
		publicKey: pair.publicKey,
		spki: b64urlEncode(spki),
		registered: false
	};
	await saveKey(key);
	return key;
}

function isSupported(): boolean {
	return typeof indexedDB !== 'undefined' && typeof crypto !== 'undefined' && !!crypto.subtle;
}

function deviceName(): string {
	if (typeof navigator === 'undefined') return '';
	const ua = navigator.userAgent;
	const os = /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS' : /Mac/.test(ua) ? 'macOS' : /Windows/.test(ua) ? 'Windows' : /Linux/.test(ua) ? 'Linux' : '';
	const browser = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : 'Browser';
	return [browser, os].filter(Boolean).join(' on ').slice(0, 100);
}

let ensuring: Promise<void> | null = null;

/**
 * Make sure this browser has a key for the account and that the server knows it.
 * Safe to call repeatedly (one request per call while online; idempotent on the
 * server). A key revoked from another device is replaced by a fresh one.
 */
export function ensureMeshKeyRegistered(userId: number): Promise<void> {
	if (!isSupported()) return Promise.resolve();
	ensuring ??= (async () => {
		let key = (await loadKey(userId)) ?? (await createKey(userId));
		for (let attempt = 0; attempt < 2; attempt++) {
			try {
				await api('/mesh/keys', {
					method: 'POST',
					auth: true,
					body: {
						public_key: key.spki,
						device_name: deviceName(),
						proof: await signBytes(key.privateKey, registrationInput(userId, key.keyId))
					}
				});
				if (!key.registered) await saveKey({ ...key, registered: true });
				return;
			} catch (e) {
				// 409: revoked (or otherwise unusable) — start over with a new key
				if (attempt === 0 && e instanceof Error && /cannot be registered/i.test(e.message)) {
					key = await createKey(userId);
					continue;
				}
				return; // offline or server error: keep signing, retry next time
			}
		}
	})().finally(() => {
		ensuring = null;
	});
	return ensuring;
}

/**
 * Add author_user_id, key_id and sig to an outgoing message. Without a key (or
 * WebCrypto) the message goes out unsigned and the server treats it as such.
 */
export async function signMeshMessage(msg: NGMeshMessage, userId: number | null | undefined): Promise<NGMeshMessage> {
	if (!userId || !isSupported()) return msg;
	try {
		const key = (await loadKey(userId)) ?? (await createKey(userId));
		const signed: NGMeshMessage = { ...msg, author_user_id: userId, key_id: key.keyId };
		signed.sig = await signFields(key.privateKey, {
			type: msg.type,
			community_id: msg.community_id,
			ts: msg.ts,
			id: msg.id,
			data: msg.data,
			author_user_id: userId
		});
		return signed;
	} catch {
		return msg;
	}
}

/** This browser's key ID for the account, if one exists. */
export async function currentMeshKeyId(userId: number): Promise<string | null> {
	if (!isSupported()) return null;
	try {
		return (await loadKey(userId))?.keyId ?? null;
	} catch {
		return null;
	}
}

export function listMeshKeys(): Promise<MeshKeyInfo[]> {
	return api<MeshKeyInfo[]>('/mesh/keys/me', { auth: true });
}

export function revokeMeshKey(keyId: string): Promise<void> {
	return api<void>(`/mesh/keys/me/${encodeURIComponent(keyId)}`, { method: 'DELETE', auth: true });
}
