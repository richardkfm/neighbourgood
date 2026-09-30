/**
 * Per-account data kept on the device for offline use: the mesh message
 * queue, the offline triage store and the offline request queue.
 *
 * It is cleared on logout, and also when a different account signs in on the
 * same browser (e.g. after a session expired without an explicit logout), so
 * the next user neither sees nor syncs the previous user's data.
 */

import { clearAllMeshData } from '$lib/stores/mesh';
import { clearOfflineQueue } from '$lib/stores/offline';

const OWNER_KEY = 'ng_local_data_owner';

export async function clearLocalUserData(): Promise<void> {
	await Promise.allSettled([clearAllMeshData(), clearOfflineQueue()]);
	try {
		localStorage.removeItem(OWNER_KEY);
		sessionStorage.removeItem('ng_mesh_last_sync');
	} catch {
		// storage unavailable
	}
}

/** Record which account the local data belongs to; wipe it if it was someone else's. */
export async function claimLocalData(userId: number): Promise<void> {
	let owner: string | null = null;
	try {
		owner = localStorage.getItem(OWNER_KEY);
	} catch {
		return;
	}
	if (owner !== null && owner !== String(userId)) {
		await clearLocalUserData();
	}
	try {
		localStorage.setItem(OWNER_KEY, String(userId));
	} catch {
		// storage unavailable
	}
}
