<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { isLoggedIn, user, token, logout, syncTokenFromStorage } from '$lib/stores/auth';
	import type { UserProfile } from '$lib/stores/auth';
	import { theme, toggleTheme, bandwidth, toggleBandwidth, platformMode, setPlatformMode } from '$lib/stores/theme';
	import { page } from '$app/stores';
	import { api } from '$lib/api';
	import { t } from 'svelte-i18n';
	import { setupI18n, detectInitialLocale, AVAILABLE_LOCALES } from '$lib/i18n';
	import { setLocale, hydrateLocale, currentLocale } from '$lib/stores/locale';
	import { isOnline, queueCount, flushQueue, initOfflineTracking } from '$lib/stores/offline';

	// Initialise svelte-i18n as early as possible.
	// detectInitialLocale safely reads localStorage (browser-only) and navigator.language.
	setupI18n(detectInitialLocale());

	let { children } = $props();
	let mobileMenuOpen = $state(false);
	let unreadCount = $state(0);
	let crisisBannerDismissed = $state(false);
	let showUpdateBanner = $state(false);
	let installPrompt = $state<Event | null>(null);
	let langMenuOpen = $state(false);
	let syncMessage = $state('');

	function closeMobileMenu() {
		mobileMenuOpen = false;
	}

	function toggleLangMenu() {
		langMenuOpen = !langMenuOpen;
	}

	function closeLangMenu() {
		langMenuOpen = false;
	}

	async function selectLanguage(code: string) {
		await setLocale(code);
		closeLangMenu();
	}

	onMount(async () => {
		// ── Sync token from localStorage after SSR hydration ────────────────────
		syncTokenFromStorage();

		// ── Service worker registration ───────────────────────────────────────
		if ('serviceWorker' in navigator) {
			try {
				const reg = await navigator.serviceWorker.register('/service-worker.js');
				reg.addEventListener('updatefound', () => {
					const newWorker = reg.installing;
					if (!newWorker) return;
					newWorker.addEventListener('statechange', () => {
						// Show update banner once the new SW is active and a prior one existed.
						if (newWorker.state === 'activated' && navigator.serviceWorker.controller) {
							showUpdateBanner = true;
						}
					});
				});
			} catch {
				// Service worker registration failed — app still works online.
			}
		}

		// ── Install prompt (Android / desktop Chrome) ─────────────────────────
		window.addEventListener('beforeinstallprompt', (e) => {
			e.preventDefault();
			installPrompt = e;
		});

		const t = $token;
		if (t && !$user) {
			try {
				const profile = await api<UserProfile>('/users/me', { auth: true });
				user.set(profile);
				// Apply the user's saved language preference
				hydrateLocale(profile.language_code);
			} catch {
				logout();
			}
		} else if ($user) {
			hydrateLocale($user.language_code);
		}

		// Fetch platform mode and apply Red Sky automatically when active
		try {
			const res = await fetch('/api/status');
			if (res.ok) {
				const status = await res.json();
				setPlatformMode(status.mode);
			}
		} catch {
			// Backend unreachable — leave mode at default blue
		}

		// Check if user is a member of any Red Sky communities
		if (t) {
			try {
				const communities = await api<Array<{ id: number; mode: string }>>(
					'/communities/my/memberships',
					{ auth: true }
				);
				// If any community is in Red Sky mode, activate it globally
				const hasRedSky = communities.some((c) => c.mode === 'red');
				if (hasRedSky) {
					setPlatformMode('red');
				}
			} catch {
				// If we can't fetch communities, just use the instance mode
			}
		}

		// Fetch unread message count for nav badge
		if (t) {
			try {
				const data = await api<{ count: number }>('/messages/unread', { auth: true });
				unreadCount = data.count;
			} catch {
				// Ignore — badge just won't show
			}
		}

		// Restore crisis banner dismissal from session
		crisisBannerDismissed = sessionStorage.getItem('ng_crisis_banner_dismissed') === 'true';
	});

	function dismissCrisisBanner() {
		crisisBannerDismissed = true;
		sessionStorage.setItem('ng_crisis_banner_dismissed', 'true');
	}

	// Register online/offline listeners and auto-flush the request queue when
	// the device reconnects. Runs in a separate (synchronous) onMount so that
	// the cleanup function is properly returned.
	onMount(() => {
		initOfflineTracking();
		let prevOnline = navigator.onLine;
		const unsub = isOnline.subscribe((online) => {
			if (online && !prevOnline && $queueCount > 0) {
				flushQueue().then(({ succeeded }) => {
					if (succeeded > 0) {
						syncMessage = `${succeeded} queued request${succeeded !== 1 ? 's' : ''} sent successfully`;
						setTimeout(() => { syncMessage = ''; }, 5000);
					}
				});
			}
			prevOnline = online;
		});
		return () => unsub();
	});

	async function installApp() {
		if (!installPrompt) return;
		// @ts-expect-error BeforeInstallPromptEvent is not in the standard TS lib
		await installPrompt.prompt();
		installPrompt = null;
	}
