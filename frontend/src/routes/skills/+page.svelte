<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { t } from 'svelte-i18n';
	import { api } from '$lib/api';
	import { isLoggedIn } from '$lib/stores/auth';
	import { isOnline } from '$lib/stores/offline';

	import type { OwnerTrust } from '$lib/types';

	interface SkillOwner {
		id: number;
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
		owner_trust?: OwnerTrust | null;
		created_at: string;
	}

	interface MyCommunity {
		id: number;
		name: string;
		postal_code: string;
	}

	const CATEGORIES = ['', 'tutoring', 'repairs', 'cooking', 'languages', 'music', 'gardening', 'tech', 'crafts', 'fitness', 'other'];

	const CATEGORY_ICONS: Record<string, string> = {
		tutoring: '📚', repairs: '🔧', cooking: '🍳', languages: '🌐',
		music: '🎵', gardening: '🌱', tech: '💻', crafts: '✂️',
		fitness: '💪', other: '⭐'
	};

	const TYPE_FILTERS = ['', 'offer', 'request'];

	let skills: Skill[] = $state([]);
	let total = $state(0);
	let loading = $state(true);
	let filterCategory = $state('');
	let filterType = $state('');
	let filterCommunity = $state('');
	let searchQuery = $state('');
	let searchTimeout: ReturnType<typeof setTimeout> | null = $state(null);
	let showCreateForm = $state(false);
	let myCommunitiesLoaded = $state(false);
	let requestId = 0;

	// Create form
	let newTitle = $state('');
	let newDescription = $state('');
	let newCategory = $state('tutoring');
	let newSkillType = $state('offer');
	let newCommunityId = $state('');
	let createError = $state('');
	let myCommunities = $state<MyCommunity[]>([]);

	async function loadSkills() {
		const thisRequest = ++requestId;
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
			if (thisRequest !== requestId) return; // superseded by a newer request
			skills = res.items;
			total = res.total;
		} catch {
			if (thisRequest !== requestId) return;
			skills = [];
		} finally {
			if (thisRequest === requestId) loading = false;
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
				},
				offline: { label: $t('skills.offline_new', { values: { title: newTitle } }) }
			});
			showCreateForm = false;
			newTitle = '';
			newDescription = '';
			if (get(isOnline)) {
				await loadSkills();
			}
		} catch (err) {
			createError = err instanceof Error ? err.message : $t('skills.create_failed');
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
		filterType;
		filterCommunity;
		if (!myCommunitiesLoaded) return;
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
		<a href="/resources" class="browse-tab">{$t('resources.tab_label')}</a>
		<a href="/skills" class="browse-tab active">{$t('skills.tab_label')}</a>
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
					<input type="text" bind:value={newTitle} required placeholder={$t('skills.title_placeholder')} />
				</label>
				<label>
					<span>{$t('skills.description_label')}</span>
					<textarea bind:value={newDescription} rows="3" placeholder={$t('skills.description_placeholder')}></textarea>
				</label>
				<div class="form-row">
					<label>
						<span>{$t('skills.category_label')}</span>
						<select bind:value={newCategory}>
							{#each CATEGORIES.slice(1) as cat}
								<option value={cat}>{$t('skills.categories.' + cat)}</option>
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
				{#if myCommunities.length > 1}
					<label>
						<span>{$t('skills.community_label')}</span>
						<select bind:value={newCommunityId} required>
							{#each myCommunities as c}
								<option value={c.id}>{c.name} ({c.postal_code})</option>
							{/each}
						</select>
					</label>
				{:else if myCommunities.length === 0}
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
				<option value={cat}>
					{cat === '' ? $t('skills.all_categories') : $t('skills.categories.' + cat)}
				</option>
			{/each}
		</select>
		<select bind:value={filterType}>
			{#each TYPE_FILTERS as typeFilter}
				<option value={typeFilter}>
					{#if typeFilter === ''}
						{$t('skills.all_types')}
					{:else if typeFilter === 'offer'}
						{$t('skills.offers')}
					{:else}
						{$t('skills.requests')}
					{/if}
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
		<span class="result-count">{$t(total === 1 ? 'common.result' : 'common.results', { values: { count: total } })}</span>
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
							<span class="category-badge">{$t('skills.categories.' + skill.category)}</span>
							<span class="type-badge" class:type-offer={skill.skill_type === 'offer'} class:type-request={skill.skill_type === 'request'}>
								{skill.skill_type === 'offer' ? $t('skills.offering') : $t('skills.looking_for')}
							</span>
						</div>
						<h3>{skill.title}</h3>
						{#if skill.description}
							<p class="description">{skill.description}</p>
						{/if}
						<div class="card-spacer"></div>
						<div class="card-footer">
							<span class="owner">{$t('common.by_name', { values: { name: skill.owner.display_name } })}</span>
							{#if skill.owner_trust}
								{#if skill.owner_trust.total_reviews > 0}
									<span class="trust-stars">★ {skill.owner_trust.average_rating.toFixed(1)}</span>
								{/if}
								{#each skill.owner_trust.badges as badge}
									<span class="trust-pill">{badge === 'skilled_helper' ? '⭐' : badge === 'trusted_lender' ? '📦' : '🤝'}</span>
								{/each}
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
		color: var(--color-primary);
		border-bottom-color: var(--color-primary);
		font-weight: 600;
	}

	.skills-page {
		max-width: 960px;
	}

	.page-header {
		margin-bottom: 1.25rem;
	}

	.btn-primary {
		background: var(--color-primary);
		color: white;
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

	.skill-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
		gap: 1.5rem;
	}

	.skill-card {
		display: flex;
		gap: 1rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 1.25rem;
		transition: border-color var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast);
		text-decoration: none;
		color: var(--color-text);
	}

	.skill-card:hover {
		border-color: var(--color-primary);
		box-shadow: var(--shadow-md);
		transform: translateY(-3px);
		text-decoration: none;
	}

	.card-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		border-radius: var(--radius);
		background: var(--color-primary-light);
		font-size: 1.35rem;
		flex-shrink: 0;
	}

	.card-body {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-width: 0;
	}

	.card-spacer {
		flex: 1;
	}

	.card-header {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 0.6rem;
		flex-wrap: wrap;
	}

	.category-badge {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		background: var(--color-primary-light);
		padding: 0.15rem 0.55rem;
		border-radius: 999px;
		color: var(--color-primary);
		font-weight: 600;
	}

	.type-badge {
		font-size: 0.7rem;
		padding: 0.15rem 0.55rem;
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
		font-size: 0.78rem;
		color: var(--color-text-muted);
		display: flex;
		align-items: center;
		gap: 0.4rem;
		flex-wrap: wrap;
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
