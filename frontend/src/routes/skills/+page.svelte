<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { t } from 'svelte-i18n';
	import { api } from '$lib/api';
	import { isLoggedIn } from '$lib/stores/auth';

	interface SkillOwner {
		display_name: string;
		neighbourhood: string | null;
	}

	interface Skill {
		id: number;
		title: string;
		description: string | null;
		category: string;
		skill_type: string;
		community_id: number | null;
		owner: SkillOwner;
		created_at: string;
	}

	interface MyCommunity {
		id: number;
		name: string;
		postal_code: string;
	}

	const CATEGORIES = [
		{ value: '', label: 'All Categories' },
		{ value: 'tutoring', label: 'Tutoring' },
		{ value: 'repairs', label: 'Repairs' },
		{ value: 'cooking', label: 'Cooking' },
		{ value: 'languages', label: 'Languages' },
		{ value: 'music', label: 'Music' },
		{ value: 'gardening', label: 'Gardening' },
		{ value: 'tech', label: 'Tech' },
		{ value: 'crafts', label: 'Crafts' },
		{ value: 'fitness', label: 'Fitness' },
		{ value: 'other', label: 'Other' }
	];

	const CATEGORY_ICONS: Record<string, string> = {
		tutoring: '📚', repairs: '🔧', cooking: '🍳', languages: '🌐',
		music: '🎵', gardening: '🌱', tech: '💻', crafts: '✂️',
		fitness: '💪', other: '⭐'
	};

	const TYPE_FILTERS = [
		{ value: '', label: 'All Types' },
		{ value: 'offer', label: 'Offers' },
		{ value: 'request', label: 'Requests' }
	];

	let skills: Skill[] = $state([]);
	let total = $state(0);
	let loading = $state(true);
	let filterCategory = $state('');
	let filterType = $state('');
	let filterCommunity = $state('');
	let searchQuery = $state('');
	let searchTimeout: ReturnType<typeof setTimeout> | null = $state(null);
	let showCreateForm = $state(false);

	// Create form
	let newTitle = $state('');
	let newDescription = $state('');
	let newCategory = $state('tutoring');
	let newSkillType = $state('offer');
	let newCommunityId = $state('');
	let createError = $state('');
	let myCommunities = $state<MyCommunity[]>([]);

	async function loadSkills() {
		loading = true;
		try {
			const params = new URLSearchParams();
			if (filterCommunity) params.set('community_id', filterCommunity);
			if (filterCategory) params.set('category', filterCategory);
			if (filterType) params.set('skill_type', filterType);
			if (searchQuery.trim()) params.set('q', searchQuery.trim());
			const res = await api<{ items: Skill[]; total: number }>(
				`/skills?${params.toString()}`
			);
			skills = res.items;
			total = res.total;
		} catch {
			skills = [];
		} finally {
			loading = false;
		}
	}

	function handleSearchInput() {
		if (searchTimeout) clearTimeout(searchTimeout);
		searchTimeout = setTimeout(loadSkills, 300);
	}

	async function handleCreate(e: Event) {
		e.preventDefault();
		createError = '';
		if (!newCommunityId) {
			createError = get(t)('resources.please_select_community');
			return;
		}
		try {
			await api('/skills', {
				method: 'POST',
				auth: true,
				body: {
					title: newTitle,
					description: newDescription || null,
					category: newCategory,
					skill_type: newSkillType,
					community_id: Number(newCommunityId)
				}
			});
			showCreateForm = false;
			newTitle = '';
			newDescription = '';
			await loadSkills();
		} catch (err) {
			createError = err instanceof Error ? err.message : 'Failed to create skill listing';
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
		loadSkills();
	});

	$effect(() => {
		filterCategory;
		filterType;
		filterCommunity;
		loadSkills();
	});
</script>

