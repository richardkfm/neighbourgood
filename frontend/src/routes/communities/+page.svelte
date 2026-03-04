<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { isLoggedIn } from '$lib/stores/auth';
	import { theme } from '$lib/stores/theme';
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

	interface MyCommunity {
		id: number;
		name: string;
		description: string | null;
		postal_code: string;
		city: string;
		member_count: number;
		is_active: boolean;
		mode: string;
	}

	let allCommunities = $state<MapCommunity[]>([]);
	let myCommunities = $state<MyCommunity[]>([]);
	let loading = $state(true);
	let error = $state('');
	let mapContainer: HTMLDivElement;
	let map: any = $state(null);
	let userLat = $state(51.1657);
	let userLng = $state(10.4515);
	let userLocated = $state(false);

	function activityLevel(c: MapCommunity): 'high' | 'medium' | 'low' {
		const s = c.member_count + c.resource_count * 2 + c.skill_count * 2;
		if (s >= 10) return 'high';
		if (s >= 4) return 'medium';
		return 'low';
	}

	async function loadLeaflet(): Promise<any> {
		if (!document.querySelector('link[href*="leaflet"]')) {
			const link = document.createElement('link');
			link.rel = 'stylesheet';
			link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
			document.head.appendChild(link);
		}
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
			if (!navigator.geolocation) { resolve(null); return; }
			navigator.geolocation.getCurrentPosition(
				(pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
				() => resolve(null),
				{ timeout: 5000, enableHighAccuracy: false }
			);
		});
	}

	const myIds = $derived(new Set(myCommunities.map((c) => c.id)));

	onMount(async () => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}

		// Fetch map communities and user's memberships in parallel
		try {
			const [mapData, myData] = await Promise.all([
				fetch('/api/communities/map').then((r) => r.ok ? r.json() : []),
				api<MyCommunity[]>('/communities/my/memberships', { auth: true })
			]);
			allCommunities = mapData;
			myCommunities = myData;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load communities';
		} finally {
			loading = false;
		}

		// Initialize map
		try {
			const L = await loadLeaflet();
			const pos = await locateUser();
			if (pos) {
				userLat = pos.lat;
				userLng = pos.lng;
				userLocated = true;
			}

			// If user has a community with coordinates, center on that
			const myCom = allCommunities.find((c) => myIds.has(c.id) && c.latitude != null);
			const centerLat = myCom?.latitude ?? userLat;
			const centerLng = myCom?.longitude ?? userLng;
			const zoom = myCom || userLocated ? 12 : 6;

			map = L.map(mapContainer).setView([centerLat, centerLng], zoom);

			const isDark = $theme === 'dark';
			const tileUrl = isDark
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
					.bindPopup(`<strong>${get(t)('communities.you_are_here')}</strong>`);
			}

			// Community markers
			for (const c of allCommunities) {
				if (c.latitude == null || c.longitude == null) continue;
				const isMine = myIds.has(c.id);
				const level = activityLevel(c);
				const size = level === 'high' ? 40 : level === 'medium' ? 34 : 28;
				const color = isMine ? '#22c55e' : c.mode === 'red' ? '#ef4444' : '#4f46e5';
				const ringClass = isMine ? 'ring-mine' : level === 'high' ? 'ring-active' : '';
				const icon = L.divIcon({
					className: 'community-marker',
					html: `<div class="community-dot ${ringClass}" style="background:${color};width:${size}px;height:${size}px"><span>${c.member_count}</span></div>`,
					iconSize: [size, size],
					iconAnchor: [size / 2, size / 2],
				});
				L.marker([c.latitude, c.longitude], { icon })
					.addTo(map)
					.bindPopup(`
						<strong>${c.name}</strong>${isMine ? ' (your community)' : ''}<br/>
						${c.city} (${c.postal_code})<br/>
						${c.member_count} member${c.member_count !== 1 ? 's' : ''}
						&middot; ${c.resource_count} item${c.resource_count !== 1 ? 's' : ''}
						&middot; ${c.skill_count} skill${c.skill_count !== 1 ? 's' : ''}<br/>
						<a href="/communities/${c.id}">${get(t)('communities.view_community')}</a>
					`);
			}
		} catch (e) {
			console.warn('Map initialization failed:', e);
		}
	});
</script>

<svelte:head>
	<title>Communities - NeighbourGood</title>
</svelte:head>

