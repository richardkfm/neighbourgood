<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { isLoggedIn, user } from '$lib/stores/auth';
	import { theme } from '$lib/stores/theme';
	import { t } from 'svelte-i18n';
	import type { KnownInstance, RedSkyAlertInfo } from '$lib/types';

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

	// Federation state
	const isAdmin = $derived($user?.role === 'admin');
	let instances = $state<KnownInstance[]>([]);
	let fedAlerts = $state<RedSkyAlertInfo[]>([]);
	let fedLoading = $state(false);
	let addUrl = $state('');
	let addError = $state('');
	let adding = $state(false);
	let refreshing = $state(false);
	let syncMessage = $state('');

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

	// Federation functions
	async function loadFederation() {
		fedLoading = true;
		try {
			const [instData, alertData] = await Promise.all([
				api<KnownInstance[]>('/federation/directory', { auth: true }),
				api<RedSkyAlertInfo[]>('/federation/alerts?active_only=true', { auth: true })
			]);
			instances = instData;
			fedAlerts = alertData;
		} catch {
			// empty state handles it
		} finally {
			fedLoading = false;
		}
	}

	async function addInstance() {
		if (!addUrl.trim()) return;
		adding = true;
		addError = '';
		try {
			await api<KnownInstance>('/federation/directory', {
				method: 'POST',
				body: { url: addUrl.trim() },
				auth: true
			});
			addUrl = '';
			await loadFederation();
		} catch (e: unknown) {
			addError = e instanceof Error ? e.message : $t('federation.add_error');
		} finally {
			adding = false;
		}
	}

	async function removeInstance(id: number) {
		try {
			await api(`/federation/directory/${id}`, { method: 'DELETE', auth: true });
			instances = instances.filter((i) => i.id !== id);
		} catch {
			// ignore
		}
	}

	async function refreshAll() {
		refreshing = true;
		try {
			instances = await api<KnownInstance[]>('/federation/directory/refresh', {
				method: 'POST',
				auth: true
			});
		} catch {
			// ignore
		} finally {
			refreshing = false;
		}
	}

	async function triggerSync() {
		syncMessage = '';
		try {
			const result = await api<{
				instances_attempted: number;
				instances_ok: number;
				total_resources_synced: number;
				total_skills_synced: number;
			}>('/federation/sync/pull', { method: 'POST', auth: true });
			syncMessage = `${$t('federation.synced')}: ${result.total_resources_synced} ${$t('federation.resources_label')}, ${result.total_skills_synced} ${$t('federation.skills_label')} (${result.instances_ok}/${result.instances_attempted} ${$t('federation.instances_ok')})`;
		} catch {
			syncMessage = $t('federation.sync_error');
		}
	}

	function modeClass(mode: string) {
		return mode === 'red' ? 'mode-red' : 'mode-blue';
	}

	function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
		const R = 6371;
		const dLat = ((lat2 - lat1) * Math.PI) / 180;
		const dLng = ((lng2 - lng1) * Math.PI) / 180;
		const a =
			Math.sin(dLat / 2) ** 2 +
			Math.cos((lat1 * Math.PI) / 180) *
				Math.cos((lat2 * Math.PI) / 180) *
				Math.sin(dLng / 2) ** 2;
		return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
	}

	const PAGE_SIZE = 10;
	let currentPage = $state(0);

	const sortedCommunities = $derived(
		[...allCommunities].sort((a, b) => {
			const aHasCoords = a.latitude != null && a.longitude != null;
			const bHasCoords = b.latitude != null && b.longitude != null;
			if (aHasCoords && bHasCoords) {
				return (
					haversineKm(userLat, userLng, a.latitude!, a.longitude!) -
					haversineKm(userLat, userLng, b.latitude!, b.longitude!)
				);
			}
			if (!aHasCoords && bHasCoords) return 1;
			if (aHasCoords && !bHasCoords) return -1;
			return a.name.localeCompare(b.name);
		})
	);

	const totalPages = $derived(Math.ceil(sortedCommunities.length / PAGE_SIZE));
	const pagedCommunities = $derived(
		sortedCommunities.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE)
	);

	$effect(() => {
		// Reset to first page whenever the community list changes
		void allCommunities;
		currentPage = 0;
	});

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

		// Load federation data for admins
		if (isAdmin) {
			loadFederation();
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

	{#if !loading && allCommunities.length > 0}
		<section class="all-communities-section">
			<h2>{$t('communities.all_communities')}</h2>
			<div class="community-list">
				{#each pagedCommunities as c (c.id)}
					<a href="/communities/{c.id}" class="community-list-card {myIds.has(c.id) ? 'is-mine' : ''}">
						<div class="list-card-info">
							<h3>{c.name}</h3>
							<div class="list-card-meta">
								<span class="tag">{c.postal_code}</span>
								<span class="tag">{c.city}</span>
								{#if c.mode === 'red'}
									<span class="tag tag-crisis">{$t('communities.crisis_badge')}</span>
								{/if}
								{#if myIds.has(c.id)}
									<span class="tag tag-mine">{$t('communities.your_community_badge')}</span>
								{/if}
							</div>
						</div>
						<div class="list-card-stats">
							<span>{c.member_count} member{c.member_count !== 1 ? 's' : ''}</span>
							{#if c.latitude != null && c.longitude != null && userLocated}
								<span class="distance">{haversineKm(userLat, userLng, c.latitude, c.longitude).toFixed(1)} km</span>
							{/if}
						</div>
					</a>
				{/each}
			</div>
			{#if totalPages > 1}
				<div class="pagination">
					<button class="btn-page" disabled={currentPage === 0} onclick={() => currentPage--}>← {$t('common.prev')}</button>
					<span class="page-info">{currentPage + 1} / {totalPages}</span>
					<button class="btn-page" disabled={currentPage >= totalPages - 1} onclick={() => currentPage++}>{$t('common.next')} →</button>
				</div>
			{/if}
		</section>
	{/if}

	{#if isAdmin}
		<section class="federation-section" id="federation">
			<div class="fed-header">
				<div>
					<h2>{$t('federation.title')}</h2>
					<p class="fed-subtitle">{$t('federation.subtitle')}</p>
				</div>
				<div class="fed-header-actions">
					<a href="/federation/resources" class="action-link">{$t('federation.browse_resources')}</a>
					<a href="/federation/skills" class="action-link">{$t('federation.browse_skills')}</a>
				</div>
			</div>

			{#if fedAlerts.length > 0}
				<div class="fed-alerts">
					{#each fedAlerts as alert}
						<div class="fed-alert-card severity-{alert.severity}">
							<span class="alert-severity">{alert.severity.toUpperCase()}</span>
							<div class="alert-content">
								<strong>{alert.title}</strong>
								{#if alert.description}
									<p>{alert.description}</p>
								{/if}
								<span class="alert-source">{$t('federation.from')} {alert.source_instance_name}</span>
							</div>
						</div>
					{/each}
				</div>
			{/if}

			<div class="fed-admin-controls">
				<form class="fed-add-form" onsubmit={(e) => { e.preventDefault(); addInstance(); }}>
					<input
						type="url"
						bind:value={addUrl}
						placeholder={$t('federation.add_placeholder')}
						class="fed-url-input"
						required
					/>
					<button type="submit" class="btn btn-primary" disabled={adding}>
						{adding ? $t('common.loading') : $t('federation.add_btn')}
					</button>
				</form>
				{#if addError}
					<p class="fed-error-text">{addError}</p>
				{/if}

				<div class="fed-actions">
					<button class="btn btn-secondary" onclick={refreshAll} disabled={refreshing}>
						{refreshing ? $t('common.loading') : $t('federation.refresh_all')}
					</button>
					<button class="btn btn-secondary" onclick={triggerSync}>
						{$t('federation.sync_now')}
					</button>
				</div>
				{#if syncMessage}
					<p class="fed-sync-message">{syncMessage}</p>
				{/if}
			</div>

			{#if fedLoading}
				<p class="fed-loading">{$t('common.loading')}</p>
			{:else if instances.length === 0}
				<div class="fed-empty">
					<p>{$t('federation.no_instances')}</p>
				</div>
			{:else}
				<div class="instance-grid">
					{#each instances as inst}
						<div class="instance-card">
							<div class="instance-header">
								<h3>{inst.name}</h3>
								<span class="mode-badge {modeClass(inst.platform_mode)}">
									{inst.platform_mode === 'red' ? $t('federation.mode_red') : $t('federation.mode_blue')}
								</span>
							</div>
							{#if inst.description}
								<p class="instance-desc">{inst.description}</p>
							{/if}
							{#if inst.region}
								<p class="instance-region">{inst.region}</p>
							{/if}
							<div class="instance-stats">
								<div class="stat">
									<span class="stat-value">{inst.active_user_count}</span>
									<span class="stat-label">{$t('federation.stat_active_users')}</span>
								</div>
								<div class="stat">
									<span class="stat-value">{inst.resource_count}</span>
									<span class="stat-label">{$t('federation.stat_resources')}</span>
								</div>
								<div class="stat">
									<span class="stat-value">{inst.skill_count}</span>
									<span class="stat-label">{$t('federation.stat_skills')}</span>
								</div>
								<div class="stat">
									<span class="stat-value">{inst.event_count}</span>
									<span class="stat-label">{$t('federation.stat_events')}</span>
								</div>
								<div class="stat">
									<span class="stat-value">{inst.community_count}</span>
									<span class="stat-label">{$t('federation.stat_communities')}</span>
								</div>
								<div class="stat">
									<span class="stat-value">{inst.user_count}</span>
									<span class="stat-label">{$t('federation.stat_total_users')}</span>
								</div>
							</div>
							<div class="instance-footer">
								<span class="reachable-badge" class:unreachable={!inst.is_reachable}>
									{inst.is_reachable ? $t('federation.reachable') : $t('federation.unreachable')}
								</span>
								{#if inst.admin_contact}
									<span class="admin-contact">{inst.admin_contact}</span>
								{/if}
								<button class="btn-remove" onclick={() => removeInstance(inst.id)} title={$t('common.delete')}>
									&times;
								</button>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</section>
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
		font-weight: 500;
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
		font-weight: 500;
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

	/* ── All communities list ────────────────── */

	.all-communities-section {
		margin-bottom: 2rem;
	}

	.all-communities-section h2 {
		font-size: 1.2rem;
		font-weight: 500;
		margin-bottom: 0.75rem;
	}

	.community-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.community-list-card {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 1rem 1.25rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		text-decoration: none;
		color: var(--color-text);
		transition: all var(--transition-fast);
	}

	.community-list-card:hover {
		box-shadow: var(--shadow);
		border-color: var(--color-primary);
		text-decoration: none;
	}

	.community-list-card.is-mine {
		border-left: 4px solid var(--color-success);
	}

	.list-card-info h3 {
		font-size: 1rem;
		font-weight: 500;
		margin-bottom: 0.3rem;
	}

	.list-card-meta {
		display: flex;
		gap: 0.4rem;
		flex-wrap: wrap;
	}

	.tag-mine {
		background: var(--color-primary-light);
		color: var(--color-primary);
		font-size: 0.72rem;
		font-weight: 600;
		padding: 0.12rem 0.45rem;
		border-radius: 999px;
	}

	.list-card-stats {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		flex-shrink: 0;
		gap: 0.2rem;
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.distance {
		font-size: 0.78rem;
		color: var(--color-text-muted);
	}

	.pagination {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.75rem;
		margin-top: 1rem;
	}

	.page-info {
		font-size: 0.88rem;
		color: var(--color-text-muted);
		min-width: 3.5rem;
		text-align: center;
	}

	.btn-page {
		padding: 0.4rem 0.85rem;
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		color: var(--color-text);
		border-radius: var(--radius-sm);
		font-size: 0.85rem;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.btn-page:hover:not(:disabled) {
		border-color: var(--color-primary);
		color: var(--color-primary);
	}

	.btn-page:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	/* ── Federation section ───────────────────── */

	.federation-section {
		margin-top: 2.5rem;
		padding-top: 2rem;
		border-top: 1px solid var(--color-border);
	}

	.fed-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
		margin-bottom: 1.5rem;
		flex-wrap: wrap;
	}

	.fed-header h2 {
		font-family: Georgia, 'Times New Roman', serif;
		font-weight: 400;
		font-size: 1.4rem;
		color: var(--color-text);
		margin: 0;
	}

	.fed-subtitle {
		color: var(--color-text-muted);
		font-size: 0.9rem;
		margin: 0.25rem 0 0;
	}

	.fed-header-actions {
		display: flex;
		gap: 0.5rem;
	}

	.action-link {
		padding: 0.4rem 0.9rem;
		border-radius: var(--radius-sm);
		background: var(--color-primary-light);
		color: var(--color-primary);
		text-decoration: none;
		font-size: 0.85rem;
		font-weight: 600;
		transition: all var(--transition-fast);
	}

	.action-link:hover {
		background: var(--color-primary);
		color: white;
		text-decoration: none;
	}

	/* Federation alerts */
	.fed-alerts {
		margin-bottom: 1rem;
	}

	.fed-alert-card {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		padding: 0.75rem 1rem;
		border-radius: var(--radius);
		margin-bottom: 0.5rem;
		border-left: 4px solid;
	}

	.fed-alert-card.severity-info {
		background: var(--color-primary-light);
		border-color: var(--color-primary);
	}

	.fed-alert-card.severity-warning {
		background: var(--color-warning-bg, rgba(245, 158, 11, 0.1));
		border-color: var(--color-warning, #f59e0b);
	}

	.fed-alert-card.severity-critical {
		background: var(--color-error-bg, rgba(239, 68, 68, 0.1));
		border-color: var(--color-error);
	}

	.alert-severity {
		font-size: 0.7rem;
		font-weight: 700;
		padding: 0.15rem 0.5rem;
		border-radius: 999px;
		background: var(--color-surface);
		white-space: nowrap;
	}

	.alert-content {
		flex: 1;
	}

	.alert-content p {
		margin: 0.25rem 0 0;
		font-size: 0.88rem;
		color: var(--color-text-muted);
	}

	.alert-source {
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	/* Admin controls */
	.fed-admin-controls {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		padding: 1rem;
		margin-bottom: 1.5rem;
	}

	.fed-add-form {
		display: flex;
		gap: 0.5rem;
	}

	.fed-url-input {
		flex: 1;
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		font-size: 0.9rem;
		background: var(--color-bg);
		color: var(--color-text);
	}

	.fed-url-input:focus {
		outline: none;
		border-color: var(--color-primary);
	}

	.fed-actions {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.75rem;
	}

	.fed-error-text {
		color: var(--color-error);
		font-size: 0.85rem;
		margin: 0.5rem 0 0;
	}

	.fed-sync-message {
		font-size: 0.85rem;
		color: var(--color-success, #10b981);
		margin: 0.5rem 0 0;
	}

	/* Buttons */
	.btn {
		padding: 0.5rem 1rem;
		border-radius: var(--radius-sm);
		font-size: 0.88rem;
		font-weight: 600;
		cursor: pointer;
		border: none;
		transition: all var(--transition-fast);
	}

	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	:global(.federation-section) .btn-primary {
		background: var(--color-primary);
		color: white;
		display: inline-block;
	}

	:global(.federation-section) .btn-primary:hover:not(:disabled) {
		background: var(--color-primary-hover);
	}

	.btn-secondary {
		background: var(--color-surface);
		color: var(--color-text);
		border: 1px solid var(--color-border);
	}

	.btn-secondary:hover:not(:disabled) {
		border-color: var(--color-primary);
		color: var(--color-primary);
	}

	/* Instance grid */
	.instance-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
		gap: 1rem;
	}

	.instance-card {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		padding: 1.25rem;
		transition: box-shadow var(--transition-fast);
	}

	.instance-card:hover {
		box-shadow: var(--shadow-md);
	}

	.instance-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.instance-header h3 {
		margin: 0;
		font-size: 1.05rem;
		font-weight: 600;
		color: var(--color-text);
	}

	.mode-badge {
		font-size: 0.72rem;
		font-weight: 700;
		padding: 0.15rem 0.5rem;
		border-radius: 999px;
		text-transform: uppercase;
	}

	.mode-blue {
		background: var(--color-primary-light);
		color: var(--color-primary);
	}

	.mode-red {
		background: var(--color-error-bg, rgba(239, 68, 68, 0.1));
		color: var(--color-error);
	}

	.instance-desc {
		font-size: 0.88rem;
		color: var(--color-text-muted);
		margin: 0 0 0.5rem;
	}

	.instance-region {
		font-size: 0.82rem;
		color: var(--color-text-muted);
		margin: 0 0 0.75rem;
	}

	.instance-stats {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.stat {
		text-align: center;
	}

	.stat-value {
		display: block;
		font-size: 1.1rem;
		font-weight: 700;
		color: var(--color-text);
	}

	.stat-label {
		font-size: 0.72rem;
		color: var(--color-text-muted);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.instance-footer {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding-top: 0.75rem;
		border-top: 1px solid var(--color-border);
		font-size: 0.82rem;
	}

	.reachable-badge {
		color: var(--color-success, #10b981);
		font-weight: 600;
	}

	.reachable-badge.unreachable {
		color: var(--color-text-muted);
	}

	.admin-contact {
		color: var(--color-text-muted);
		margin-left: auto;
	}

	.btn-remove {
		background: none;
		border: none;
		color: var(--color-text-muted);
		font-size: 1.2rem;
		cursor: pointer;
		padding: 0 0.25rem;
		line-height: 1;
	}

	.btn-remove:hover {
		color: var(--color-error);
	}

	/* Federation empty / loading */
	.fed-loading {
		text-align: center;
		color: var(--color-text-muted);
		padding: 2rem;
	}

	.fed-empty {
		text-align: center;
		padding: 2rem 1rem;
		color: var(--color-text-muted);
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

		.fed-header {
			flex-direction: column;
		}

		.instance-grid {
			grid-template-columns: 1fr;
		}

		.fed-add-form {
			flex-direction: column;
		}
	}
</style>
