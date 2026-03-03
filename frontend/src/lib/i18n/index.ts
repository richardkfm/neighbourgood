/**
 * svelte-i18n initialisation for NeighbourGood.
 *
 * Locale resolution order (highest priority first):
 *   1. Authenticated user's language_code from their profile
 *   2. ng_locale key in localStorage
 *   3. Browser navigator.language (e.g. "ar", "fr-FR" → "fr")
 *   4. Default: "en"
 *
 * RTL languages: Arabic, Urdu, Hebrew, Farsi.
 * When one of these is active the <html dir="rtl"> attribute is set reactively
 * via the locale store in $lib/stores/locale.ts.
 */

import { register, init, getLocaleFromNavigator } from 'svelte-i18n';

export const SUPPORTED_LOCALES = ['en', 'ar', 'fr', 'es', 'sw', 'id', 'uk', 'de', 'nl', 'el', 'fa', 'su'] as const;
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

export const RTL_LOCALES: ReadonlySet<string> = new Set(['ar', 'ur', 'he', 'fa']);

/** Languages available in Tier 1 (this release). */
export const AVAILABLE_LOCALES: { code: string; name: string; rtl: boolean }[] = [
	{ code: 'en', name: 'English', rtl: false },
	{ code: 'ar', name: 'العربية', rtl: true },
	{ code: 'fr', name: 'Français', rtl: false },
	{ code: 'es', name: 'Español', rtl: false },
	{ code: 'sw', name: 'Kiswahili', rtl: false },
	{ code: 'id', name: 'Bahasa Indonesia', rtl: false },
	{ code: 'uk', name: 'Українська', rtl: false },
	{ code: 'de', name: 'Deutsch', rtl: false },
	{ code: 'nl', name: 'Nederlands', rtl: false },
	{ code: 'el', name: 'Ελληνικά', rtl: false },
	{ code: 'fa', name: 'فارسی', rtl: true },
	{ code: 'su', name: 'Basa Sunda', rtl: false }
];

// Register all supported locales as lazy loaders (only fetched when needed).
register('en', () => import('./locales/en.json'));
register('ar', () => import('./locales/ar.json'));
register('fr', () => import('./locales/fr.json'));
register('es', () => import('./locales/es.json'));
register('sw', () => import('./locales/sw.json'));
register('id', () => import('./locales/id.json'));
register('uk', () => import('./locales/uk.json'));
register('de', () => import('./locales/de.json'));
register('nl', () => import('./locales/nl.json'));
register('el', () => import('./locales/el.json'));
register('fa', () => import('./locales/fa.json'));
register('su', () => import('./locales/su.json'));

/** Normalise a BCP 47 tag to the closest supported locale, or 'en'. */
export function resolveLocale(tag: string | null | undefined): string {
	if (!tag) return 'en';
	const code = tag.split('-')[0].toLowerCase();
	if ((SUPPORTED_LOCALES as readonly string[]).includes(code)) return code;
	return 'en';
}

/**
 * Determine the initial locale without touching any stores.
 * Called once during app bootstrap.
 */
export function detectInitialLocale(userLanguageCode?: string | null): string {
	// 1. Authenticated user preference
	if (userLanguageCode) return resolveLocale(userLanguageCode);

	// 2. Persisted user choice
	if (typeof localStorage !== 'undefined') {
		const stored = localStorage.getItem('ng_locale');
		if (stored) return resolveLocale(stored);
	}

	// 3. Browser language
	return resolveLocale(getLocaleFromNavigator());
}

/** Initialise svelte-i18n. Call this once at app startup (e.g. in +layout.svelte). */
export function setupI18n(initialLocale: string = 'en') {
	init({
		fallbackLocale: 'en',
		initialLocale
	});
}
