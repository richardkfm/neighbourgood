/**
 * Universal layout load — initialises svelte-i18n and, crucially, awaits the
 * locale dictionary before any page renders.
 *
 * Without the await, the very first SSR request after a server (re)start
 * rendered while the async locale loader was still in flight and crashed with
 * "[svelte-i18n] Cannot format a message without first setting the initial
 * locale" — a 500 for whoever hit the freshly restarted instance first
 * (typically a returning logged-in user opening the app).
 */

import { get } from 'svelte/store';
import { waitLocale } from 'svelte-i18n';
import { browser } from '$app/environment';
import { api } from '$lib/api';
import { setupI18n, detectInitialLocale } from '$lib/i18n';
import { token, user } from '$lib/stores/auth';
import type { UserProfile } from '$lib/stores/auth';
import type { LayoutLoad } from './$types';

let initialised = false;

export const load: LayoutLoad = async ({ fetch }) => {
	if (!initialised) {
		// detectInitialLocale safely returns 'en' on the server (no
		// localStorage/navigator) and the visitor's preference in the browser.
		setupI18n(detectInitialLocale());
		initialised = true;
	}
	await waitLocale();

	// Child pages mount (and run their onMount) before the layout's own onMount,
	// so on a hard reload `$user` would still be null while pages decide
	// ownership / membership / "already reviewed". Load the profile here so it
	// is in place before any page renders.
	if (browser && get(token) && !get(user)) {
		try {
			user.set(await api<UserProfile>('/users/me', { auth: true, fetch }));
		} catch {
			// Invalid session or backend down: the layout's onMount handles it.
		}
	}
};
