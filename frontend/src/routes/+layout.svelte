<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { isLoggedIn, user, token, logout, syncTokenFromStorage } from '$lib/stores/auth';
	import type { UserProfile } from '$lib/stores/auth';
	import { theme, toggleTheme, bandwidth, toggleBandwidth, platformMode, refreshPlatformMode, crisisContext } from '$lib/stores/theme';
	import { page } from '$app/stores';
	import { afterNavigate } from '$app/navigation';
	import { api } from '$lib/api';
	import { t } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { AVAILABLE_LOCALES } from '$lib/i18n';
	import { setLocale, hydrateLocale, currentLocale } from '$lib/stores/locale';
	import { isOnline, queueCount, flushQueue, initOfflineTracking, reconcileWithServiceWorker, replayFailures, dismissReplayFailures } from '$lib/stores/offline';
	import { removeMeshMessages, getMeshMessages, restoreMeshMessages, syncMeshMessagesToServer } from '$lib/stores/mesh';
	import { meshEnabled } from '$lib/stores/mesh-settings';
	import { ensureMeshKeyRegistered } from '$lib/mesh-keys';
	import { claimLocalData } from '$lib/local-data';

	// svelte-i18n is initialised (and its dictionary awaited) in +layout.ts
	// so the first SSR render never races the locale loader.

	let { children } = $props();
	interface FedAlert {
		id: number;
		source_instance_name: string;
		title: string;
		severity: string;
		is_active: boolean;
	}

	let mobileMenuOpen = $state(false);
	let unreadCount = $state(0);
	let showUpdateBanner = $state(false);
	let installPrompt = $state<Event | null>(null);
	let langMenuOpen = $state(false);
	let syncMessage = $state('');
	let fedAlerts = $state<FedAlert[]>([]);
	// Dismissed per alert ID, so a later alert still shows
	let dismissedAlertIds = $state<number[]>([]);
	const visibleFedAlerts = $derived(fedAlerts.filter((a) => !dismissedAlertIds.includes(a.id)));
	// Dismissal applies to one crisis (set of red communities / instance mode)
	let crisisBannerDismissedKey = $state('');
	const isRed = $derived($platformMode === 'red');

	const isBrowse = $derived($page.url.pathname.startsWith('/resources') || $page.url.pathname.startsWith('/skills'));

	// Local offline data belongs to one account; while online, register this
	// browser's mesh signing key so messages sent offline later can be verified
	$effect(() => {
		const current = $user;
		if (!current) return;
		claimLocalData(current.id);
		if ($meshEnabled && $isOnline) ensureMeshKeyRegistered(current.id);
	});

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

	// Red Sky can start (vote / admin toggle / instance mode) while the app is
	// open, and login/logout happen without a full reload, so the global mode and
	// cross-instance alerts are re-evaluated on navigation, tab focus and a slow
	// timer rather than only once at startup.
	let lastCrisisRefresh = 0;
	const CRISIS_REFRESH_MS = 20_000;

	async function refreshCrisisAwareness(force = false) {
		const now = Date.now();
		if (!force && now - lastCrisisRefresh < CRISIS_REFRESH_MS) return;
		lastCrisisRefresh = now;
		await refreshPlatformMode();
		if (get(token)) {
			try {
				fedAlerts = await api<FedAlert[]>('/federation/alerts?active_only=true', { auth: true });
			} catch {
				// ignore — keep showing the previous alerts
			}
		} else {
			fedAlerts = [];
		}
	}

	afterNavigate(() => {
		if (typeof window !== 'undefined') refreshCrisisAwareness();
	});

	onMount(async () => {
		// ── Sync token from localStorage after SSR hydration ────────────────────
		syncTokenFromStorage();

		// Messages received over the mesh in a previous session stay queued until synced
		restoreMeshMessages();
		// Drop queued requests the service worker already replayed while no tab was open
		reconcileWithServiceWorker();

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
				logout({ keepOfflineData: true });
			}
		} else if ($user) {
			hydrateLocale($user.language_code);
		}

		// Apply Red Sky (instance mode or any of the user's communities) and load alerts
		await refreshCrisisAwareness();

		// Fetch unread message count for nav badge
		if (t) {
			try {
				const data = await api<{ count: number }>('/messages/unread', { auth: true });
				unreadCount = data.count;
			} catch {
				// Ignore — badge just won't show
			}
		}

		// Restore banner dismissals
		try {
			crisisBannerDismissedKey = localStorage.getItem('ng_crisis_banner_dismissed') ?? '';
			dismissedAlertIds = JSON.parse(localStorage.getItem('ng_fed_alerts_dismissed') ?? '[]');
			if (!Array.isArray(dismissedAlertIds)) dismissedAlertIds = [];
		} catch {
			dismissedAlertIds = [];
		}
	});

	// A crisis that ended forgets its dismissal, so the next one shows again
	$effect(() => {
		if ($crisisContext.loaded && $crisisContext.key === '' && crisisBannerDismissedKey !== '') {
			crisisBannerDismissedKey = '';
			try { localStorage.removeItem('ng_crisis_banner_dismissed'); } catch { /* ignore */ }
		}
	});

	function dismissCrisisBanner() {
		crisisBannerDismissedKey = $crisisContext.key || 'red';
		try { localStorage.setItem('ng_crisis_banner_dismissed', crisisBannerDismissedKey); } catch { /* ignore */ }
	}

	function dismissFedAlerts() {
		// Only the alerts shown now; alerts that expired are dropped from the list
		dismissedAlertIds = [...new Set([...dismissedAlertIds.filter((id) => fedAlerts.some((a) => a.id === id)), ...visibleFedAlerts.map((a) => a.id)])];
		try { localStorage.setItem('ng_fed_alerts_dismissed', JSON.stringify(dismissedAlertIds)); } catch { /* ignore */ }
	}

	async function doLogout() {
		closeMobileMenu();
		await logout();
		window.location.href = '/';
	}

	function syncMeshNow() {
		if (getMeshMessages().length === 0 || !get(token)) return;
		syncMeshMessagesToServer().then((result) => {
			if (!result) return;
			const total = result.synced + result.duplicates;
			if (total > 0) {
				syncMessage = get(t)('mesh.sync_result', { values: { synced: result.synced, duplicates: result.duplicates, errors: result.errors } });
				setTimeout(() => { syncMessage = ''; }, 5000);
			}
		}).catch(() => {
			// Mesh sync failed — messages stay in queue for manual sync
		});
	}

	function flushNow() {
		flushQueue().then(({ succeeded }) => {
			if (succeeded > 0) {
				syncMessage = get(t)('offline.sync_success', { values: { count: succeeded } });
				setTimeout(() => { syncMessage = ''; }, 5000);
			}
		});
	}

	// Register online/offline listeners and auto-flush the request queue when
	// the device reconnects. Runs in a separate (synchronous) onMount so that
	// the cleanup function is properly returned.
	onMount(() => {
		initOfflineTracking();
		let prevOnline = navigator.onLine;
		const unsub = isOnline.subscribe(async (online) => {
			if (online && !prevOnline) {
				if ($queueCount > 0) flushNow();
				// Auto-sync mesh messages when coming back online
				syncMeshNow();
			}
			// Register Background Sync when going offline with a non-empty queue
			if (!online && $queueCount > 0 && 'serviceWorker' in navigator) {
				try {
					const reg = await navigator.serviceWorker.ready;
					if ('sync' in reg) {
						await (reg as any).sync.register('ng-flush-queue');
					}
				} catch { /* Background Sync not supported — will flush on next open */ }
			}
			prevOnline = online;
		});

		// Listen for service worker messages (e.g. queue flushed via Background Sync)
		const handleSWMessage = (event: MessageEvent) => {
			if (event.data?.type === 'ng-queue-flushed') {
				// The worker replayed requests while no tab was open: drop them here
				reconcileWithServiceWorker();
			} else if (event.data?.type === 'ng-flush-request') {
				// Background Sync fired while this tab is open: the tab replays
				if (navigator.onLine) flushNow();
			} else if (event.data?.type === 'ng-mesh-sync-request') {
				if (navigator.onLine) syncMeshNow();
			} else if (event.data?.type === 'ng-mesh-synced') {
				// Service worker synced mesh messages in the background
				if (Array.isArray(event.data.ids)) removeMeshMessages(event.data.ids);
			}
		};
		navigator.serviceWorker?.addEventListener('message', handleSWMessage);

		// Pick up a Red Sky switch that happens while the app stays open
		const onVisible = () => {
			if (document.visibilityState === 'visible') refreshCrisisAwareness();
		};
		document.addEventListener('visibilitychange', onVisible);
		const crisisTimer = setInterval(() => refreshCrisisAwareness(), 60_000);

		return () => {
			unsub();
			navigator.serviceWorker?.removeEventListener('message', handleSWMessage);
			document.removeEventListener('visibilitychange', onVisible);
			clearInterval(crisisTimer);
		};
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
		{#if $platformMode !== 'red'}
			<!-- Display serif for heros & page headers only. Deliberately not
			     loaded in Red Sky mode: the crisis UI must render fast on bad
			     connections, and Georgia (the --font-heading fallback) is free. -->
			<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;1,9..144,400&display=swap" rel="stylesheet" />
		{/if}
	{/if}
</svelte:head>

<a href="#main" class="skip-link">{$t('nav.skip_to_content')}</a>

{#if langMenuOpen}
	<button class="mobile-overlay" onclick={closeLangMenu} aria-label={$t('common.close')}></button>
{/if}

<nav class="main-nav" class:crisis={$platformMode === 'red'} aria-label={$t('nav.main_nav')}>
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
		{#if $platformMode === 'red'}
			<span class="crisis-pill">{$t('nav.crisis_mode')}</span>
		{/if}

		<button
			class="hamburger"
			class:has-tabs={$isLoggedIn}
			class:open={mobileMenuOpen}
			onclick={() => mobileMenuOpen = !mobileMenuOpen}
			aria-label={$t('nav.toggle_menu')}
			aria-expanded={mobileMenuOpen}
			aria-controls="primary-nav-links"
		>
			<span class="hamburger-line"></span>
			<span class="hamburger-line"></span>
			<span class="hamburger-line"></span>
		</button>

		<div class="nav-links" id="primary-nav-links" class:has-tabs={$isLoggedIn} class:mobile-open={mobileMenuOpen}>
			{#if $isLoggedIn && isRed}
				<!-- Red Sky: crisis-relevant items only; every other page stays reachable by URL -->
				<a href="/triage" class="nav-link nav-link-crisis" class:active={$page.url.pathname.startsWith('/triage')} onclick={closeMobileMenu}>{$t('nav.emergency')}</a>
				<a href="/resources" class="nav-link" class:active={isBrowse} onclick={closeMobileMenu}>{$t('nav.resources')}</a>
				<a href="/messages" class="nav-link" class:active={$page.url.pathname === '/messages'} onclick={closeMobileMenu}>
					{$t('nav.messages')}
					{#if unreadCount > 0}
						<span class="nav-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>
					{/if}
				</a>
				<a href="/explore" class="nav-link" class:active={$page.url.pathname === '/explore'} onclick={closeMobileMenu}>{$t('nav.map')}</a>
				{#if $meshEnabled}
					<a href="/mesh" class="nav-link" class:active={$page.url.pathname.startsWith('/mesh')} onclick={closeMobileMenu}>{$t('nav.mesh')}</a>
				{/if}
				<a href="/alerts" class="nav-link" class:active={$page.url.pathname.startsWith('/alerts')} onclick={closeMobileMenu}>{$t('nav.alerts')}</a>
				<a href="/communities" class="nav-link" class:active={$page.url.pathname.startsWith('/communities')} onclick={closeMobileMenu}>{$t('nav.communities')}</a>
			{:else if $isLoggedIn}
				<a href="/dashboard" class="nav-link" class:active={$page.url.pathname === '/dashboard'} onclick={closeMobileMenu}>{$t('nav.home')}</a>
				<a href="/resources" class="nav-link" class:active={$page.url.pathname.startsWith('/resources') || $page.url.pathname.startsWith('/skills')} onclick={closeMobileMenu}>{$t('nav.browse')}</a>
				<a href="/bookings" class="nav-link" class:active={$page.url.pathname === '/bookings'} onclick={closeMobileMenu}>{$t('nav.bookings')}</a>
				<a href="/communities" class="nav-link" class:active={$page.url.pathname.startsWith('/communities') || $page.url.pathname === '/explore'} onclick={closeMobileMenu}>{$t('nav.communities')}</a>
				<a href="/events" class="nav-link" class:active={$page.url.pathname.startsWith('/events')} onclick={closeMobileMenu}>{$t('nav.events')}</a>
				<a href="/messages" class="nav-link" class:active={$page.url.pathname === '/messages'} onclick={closeMobileMenu}>
					{$t('nav.messages')}
					{#if unreadCount > 0}
						<span class="nav-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>
					{/if}
				</a>
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
					aria-label={$t('nav.select_language')}
					title={$t('nav.select_language')}
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
					<a href="/settings" class="nav-icon-btn" title={$t('nav.settings')} aria-label={$t('nav.settings')} onclick={closeMobileMenu}>
						<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
					</a>
					{#if $user}
						<a href="/profile/{$user.id}" class="nav-user nav-user-link" title={$t('nav.view_profile')} onclick={closeMobileMenu}>{$user.display_name}</a>
					{:else}
						<span class="nav-user">{$t('nav.account')}</span>
					{/if}
					<button class="nav-btn" onclick={doLogout}>
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
		<span>{$t('offline.banner')}</span>
		{#if $queueCount > 0}
			<span class="offline-queue-chip">{$t('offline.queued', { values: { count: $queueCount } })}</span>
		{/if}
	</div>
{/if}

{#if syncMessage}
	<div class="sync-banner">
		<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
			<polyline points="20 6 9 17 4 12"/>
		</svg>
		<span>{syncMessage}</span>
		<button class="sync-banner-dismiss" onclick={() => (syncMessage = '')} aria-label={$t('banner.dismiss')}>&times;</button>
	</div>
{/if}

{#if $replayFailures.length > 0}
	<div class="replay-error-banner" role="alert">
		<span>
			{$t('offline.replay_failed', { values: { count: $replayFailures.length } })}
			{$replayFailures.map((f) => f.detail ? `${f.label} (${f.detail})` : f.label).join('; ')}
		</span>
		<button class="replay-error-dismiss" onclick={dismissReplayFailures} aria-label={$t('banner.dismiss')}>&times;</button>
	</div>
{/if}

{#if $isLoggedIn && isRed && crisisBannerDismissedKey !== ($crisisContext.key || 'red')}
	<div class="crisis-banner">
		<span class="crisis-banner-dot"></span>
		<span>{$crisisContext.instanceRed ? $t('banner.crisis_instance') : $t('banner.crisis_active')}</span>
		<a href="/triage" class="crisis-banner-link">{$t('banner.go_to_emergency')}</a>
		<button class="crisis-banner-dismiss" onclick={dismissCrisisBanner} aria-label={$t('banner.dismiss')}>&times;</button>
	</div>
{/if}

{#if visibleFedAlerts.length > 0}
	<div class="fed-alert-banner">
		<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
			<circle cx="12" cy="12" r="10"/>
			<line x1="2" y1="12" x2="22" y2="12"/>
			<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
		</svg>
		<span>
			{visibleFedAlerts.length === 1
				? `${$t('banner.fed_alert')}: ${visibleFedAlerts[0].title} (${visibleFedAlerts[0].source_instance_name})`
				: `${visibleFedAlerts.length} ${$t('banner.fed_alerts_plural')}`}
		</span>
		<a href={visibleFedAlerts.length === 1 ? `/alerts/${visibleFedAlerts[0].id}` : '/alerts'} class="fed-alert-link">{$t('banner.view_alerts')}</a>
		<button class="fed-alert-dismiss" onclick={dismissFedAlerts} aria-label={$t('banner.dismiss')}>&times;</button>
	</div>
{/if}

<main id="main" class="page-content fade-in" class:has-tabs={$isLoggedIn} tabindex="-1">
	{@render children()}
</main>

{#if $isLoggedIn}
	<nav class="bottom-nav" class:crisis={$platformMode === 'red'} aria-label={$t('nav.quick_nav')}>
		<!-- Red Sky: Resources, Emergency, Messages, Map; everything else stays under More -->
		{#if !isRed}
			<a href="/dashboard" class="bn-item" class:active={$page.url.pathname === '/dashboard'} aria-current={$page.url.pathname === '/dashboard' ? 'page' : undefined}>
				<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/></svg>
				<span>{$t('nav.home')}</span>
			</a>
		{/if}
		<a href="/resources" class="bn-item" class:active={isBrowse} aria-current={isBrowse ? 'page' : undefined}>
			<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
			<span>{isRed ? $t('nav.resources') : $t('nav.browse')}</span>
		</a>
		{#if $platformMode === 'red'}
			<a href="/triage" class="bn-item bn-crisis" class:active={$page.url.pathname.startsWith('/triage')} aria-current={$page.url.pathname.startsWith('/triage') ? 'page' : undefined}>
				<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
				<span>{$t('nav.emergency')}</span>
			</a>
		{:else}
			<a href="/bookings" class="bn-item" class:active={$page.url.pathname === '/bookings'} aria-current={$page.url.pathname === '/bookings' ? 'page' : undefined}>
				<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
				<span>{$t('nav.bookings')}</span>
			</a>
		{/if}
		<a href="/messages" class="bn-item" class:active={$page.url.pathname === '/messages'} aria-current={$page.url.pathname === '/messages' ? 'page' : undefined}>
			<span class="bn-icon">
				<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
				{#if unreadCount > 0}<span class="bn-badge" aria-hidden="true">{unreadCount > 9 ? '9+' : unreadCount}</span>{/if}
			</span>
			<span>{$t('nav.messages')}</span>
		</a>
		{#if isRed}
			<a href="/explore" class="bn-item" class:active={$page.url.pathname === '/explore'} aria-current={$page.url.pathname === '/explore' ? 'page' : undefined}>
				<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/></svg>
				<span>{$t('nav.map')}</span>
			</a>
		{/if}
		<button class="bn-item" class:active={mobileMenuOpen} onclick={() => (mobileMenuOpen = !mobileMenuOpen)} aria-expanded={mobileMenuOpen} aria-controls="primary-nav-links">
			<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/></svg>
			<span>{$t('nav.more')}</span>
		</button>
	</nav>
{/if}

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
		max-width: 1240px;
		gap: 1rem;
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
		background: var(--color-accent);
		color: white;
		flex-shrink: 0;
	}

	.brand-text {
		font-family: var(--font-heading);
		font-weight: 400;
		font-size: 1.2rem;
		letter-spacing: -0.01em;
		color: var(--color-text);
	}

	.brand-accent {
		color: var(--color-accent);
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
		color: var(--color-on-error);
		font-size: 0.7rem;
		font-weight: 700;
		line-height: 1;
		margin-inline-start: 4px;
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
		margin-inline-start: 0.25rem;
		padding-inline-start: 0.75rem;
		border-inline-start: 1px solid var(--color-border);
	}

	.nav-user {
		font-size: 0.85rem;
		font-weight: 500;
		color: var(--color-text);
	}

	.nav-user-link {
		text-decoration: none;
		transition: color var(--transition-fast);
	}

	.nav-user-link:hover {
		color: var(--color-primary);
		text-decoration: none;
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

	/* ── Red Sky identity in the nav ─────────────────────────── */

	.main-nav.crisis {
		border-top: 3px solid var(--color-primary);
		border-bottom-color: var(--color-primary);
	}

	.crisis-pill {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		margin-inline-start: 0.75rem;
		padding: 0.15rem 0.6rem;
		border-radius: 999px;
		background: var(--color-primary-hover);
		color: #fff;
		font-size: 0.68rem;
		font-weight: 800;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		white-space: nowrap;
	}

	.crisis-pill::before {
		content: '';
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: currentColor;
		animation: pulse 1.5s ease-in-out infinite;
	}

	/* Keep every nav item on one line; long display names truncate instead of
	   wrapping (the Red Sky nav has two extra controls and used to break). */
	.nav-link,
	.nav-btn,
	.nav-user {
		white-space: nowrap;
	}

	.nav-user {
		max-width: 8rem;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.nav-brand {
		flex-shrink: 0;
	}

	.nav-links {
		min-width: 0;
	}

	@media (max-width: 1040px) and (min-width: 769px) {
		.nav-inner {
			padding-inline: 1rem;
		}

		.nav-link {
			padding-inline: 0.5rem;
		}

		.nav-user {
			display: none;
		}
	}

	/* ── Mobile bottom tab bar ───────────────────────────────── */

	.bottom-nav {
		display: none;
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
			border-inline-start: none;
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

		/* 44px minimum touch targets in the dropdown */
		.hamburger {
			width: var(--tap-target);
			height: var(--tap-target);
		}

		.theme-toggle,
		.nav-icon-btn,
		.nav-btn {
			min-width: var(--tap-target);
			min-height: var(--tap-target);
		}

		.nav-link {
			min-height: var(--tap-target);
			display: flex;
			align-items: center;
		}

		/* Signed-in users get the bottom tab bar, so the dropdown becomes
		   a bottom sheet opened by its "More" tab (thumb reach) and the
		   top hamburger is redundant. */
		.hamburger.has-tabs {
			display: none;
		}

		.nav-links.has-tabs {
			position: fixed;
			top: auto;
			bottom: calc(var(--bottom-nav-height) + env(safe-area-inset-bottom, 0px));
			max-height: calc(100dvh - var(--bottom-nav-height) - 5rem);
			overflow-y: auto;
			border-bottom: none;
			border-top: 1px solid var(--color-border);
			border-radius: var(--radius-lg) var(--radius-lg) 0 0;
			box-shadow: var(--shadow-lg);
			padding: 0.75rem 0;
			z-index: 120;
		}

		.nav-links.has-tabs.mobile-open {
			flex-direction: row;
			flex-wrap: wrap;
			align-items: center;
			animation: slideUp var(--transition) ease-out;
		}

		.nav-links.has-tabs .nav-link,
		.nav-links.has-tabs .nav-user-group {
			flex: 1 1 100%;
		}

		.nav-links.has-tabs .theme-toggle {
			margin-block: 0.25rem;
			margin-inline: 0 0.25rem;
		}

		.nav-links.has-tabs .nav-link + .theme-toggle {
			margin-inline-start: 1.5rem;
		}

		.nav-links.has-tabs .lang-selector {
			flex-wrap: wrap;
			margin-inline: 0 1.5rem;
		}

		.nav-links.has-tabs .lang-menu {
			flex-basis: 100%;
		}

		.bottom-nav {
			display: flex;
			position: fixed;
			inset-inline: 0;
			bottom: 0;
			z-index: 130;
			height: calc(var(--bottom-nav-height) + env(safe-area-inset-bottom, 0px));
			padding-bottom: env(safe-area-inset-bottom, 0px);
			background: var(--color-surface);
			border-top: 1px solid var(--color-border);
			box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.06);
		}

		.bottom-nav.crisis {
			border-top: 2px solid var(--color-primary);
		}

		.bn-item {
			flex: 1;
			min-width: 0;
			display: flex;
			flex-direction: column;
			align-items: center;
			justify-content: center;
			gap: 0.2rem;
			padding: 0.4rem 0.25rem;
			background: none;
			border: none;
			color: var(--color-text-muted);
			font-family: inherit;
			font-size: 0.68rem;
			font-weight: 600;
			letter-spacing: 0.01em;
			text-decoration: none;
			cursor: pointer;
			-webkit-tap-highlight-color: transparent;
		}

		.bn-item span:not(.bn-icon):not(.bn-badge) {
			max-width: 100%;
			overflow: hidden;
			text-overflow: ellipsis;
			white-space: nowrap;
		}

		.bn-item:hover {
			text-decoration: none;
			color: var(--color-text);
		}

		.bn-item.active {
			color: var(--color-primary);
		}

		.bn-item.active svg {
			stroke-width: 2.4;
		}

		.bn-crisis:not(.active) {
			color: var(--color-error);
		}

		.bn-icon {
			position: relative;
			display: inline-flex;
		}

		.bn-badge {
			position: absolute;
			top: -5px;
			inset-inline-end: -9px;
			min-width: 16px;
			height: 16px;
			padding: 0 4px;
			border-radius: 999px;
			background: var(--color-error);
			color: var(--color-on-error);
			font-size: 0.62rem;
			font-weight: 800;
			line-height: 16px;
			text-align: center;
		}
	}

	.page-content {
		max-width: 1000px;
		margin: 0 auto;
		padding: 3.5rem 1.5rem;
	}

	.page-content:focus {
		outline: none;
	}

	@media (max-width: 768px) {
		.page-content {
			padding: 2rem 1rem;
		}

		.page-content.has-tabs {
			padding-bottom: calc(var(--bottom-nav-height) + env(safe-area-inset-bottom, 0px) + 1.5rem);
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
		margin-inline-start: auto;
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

	/* Banner dismiss buttons: 44px hit area without growing the banner */
	.update-banner-dismiss,
	.crisis-banner-dismiss,
	.fed-alert-dismiss,
	.sync-banner-dismiss {
		min-width: var(--tap-target);
		min-height: var(--tap-target);
		margin-block: -0.7rem;
		margin-inline-end: -0.75rem;
	}

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
		inset-inline-end: 0;
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
		text-align: start;
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
		margin-inline-start: auto;
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

	/* ── Federation alert banner ────────────────────────────────── */

	.fed-alert-banner {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.55rem 1.5rem;
		background: var(--color-warning-bg, rgba(245, 158, 11, 0.1));
		border-bottom: 1px solid var(--color-warning, #f59e0b);
		font-size: 0.85rem;
		color: var(--color-warning, #92400e);
	}

	.fed-alert-link {
		margin-inline-start: auto;
		font-weight: 600;
		color: var(--color-warning, #92400e);
		text-decoration: none;
		white-space: nowrap;
	}

	.fed-alert-link:hover {
		text-decoration: underline;
	}

	.fed-alert-dismiss {
		background: none;
		border: none;
		font-size: 1.2rem;
		color: var(--color-warning, #f59e0b);
		cursor: pointer;
		padding: 0 0.25rem;
		opacity: 0.7;
		line-height: 1;
	}

	.fed-alert-dismiss:hover {
		opacity: 1;
	}

	/* ── Replay failure banner ──────────────────────────────────── */

	.replay-error-banner {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.55rem 1.5rem;
		background: var(--color-error-bg);
		border-bottom: 1px solid var(--color-error);
		font-size: 0.85rem;
		color: var(--color-error);
	}

	.replay-error-dismiss {
		margin-inline-start: auto;
		background: none;
		border: none;
		font-size: 1.1rem;
		color: var(--color-error);
		cursor: pointer;
		padding: 0 0.2rem;
		opacity: 0.7;
		line-height: 1;
	}

	.replay-error-dismiss:hover {
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
		margin-inline-start: auto;
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
		margin-inline-start: auto;
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
