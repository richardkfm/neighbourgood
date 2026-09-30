<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { isLoggedIn, user } from '$lib/stores/auth';
	import { t } from 'svelte-i18n';
	import CommunityMap from '$lib/components/CommunityMap.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import type { KnownInstance, MapCommunity, RedSkyAlertInfo } from '$lib/types';

	interface MyCommunity {
		id: number;
		name: string;
		description: string | null;
		postal_code: string;
		city: string;
		member_count: number;
		is_active: boolean;
		mode: string;
		effective_mode?: string;
	}

	let allCommunities = $state<MapCommunity[]>([]);
	let myCommunities = $state<MyCommunity[]>([]);
	let loading = $state(true);
	let error = $state('');
	let userLat = $state(51.1657);
	let userLng = $state(10.4515);
	let userLocated = $state(false);

	function handleLocate(lat: number, lng: number) {
		userLat = lat;
		userLng = lng;
		userLocated = true;
	}

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
				api<MapCommunity[]>('/communities/map').catch(() => [] as MapCommunity[]),
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
		<a href="/onboarding" class="btn btn-primary">{$t('communities.find_or_create')}</a>
	</div>

	{#if error}
		<div class="alert alert-error fade-in">{error}</div>
	{/if}

	<CommunityMap communities={allCommunities} {myIds} {loading} onlocate={handleLocate} />

	{#if myCommunities.length > 0}
		<section class="my-community-section">
			<h2>{$t('communities.your_community')}</h2>
			{#each myCommunities as c (c.id)}
				<a href="/communities/{c.id}" class="card card-interactive my-community-card">
					<div class="my-card-left">
						<h3>{c.name}</h3>
						<div class="my-card-meta">
							<span class="tag">{c.postal_code}</span>
							<span class="tag">{c.city}</span>
							{#if (c.effective_mode ?? c.mode) === 'red'}
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
	{:else if !loading && allCommunities.length === 0}
		<div class="empty-state fade-in">
			<span class="empty-icon"><Icon name="users" size={26} /></span>
			<h2>{$t('communities.no_communities_yet')}</h2>
			<p>{$t('communities.join_prompt')}</p>
			<a href="/onboarding" class="btn btn-primary">{$t('communities.find_or_create')}</a>
		</div>
	{:else if !loading}
		<div class="not-member-notice fade-in">
			<p>{$t('communities.not_member_yet')}</p>
		</div>
	{/if}

	{#if !loading && allCommunities.length > 0}
		<section class="all-communities-section">
			<h2>{$t('communities.all_communities')}</h2>
			<div class="community-list">
				{#each pagedCommunities as c (c.id)}
					<a href="/communities/{c.id}" class="card card-interactive community-list-card {myIds.has(c.id) ? 'is-mine' : ''}">
						<div class="list-card-info">
							<h3>{c.name}</h3>
							<div class="list-card-meta">
								<span class="tag">{c.postal_code}</span>
								<span class="tag">{c.city}</span>
								{#if (c.effective_mode ?? c.mode) === 'red'}
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
					<button class="btn btn-secondary btn-sm" disabled={currentPage === 0} onclick={() => currentPage--}><Icon name="arrow-left" size={14} class="flip-rtl" /> {$t('common.prev')}</button>
					<span class="page-info">{currentPage + 1} / {totalPages}</span>
					<button class="btn btn-secondary btn-sm" disabled={currentPage >= totalPages - 1} onclick={() => currentPage++}>{$t('common.next')} <Icon name="arrow-right" size={14} class="flip-rtl" /></button>
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
					<a href="/federation/resources" class="btn btn-secondary btn-sm">{$t('federation.browse_resources')}</a>
					<a href="/federation/skills" class="btn btn-secondary btn-sm">{$t('federation.browse_skills')}</a>
				</div>
			</div>

			{#if fedAlerts.length > 0}
				<div class="fed-alerts">
					{#each fedAlerts as alert}
						<div class="fed-alert-card severity-{alert.severity}">
							<span class="badge alert-severity">{alert.severity.toUpperCase()}</span>
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

			<div class="card fed-admin-controls">
				<form class="fed-add-form" onsubmit={(e) => { e.preventDefault(); addInstance(); }}>
					<input
						type="url"
						bind:value={addUrl}
						placeholder={$t('federation.add_placeholder')}
						class="input fed-url-input"
						required
					/>
					<button type="submit" class="btn btn-primary" class:is-loading={adding} disabled={adding}>
						{adding ? $t('common.loading') : $t('federation.add_btn')}
					</button>
				</form>
				{#if addError}
					<p class="alert alert-error" role="alert">{addError}</p>
				{/if}

				<div class="fed-actions">
					<button class="btn btn-secondary" class:is-loading={refreshing} onclick={refreshAll} disabled={refreshing}>
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
				<div class="instance-grid" role="status" aria-busy="true">
				<span class="sr-only">{$t('common.loading')}</span>
				{#each [1, 2, 3] as n (n)}
					<div class="skeleton skeleton-card" style="height: 11rem" aria-hidden="true"></div>
				{/each}
			</div>
			{:else if instances.length === 0}
				<div class="empty-state fed-empty">
					<span class="empty-icon"><Icon name="globe" size={26} /></span>
					<p>{$t('federation.no_instances')}</p>
				</div>
			{:else}
				<div class="instance-grid">
					{#each instances as inst}
						<div class="card instance-card">
							<div class="instance-header">
								<h3>{inst.name}</h3>
								<span class="badge badge-caps {inst.platform_mode === 'red' ? 'badge-error' : 'badge-primary'}">
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
								<span class="badge" class:badge-success={inst.is_reachable}>
									{inst.is_reachable ? $t('federation.reachable') : $t('federation.unreachable')}
								</span>
								{#if inst.admin_contact}
									<span class="admin-contact">{inst.admin_contact}</span>
								{/if}
								<button class="btn btn-ghost btn-sm btn-remove" onclick={() => removeInstance(inst.id)} title={$t('common.delete')} aria-label={$t('common.delete')}>
									<Icon name="x" size={16} />
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
		background: linear-gradient(135deg, var(--color-surface) 0%, var(--color-primary-light) 100%);
		border-color: var(--color-primary);
		border-inline-start: 4px solid var(--color-success);
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

	.tag-crisis {
		background: var(--color-error);
		color: var(--color-on-error);
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
		color: var(--color-primary-text);
		line-height: 1;
	}

	.member-label {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}

	/* ── Not-member notice ───────────────────── */

	.not-member-notice {
		padding: 0.65rem 1rem;
		border-radius: var(--radius);
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		color: var(--color-text-muted);
		font-size: 0.9rem;
		margin-bottom: 1rem;
	}

	/* ── Empty state ─────────────────────────── */

	.empty-state {
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
	}

	.community-list-card:hover {
		border-color: var(--color-primary);
	}

	.community-list-card.is-mine {
		border-inline-start: 4px solid var(--color-success);
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
		font-family: var(--font-heading);
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
		border-inline-start: 4px solid;
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
		padding: 1rem;
		margin-bottom: 1.5rem;
	}

	.fed-add-form {
		display: flex;
		gap: 0.5rem;
	}

	.fed-url-input {
		flex: 1;
	}

	.fed-actions {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.75rem;
	}

	/* Instance grid */
	.instance-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
		gap: 1rem;
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

	.admin-contact {
		color: var(--color-text-muted);
		margin-inline-start: auto;
	}

	.btn-remove {
		color: var(--color-text-muted);
	}

	.btn-remove:hover:not(:disabled) {
		color: var(--color-error);
	}

	/* Federation empty / loading */
	.fed-empty {
		text-align: center;
		padding: 2rem 1rem;
		color: var(--color-text-muted);
	}

	@media (max-width: 640px) {
		.page-header {
			flex-direction: column;
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
