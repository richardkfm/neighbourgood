/**
 * Theme store – manages dark/light mode preference.
 * Persists to localStorage and syncs with the <html> data-theme attribute.
 */

import { writable, get } from 'svelte/store';
import { api } from '$lib/api';
import { token } from '$lib/stores/auth';

function getInitialTheme(): 'light' | 'dark' {
	if (typeof localStorage === 'undefined') return 'light';
	const stored = localStorage.getItem('ng_theme');
	if (stored === 'dark' || stored === 'light') return stored;
	return 'light';
}

export const theme = writable<'light' | 'dark'>(getInitialTheme());

theme.subscribe((val) => {
	if (typeof document !== 'undefined') {
		document.documentElement.setAttribute('data-theme', val);
	}
	if (typeof localStorage !== 'undefined') {
		localStorage.setItem('ng_theme', val);
	}
});

export function toggleTheme() {
	theme.update((t) => (t === 'light' ? 'dark' : 'light'));
}

// ── Low-bandwidth mode ────────────────────────────────────────────────────────
// Eliminates transitions, shadows, and decorative images to reduce data usage
// and rendering cost on slow or metered connections.

function getInitialBandwidth(): 'normal' | 'low' {
	if (typeof localStorage === 'undefined') return 'normal';
	const stored = localStorage.getItem('ng_bandwidth');
	if (stored === 'low' || stored === 'normal') return stored;
	return 'normal';
}

export const bandwidth = writable<'normal' | 'low'>(getInitialBandwidth());

bandwidth.subscribe((val) => {
	if (typeof document !== 'undefined') {
		document.documentElement.setAttribute('data-bandwidth', val);
	}
	if (typeof localStorage !== 'undefined') {
		localStorage.setItem('ng_bandwidth', val);
	}
});

export function toggleBandwidth() {
	bandwidth.update((b) => (b === 'normal' ? 'low' : 'normal'));
}

// ── Platform mode ─────────────────────────────────────────────────────────────
// Tracks whether the instance is in Blue Sky (normal) or Red Sky (crisis) mode.
// Setting Red Sky automatically forces low-bandwidth mode to reduce data usage
// during emergencies.

export const platformMode = writable<'blue' | 'red'>('blue');

/** Bandwidth preference to restore once Red Sky ends (Red Sky forces 'low'). */
const PRE_RED_BANDWIDTH_KEY = 'ng_bandwidth_pre_red';

export function setPlatformMode(mode: 'blue' | 'red') {
	platformMode.set(mode);
	if (typeof document !== 'undefined') {
		if (mode === 'red') {
			document.documentElement.setAttribute('data-mode', 'red');
			try {
				// Remember the user's own preference once; a reload while still in
				// Red Sky must not overwrite it with the forced 'low'.
				if (localStorage.getItem(PRE_RED_BANDWIDTH_KEY) === null) {
					localStorage.setItem(PRE_RED_BANDWIDTH_KEY, get(bandwidth));
				}
			} catch {
				// localStorage unavailable — skip restore support
			}
			bandwidth.set('low');
		} else {
			document.documentElement.removeAttribute('data-mode');
			// The bandwidth toggle is only shown in Red Sky, so without this the
			// forced low-bandwidth mode would stick forever after the crisis (also
			// when the crisis ended while the app was closed).
			try {
				const previous = localStorage.getItem(PRE_RED_BANDWIDTH_KEY);
				if (previous !== null) {
					localStorage.removeItem(PRE_RED_BANDWIDTH_KEY);
					if (previous === 'normal') bandwidth.set('normal');
				}
			} catch {
				// ignore
			}
		}
	}
}

/**
 * Derive the global Blue/Red Sky UI mode from the instance mode and the
 * viewer's own community memberships (any Red Sky community => Red Sky UI).
 * On a network error the current mode is kept, so going offline mid-crisis
 * never flips the UI back to Blue Sky.
 */
export async function refreshPlatformMode(): Promise<void> {
	let mode: 'blue' | 'red';
	try {
		const status = await api<{ mode: string }>('/status');
		mode = status.mode === 'red' ? 'red' : 'blue';
	} catch {
		return;
	}
	if (get(token)) {
		try {
			const communities = await api<Array<{ mode: string }>>('/communities/my/memberships', {
				auth: true
			});
			if (communities.some((c) => c.mode === 'red')) mode = 'red';
		} catch {
			return;
		}
	}
	setPlatformMode(mode);
}