</script>

<svelte:head>
	<title>NeighbourGood</title>
	<meta name="description" content="Community resource sharing platform" />
	{#if $bandwidth === 'normal'}
		<link rel="preconnect" href="https://fonts.googleapis.com" />
		<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
		<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
	{/if}
</svelte:head>

{#if langMenuOpen}
	<button class="mobile-overlay" onclick={closeLangMenu} aria-label={$t('common.close')}></button>
{/if}

<nav class="main-nav">
	<div class="nav-inner">
		<a href={$isLoggedIn ? '/dashboard' : '/'} class="nav-brand" onclick={closeMobileMenu}>
			<span class="brand-icon" aria-hidden="true">
				<svg width="18" height="17" viewBox="0 0 18 17" fill="none" xmlns="http://www.w3.org/2000/svg">
					<path d="M1 8.5L9 1l8 7.5" stroke="white" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
					<path d="M3 8.5v7a.5.5 0 00.5.5H7v-4.5h4V16h3.5a.5.5 0 00.5-.5v-7" stroke="white" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
					<path d="M9 12c0 0-2.2-1.7-2.2-3 0-.8.6-1.3 1.4-1 .3.1.6.4.8.7.2-.3.5-.6.8-.7.8-.3 1.4.2 1.4 1 0 1.3-2.2 3-2.2 3z" fill="white" opacity="0.9"/>
				</svg>
			</span>
			<span class="brand-text">Neighbour<span class="brand-accent">Good</span></span>
		</a>

		<button
			class="hamburger"
			class:open={mobileMenuOpen}
			onclick={() => mobileMenuOpen = !mobileMenuOpen}
			aria-label={$t('nav.toggle_menu')}
			aria-expanded={mobileMenuOpen}
		>
			<span class="hamburger-line"></span>
			<span class="hamburger-line"></span>
			<span class="hamburger-line"></span>
		</button>

		<div class="nav-links" class:mobile-open={mobileMenuOpen}>
			{#if $isLoggedIn}
				<a href="/dashboard" class="nav-link" class:active={$page.url.pathname === '/dashboard'} onclick={closeMobileMenu}>{$t('nav.home')}</a>
				<a href="/resources" class="nav-link" class:active={$page.url.pathname.startsWith('/resources') || $page.url.pathname.startsWith('/skills')} onclick={closeMobileMenu}>{$t('nav.browse')}</a>
				<a href="/communities" class="nav-link" class:active={$page.url.pathname.startsWith('/communities') || $page.url.pathname === '/explore'} onclick={closeMobileMenu}>{$t('nav.communities')}</a>
				<a href="/messages" class="nav-link" class:active={$page.url.pathname === '/messages'} onclick={closeMobileMenu}>
					{$t('nav.messages')}
					{#if unreadCount > 0}
						<span class="nav-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>
					{/if}
				</a>
				{#if $platformMode === 'red'}
					<a href="/triage" class="nav-link nav-link-crisis" class:active={$page.url.pathname === '/triage'} onclick={closeMobileMenu}>{$t('nav.emergency')}</a>
				{/if}
			{:else}
				<a href="/explore" class="nav-link" class:active={$page.url.pathname === '/explore'} onclick={closeMobileMenu}>{$t('nav.explore')}</a>
			{/if}

			<button
				class="theme-toggle"
				onclick={toggleTheme}
				aria-label={$t('nav.toggle_dark_mode')}
				title={$theme === 'light' ? $t('nav.switch_to_dark') : $t('nav.switch_to_light')}
			>
				{#if $theme === 'light'}
					<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
				{:else}
					<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
				{/if}
			</button>

			{#if $platformMode === 'red'}
				<button
					class="theme-toggle bandwidth-toggle"
					class:active={$bandwidth === 'low'}
					onclick={toggleBandwidth}
					aria-label={$t('nav.toggle_low_bandwidth')}
					title={$bandwidth === 'normal' ? $t('nav.enable_low_bandwidth') : $t('nav.disable_low_bandwidth')}
				>
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
						<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
					</svg>
				</button>
			{/if}

			<!-- Language selector -->
			<div class="lang-selector">
				<button
					class="theme-toggle lang-toggle"
					onclick={toggleLangMenu}
					aria-label="Select language"
					title="Select language / Choisir la langue / Seleccionar idioma"
					aria-expanded={langMenuOpen}
				>
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
						<circle cx="12" cy="12" r="10"/>
						<line x1="2" y1="12" x2="22" y2="12"/>
						<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
					</svg>
					<span class="lang-code">{$currentLocale.toUpperCase()}</span>
				</button>
				{#if langMenuOpen}
					<div class="lang-menu" role="menu">
						{#each AVAILABLE_LOCALES as lang}
							<button
								class="lang-option"
								class:active={$currentLocale === lang.code}
								onclick={() => selectLanguage(lang.code)}
								role="menuitem"
								dir={lang.rtl ? 'rtl' : 'ltr'}
							>
								{lang.name}
							</button>
						{/each}
					</div>
				{/if}
			</div>

			{#if installPrompt}
				<button class="nav-install-btn" onclick={installApp} title={$t('nav.install_app')}>
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v13M8 11l4 4 4-4"/><path d="M3 17v2a2 2 0 002 2h14a2 2 0 002-2v-2"/></svg>
					{$t('nav.install')}
				</button>
			{/if}

			{#if $isLoggedIn}
				<div class="nav-user-group">
					<a href="/settings" class="nav-icon-btn" title={$t('nav.settings')} onclick={closeMobileMenu}>
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
					</a>
					<span class="nav-user">{$user?.display_name ?? $t('nav.account')}</span>
					<button class="nav-btn" onclick={() => { closeMobileMenu(); logout(); window.location.href = '/'; }}>
						{$t('nav.logout')}
					</button>
				</div>
			{:else}
				<a href="/login" class="nav-link" onclick={closeMobileMenu}>{$t('nav.login')}</a>
				<a href="/register" class="nav-btn-primary" onclick={closeMobileMenu}>{$t('nav.signup')}</a>
			{/if}
		</div>
	</div>
</nav>

{#if mobileMenuOpen}
	<button class="mobile-overlay" onclick={closeMobileMenu} aria-label={$t('nav.close_menu')}></button>
{/if}

{#if showUpdateBanner}
	<div class="update-banner">
		<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
		<span>{$t('banner.update_available')}</span>
		<button class="update-banner-btn" onclick={() => location.reload()}>{$t('banner.refresh')}</button>
		<button class="update-banner-dismiss" onclick={() => (showUpdateBanner = false)} aria-label={$t('banner.dismiss')}>&times;</button>
	</div>
{/if}

{#if !$isOnline}
	<div class="offline-banner">
		<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
			<line x1="1" y1="1" x2="23" y2="23"/>
			<path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55"/>
			<path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39"/>
			<path d="M10.71 5.05A16 16 0 0 1 22.56 9"/>
			<path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88"/>
			<path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>
			<line x1="12" y1="20" x2="12.01" y2="20"/>
		</svg>
		<span>You're offline — browsing cached content</span>
		{#if $queueCount > 0}
			<span class="offline-queue-chip">{$queueCount} request{$queueCount !== 1 ? 's' : ''} queued</span>
		{/if}
	</div>
{/if}

{#if syncMessage}
	<div class="sync-banner">
		<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
			<polyline points="20 6 9 17 4 12"/>
		</svg>
		<span>{syncMessage}</span>
		<button class="sync-banner-dismiss" onclick={() => (syncMessage = '')} aria-label="Dismiss">&times;</button>
	</div>
{/if}

{#if $isLoggedIn && $platformMode === 'red' && !crisisBannerDismissed}
	<div class="crisis-banner">
		<span class="crisis-banner-dot"></span>
		<span>{$t('banner.crisis_active')}</span>
		<a href="/triage" class="crisis-banner-link">{$t('banner.go_to_emergency')}</a>
		<button class="crisis-banner-dismiss" onclick={dismissCrisisBanner} aria-label={$t('banner.dismiss')}>&times;</button>
	</div>
{/if}

<div class="page-content fade-in">
	{@render children()}
</div>

<style>
	.main-nav {
		position: sticky;
		top: 0;
		z-index: 100;
		background: var(--color-surface);
		border-bottom: 1px solid var(--color-border);
		box-shadow: var(--shadow-sm);
		transition: background-color var(--transition), border-color var(--transition), box-shadow var(--transition);
	}

	.nav-inner {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.75rem 1.5rem;
		max-width: 1100px;
		margin: 0 auto;
	}

	.nav-brand {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		text-decoration: none;
		color: var(--color-text);
		transition: transform var(--transition-fast);
	}

	.nav-brand:hover {
		text-decoration: none;
		transform: scale(1.02);
	}

	.brand-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 34px;
		height: 34px;
		border-radius: var(--radius-sm);
		background: var(--color-primary);
		color: white;
		flex-shrink: 0;
	}

	.brand-text {
		font-family: Georgia, 'Times New Roman', serif;
		font-weight: 400;
		font-size: 1.2rem;
		letter-spacing: -0.01em;
		color: var(--color-text);
	}

	.brand-accent {
		color: var(--color-primary);
	}

	/* ── Hamburger button (hidden on desktop) ────────────────── */

	.hamburger {
		display: none;
		flex-direction: column;
		justify-content: center;
		gap: 4px;
		width: 36px;
		height: 36px;
		padding: 6px;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-surface);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.hamburger:hover {
		border-color: var(--color-primary);
	}

	.hamburger-line {
		display: block;
		width: 100%;
		height: 2px;
		background: var(--color-text);
		border-radius: 1px;
		transition: all var(--transition-fast);
		transform-origin: center;
	}

	.hamburger.open .hamburger-line:nth-child(1) {
		transform: translateY(6px) rotate(45deg);
	}

	.hamburger.open .hamburger-line:nth-child(2) {
		opacity: 0;
	}

	.hamburger.open .hamburger-line:nth-child(3) {
		transform: translateY(-6px) rotate(-45deg);
	}

	/* ── Nav links ────────────────────────────────────────────── */

	.nav-links {
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}

	.nav-link {
		color: var(--color-text-muted);
		text-decoration: none;
		font-size: 0.88rem;
		font-weight: 500;
		padding: 0.4rem 0.7rem;
		border-radius: var(--radius-sm);
		transition: color var(--transition-fast), background-color var(--transition-fast);
		position: relative;
	}

	.nav-link:hover {
		color: var(--color-text);
		background: var(--color-primary-light);
		text-decoration: none;
	}

	.nav-link.active {
		color: var(--color-primary);
		background: var(--color-primary-light);
		font-weight: 600;
	}

	.nav-badge {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 18px;
		height: 18px;
		padding: 0 5px;
		border-radius: 999px;
		background: var(--color-error);
		color: white;
		font-size: 0.7rem;
		font-weight: 700;
		line-height: 1;
		margin-left: 4px;
		vertical-align: middle;
	}

	.nav-icon-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 32px;
		height: 32px;
		border-radius: var(--radius-sm);
		color: var(--color-text-muted);
		transition: all var(--transition-fast);
		text-decoration: none;
	}

	.nav-icon-btn:hover {
		color: var(--color-primary);
		background: var(--color-primary-light);
		text-decoration: none;
	}

	.theme-toggle {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 36px;
		height: 36px;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-surface);
		color: var(--color-text-muted);
		cursor: pointer;
		transition: all var(--transition-fast);
		margin: 0 0.25rem;
	}

	.theme-toggle:hover {
		border-color: var(--color-primary);
		color: var(--color-primary);
		background: var(--color-primary-light);
	}

	.theme-toggle:active {
		transform: scale(0.92);
	}

	.bandwidth-toggle.active {
		border-color: var(--color-accent);
		color: var(--color-accent);
		background: var(--color-accent-light);
	}

	.nav-link-crisis {
		color: var(--color-error);
		font-weight: 600;
	}

	.nav-link-crisis:hover {
		color: var(--color-error);
		background: var(--color-error-bg);
	}

	.nav-user-group {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-left: 0.25rem;
		padding-left: 0.75rem;
		border-left: 1px solid var(--color-border);
	}

	.nav-user {
		font-size: 0.85rem;
		font-weight: 500;
		color: var(--color-text);
	}

	.nav-btn {
		background: none;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		padding: 0.3rem 0.7rem;
		font-size: 0.82rem;
		font-weight: 500;
		color: var(--color-text-muted);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.nav-btn:hover {
		border-color: var(--color-error);
		color: var(--color-error);
	}

	.nav-btn-primary {
		display: inline-flex;
		align-items: center;
		background: var(--color-primary);
		color: white !important;
		padding: 0.4rem 0.9rem;
		border-radius: var(--radius-sm);
		font-size: 0.85rem;
		font-weight: 600;
		transition: all var(--transition-fast);
		text-decoration: none;
	}

	.nav-btn-primary:hover {
		background: var(--color-primary-hover);
		text-decoration: none;
		box-shadow: var(--shadow-md);
		transform: translateY(-1px);
	}

	/* ── Mobile overlay ──────────────────────────────────────── */

	.mobile-overlay {
		display: none;
	}

	/* ── Responsive: mobile layout ───────────────────────────── */

	@media (max-width: 768px) {
		.hamburger {
			display: flex;
		}

		.nav-links {
			display: none;
			position: absolute;
			top: 100%;
			left: 0;
			right: 0;
			flex-direction: column;
			align-items: stretch;
			gap: 0;
			background: var(--color-surface);
			border-bottom: 1px solid var(--color-border);
			box-shadow: var(--shadow-md);
			padding: 0.5rem 0;
			z-index: 99;
		}

		.nav-links.mobile-open {
			display: flex;
			animation: slideDown 0.18s ease-out;
		}

		@keyframes slideDown {
			from { opacity: 0; transform: translateY(-6px); }
			to   { opacity: 1; transform: translateY(0); }
		}

		.nav-link {
			padding: 0.75rem 1.5rem;
			border-radius: 0;
			font-size: 0.95rem;
		}

		.nav-link:hover {
			background: var(--color-primary-light);
		}

		.theme-toggle {
			margin: 0.25rem 1.5rem;
			align-self: flex-start;
		}

		.nav-user-group {
			margin: 0;
			padding: 0.5rem 1.5rem;
			border-left: none;
			border-top: 1px solid var(--color-border);
			justify-content: space-between;
		}

		.nav-btn-primary {
			margin: 0.25rem 1.5rem;
			justify-content: center;
		}

		.mobile-overlay {
			display: block;
			position: fixed;
			inset: 0;
			background: rgba(0, 0, 0, 0.3);
			z-index: 50;
			border: none;
			cursor: default;
		}

		.brand-text {
			font-size: 1.05rem;
		}
	}

	.page-content {
		max-width: 1000px;
		margin: 0 auto;
		padding: 3.5rem 1.5rem;
	}

	@media (max-width: 768px) {
		.page-content {
			padding: 2rem 1rem;
		}
	}

	/* ── Crisis banner ──────────────────────────────────────── */

	/* ── Update banner ──────────────────────────────────────────── */

	.update-banner {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.55rem 1.5rem;
		background: var(--color-accent-light);
		border-bottom: 1px solid var(--color-accent);
		font-size: 0.85rem;
		color: var(--color-accent);
	}

	.update-banner-btn {
		margin-left: auto;
		background: var(--color-accent);
		color: white;
		border: none;
		border-radius: var(--radius-sm);
		padding: 0.25rem 0.75rem;
		font-size: 0.82rem;
		font-weight: 600;
		cursor: pointer;
		transition: opacity var(--transition-fast);
	}

	.update-banner-btn:hover { opacity: 0.85; }

	.update-banner-dismiss {
		background: none;
		border: none;
		font-size: 1.1rem;
		color: var(--color-accent);
		cursor: pointer;
		padding: 0 0.2rem;
		opacity: 0.7;
		line-height: 1;
	}

	.update-banner-dismiss:hover { opacity: 1; }

	/* ── Install button ─────────────────────────────────────────── */

	.nav-install-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		background: var(--color-primary-light);
		color: var(--color-primary);
		border: 1px solid var(--color-primary);
		border-radius: var(--radius-sm);
		padding: 0.3rem 0.7rem;
		font-size: 0.82rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
		margin: 0 0.25rem;
	}

	.nav-install-btn:hover {
		background: var(--color-primary);
		color: white;
	}

	/* ── Language selector ──────────────────────────────────────────── */

	.lang-selector {
		position: relative;
		display: flex;
		align-items: center;
	}

	.lang-toggle {
		display: flex;
		align-items: center;
		gap: 0.3rem;
		min-width: 58px;
	}

	.lang-code {
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.03em;
	}

	.lang-menu {
		position: absolute;
		top: calc(100% + 6px);
		right: 0;
		z-index: 200;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		box-shadow: var(--shadow-md);
		min-width: 180px;
		padding: 0.35rem 0;
		display: flex;
		flex-direction: column;
	}

	.lang-option {
		background: none;
		border: none;
		padding: 0.5rem 1rem;
		text-align: left;
		font-size: 0.88rem;
		color: var(--color-text-muted);
		cursor: pointer;
		transition: background-color var(--transition-fast), color var(--transition-fast);
	}

	.lang-option:hover {
		background: var(--color-primary-light);
		color: var(--color-text);
	}

	.lang-option.active {
		color: var(--color-primary);
		font-weight: 600;
	}

	@media (max-width: 768px) {
		.lang-selector {
			margin: 0.25rem 1.5rem;
			align-self: flex-start;
		}

		.lang-menu {
			position: static;
			border: none;
			box-shadow: none;
			background: transparent;
			padding: 0;
			min-width: unset;
		}

		.lang-option {
			padding: 0.4rem 0;
			font-size: 0.9rem;
		}
	}

	/* ── Crisis banner ──────────────────────────────────────────── */

	.crisis-banner {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.6rem 1.5rem;
		background: var(--color-error-bg, rgba(239, 68, 68, 0.1));
		border-bottom: 1px solid var(--color-error);
		font-size: 0.88rem;
		color: var(--color-error);
		max-width: 100%;
	}

	.crisis-banner-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--color-error);
		flex-shrink: 0;
		animation: pulse 1.5s ease-in-out infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.4; }
	}

	.crisis-banner-link {
		margin-left: auto;
		font-weight: 600;
		color: var(--color-error);
		text-decoration: none;
		white-space: nowrap;
	}

	.crisis-banner-link:hover {
		text-decoration: underline;
	}

	.crisis-banner-dismiss {
		background: none;
		border: none;
		font-size: 1.2rem;
		color: var(--color-error);
		cursor: pointer;
		padding: 0 0.25rem;
		opacity: 0.7;
		line-height: 1;
	}

	.crisis-banner-dismiss:hover {
		opacity: 1;
	}

	/* ── Offline banner ─────────────────────────────────────────── */

	.offline-banner {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.55rem 1.5rem;
		background: var(--color-warning-bg, rgba(245, 158, 11, 0.1));
		border-bottom: 1px solid var(--color-warning, #f59e0b);
		font-size: 0.85rem;
		color: var(--color-warning, #92400e);
	}

	.offline-queue-chip {
		margin-left: auto;
		background: var(--color-warning, #f59e0b);
		color: white;
		font-size: 0.75rem;
		font-weight: 700;
		padding: 0.15rem 0.6rem;
		border-radius: 999px;
		white-space: nowrap;
	}

	/* ── Sync success banner ─────────────────────────────────────── */

	.sync-banner {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.55rem 1.5rem;
		background: var(--color-success-bg, rgba(16, 185, 129, 0.1));
		border-bottom: 1px solid var(--color-success, #10b981);
		font-size: 0.85rem;
		color: var(--color-success, #065f46);
	}

	.sync-banner-dismiss {
		margin-left: auto;
		background: none;
		border: none;
		font-size: 1.1rem;
		color: var(--color-success, #10b981);
		cursor: pointer;
		padding: 0 0.2rem;
		opacity: 0.7;
		line-height: 1;
	}

	.sync-banner-dismiss:hover {
		opacity: 1;
	}
</style>
