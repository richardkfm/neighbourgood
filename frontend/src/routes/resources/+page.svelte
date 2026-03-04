<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { t } from 'svelte-i18n';
	import { api } from '$lib/api';
	import { isLoggedIn } from '$lib/stores/auth';
	import { bandwidth } from '$lib/stores/theme';
	import { isOnline } from '$lib/stores/offline';

	interface Resource {
		id: number;
		title: string;
		description: string | null;
		category: string;
		condition: string | null;
		image_url: string | null;
		is_available: boolean;
		community_id: number | null;
		owner: { display_name: string; neighbourhood: string | null };
		created_at: string;
	}

	interface MyCommunity {
		id: number;
		name: string;
		postal_code: string;
	}

	const CATEGORIES = [
		{ value: '', label: 'All Categories' },
		{ value: 'tool', label: 'Tools' },
		{ value: 'vehicle', label: 'Vehicles' },
		{ value: 'electronics', label: 'Electronics' },
		{ value: 'furniture', label: 'Furniture' },
		{ value: 'food', label: 'Food' },
		{ value: 'clothing', label: 'Clothing' },
		{ value: 'skill', label: 'Skills' },
		{ value: 'other', label: 'Other' }
	];

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

	// Create form
	let newTitle = $state('');
	let newDescription = $state('');
	let newCategory = $state('tool');
	let newCondition = $state('good');
	let newCommunityId = $state('');
	let createError = $state('');
	let myCommunities = $state<MyCommunity[]>([]);

	async function loadResources() {
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
			if (rawRes.headers.get('X-Served-From') === 'offline-cache') {
				fromCache = true;
			}
			if (rawRes.ok) {
				const data: { items: Resource[]; total: number } = await rawRes.json();
				resources = data.items;
				total = data.total;
			} else {
				resources = [];
				total = 0;
			}
		} catch {
			resources = [];
			total = 0;
		} finally {
			loading = false;
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
			}
		} catch {
			myCommunities = [];
		}
	}

	onMount(async () => {
		if ($isLoggedIn) {
			await loadMyCommunities();
		}
		loadResources();
	});

	$effect(() => {
		filterCategory;
		filterCommunity;
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
		<h1>{$t('resources.title')}</h1>
		{#if $isLoggedIn}
			<button class="btn-primary" onclick={() => (showCreateForm = !showCreateForm)}>
				{showCreateForm ? $t('common.cancel') : $t('resources.add')}
			</button>
		{/if}
	</div>

	<nav class="browse-tabs">
		<a href="/resources" class="browse-tab active">Resources</a>
		<a href="/skills" class="browse-tab">Skills</a>
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
				{#if myCommunities.length > 0}
					<label>
						<span>{$t('resources.community_label')}</span>
						<select bind:value={newCommunityId} required>
							{#each myCommunities as c}
								<option value={c.id}>{c.name} ({c.postal_code})</option>
							{/each}
						</select>
					</label>
				{:else}
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
			bind:value={searchQuery}
			oninput={handleSearchInput}
		/>
		<select bind:value={filterCategory}>
			{#each CATEGORIES as cat}
				<option value={cat.value}>
					{cat.value === '' ? $t('resources.all_categories') : $t('resources.categories.' + cat.value)}
				</option>
			{/each}
		</select>
		{#if myCommunities.length > 0}
			<select bind:value={filterCommunity}>
				<option value="">{$t('resources.all_communities')}</option>
				{#each myCommunities as c}
					<option value={c.id}>{c.name}</option>
				{/each}
			</select>
		{/if}
		<span class="result-count">{total} result{total !== 1 ? 's' : ''}</span>
	</div>

	{#if loading}
		<p class="loading">{$t('common.loading')}</p>
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
						<div class="card-footer">
							<span class="owner">by {resource.owner.display_name}</span>
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
		border-bottom: 2px solid var(--color-border);
		margin-top: 0.5rem;
		margin-bottom: 1.5rem;
	}

	.browse-tab {
		padding: 0.6rem 1.25rem;
		font-size: 0.95rem;
		font-weight: 500;
		color: var(--color-text-muted);
		text-decoration: none;
		border-bottom: 3px solid transparent;
		margin-bottom: -2px;
		transition: all var(--transition-fast);
	}

	.browse-tab:hover {
		color: var(--color-text);
		text-decoration: none;
	}

	.browse-tab.active {
		color: var(--color-primary);
		border-bottom-color: var(--color-primary);
		font-weight: 600;
	}

	.resources-page {
		max-width: 900px;
	}

	.page-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.75rem;
		gap: 1rem;
		flex-wrap: wrap;
	}

	h1 {
		font-size: 1.9rem;
		font-weight: 400;
	}

	.btn-primary {
		background: var(--color-primary);
		color: white;
		border: none;
		border-radius: var(--radius);
		padding: 0.5rem 1rem;
		font-size: 0.9rem;
		cursor: pointer;
	}

	.btn-primary:hover {
		background: var(--color-primary-hover);
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
		margin-bottom: 1.5rem;
		flex-wrap: wrap;
	}

	.search-input {
		flex: 1;
		min-width: 0;
	}

	.filter-bar select {
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.85rem;
		background: var(--color-surface);
		color: var(--color-text);
	}

	.result-count {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		white-space: nowrap;
	}

	.resource-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
		gap: 1rem;
	}

	.resource-card {
		display: flex;
		flex-direction: column;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		text-decoration: none;
		color: var(--color-text);
		transition: border-color 0.15s;
		overflow: hidden;
	}

	.resource-card:hover {
		border-color: var(--color-primary);
		box-shadow: var(--shadow-md);
		transform: translateY(-2px);
		text-decoration: none;
	}

	.card-image {
		width: 100%;
		height: 140px;
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
	}

	.placeholder-icon {
		font-size: 2.5rem;
		opacity: 0.5;
	}

	.card-body {
		padding: 0.75rem 1rem 1rem;
	}

	.card-header {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 0.35rem;
	}

	.category-badge {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		background: var(--color-bg);
		padding: 0.1rem 0.45rem;
		border-radius: 999px;
		color: var(--color-primary);
		font-weight: 600;
	}

	.unavailable-badge {
		font-size: 0.7rem;
		background: var(--color-error-bg);
		color: var(--color-error);
		padding: 0.1rem 0.45rem;
		border-radius: 999px;
	}

	.resource-card h3 {
		font-size: 1rem;
		margin-bottom: 0.25rem;
	}

	.description {
		font-size: 0.82rem;
		color: var(--color-text-muted);
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
		margin-bottom: 0.4rem;
	}

	.card-footer {
		display: flex;
		justify-content: space-between;
		font-size: 0.78rem;
		color: var(--color-text-muted);
	}

	.loading {
		color: var(--color-text-muted);
	}

	.empty-state {
		text-align: center;
		padding: 3rem 1rem;
		color: var(--color-text-muted);
	}

	.empty-state p + p {
		margin-top: 0.5rem;
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