<div class="skills-page">
	<div class="page-header">
		<h1>{$t('skills.title')}</h1>
		{#if $isLoggedIn}
			<button class="btn-primary" onclick={() => (showCreateForm = !showCreateForm)}>
				{showCreateForm ? $t('common.cancel') : $t('skills.share_btn')}
			</button>
		{/if}
	</div>

	<nav class="browse-tabs">
		<a href="/resources" class="browse-tab">Resources</a>
		<a href="/skills" class="browse-tab active">Skills</a>
	</nav>

	{#if showCreateForm}
		<div class="create-form-card">
			<h2>{$t('skills.share_title')}</h2>
			{#if createError}
				<p class="error">{createError}</p>
			{/if}
			<form onsubmit={handleCreate}>
				<label>
					<span>{$t('skills.title_label')}</span>
					<input type="text" bind:value={newTitle} required placeholder="e.g. Piano Lessons" />
				</label>
				<label>
					<span>{$t('skills.description_label')}</span>
					<textarea bind:value={newDescription} rows="3" placeholder="What skill are you offering or looking for?"></textarea>
				</label>
				<div class="form-row">
					<label>
						<span>{$t('skills.category_label')}</span>
						<select bind:value={newCategory}>
							{#each CATEGORIES.slice(1) as cat}
								<option value={cat.value}>{$t('skills.categories.' + cat.value)}</option>
							{/each}
						</select>
					</label>
					<label>
						<span>{$t('skills.type_label')}</span>
						<select bind:value={newSkillType}>
							<option value="offer">{$t('skills.type_offering')}</option>
							<option value="request">{$t('skills.type_seeking')}</option>
						</select>
					</label>
				</div>
				{#if myCommunities.length > 0}
					<label>
						<span>{$t('skills.community_label')}</span>
						<select bind:value={newCommunityId} required>
							{#each myCommunities as c}
								<option value={c.id}>{c.name} ({c.postal_code})</option>
							{/each}
						</select>
					</label>
				{:else}
					<p class="hint">{$t('skills.need_community')}</p>
				{/if}
				<button type="submit" class="btn-primary" disabled={myCommunities.length === 0}>{$t('skills.post_btn')}</button>
			</form>
		</div>
	{/if}

	<div class="filter-bar">
		<input
			type="search"
			class="search-input"
			placeholder={$t('skills.search_placeholder')}
			bind:value={searchQuery}
			oninput={handleSearchInput}
		/>
		<select bind:value={filterCategory}>
			{#each CATEGORIES as cat}
				<option value={cat.value}>
					{cat.value === '' ? $t('skills.all_categories') : $t('skills.categories.' + cat.value)}
				</option>
			{/each}
		</select>
		<select bind:value={filterType}>
			{#each TYPE_FILTERS as typeFilter}
				<option value={typeFilter.value}>
					{#if typeFilter.value === ''}
						{$t('skills.all_types')}
					{:else if typeFilter.value === 'offer'}
						{$t('skills.offers')}
					{:else}
						{$t('skills.requests')}
					{/if}
				</option>
			{/each}
		</select>
		{#if myCommunities.length > 0}
			<select bind:value={filterCommunity}>
				<option value="">{$t('skills.all_communities')}</option>
				{#each myCommunities as c}
					<option value={c.id}>{c.name}</option>
				{/each}
			</select>
		{/if}
		<span class="result-count">{total} result{total !== 1 ? 's' : ''}</span>
	</div>

	{#if loading}
		<p class="loading">{$t('common.loading')}</p>
	{:else if skills.length === 0}
		<div class="empty-state">
			<p>{$t('skills.no_skills')}</p>
			{#if searchQuery || filterCategory || filterType}
				<p>{$t('resources.adjust_filters')}</p>
			{:else if $isLoggedIn}
				<p>{$t('skills.first_skill')}</p>
			{:else}
				<p>{$t('skills.sign_up_skills')}</p>
			{/if}
		</div>
	{:else}
		<div class="skill-grid">
			{#each skills as skill}
				<a href="/skills/{skill.id}" class="skill-card">
					<div class="card-icon">
						<span>{CATEGORY_ICONS[skill.category] ?? '⭐'}</span>
					</div>
					<div class="card-body">
						<div class="card-header">
							<span class="category-badge">{skill.category}</span>
							<span class="type-badge" class:type-offer={skill.skill_type === 'offer'} class:type-request={skill.skill_type === 'request'}>
								{skill.skill_type === 'offer' ? $t('skills.offering') : $t('skills.looking_for')}
							</span>
						</div>
						<h3>{skill.title}</h3>
						{#if skill.description}
							<p class="description">{skill.description}</p>
						{/if}
						<div class="card-footer">
							<span class="owner">by {skill.owner.display_name}</span>
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

	.skills-page {
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

	.skill-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
		gap: 1rem;
	}

	.skill-card {
		display: flex;
		gap: 1rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		padding: 1rem 1.25rem;
		transition: border-color 0.15s;
		text-decoration: none;
		color: var(--color-text);
	}

	.skill-card:hover {
		border-color: var(--color-primary);
		text-decoration: none;
	}

	.card-icon {
		font-size: 1.75rem;
		flex-shrink: 0;
		padding-top: 0.1rem;
	}

	.card-body {
		flex: 1;
		min-width: 0;
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

	.type-badge {
		font-size: 0.7rem;
		padding: 0.1rem 0.45rem;
		border-radius: 999px;
		font-weight: 600;
	}

	.type-offer {
		background: var(--color-success-bg);
		color: var(--color-success);
	}

	.type-request {
		background: var(--color-warning-bg);
		color: var(--color-warning);
	}

	.skill-card h3 {
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
</style>
