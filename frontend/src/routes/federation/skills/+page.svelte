<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { t } from 'svelte-i18n';
	import Icon from '$lib/components/Icon.svelte';
	import { api } from '$lib/api';
	import { isLoggedIn } from '$lib/stores/auth';
	import type { FederatedSkill, KnownInstance } from '$lib/types';

	let skills = $state<FederatedSkill[]>([]);
	let instances = $state<KnownInstance[]>([]);
	let loading = $state(true);
	let filterCategory = $state('');
	let filterType = $state('');
	let filterInstance = $state('');

	async function loadSkills() {
		loading = true;
		try {
			const params = new URLSearchParams();
			if (filterCategory) params.set('category', filterCategory);
			if (filterType) params.set('skill_type', filterType);
			if (filterInstance) params.set('instance_id', filterInstance);
			params.set('limit', '100');

			const qs = params.toString();
			skills = await api<FederatedSkill[]>(
				`/federation/federated-skills${qs ? '?' + qs : ''}`,
				{ auth: true }
			);
		} catch {
			skills = [];
		} finally {
			loading = false;
		}
	}

	async function loadInstances() {
		try {
			instances = await api<KnownInstance[]>('/federation/directory?reachable_only=true', { auth: true });
		} catch {
			instances = [];
		}
	}

	onMount(() => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}
		loadInstances();
		loadSkills();
	});

	function applyFilters() {
		loadSkills();
	}
</script>

<svelte:head>
	<title>{$t('federation.federated_skills')} — NeighbourGood</title>
</svelte:head>

<div class="fed-page">
	<header class="page-header">
		<div>
			<h1>{$t('federation.federated_skills')}</h1>
			<p class="subtitle">{$t('federation.skills_subtitle')}</p>
		</div>
		<a href="/communities#federation" class="btn btn-ghost btn-sm"><Icon name="arrow-left" size={14} class="flip-rtl" /> {$t('federation.back_to_directory')}</a>
	</header>

	<div class="filter-bar">
		<select class="input" bind:value={filterType} onchange={applyFilters}>
			<option value="">{$t('skills.all_types')}</option>
			<option value="offer">{$t('skills.type_offer')}</option>
			<option value="request">{$t('skills.type_request')}</option>
		</select>

		<select class="input" bind:value={filterCategory} onchange={applyFilters}>
			<option value="">{$t('skills.all_categories')}</option>
			<option value="tutoring">{$t('skills.categories.tutoring')}</option>
			<option value="repairs">{$t('skills.categories.repairs')}</option>
			<option value="cooking">{$t('skills.categories.cooking')}</option>
			<option value="languages">{$t('skills.categories.languages')}</option>
			<option value="music">{$t('skills.categories.music')}</option>
			<option value="gardening">{$t('skills.categories.gardening')}</option>
			<option value="tech">{$t('skills.categories.tech')}</option>
			<option value="crafts">{$t('skills.categories.crafts')}</option>
			<option value="fitness">{$t('skills.categories.fitness')}</option>
			<option value="other">{$t('skills.categories.other')}</option>
		</select>

		<select class="input" bind:value={filterInstance} onchange={applyFilters}>
			<option value="">{$t('federation.all_instances')}</option>
			{#each instances as inst}
				<option value={String(inst.id)}>{inst.name}</option>
			{/each}
		</select>
	</div>

	{#if loading}
		<div class="skill-grid" role="status" aria-busy="true">
			<span class="sr-only">{$t('common.loading')}</span>
			{#each [1, 2, 3, 4] as n (n)}
				<div class="skeleton skeleton-card" style="height: 8.5rem" aria-hidden="true"></div>
			{/each}
		</div>
	{:else if skills.length === 0}
		<div class="empty-state">
			<span class="empty-icon"><Icon name="globe" size={26} /></span>
			<p>{$t('federation.no_federated_skills')}</p>
		</div>
	{:else}
		<div class="skill-grid">
			{#each skills as skill}
				<div class="card skill-card">
					<div class="card-header">
						<h3>{skill.title}</h3>
						<span class="badge" class:badge-success={skill.skill_type === 'offer'} class:badge-warning={skill.skill_type === 'request'}>
							{skill.skill_type === 'offer' ? $t('skills.type_offer') : $t('skills.type_request')}
						</span>
					</div>
					{#if skill.description}
						<p class="card-desc">{skill.description}</p>
					{/if}
					<div class="card-meta">
						<span class="meta-item">{$t('skills.categories.' + skill.category, { default: skill.category })}</span>
						{#if skill.community_name}
							<span class="meta-item">{skill.community_name}</span>
						{/if}
					</div>
					<div class="card-footer">
						<span class="owner">{$t('common.by')} {skill.owner_display_name}</span>
						<span class="source">{skill.instance_name}</span>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.fed-page {
		max-width: 900px;
		margin: 0 auto;
	}

	.page-header h1 {
		font-family: var(--font-heading);
		font-weight: 400;
		font-size: 1.6rem;
		color: var(--color-text);
		margin: 0;
	}

	.subtitle {
		color: var(--color-text-muted);
		font-size: 0.9rem;
		margin: 0.25rem 0 0;
	}

	.skill-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
		gap: 1rem;
	}

	.skill-card:hover {
		box-shadow: var(--shadow-md);
	}

	.card-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.card-header h3 {
		margin: 0;
		font-size: 1rem;
		font-weight: 600;
		color: var(--color-text);
	}

	.card-desc {
		font-size: 0.88rem;
		color: var(--color-text-muted);
		margin: 0 0 0.5rem;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	.card-meta {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
		margin-bottom: 0.5rem;
	}

	.meta-item {
		font-size: 0.78rem;
		color: var(--color-text-muted);
		background: var(--color-bg);
		padding: 0.15rem 0.45rem;
		border-radius: var(--radius-sm);
		text-transform: capitalize;
	}

	.card-footer {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding-top: 0.5rem;
		border-top: 1px solid var(--color-border);
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	.source {
		font-weight: 600;
		color: var(--color-primary-text);
	}

	@media (max-width: 768px) {
		.skill-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
