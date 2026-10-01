<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { t } from 'svelte-i18n';
	import { api } from '$lib/api';
	import { isLoggedIn } from '$lib/stores/auth';
	import { bandwidth } from '$lib/stores/theme';
	import { isOnline } from '$lib/stores/offline';
	import Icon from '$lib/components/Icon.svelte';
	import { RESOURCE_CATEGORY_ICON, TRUST_BADGE_ICON } from '$lib/icons';

	import type { Resource } from '$lib/types';

	interface MyCommunity {
		id: number;
		name: string;
		postal_code: string;
	}

	const CATEGORIES = ['', 'tool', 'vehicle', 'electronics', 'furniture', 'food', 'clothing', 'skill', 'other'];

	let resources: Resource[] = $state([]);
	let total = $state(0);
	let loading = $state(true);
	let fromCache = $state(false);
	let filterCategory = $state('');
	let filterCommunity = $state(''); // Only used to filter a specific community, auto-filters to joined communities if empty
	let searchQuery = $state('');
	let searchTimeout: ReturnType<typeof setTimeout> | null = $state(null);
	let showCreateForm = $state(false);
	let myCommunitiesLoaded = $state(false);
	let requestId = 0;

	// Create form
	let newTitle = $state('');
	let newDescription = $state('');
	let newCategory = $state('tool');
	let newCondition = $state('good');
	let newCommunityId = $state('');
	let createError = $state('');
	let creating = $state(false);
	let myCommunities = $state<MyCommunity[]>([]);

	async function loadResources() {
		const thisRequest = ++requestId;
		loading = true;
		fromCache = false;
		try {
			const params = new URLSearchParams();
			if (filterCommunity) params.set('community_id', filterCommunity);
			if (filterCategory) params.set('category', filterCategory);
			if (searchQuery.trim()) params.set('q', searchQuery.trim());

			// Use raw fetch so we can inspect the X-Served-From header the
			// service worker sets when replaying a cached response.
			const rawRes = await fetch(`/api/resources?${params.toString()}`);
			if (thisRequest !== requestId) return; // superseded by a newer request
			if (rawRes.headers.get('X-Served-From') === 'offline-cache') {
				fromCache = true;
			}
			if (rawRes.ok) {
				const data: { items: Resource[]; total: number } = await rawRes.json();
				if (thisRequest !== requestId) return;
				resources = data.items;
				total = data.total;
			} else {
				resources = [];
				total = 0;
			}
		} catch {
			if (thisRequest !== requestId) return;
			resources = [];
			total = 0;
		} finally {
			if (thisRequest === requestId) loading = false;
		}
	}

	function handleSearchInput() {
		if (searchTimeout) clearTimeout(searchTimeout);
		searchTimeout = setTimeout(loadResources, 300);
	}

	async function handleCreate(e: Event) {
		e.preventDefault();
		createError = '';
		if (creating) return;
		if (!newCommunityId) {
			createError = get(t)('resources.please_select_community');
			return;
		}
		creating = true;
		try {
			await api('/resources', {
				method: 'POST',
				auth: true,
				body: {
					title: newTitle,
					description: newDescription || null,
					category: newCategory,
					condition: newCondition,
					community_id: Number(newCommunityId)
				}
			});
			showCreateForm = false;
			newTitle = '';
			newDescription = '';
			await loadResources();
		} catch (err) {
			createError = err instanceof Error ? err.message : $t('resources.create_failed');
		} finally {
			creating = false;
		}
	}

	async function loadMyCommunities() {
		try {
			myCommunities = await api<MyCommunity[]>(
				'/communities/my/memberships', { auth: true }
			);
			if (myCommunities.length > 0) {
				newCommunityId = String(myCommunities[0].id);
				filterCommunity = String(myCommunities[0].id);
			}
		} catch {
			myCommunities = [];
		} finally {
			myCommunitiesLoaded = true;
		}
	}

	onMount(async () => {
		if ($isLoggedIn) {
			await loadMyCommunities();
		} else {
			myCommunitiesLoaded = true;
		}
	});

	$effect(() => {
		filterCategory;
		filterCommunity;
		if (!myCommunitiesLoaded) return;
		loadResources();
	});
</script>

