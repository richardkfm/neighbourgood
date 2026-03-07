<script lang="ts">
	import { onMount } from 'svelte';
	import { isLoggedIn } from '$lib/stores/auth';
	import { t } from 'svelte-i18n';

	interface MapCommunity {
		id: number;
		name: string;
		city: string;
		postal_code: string;
		country_code: string;
		member_count: number;
		resource_count: number;
		skill_count: number;
		mode: string;
		latitude: number | null;
		longitude: number | null;
	}

	function activityScore(c: MapCommunity): number {
		return c.member_count + c.resource_count * 2 + c.skill_count * 2;
	}

	function activityLevel(c: MapCommunity): 'high' | 'medium' | 'low' {
		const s = activityScore(c);
		if (s >= 10) return 'high';
		if (s >= 4) return 'medium';
		return 'low';
	}

	let communities = $state<MapCommunity[]>([]);
	let loading = $state(true);
	let error = $state('');
	let mapContainer: HTMLDivElement;
	let map: any = $state(null);
	let userLocated = $state(false);
	let userLat = $state(51.1657);  // Default: center of Germany
	let userLng = $state(10.4515);

	async function loadLeaflet(): Promise<any> {
		// Load Leaflet CSS
		if (!document.querySelector('link[href*="leaflet"]')) {
			const link = document.createElement('link');
			link.rel = 'stylesheet';
			link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
			document.head.appendChild(link);
		}
		// Load Leaflet JS
		if ((window as any).L) return (window as any).L;
		return new Promise((resolve, reject) => {
			const script = document.createElement('script');
			script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
			script.onload = () => resolve((window as any).L);
			script.onerror = reject;
			document.head.appendChild(script);
		});
	}

	function locateUser(): Promise<{ lat: number; lng: number } | null> {
		return new Promise((resolve) => {
			if (!navigator.geolocation) {
				resolve(null);
				return;
			}
			navigator.geolocation.getCurrentPosition(
				(pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
				() => resolve(null),
				{ timeout: 5000, enableHighAccuracy: false }
			);
		});
	}

	onMount(async () => {
		// Fetch communities
		try {
			const res = await fetch('/api/communities/map');
			if (res.ok) {
				communities = await res.json();
			} else {
				error = 'Could not load communities';
			}
		} catch {
			error = 'Could not connect to backend';
		} finally {
			loading = false;
		}

		// Initialize map
		try {
			const L = await loadLeaflet();

			// Try to locate user
			const pos = await locateUser();
			if (pos) {
				userLat = pos.lat;
				userLng = pos.lng;
				userLocated = true;
			}

			map = L.map(mapContainer).setView([userLat, userLng], userLocated ? 12 : 6);

			// Themed tiles: dark or light based on system preference
			const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
			const tileUrl = prefersDark
				? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
				: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';
			L.tileLayer(tileUrl, {
				attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
				maxZoom: 19,
				subdomains: 'abcd',
			}).addTo(map);

			// User position marker
			if (userLocated) {
				const userIcon = L.divIcon({
					className: 'user-marker',
					html: '<div class="user-dot"></div>',
					iconSize: [20, 20],
					iconAnchor: [10, 10],
				});
				L.marker([userLat, userLng], { icon: userIcon })
					.addTo(map)
					.bindPopup(`<strong>${$t('explore.you_are_here')}</strong>`);
			}

			// Community markers – size scales with activity
			for (const c of communities) {
				if (c.latitude != null && c.longitude != null) {
					const level = activityLevel(c);
					const size = level === 'high' ? 40 : level === 'medium' ? 34 : 28;
					const color = c.mode === 'red' ? '#ef4444' : '#4f46e5';
					const ringClass = level === 'high' ? 'ring-active' : '';
					const icon = L.divIcon({
						className: 'community-marker',
						html: `<div class="community-dot ${ringClass}" style="background:${color};width:${size}px;height:${size}px"><span>${c.member_count}</span></div>`,
						iconSize: [size, size],
						iconAnchor: [size / 2, size / 2],
					});
					const totalItems = c.resource_count + c.skill_count;
					L.marker([c.latitude, c.longitude], { icon })
						.addTo(map)
						.bindPopup(`
							<strong>${c.name}</strong><br/>
							${c.city} (${c.postal_code})<br/>
							${c.member_count} member${c.member_count !== 1 ? 's' : ''}
							&middot; ${c.resource_count} item${c.resource_count !== 1 ? 's' : ''}
							&middot; ${c.skill_count} skill${c.skill_count !== 1 ? 's' : ''}<br/>
							<a href="/communities/${c.id}">${$t('explore.view_community')}</a>
						`);
				}
			}
		} catch (e) {
			console.warn('Map initialization failed:', e);
		}
	});

	const sortedCommunities = $derived(
		[...communities].sort((a, b) => activityScore(b) - activityScore(a))
	);
</script>

<div class="explore-page">
	<div class="explore-header slide-up">
		<div>
			<h1>{$t('explore.title')}</h1>
			<p class="subtitle">{$t('explore.subtitle')}</p>
		</div>
		{#if !$isLoggedIn}
			<a href="/register" class="btn-cta">{$t('explore.join_neighbourgood')}</a>
		{/if}
	</div>

	{#if error}
		<div class="alert alert-error fade-in">{error}</div>
	{/if}

	<div class="map-wrapper slide-up" style="animation-delay: 0.05s">
		<div bind:this={mapContainer} class="map-container"></div>
		{#if loading}
			<div class="map-loading">
				<p>{$t('explore.map_loading')}</p>
			</div>
		{/if}
	</div>

	{#if !userLocated && !loading}
		<div class="location-hint fade-in">
			<p>{$t('explore.no_location')}</p>
		</div>
	{/if}

	{#if communities.length === 0 && !loading && !error}
		<div class="no-communities fade-in">
			<h2>{$t('explore.no_communities')}</h2>
			<p>{$t('explore.first_community')}</p>
			{#if $isLoggedIn}
				<a href="/onboarding" class="btn-primary">{$t('explore.create_community')}</a>
			{:else}
				<a href="/register" class="btn-primary">{$t('explore.sign_up_create')}</a>
			{/if}
		</div>
	{/if}

	{#if sortedCommunities.length > 0}
		<section class="community-list slide-up" style="animation-delay: 0.1s">
			<h2>{$t('explore.communities_heading')}</h2>
			<div class="list-grid">
				{#each sortedCommunities as c, i (c.id)}
					{@const level = activityLevel(c)}
					<a href={$isLoggedIn ? `/communities/${c.id}` : '/register'}
					   class="list-card"
					   class:card-active={level === 'high'}
					   class:card-medium={level === 'medium'}>
						<div class="list-card-header">
							<h3>{c.name}</h3>
							{#if level === 'high'}
								<span class="badge-active">{$t('explore.active_badge')}</span>
							{/if}
							{#if c.mode === 'red'}
								<span class="badge-crisis">{$t('explore.crisis_badge')}</span>
							{/if}
						</div>
						<div class="list-card-meta">
							<span class="tag">{c.postal_code}</span>
							<span class="tag">{c.city}</span>
						</div>
						<div class="list-card-stats">
							<span>{c.member_count} member{c.member_count !== 1 ? 's' : ''}</span>
							<span class="stat-sep">&middot;</span>
							<span>{c.resource_count} item{c.resource_count !== 1 ? 's' : ''}</span>
							<span class="stat-sep">&middot;</span>
							<span>{c.skill_count} skill{c.skill_count !== 1 ? 's' : ''}</span>
						</div>
					</a>
				{/each}
			</div>
		</section>
	{/if}

	{#if !$isLoggedIn}
		<section class="cta-section slide-up" style="animation-delay: 0.15s">
			<h2>{$t('explore.cta_title')}</h2>
			<p>{$t('explore.cta_desc')}</p>
			<div class="cta-actions">
				<a href="/register" class="btn-cta">{$t('auth.register_btn')}</a>
				<a href="/login" class="btn-secondary">{$t('auth.have_account')}</a>
			</div>
		</section>
	{/if}
</div>

<style>
	.explore-page {
		max-width: 900px;
		margin: 0 auto;
	}

	.explore-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 1.5rem;
	}

	.explore-header h1 {
		font-size: 1.75rem;
		font-weight: 400;
		letter-spacing: -0.02em;
	}

	.subtitle {
		color: var(--color-text-muted);
		font-size: 0.95rem;
		margin-top: 0.25rem;
	}

	/* ── Map ──────────────────────────────────── */

	.map-wrapper {
		position: relative;
		border-radius: var(--radius-lg);
		overflow: hidden;
		border: 1px solid var(--color-border);
		box-shadow: var(--shadow-md);
		margin-bottom: 1.5rem;
	}

	.map-container {
		width: 100%;
		height: 450px;
		background: var(--color-surface);
	}

	.map-loading {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--color-surface);
		z-index: 10;
	}

	.map-loading p {
		color: var(--color-text-muted);
		font-size: 0.9rem;
	}

	.location-hint {
		padding: 0.65rem 1rem;
		border-radius: var(--radius);
		background: var(--color-warning-bg);
		border: 1px solid var(--color-warning);
		color: var(--color-warning);
		font-size: 0.85rem;
		margin-bottom: 1.5rem;
	}

	/* ── Custom Leaflet markers ──────────────── */

	:global(.user-marker) {
		background: none !important;
		border: none !important;
	}

	:global(.user-dot) {
		width: 16px;
		height: 16px;
		background: #3b82f6;
		border: 3px solid white;
		border-radius: 50%;
		box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.4), 0 2px 8px rgba(0, 0, 0, 0.2);
		animation: pulse-dot 2s infinite;
	}

	@keyframes pulse-dot {
		0%, 100% { box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.4), 0 2px 8px rgba(0, 0, 0, 0.2); }
		50% { box-shadow: 0 0 0 8px rgba(59, 130, 246, 0.15), 0 2px 8px rgba(0, 0, 0, 0.2); }
	}

	:global(.community-marker) {
		background: none !important;
		border: none !important;
	}

	:global(.community-dot) {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 32px;
		height: 32px;
		border-radius: 50%;
		color: white;
		font-size: 0.7rem;
		font-weight: 700;
		box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
		border: 2px solid white;
	}

	:global(.community-dot span) {
		line-height: 1;
	}

	:global(.ring-active) {
		box-shadow: 0 0 0 4px rgba(79, 70, 229, 0.25), 0 2px 6px rgba(0, 0, 0, 0.3) !important;
		animation: pulse-ring 2s infinite;
	}

	@keyframes pulse-ring {
		0%, 100% { box-shadow: 0 0 0 4px rgba(79, 70, 229, 0.25), 0 2px 6px rgba(0, 0, 0, 0.3); }
		50% { box-shadow: 0 0 0 8px rgba(79, 70, 229, 0.1), 0 2px 6px rgba(0, 0, 0, 0.3); }
	}

	/* ── Community list ──────────────────────── */

	.community-list {
		margin-bottom: 1.5rem;
	}

	.community-list h2 {
		font-size: 1.2rem;
		font-weight: 500;
		margin-bottom: 0.75rem;
	}

	.list-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
		gap: 0.75rem;
	}

	.list-card {
		display: block;
		padding: 1rem 1.25rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		text-decoration: none;
		color: var(--color-text);
		transition: all var(--transition-fast);
	}

	.list-card:hover {
		border-color: var(--color-primary);
		box-shadow: var(--shadow-md);
		transform: translateY(-2px);
		text-decoration: none;
	}

	.card-active {
		border-color: var(--color-primary);
		border-left: 3px solid var(--color-primary);
		background: linear-gradient(135deg, var(--color-surface) 0%, var(--color-primary-light) 100%);
	}

	.card-medium {
		border-left: 3px solid var(--color-accent);
	}

	.list-card-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.35rem;
	}

	.list-card-header h3 {
		font-size: 0.95rem;
		font-weight: 500;
	}

	.badge-active {
		font-size: 0.6rem;
		font-weight: 600;
		padding: 0.1rem 0.4rem;
		border-radius: 999px;
		background: var(--color-primary);
		color: white;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.badge-crisis {
		font-size: 0.65rem;
		font-weight: 600;
		padding: 0.1rem 0.4rem;
		border-radius: 999px;
		background: var(--color-error);
		color: white;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.list-card-meta {
		display: flex;
		gap: 0.35rem;
		margin-bottom: 0.35rem;
	}

	.list-card-stats {
		display: flex;
		gap: 0.3rem;
		font-size: 0.78rem;
		color: var(--color-text-muted);
		margin-top: 0.15rem;
	}

	.stat-sep {
		color: var(--color-border);
	}

	/* ── No communities ──────────────────────── */

	.no-communities {
		text-align: center;
		padding: 2.5rem 1rem;
		background: var(--color-surface);
		border: 1px dashed var(--color-border);
		border-radius: var(--radius-lg);
		margin-bottom: 1.5rem;
	}

	.no-communities h2 {
		font-size: 1.2rem;
		margin-bottom: 0.4rem;
	}

	.no-communities p {
		color: var(--color-text-muted);
		margin-bottom: 1rem;
	}

	/* ── CTA section ─────────────────────────── */

	.cta-section {
		text-align: center;
		padding: 2.5rem 1.5rem;
		background: var(--color-primary-light);
		border: 1px solid var(--color-primary);
		border-radius: var(--radius-lg);
		margin-bottom: 1.5rem;
	}

	.cta-section h2 {
		font-size: 1.25rem;
		font-weight: 500;
		margin-bottom: 0.5rem;
	}

	.cta-section p {
		color: var(--color-text-muted);
		margin-bottom: 1.25rem;
		max-width: 500px;
		margin-left: auto;
		margin-right: auto;
	}

	.cta-actions {
		display: flex;
		justify-content: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	/* ── Buttons ──────────────────────────────── */

	.btn-cta {
		display: inline-flex;
		align-items: center;
		padding: 0.6rem 1.25rem;
		background: var(--color-primary);
		color: white !important;
		border-radius: var(--radius);
		font-size: 0.9rem;
		font-weight: 600;
		text-decoration: none;
		transition: all var(--transition-fast);
		box-shadow: var(--shadow);
	}

	.btn-cta:hover {
		background: var(--color-primary-hover);
		box-shadow: var(--shadow-md);
		transform: translateY(-1px);
		text-decoration: none;
	}

	.btn-primary {
		display: inline-block;
		padding: 0.5rem 1.25rem;
		background: var(--color-primary);
		color: white !important;
		border-radius: var(--radius);
		font-size: 0.9rem;
		font-weight: 600;
		text-decoration: none;
		transition: all var(--transition-fast);
	}

	.btn-primary:hover {
		background: var(--color-primary-hover);
		text-decoration: none;
	}

	.btn-secondary {
		display: inline-flex;
		align-items: center;
		padding: 0.6rem 1.25rem;
		background: var(--color-surface);
		color: var(--color-text);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.9rem;
		font-weight: 500;
		text-decoration: none;
		transition: all var(--transition-fast);
	}

	.btn-secondary:hover {
		border-color: var(--color-primary);
		color: var(--color-primary);
		text-decoration: none;
	}

	@media (max-width: 640px) {
		.explore-header {
			flex-direction: column;
		}

		.map-container {
			height: 350px;
		}

		.list-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
