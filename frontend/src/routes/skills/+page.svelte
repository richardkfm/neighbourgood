<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { t } from 'svelte-i18n';
	import { api } from '$lib/api';
	import { isLoggedIn } from '$lib/stores/auth';
	import { isOnline } from '$lib/stores/offline';
	import Icon from '$lib/components/Icon.svelte';
	import ExpandableItem from '$lib/components/ExpandableItem.svelte';
	import { user } from '$lib/stores/auth';
	import { SKILL_CATEGORY_ICON, TRUST_BADGE_ICON } from '$lib/icons';

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
	let creating = $state(false);
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
		if (creating) return;
		creating = true;
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
			<button class="btn btn-primary" onclick={() => (showCreateForm = !showCreateForm)} aria-expanded={showCreateForm}>
				{showCreateForm ? $t('common.cancel') : $t('skills.share_btn')}
			</button>
		{/if}
	</div>

	<nav class="browse-tabs">
		<a href="/resources" class="browse-tab">{$t('resources.tab_label')}</a>
		<a href="/skills" class="browse-tab active">{$t('skills.tab_label')}</a>
	</nav>

	{#if showCreateForm}
		<div class="card create-form-card">
			<h2>{$t('skills.share_title')}</h2>
			{#if createError}
				<p class="alert alert-error" role="alert">{createError}</p>
			{/if}
			<form class="form-stack" onsubmit={handleCreate}>
				<label class="field">
					<span>{$t('skills.title_label')}</span>
					<input type="text" bind:value={newTitle} required placeholder={$t('skills.title_placeholder')} />
				</label>
				<label class="field">
					<span>{$t('skills.description_label')}</span>
					<textarea bind:value={newDescription} rows="3" placeholder={$t('skills.description_placeholder')}></textarea>
				</label>
				<div class="field-row">
					<label class="field">
						<span>{$t('skills.category_label')}</span>
						<select bind:value={newCategory}>
							{#each CATEGORIES.slice(1) as cat}
								<option value={cat}>{$t('skills.categories.' + cat)}</option>
							{/each}
						</select>
					</label>
					<label class="field">
						<span>{$t('skills.type_label')}</span>
						<select bind:value={newSkillType}>
							<option value="offer">{$t('skills.type_offering')}</option>
							<option value="request">{$t('skills.type_seeking')}</option>
						</select>
					</label>
				</div>
				{#if myCommunities.length > 1}
					<label class="field">
						<span>{$t('skills.community_label')}</span>
						<select bind:value={newCommunityId} required>
							{#each myCommunities as c}
								<option value={c.id}>{c.name} ({c.postal_code})</option>
							{/each}
						</select>
					</label>
				{:else if myCommunities.length === 0}
					<p class="field-hint">{$t('skills.need_community')}</p>
				{/if}
				<button type="submit" class="btn btn-primary" class:is-loading={creating} disabled={myCommunities.length === 0}>{$t('skills.post_btn')}</button>
			</form>
		</div>
	{/if}

	<div class="filter-bar">
		<input
			type="search"
			class="input input-grow"
			placeholder={$t('skills.search_placeholder')}
			bind:value={searchQuery}
			oninput={handleSearchInput}
		/>
		<select class="input" bind:value={filterCategory}>
			{#each CATEGORIES as cat}
				<option value={cat}>
					{cat === '' ? $t('skills.all_categories') : $t('skills.categories.' + cat)}
				</option>
			{/each}
		</select>
		<select class="input" bind:value={filterType}>
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
			<select class="input" bind:value={filterCommunity}>
				{#each myCommunities as c}
					<option value={c.id}>{c.name}</option>
				{/each}
			</select>
		{/if}
		<span class="result-count">{$t(total === 1 ? 'common.result' : 'common.results', { values: { count: total } })}</span>
	</div>

	{#if loading}
		<div class="item-grid" role="status" aria-busy="true">
			<span class="sr-only">{$t('common.loading')}</span>
			{#each [1, 2, 3, 4, 5, 6] as n (n)}
				<div class="skeleton skeleton-card" style="height: 4.5rem" aria-hidden="true"></div>
			{/each}
		</div>
	{:else if skills.length === 0}
		<div class="empty-state">
			<span class="empty-icon"><Icon name="lightbulb" size={26} /></span>
			<p>{$t('skills.no_skills')}</p>
			{#if searchQuery || filterCategory || filterType}
				<p>{$t('resources.adjust_filters')}</p>
			{:else if $isLoggedIn}
				<p>{$t('skills.first_skill')}</p>
				<button class="btn btn-primary" onclick={() => { showCreateForm = true; window.scrollTo({ top: 0, behavior: 'smooth' }); }}>
					<Icon name="plus" size={16} />{$t('skills.share_btn')}
				</button>
			{:else}
				<p>{$t('skills.sign_up_skills')}</p>
				<a href="/register" class="btn btn-primary">{$t('nav.signup')}</a>
			{/if}
		</div>
	{:else}
		<div class="item-grid">
			{#each skills as skill (skill.id)}
				{@const mine = $user?.id === skill.owner.id}
				<ExpandableItem
					variant="card"
					title={skill.title}
					meta="{$t('skills.categories.' + skill.category)} · {mine ? $t('resources.yours') : skill.owner.display_name}"
					icon={SKILL_CATEGORY_ICON[skill.category] ?? 'star'}
					tone={skill.skill_type === 'offer' ? 'primary' : 'accent'}
				>
					{#snippet aside()}
						<span class="meta-text">{skill.skill_type === 'offer' ? $t('skills.offering') : $t('skills.looking_for')}</span>
					{/snippet}
					{#if skill.description}<p class="clamp">{skill.description}</p>{/if}
					{#if skill.owner_trust && (skill.owner_trust.total_reviews > 0 || skill.owner_trust.badges.length > 0)}
						<p class="meta-text item-facts">
							{#if skill.owner_trust.total_reviews > 0}
								<span class="trust-stars"><Icon name="star" size={13} />{skill.owner_trust.average_rating.toFixed(1)}</span>
							{/if}
							{#each skill.owner_trust.badges as badge}
								<span class="trust-pill" title={badge}><Icon name={TRUST_BADGE_ICON[badge] ?? 'handshake'} size={14} /></span>
							{/each}
						</p>
					{/if}
					<div class="xp-actions">
						<a href="/skills/{skill.id}" class="btn btn-sm" class:btn-primary={!mine} class:btn-secondary={mine}>
							{mine ? $t('resources.view_details') : skill.skill_type === 'offer' ? $t('skills.ask_for_help') : $t('skills.offer_help')}
						</a>
						{#if $isLoggedIn && !mine}
							<a href="/messages?partner={skill.owner.id}&skill={skill.id}" class="btn btn-secondary btn-sm">{$t('dashboard.message_name', { values: { name: skill.owner.display_name } })}</a>
						{/if}
					</div>
				</ExpandableItem>
			{/each}
		</div>
	{/if}
</div>

<style>
	.skills-page {
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

	.clamp {
		display: -webkit-box;
		-webkit-line-clamp: 4;
		line-clamp: 4;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	.item-facts {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.6rem;
	}

	.trust-stars {
		display: inline-flex;
		align-items: center;
		gap: 0.2rem;
		color: var(--color-rating);
		font-weight: 600;
	}

	.trust-pill {
		display: inline-flex;
		color: var(--color-primary-text);
	}

</style>