<div class="resources-page">
	{#if !$isOnline || fromCache}
		<div class="cache-notice">
			<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
				<circle cx="12" cy="12" r="10"/>
				<line x1="12" y1="8" x2="12" y2="12"/>
				<line x1="12" y1="16" x2="12.01" y2="16"/>
			</svg>
			{$t('resources.showing_cached')}
		</div>
	{/if}

	<div class="page-header">
		<div>
			<h1>{$t('resources.title')}</h1>
			<p class="subtitle">{$t('resources.subtitle')}</p>
		</div>
		{#if $isLoggedIn}
			<button class="btn btn-primary" onclick={() => (showCreateForm = !showCreateForm)} aria-expanded={showCreateForm}>
				{showCreateForm ? $t('common.cancel') : $t('resources.add')}
			</button>
		{/if}
	</div>

	<nav class="browse-tabs">
		<a href="/resources" class="browse-tab active">{$t('resources.tab_label')}</a>
		<a href="/skills" class="browse-tab">{$t('skills.tab_label')}</a>
	</nav>

	{#if showCreateForm}
		<div class="card create-form-card">
			<h2>{$t('resources.form_title')}</h2>
			{#if createError}
				<p class="alert alert-error" role="alert">{createError}</p>
			{/if}
			<form class="form-stack" onsubmit={handleCreate}>
				<label class="field">
					<span>{$t('resources.title_label')}</span>
					<input type="text" bind:value={newTitle} required placeholder={$t('resources.title_placeholder')} />
				</label>
				<label class="field">
					<span>{$t('resources.description_label')}</span>
					<textarea bind:value={newDescription} rows="3" placeholder={$t('resources.description_placeholder')}></textarea>
				</label>
				<div class="field-row">
					<label class="field">
						<span>{$t('resources.category')}</span>
						<select bind:value={newCategory}>
							<option value="tool">{$t('resources.categories.tool')}</option>
							<option value="vehicle">{$t('resources.categories.vehicle')}</option>
							<option value="electronics">{$t('resources.categories.electronics')}</option>
							<option value="furniture">{$t('resources.categories.furniture')}</option>
							<option value="food">{$t('resources.categories.food')}</option>
							<option value="clothing">{$t('resources.categories.clothing')}</option>
							<option value="skill">{$t('resources.categories.skill')}</option>
							<option value="other">{$t('resources.categories.other')}</option>
						</select>
					</label>
					<label class="field">
						<span>{$t('resources.condition')}</span>
						<select bind:value={newCondition}>
							<option value="new">{$t('resources.conditions.new')}</option>
							<option value="good">{$t('resources.conditions.good')}</option>
							<option value="fair">{$t('resources.conditions.fair')}</option>
							<option value="worn">{$t('resources.conditions.worn')}</option>
						</select>
					</label>
				</div>
				{#if myCommunities.length > 1}
					<label class="field">
						<span>{$t('resources.community_label')}</span>
						<select bind:value={newCommunityId} required>
							{#each myCommunities as c}
								<option value={c.id}>{c.name} ({c.postal_code})</option>
							{/each}
						</select>
					</label>
				{:else if myCommunities.length === 0}
					<p class="field-hint">{$t('resources.need_community')}</p>
				{/if}
				<button type="submit" class="btn btn-primary" class:is-loading={creating} disabled={myCommunities.length === 0}>{$t('resources.share_btn')}</button>
			</form>
		</div>
	{/if}

	<div class="filter-bar">
		<input
			type="search"
			class="input input-grow"
			placeholder={$t('resources.search_placeholder')}
			aria-label={$t('resources.search_placeholder')}
			bind:value={searchQuery}
			oninput={handleSearchInput}
		/>
		<select class="input" bind:value={filterCategory}>
			{#each CATEGORIES as cat}
				<option value={cat}>
					{cat === '' ? $t('resources.all_categories') : $t('resources.categories.' + cat)}
				</option>
			{/each}
		</select>
		{#if myCommunities.length > 1}
			<select class="input" bind:value={filterCommunity}>
				{#each myCommunities as c}
					<option value={c.id}>{c.name}</option>
				{/each}
			</select>
		{/if}
		<span class="result-count" aria-live="polite">{$t(total === 1 ? 'common.result' : 'common.results', { values: { count: total } })}</span>
	</div>

	{#if loading}
		<div class="resource-grid" role="status" aria-live="polite" aria-busy="true">
			<span class="sr-only">{$t('common.loading')}</span>
			{#each [1, 2, 3, 4, 5, 6] as n (n)}
				<div class="card card-flush resource-card" aria-hidden="true">
					<div class="card-image skeleton"></div>
					<div class="card-body">
						<span class="skeleton" style="height: 0.9rem; width: 30%"></span>
						<span class="skeleton" style="height: 1.1rem; width: 70%; margin-top: 0.6rem"></span>
						<span class="skeleton" style="height: 0.8rem; width: 90%; margin-top: 0.6rem"></span>
					</div>
				</div>
			{/each}
		</div>
	{:else if resources.length === 0}
		<div class="empty-state">
				<span class="empty-icon"><Icon name="package" size={26} /></span>
				<p>{$t('resources.no_results')}</p>
				{#if searchQuery || filterCategory}
					<p>{$t('resources.adjust_filters')}</p>
				{:else if $isLoggedIn}
					<p>{$t('resources.first_share')}</p>
					<button class="btn btn-primary" onclick={() => { showCreateForm = true; window.scrollTo({ top: 0, behavior: 'smooth' }); }}>
						<Icon name="plus" size={16} />{$t('resources.add')}
					</button>
				{:else}
					<p>{$t('resources.sign_up_share')}</p>
					<a href="/register" class="btn btn-primary">{$t('nav.signup')}</a>
				{/if}
			</div>
	{:else}
		<div class="resource-grid">
			{#each resources as resource}
				<a href="/resources/{resource.id}" class="card card-flush card-interactive resource-card">
					{#if resource.image_url && $bandwidth !== 'low'}
						<div class="card-image">
							<img src="/api{resource.image_url}" alt={resource.title} />
						</div>
					{:else}
						<div class="card-image card-image-placeholder">
							<span class="placeholder-icon"><Icon name={RESOURCE_CATEGORY_ICON[resource.category] ?? 'package'} size={40} strokeWidth={1.5} /></span>
						</div>
					{/if}
					<div class="card-body">
						<div class="card-header">
							<span class="badge badge-primary badge-caps">{$t('resources.categories.' + resource.category)}</span>
							{#if !resource.is_available}
								<span class="badge badge-error">{$t('resources.unavailable')}</span>
							{/if}
						</div>
						<h3>{resource.title}</h3>
						{#if resource.description}
							<p class="description">{resource.description}</p>
						{/if}
						<div class="card-spacer"></div>
						<div class="card-footer">
							<span class="owner">{$t('common.by_name', { values: { name: resource.owner.display_name } })}</span>
							{#if resource.owner_trust && resource.owner_trust.total_reviews > 0}
								<span class="trust-stars"><Icon name="star" size={13} />{resource.owner_trust.average_rating.toFixed(1)}</span>
							{/if}
							{#if resource.owner_trust}
								{#each resource.owner_trust.badges as badge}
									<span class="trust-pill"><Icon name={TRUST_BADGE_ICON[badge] ?? 'handshake'} size={14} /></span>
								{/each}
							{/if}
							{#if resource.condition}
								<span class="condition">{$t('resources.conditions.' + resource.condition)}</span>
							{/if}
						</div>
					</div>
				</a>
			{/each}
		</div>
	{/if}
</div>

<style>
	.resources-page {
		max-width: 960px;
	}

	.page-header {
		margin-bottom: 1.25rem;
	}

	.filter-bar {
		margin-bottom: 2rem;
	}

	.result-count {
		margin-inline-start: auto;
		font-size: 0.85rem;
		color: var(--color-text-muted);
		white-space: nowrap;
	}

	.resource-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
		gap: 1.5rem;
	}

	.resource-card {
		display: flex;
		flex-direction: column;
	}

	.resource-card:hover {
		border-color: var(--color-primary);
		transform: translateY(-3px);
	}

	.card-image {
		width: 100%;
		height: 160px;
		overflow: hidden;
		background: var(--color-bg);
	}

	.card-image img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	.card-image-placeholder {
		display: flex;
		align-items: center;
		justify-content: center;
		background: linear-gradient(135deg, var(--color-primary-light), var(--color-bg));
	}

	.placeholder-icon {
		display: inline-flex;
		color: var(--color-primary-text);
		opacity: 0.55;
	}

	.card-body {
		display: flex;
		flex-direction: column;
		flex: 1;
		padding: 1.1rem 1.25rem 1.25rem;
	}

	.card-spacer {
		flex: 1;
	}

	.card-header {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 0.6rem;
	}

	.resource-card h3 {
		font-size: 1.05rem;
		margin-bottom: 0.35rem;
		line-height: 1.35;
	}

	.description {
		font-size: 0.84rem;
		color: var(--color-text-muted);
		line-height: 1.55;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	.card-footer {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		flex-wrap: wrap;
		font-size: 0.78rem;
		color: var(--color-text-muted);
		border-top: 1px solid var(--color-border);
		padding-top: 0.7rem;
		margin-top: 0.85rem;
	}

	.trust-stars {
		display: inline-flex;
		align-items: center;
		gap: 0.2rem;
		color: var(--color-warning);
		font-weight: 600;
	}

	.trust-pill {
		display: inline-flex;
		color: var(--color-primary-text);
	}

	.condition {
		margin-inline-start: auto;
	}

	/* Phones: a dense list (thumbnail left, details right) instead of one huge
	   image per screen-height, so ~4 items fit instead of ~1.5. */
	@media (max-width: 560px) {
		.filter-bar {
			margin-bottom: 1.25rem;
		}

		.filter-bar .input-grow {
			flex-basis: 100%;
		}

		.filter-bar select {
			flex: 1;
			min-width: 0;
		}

		.resource-grid {
			grid-template-columns: 1fr;
			gap: 0.75rem;
		}

		.resource-card {
			flex-direction: row;
		}

		.resource-card:hover {
			transform: none;
		}

		.card-image {
			width: 96px;
			height: auto;
			min-height: 120px;
			flex-shrink: 0;
		}

		.card-body {
			min-width: 0;
			padding: 0.85rem 1rem;
		}

		.card-footer {
			margin-top: 0.5rem;
			padding-top: 0.5rem;
		}
	}

	.cache-notice {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.55rem 0.9rem;
		background: var(--color-warning-bg, rgba(245, 158, 11, 0.08));
		border: 1px solid var(--color-warning, #f59e0b);
		border-radius: var(--radius);
		font-size: 0.82rem;
		color: var(--color-warning, #92400e);
		margin-bottom: 1rem;
	}
</style>
