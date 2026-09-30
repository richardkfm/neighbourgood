/**
 * Locale store — manages the active language and RTL state.
 *
 * Consumers:
 *   import { setLocale, isRTL, currentLocale } from '$lib/stores/locale';
 */

import { derived, get } from 'svelte/store';
import { locale } from 'svelte-i18n';
import { browser } from '$app/environment';
import { RTL_LOCALES, resolveLocale, AVAILABLE_LOCALES } from '$lib/i18n';
import { api } from '$lib/api';
import { isLoggedIn } from '$lib/stores/auth';

export { AVAILABLE_LOCALES };

/** The currently active locale code (e.g. "en", "ar"). */
export const currentLocale = derived(locale, ($l) => $l ?? 'en');

/** True when the active locale is right-to-left. */
export const isRTL = derived(locale, ($l) => RTL_LOCALES.has($l ?? ''));

// Keep <html lang/dir> in step with the active locale however it was chosen
// (saved choice, browser language, profile, language menu). Without this a
// reload of an RTL locale chosen earlier, or one detected from the browser,
// rendered Arabic/Farsi text in a left-to-right page.
if (browser) {
	locale.subscribe(($l) => {
		if (!$l) return;
		document.documentElement.setAttribute('lang', $l);
		document.documentElement.setAttribute('dir', RTL_LOCALES.has($l) ? 'rtl' : 'ltr');
	});
}

/**
 * Switch the active locale.
 * - Persists to localStorage.
 * - Applies dir="rtl"/"ltr" on <html>.
 * - If the user is logged in, syncs to their profile via PATCH /users/me.
 */
export async function setLocale(code: string, syncToProfile = true): Promise<void> {
	const resolved = resolveLocale(code);
	locale.set(resolved);

	if (browser) {
		localStorage.setItem('ng_locale', resolved);
		document.documentElement.setAttribute('lang', resolved);
		document.documentElement.setAttribute('dir', RTL_LOCALES.has(resolved) ? 'rtl' : 'ltr');
	}

	if (syncToProfile && get(isLoggedIn)) {
		try {
			await api('/users/me', {
				method: 'PATCH',
				body: { language_code: resolved },
				auth: true
			});
		} catch {
			// Profile sync is best-effort — locale is already applied locally.
		}
	}
}

/**
 * Initialise locale on client hydration from the user profile or localStorage.
 * Call this from onMount in +layout.svelte after the user profile is loaded.
 */
export function hydrateLocale(userLanguageCode?: string | null): void {
	if (!browser) return;

	// User profile takes priority over localStorage
	if (userLanguageCode) {
		const resolved = resolveLocale(userLanguageCode);
		locale.set(resolved);
		document.documentElement.setAttribute('lang', resolved);
		document.documentElement.setAttribute('dir', RTL_LOCALES.has(resolved) ? 'rtl' : 'ltr');
		localStorage.setItem('ng_locale', resolved);
		return;
	}

	// Restore from localStorage (already done by setupI18n, but re-apply DOM attributes)
	const stored = localStorage.getItem('ng_locale');
	if (stored) {
		const resolved = resolveLocale(stored);
		document.documentElement.setAttribute('lang', resolved);
		document.documentElement.setAttribute('dir', RTL_LOCALES.has(resolved) ? 'rtl' : 'ltr');
	}
}
