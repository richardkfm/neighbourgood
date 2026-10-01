/**
 * Simple auth store – keeps the JWT token and user profile in memory.
 * In a real app this would sync to localStorage for persistence.
 */

import { writable, derived } from 'svelte/store';
import { browser } from '$app/environment';

export interface UserProfile {
	id: number;
	email: string;
	display_name: string;
	neighbourhood: string | null;
	role: string;
	language_code: string;
	created_at: string;
}

export const token = writable<string | null>(
	browser ? localStorage.getItem('ng_token') : null
);
export const user = writable<UserProfile | null>(null);
export const isLoggedIn = derived(token, ($token) => $token !== null);

/**
 * The service worker cannot read localStorage, so the current token is also
 * kept in the Cache API for Background Sync of the mesh queue (which runs even
 * when the offline request queue is empty). Removed on logout.
 */
export const AUTH_CACHE = 'ng-auth';
export const AUTH_CACHE_KEY = '/_internal/auth-token';

function mirrorTokenForServiceWorker(val: string | null) {
	if (typeof caches === 'undefined') return;
	caches
		.open(AUTH_CACHE)
		.then(async (cache) => {
			if (val) {
				await cache.put(
					AUTH_CACHE_KEY,
					new Response(JSON.stringify({ token: val }), {
						headers: { 'Content-Type': 'application/json' }
					})
				);
			} else {
				await cache.delete(AUTH_CACHE_KEY);
			}
		})
		.catch(() => {});
}

token.subscribe((val) => {
	if (typeof localStorage !== 'undefined') {
		if (val) localStorage.setItem('ng_token', val);
		else localStorage.removeItem('ng_token');
	}
	mirrorTokenForServiceWorker(val);
});

/**
 * Sign out. Unless `keepOfflineData` is set (an expired session, where the same
 * person usually signs in again), the mesh queue, the offline triage store and
 * the offline request queue are wiped so the next user of this device cannot
 * see or sync them.
 */
export async function logout(options: { keepOfflineData?: boolean } = {}): Promise<void> {
	token.set(null);
	user.set(null);
	if (!options.keepOfflineData && browser) {
		try {
			const { clearLocalUserData } = await import('$lib/local-data');
			await clearLocalUserData();
		} catch {
			// best effort
		}
	}
}

/**
 * Synchronize token from localStorage on client-side hydration.
 * Call this from onMount to ensure token is loaded after server-side rendering.
 */
export function syncTokenFromStorage() {
	if (browser) {
		const storedToken = localStorage.getItem('ng_token');
		if (storedToken) {
			token.set(storedToken);
		}
	}
}