<div class="communities-page">
	<div class="page-header">
		<div>
			<h1>{$t('communities.title')}</h1>
			<p class="subtitle">{$t('communities.subtitle')}</p>
		</div>
		<a href="/onboarding" class="btn-find">{$t('communities.find_or_create')}</a>
	</div>

	{#if error}
		<div class="alert alert-error fade-in">{error}</div>
	{/if}

	<div class="map-wrapper">
		<div bind:this={mapContainer} class="map-container"></div>
		{#if loading}
			<div class="map-loading">
				<p>{$t('communities.loading_map')}</p>
			</div>
		{/if}
	</div>

	{#if !userLocated && !loading}
		<div class="location-hint fade-in">
			<p>{$t('communities.location_error')}</p>
		</div>
	{/if}

	{#if myCommunities.length > 0}
		<section class="my-community-section">
			<h2>{$t('communities.your_community')}</h2>
			{#each myCommunities as c (c.id)}
				<a href="/communities/{c.id}" class="my-community-card">
					<div class="my-card-left">
						<h3>{c.name}</h3>
						<div class="my-card-meta">
							<span class="tag">{c.postal_code}</span>
							<span class="tag">{c.city}</span>
							{#if c.mode === 'red'}
								<span class="tag tag-crisis">{$t('communities.crisis_badge')}</span>
							{/if}
						</div>
						{#if c.description}
							<p class="my-card-desc">{c.description}</p>
						{/if}
					</div>
					<div class="my-card-right">
						<span class="member-count">{c.member_count}</span>
						<span class="member-label">member{c.member_count !== 1 ? 's' : ''}</span>
					</div>
				</a>
			{/each}
		</section>
	{:else if !loading}
		<div class="empty-state fade-in">
			<h2>{$t('communities.no_communities_yet')}</h2>
			<p>{$t('communities.join_prompt')}</p>
			<a href="/onboarding" class="btn-primary">{$t('communities.find_or_create')}</a>
		</div>
	{/if}
</div>

<style>
	.communities-page {
		width: 100%;
	}

	.page-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 1.5rem;
	}

	.page-header h1 {
		font-size: 1.9rem;
		font-weight: 400;
		letter-spacing: -0.01em;
	}

	.subtitle {
		color: var(--color-text-muted);
		font-size: 0.9rem;
		margin-top: 0.25rem;
	}

	.btn-find {
		padding: 0.5rem 1rem;
		background: var(--color-primary);
		color: white;
		border-radius: var(--radius);
		font-size: 0.88rem;
		font-weight: 600;
		text-decoration: none;
		transition: all var(--transition-fast);
		white-space: nowrap;
	}

	.btn-find:hover {
		background: var(--color-primary-hover);
		text-decoration: none;
		box-shadow: var(--shadow);
		transform: translateY(-1px);
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
		height: 420px;
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

	:global(.ring-mine) {
		box-shadow: 0 0 0 5px rgba(34, 197, 94, 0.3), 0 2px 6px rgba(0, 0, 0, 0.3) !important;
		animation: pulse-mine 2s infinite;
	}

	@keyframes pulse-ring {
		0%, 100% { box-shadow: 0 0 0 4px rgba(79, 70, 229, 0.25), 0 2px 6px rgba(0, 0, 0, 0.3); }
		50% { box-shadow: 0 0 0 8px rgba(79, 70, 229, 0.1), 0 2px 6px rgba(0, 0, 0, 0.3); }
	}

	@keyframes pulse-mine {
		0%, 100% { box-shadow: 0 0 0 5px rgba(34, 197, 94, 0.3), 0 2px 6px rgba(0, 0, 0, 0.3); }
		50% { box-shadow: 0 0 0 10px rgba(34, 197, 94, 0.1), 0 2px 6px rgba(0, 0, 0, 0.3); }
	}

	/* ── My community card ──────────────────── */

	.my-community-section {
		margin-bottom: 1.5rem;
	}

	.my-community-section h2 {
		font-size: 1.2rem;
		font-weight: 600;
		margin-bottom: 0.75rem;
	}

	.my-community-card {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 1.25rem;
		background: linear-gradient(135deg, var(--color-surface) 0%, var(--color-primary-light) 100%);
		border: 1px solid var(--color-primary);
		border-left: 4px solid var(--color-success);
		border-radius: var(--radius-lg);
		text-decoration: none;
		color: var(--color-text);
		transition: all var(--transition-fast);
	}

	.my-community-card:hover {
		box-shadow: var(--shadow-md);
		transform: translateY(-2px);
		text-decoration: none;
	}

	.my-card-left h3 {
		font-size: 1.05rem;
		font-weight: 600;
		margin-bottom: 0.35rem;
	}

	.my-card-meta {
		display: flex;
		gap: 0.4rem;
		flex-wrap: wrap;
	}

	.tag {
		font-size: 0.72rem;
		font-weight: 500;
		padding: 0.12rem 0.45rem;
		border-radius: 999px;
		background: var(--color-primary-light);
		color: var(--color-primary);
	}

	.tag-crisis {
		background: var(--color-error);
		color: white;
	}

	.my-card-desc {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		line-height: 1.5;
		margin-top: 0.35rem;
	}

	.my-card-right {
		display: flex;
		flex-direction: column;
		align-items: center;
		flex-shrink: 0;
	}

	.member-count {
		font-size: 1.75rem;
		font-weight: 700;
		color: var(--color-primary);
		line-height: 1;
	}

	.member-label {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}

	/* ── Empty state ─────────────────────────── */

	.empty-state {
		text-align: center;
		padding: 3rem 1rem;
		background: var(--color-surface);
		border: 1px dashed var(--color-border);
		border-radius: var(--radius-lg);
	}

	.empty-state h2 {
		font-size: 1.25rem;
		margin-bottom: 0.5rem;
	}

	.empty-state p {
		color: var(--color-text-muted);
		margin-bottom: 1rem;
	}

	.btn-primary {
		display: inline-block;
		padding: 0.5rem 1.25rem;
		background: var(--color-primary);
		color: white;
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

	/* ── Alerts ───────────────────────────────── */

	.alert {
		padding: 0.65rem 1rem;
		border-radius: var(--radius);
		font-size: 0.9rem;
		margin-bottom: 1rem;
	}

	.alert-error {
		background: var(--color-error-bg);
		color: var(--color-error);
		border: 1px solid var(--color-error);
	}

	@media (max-width: 640px) {
		.page-header {
			flex-direction: column;
		}

		.map-container {
			height: 300px;
		}

		.my-community-card {
			flex-direction: column;
			align-items: flex-start;
		}

		.my-card-right {
			flex-direction: row;
			gap: 0.4rem;
		}

		.member-count {
			font-size: 1.25rem;
		}
	}
</style>
