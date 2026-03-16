/**
 * End-to-end encryption for mesh direct messages.
 *
 * Uses ECDH (P-256) for key agreement + AES-256-GCM for symmetric encryption.
 * Web Crypto API — available in all modern browsers including service workers.
 */

const ALGO = { name: 'ECDH', namedCurve: 'P-256' };
const AES_ALGO = 'AES-GCM';
const IV_LENGTH = 12;

export interface MeshKeyPair {
	publicKey: JsonWebKey;
	privateKey: CryptoKey;
}

const KEY_DB_NAME = 'ng-mesh-keys';
const KEY_STORE = 'keypair';
const PEER_STORE = 'peer-keys';

// ── Key Generation & Storage ─────────────────────────────────────────────────

/** Generate a new ECDH key pair for mesh encryption. */
export async function generateKeyPair(): Promise<MeshKeyPair> {
	const pair = await crypto.subtle.generateKey(ALGO, true, ['deriveKey']);
	const publicKey = await crypto.subtle.exportKey('jwk', pair.publicKey);
	return { publicKey, privateKey: pair.privateKey };
}

/** Store our key pair in IndexedDB. */
export async function storeKeyPair(kp: MeshKeyPair): Promise<void> {
	const exportedPrivate = await crypto.subtle.exportKey('jwk', kp.privateKey);
	const db = await openKeyDB();
	const tx = db.transaction(KEY_STORE, 'readwrite');
	tx.objectStore(KEY_STORE).put({
		id: 'self',
		publicKey: kp.publicKey,
		privateKey: exportedPrivate,
	});
	return txComplete(db, tx);
}

/** Load our key pair from IndexedDB. Returns null if not yet generated. */
export async function loadKeyPair(): Promise<MeshKeyPair | null> {
	const db = await openKeyDB();
	const tx = db.transaction(KEY_STORE, 'readonly');
	const req = tx.objectStore(KEY_STORE).get('self');
	const result = await reqResult<{ publicKey: JsonWebKey; privateKey: JsonWebKey } | undefined>(db, req);
	if (!result) return null;

	const privateKey = await crypto.subtle.importKey(
		'jwk', result.privateKey, ALGO, false, ['deriveKey']
	);
	return { publicKey: result.publicKey, privateKey };
}

/** Get or create our key pair. */
export async function ensureKeyPair(): Promise<MeshKeyPair> {
	let kp = await loadKeyPair();
	if (!kp) {
		kp = await generateKeyPair();
		await storeKeyPair(kp);
	}
	return kp;
}

/** Export our public key as a compact base64 string for sharing. */
export function exportPublicKey(jwk: JsonWebKey): string {
	return btoa(JSON.stringify(jwk));
}

/** Import a peer's public key from base64. */
export function importPublicKeyString(b64: string): JsonWebKey {
	return JSON.parse(atob(b64));
}

// ── Peer Key Management ──────────────────────────────────────────────────────

/** Store a peer's public key, keyed by user ID. */
export async function storePeerKey(userId: number, publicKey: JsonWebKey): Promise<void> {
	const db = await openKeyDB();
	const tx = db.transaction(PEER_STORE, 'readwrite');
	tx.objectStore(PEER_STORE).put({ id: userId, publicKey });
	return txComplete(db, tx);
}

/** Load a peer's public key. Returns null if unknown. */
export async function loadPeerKey(userId: number): Promise<JsonWebKey | null> {
	const db = await openKeyDB();
	const tx = db.transaction(PEER_STORE, 'readonly');
	const req = tx.objectStore(PEER_STORE).get(userId);
	const result = await reqResult<{ publicKey: JsonWebKey } | undefined>(db, req);
	return result?.publicKey ?? null;
}

// ── Encryption / Decryption ──────────────────────────────────────────────────

/** Encrypt a plaintext string for a peer. Returns base64-encoded ciphertext. */
export async function encryptForPeer(
	plaintext: string,
	ourPrivateKey: CryptoKey,
	peerPublicKeyJwk: JsonWebKey
): Promise<string> {
	const peerKey = await crypto.subtle.importKey('jwk', peerPublicKeyJwk, ALGO, false, []);
	const sharedKey = await crypto.subtle.deriveKey(
		{ name: 'ECDH', public: peerKey },
		ourPrivateKey,
		{ name: AES_ALGO, length: 256 },
		false,
		['encrypt']
	);

	const iv = crypto.getRandomValues(new Uint8Array(IV_LENGTH));
	const encoded = new TextEncoder().encode(plaintext);
	const ciphertext = await crypto.subtle.encrypt(
		{ name: AES_ALGO, iv },
		sharedKey,
		encoded
	);

	// Combine IV + ciphertext and base64 encode
	const combined = new Uint8Array(iv.length + ciphertext.byteLength);
	combined.set(iv, 0);
	combined.set(new Uint8Array(ciphertext), iv.length);
	return btoa(String.fromCharCode(...combined));
}

/** Decrypt a ciphertext received from a peer. Returns plaintext string. */
export async function decryptFromPeer(
	b64Ciphertext: string,
	ourPrivateKey: CryptoKey,
	peerPublicKeyJwk: JsonWebKey
): Promise<string> {
	const peerKey = await crypto.subtle.importKey('jwk', peerPublicKeyJwk, ALGO, false, []);
	const sharedKey = await crypto.subtle.deriveKey(
		{ name: 'ECDH', public: peerKey },
		ourPrivateKey,
		{ name: AES_ALGO, length: 256 },
		false,
		['decrypt']
	);

	const combined = Uint8Array.from(atob(b64Ciphertext), (c) => c.charCodeAt(0));
	const iv = combined.slice(0, IV_LENGTH);
	const ciphertext = combined.slice(IV_LENGTH);

	const decrypted = await crypto.subtle.decrypt(
		{ name: AES_ALGO, iv },
		sharedKey,
		ciphertext
	);

	return new TextDecoder().decode(decrypted);
}

// ── IndexedDB helpers ────────────────────────────────────────────────────────

function openKeyDB(): Promise<IDBDatabase> {
	return new Promise((resolve, reject) => {
		const request = indexedDB.open(KEY_DB_NAME, 1);
		request.onupgradeneeded = () => {
			const db = request.result;
			if (!db.objectStoreNames.contains(KEY_STORE)) {
				db.createObjectStore(KEY_STORE, { keyPath: 'id' });
			}
			if (!db.objectStoreNames.contains(PEER_STORE)) {
				db.createObjectStore(PEER_STORE, { keyPath: 'id' });
			}
		};
		request.onsuccess = () => resolve(request.result);
		request.onerror = () => reject(request.error);
	});
}

function txComplete(db: IDBDatabase, tx: IDBTransaction): Promise<void> {
	return new Promise((resolve, reject) => {
		tx.oncomplete = () => { db.close(); resolve(); };
		tx.onerror = () => { db.close(); reject(tx.error); };
	});
}

function reqResult<T>(db: IDBDatabase, req: IDBRequest): Promise<T> {
	return new Promise((resolve, reject) => {
		req.onsuccess = () => { db.close(); resolve(req.result as T); };
		req.onerror = () => { db.close(); reject(req.error); };
	});
}
