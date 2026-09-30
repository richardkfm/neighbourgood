<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { t } from 'svelte-i18n';
	import { api } from '$lib/api';
	import { isLoggedIn } from '$lib/stores/auth';
	import { bandwidth } from '$lib/stores/theme';
	import { isOnline } from '$lib/stores/offline';

	import type { Resource } from '$lib/types';

	interface MyCommunity {
		id: number;
		name: string;
		postal_code: string;
	}

	const CATEGORIES = ['', 'tool', 'vehicle', 'electronics', 'furniture', 'food', 'clothing', 'skill', 'other'];

	const CATEGORY_ICONS: Record<string, string> = {
		tool: '🔧', vehicle: '🚗', electronics: '⚡', furniture: '🪑',
		food: '🍎', clothing: '👕', skill: '💡', other: '📦'
	};

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
		if (!newCommunityId) {
			createError = get(t)('resources.please_select_community');
			return;
		}
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
			createError = err instanceof Error ? err.message : 'Failed to create resource';
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
			<button class="btn-primary" onclick={() => (showCreateForm = !showCreateForm)}>
				{showCreateForm ? $t('common.cancel') : $t('resources.add')}
			</button>
		{/if}
	</div>

	<nav class="browse-tabs">
		<a href="/resources" class="browse-tab active">{$t('resources.tab_label')}</a>
		<a href="/skills" class="browse-tab">{$t('skills.tab_label')}</a>
	</nav>

	{#if showCreateForm}
		<div class="create-form-card">
			<h2>{$t('resources.form_title')}</h2>
			{#if createError}
				<p class="error">{createError}</p>
			{/if}
			<form onsubmit={handleCreate}>
				<label>
					<span>{$t('resources.title_label')}</span>
					<input type="text" bind:value={newTitle} required placeholder="e.g. Bosch Drill" />
				</label>
				<label>
					<span>{$t('resources.description_label')}</span>
					<textarea bind:value={newDescription} rows="3" placeholder="What are you sharing? Any conditions?"></textarea>
				</label>
				<div class="form-row">
					<label>
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
					<label>
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
					<label>
						<span>{$t('resources.community_label')}</span>
						<select bind:value={newCommunityId} required>
							{#each myCommunities as c}
								<option value={c.id}>{c.name} ({c.postal_code})</option>
							{/each}
						</select>
					</label>
				{:else if myCommunities.length === 0}
					<p class="hint">{$t('resources.need_community')}</p>
				{/if}
				<button type="submit" class="btn-primary" disabled={myCommunities.length === 0}>{$t('resources.share_btn')}</button>
			</form>
		</div>
	{/if}

	<div class="filter-bar">
		<input
			type="search"
			class="search-input"
			placeholder={$t('resources.search_placeholder')}
			aria-label={$t('resources.search_placeholder')}
			bind:value={searchQuery}
			oninput={handleSearchInput}
		/>
		<select bind:value={filterCategory}>
			{#each CATEGORIES as cat}
				<option value={cat}>
					{cat === '' ? $t('resources.all_categories') : $t('resources.categories.' + cat)}
				</option>
			{/each}
		</select>
		{#if myCommunities.length > 1}
			<select bind:value={filterCommunity}>
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
				<div class="resource-card" aria-hidden="true">
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
			<p>{$t('resources.no_results')}</p>
			{#if searchQuery || filterCategory}
				<p>{$t('resources.adjust_filters')}</p>
			{:else if $isLoggedIn}
				<p>{$t('resources.first_share')}</p>
			{:else}
				<p>{$t('resources.sign_up_share')}</p>
			{/if}
		</div>
	{:else}
		<div class="resource-grid">
			{#each resources as resource}
				<a href="/resources/{resource.id}" class="resource-card">
					{#if resource.image_url && $bandwidth !== 'low'}
						<div class="card-image">
							<img src="/api{resource.image_url}" alt={resource.title} />
						</div>
					{:else}
						<div class="card-image card-image-placeholder">
							<span class="placeholder-icon">{CATEGORY_ICONS[resource.category] ?? '📦'}</span>
						</div>
					{/if}
					<div class="card-body">
						<div class="card-header">
							<span class="category-badge">{resource.category}</span>
							{#if !resource.is_available}
								<span class="unavailable-badge">{$t('resources.unavailable')}</span>
							{/if}
						</div>
						<h3>{resource.title}</h3>
						{#if resource.description}
							<p class="description">{resource.description}</p>
						{/if}
						<div class="card-spacer"></div>
						<div class="card-footer">
							<span class="owner">by {resource.owner.display_name}</span>
							{#if resource.owner_trust && resource.owner_trust.total_reviews > 0}
								<span class="trust-stars">★ {resource.owner_trust.average_rating.toFixed(1)}</span>
							{/if}
							{#if resource.owner_trust}
								{#each resource.owner_trust.badges as badge}
									<span class="trust-pill">{badge === 'skilled_helper' ? '⭐' : badge === 'trusted_lender' ? '📦' : '🤝'}</span>
								{/each}
							{/if}
							{#if resource.condition}
								<span class="condition">{resource.condition}</span>
							{/if}
						</div>
					</div>
				</a>
			{/each}
		</div>
	{/if}
</div>

<style>
	.browse-tabs {
		display: flex;
		gap: 0.25rem;
		border-bottom: 1px solid var(--color-border);
		margin-bottom: 2rem;
	}

	.browse-tab {
		padding: 0.65rem 1.25rem;
		font-size: 0.95rem;
		font-weight: 500;
		color: var(--color-text-muted);
		text-decoration: none;
		border-bottom: 2px solid transparent;
		margin-bottom: -1px;
		transition: all var(--transition-fast);
	}

	.browse-tab:hover {
		color: var(--color-text);
		text-decoration: none;
	}

	.browse-tab.active {
		color: var(--color-primary-text);
		border-bottom-color: var(--color-primary);
		font-weight: 600;
	}

	.resources-page {
		max-width: 960px;
	}

	.page-header {
		margin-bottom: 1.25rem;
	}

	.btn-primary {
		background: var(--color-primary);
		color: var(--color-on-primary);
		border: none;
		border-radius: var(--radius);
		padding: 0.55rem 1.2rem;
		font-size: 0.9rem;
		font-weight: 600;
		cursor: pointer;
		box-shadow: var(--shadow-sm);
		transition: all var(--transition-fast);
	}

	.btn-primary:hover {
		background: var(--color-primary-hover);
		box-shadow: var(--shadow-md);
	}

	.create-form-card {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		padding: 1.5rem;
		margin-bottom: 1.5rem;
	}

	.create-form-card h2 {
		font-size: 1.1rem;
		margin-bottom: 1rem;
	}

	.create-form-card form {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.form-row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.75rem;
	}

	label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	label span {
		font-size: 0.85rem;
		font-weight: 500;
	}

	input, textarea, select {
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.9rem;
		background: var(--color-surface);
		color: var(--color-text);
	}

	.error {
		color: var(--color-error);
		font-size: 0.9rem;
		margin-bottom: 0.5rem;
	}

	.hint {
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.filter-bar {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 2rem;
		flex-wrap: wrap;
	}

	.search-input {
		flex: 1;
		min-width: 0;
	}

	.filter-bar input,
	.filter-bar select {
		padding: 0.6rem 0.9rem;
	}

	.filter-bar select {
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.88rem;
		background: var(--color-surface);
		color: var(--color-text);
	}

	.result-count {
		margin-left: auto;
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
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		text-decoration: none;
		color: var(--color-text);
		transition: border-color var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast);
		overflow: hidden;
	}

	.resource-card:hover {
		border-color: var(--color-primary);
		box-shadow: var(--shadow-md);
		transform: translateY(-3px);
		text-decoration: none;
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
		font-size: 2.5rem;
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

	.category-badge {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		background: var(--color-primary-light);
		padding: 0.15rem 0.55rem;
		border-radius: 999px;
		color: var(--color-primary-text);
		font-weight: 600;
	}

	.unavailable-badge {
		font-size: 0.7rem;
		background: var(--color-error-bg);
		color: var(--color-error);
		padding: 0.15rem 0.55rem;
		border-radius: 999px;
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
		color: var(--color-warning);
		font-weight: 600;
	}

	.trust-pill {
		font-size: 0.72rem;
	}

	.condition {
		margin-left: auto;
	}

	.empty-state {
		text-align: center;
		padding: 3rem 1rem;
		color: var(--color-text-muted);
	}

	.empty-state p + p {
		margin-top: 0.5rem;
	}

	/* Phones: a dense list (thumbnail left, details right) instead of one huge
	   image per screen-height, so ~4 items fit instead of ~1.5. */
	@media (max-width: 560px) {
		.filter-bar {
			margin-bottom: 1.25rem;
		}

		.search-input {
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
