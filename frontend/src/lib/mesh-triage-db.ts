/**
 * IndexedDB persistence for offline triage tickets received via BLE mesh.
 * Separate from the raw mesh message store — this stores structured ticket data
 * for the offline triage view.
 */

export interface OfflineTicket {
	/** Mesh message ID (used as key) */
	id: string;
	community_id: number;
	sender_name: string;
	title: string;
	description: string;
	ticket_type: 'request' | 'offer' | 'emergency_ping';
	urgency: 'low' | 'medium' | 'high' | 'critical';
	ts: number;
	/** Server ticket ID after sync, if available */
	server_id?: number;
	comments: OfflineTicketComment[];
}

export interface OfflineTicketComment {
	id: string;
	sender_name: string;
	body: string;
	ts: number;
}

const DB_NAME = 'ng-mesh-triage';
const TICKETS_STORE = 'tickets';
const DB_VERSION = 1;

function openDB(): Promise<IDBDatabase> {
	return new Promise((resolve, reject) => {
		const request = indexedDB.open(DB_NAME, DB_VERSION);
		request.onupgradeneeded = () => {
			const db = request.result;
			if (!db.objectStoreNames.contains(TICKETS_STORE)) {
				const store = db.createObjectStore(TICKETS_STORE, { keyPath: 'id' });
				store.createIndex('community_id', 'community_id', { unique: false });
			}
		};
		request.onsuccess = () => resolve(request.result);
		request.onerror = () => reject(request.error);
	});
}

/** Save or update an offline ticket. */
export async function saveOfflineTicket(ticket: OfflineTicket): Promise<void> {
	const db = await openDB();
	const tx = db.transaction(TICKETS_STORE, 'readwrite');
	tx.objectStore(TICKETS_STORE).put(ticket);
	return new Promise((resolve, reject) => {
		tx.oncomplete = () => { db.close(); resolve(); };
		tx.onerror = () => { db.close(); reject(tx.error); };
	});
}

/** Add a comment to an existing offline ticket. */
export async function addCommentToTicket(ticketId: string, comment: OfflineTicketComment): Promise<void> {
	const db = await openDB();
	const tx = db.transaction(TICKETS_STORE, 'readwrite');
	const store = tx.objectStore(TICKETS_STORE);
	const getReq = store.get(ticketId);
	return new Promise((resolve, reject) => {
		getReq.onsuccess = () => {
			const ticket = getReq.result as OfflineTicket | undefined;
			if (ticket) {
				ticket.comments.push(comment);
				store.put(ticket);
			}
			tx.oncomplete = () => { db.close(); resolve(); };
		};
		getReq.onerror = () => { db.close(); reject(getReq.error); };
		tx.onerror = () => { db.close(); reject(tx.error); };
	});
}

/** Load all offline tickets, optionally filtered by community. */
export async function loadOfflineTickets(communityId?: number): Promise<OfflineTicket[]> {
	const db = await openDB();
	const tx = db.transaction(TICKETS_STORE, 'readonly');
	const store = tx.objectStore(TICKETS_STORE);

	let request: IDBRequest;
	if (communityId !== undefined) {
		const index = store.index('community_id');
		request = index.getAll(communityId);
	} else {
		request = store.getAll();
	}

	return new Promise((resolve, reject) => {
		request.onsuccess = () => {
			db.close();
			const tickets = request.result as OfflineTicket[];
			// Sort by timestamp descending
			tickets.sort((a, b) => b.ts - a.ts);
			resolve(tickets);
		};
		request.onerror = () => {
			db.close();
			reject(request.error);
		};
	});
}

/** Clear all offline tickets (e.g. after successful server sync). */
export async function clearOfflineTickets(): Promise<void> {
	const db = await openDB();
	const tx = db.transaction(TICKETS_STORE, 'readwrite');
	tx.objectStore(TICKETS_STORE).clear();
	return new Promise((resolve, reject) => {
		tx.oncomplete = () => { db.close(); resolve(); };
		tx.onerror = () => { db.close(); reject(tx.error); };
	});
}

/** Mark a ticket as synced with a server ID. */
export async function markTicketSynced(ticketId: string, serverId: number): Promise<void> {
	const db = await openDB();
	const tx = db.transaction(TICKETS_STORE, 'readwrite');
	const store = tx.objectStore(TICKETS_STORE);
	const getReq = store.get(ticketId);
	return new Promise((resolve, reject) => {
		getReq.onsuccess = () => {
			const ticket = getReq.result as OfflineTicket | undefined;
			if (ticket) {
				ticket.server_id = serverId;
				store.put(ticket);
			}
			tx.oncomplete = () => { db.close(); resolve(); };
		};
		getReq.onerror = () => { db.close(); reject(getReq.error); };
		tx.onerror = () => { db.close(); reject(tx.error); };
	});
}
