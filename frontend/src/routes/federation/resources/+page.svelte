<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { t } from 'svelte-i18n';
	import Icon from '$lib/components/Icon.svelte';
	import { api } from '$lib/api';
	import { isLoggedIn } from '$lib/stores/auth';
	import type { FederatedResource, KnownInstance } from '$lib/types';

	let resources = $state<FederatedResource[]>([]);
	let instances = $state<KnownInstance[]>([]);
	let loading = $state(true);
	let filterCategory = $state('');
	let filterInstance = $state('');

	async function loadResources() {
		loading = true;
		try {
			const params = new URLSearchParams();
			if (filterCategory) params.set('category', filterCategory);
			if (filterInstance) params.set('instance_id', filterInstance);
			params.set('limit', '100');

			const qs = params.toString();
			resources = await api<FederatedResource[]>(
				`/federation/federated-resources${qs ? '?' + qs : ''}`,
				{ auth: true }
			);
		} catch {
			resources = [];
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
		loadResources();
	});

	function applyFilters() {
		loadResources();
	}
</script>

<svelte:head>
	<title>{$t('federation.federated_resources')} — NeighbourGood</title>
</svelte:head>

<div class="fed-page">
	<header class="page-header">
		<div>
			<h1>{$t('federation.federated_resources')}</h1>
			<p class="subtitle">{$t('federation.resources_subtitle')}</p>
		</div>
		<a href="/communities#federation" class="btn btn-ghost btn-sm"><Icon name="arrow-left" size={14} class="flip-rtl" /> {$t('federation.back_to_directory')}</a>
	</header>

	<div class="filter-bar">
		<select class="input" bind:value={filterCategory} onchange={applyFilters}>
			<option value="">{$t('resources.all_categories')}</option>
			<option value="tool">{$t('resources.categories.tool')}</option>
			<option value="vehicle">{$t('resources.categories.vehicle')}</option>
			<option value="electronics">{$t('resources.categories.electronics')}</option>
			<option value="furniture">{$t('resources.categories.furniture')}</option>
			<option value="food">{$t('resources.categories.food')}</option>
			<option value="clothing">{$t('resources.categories.clothing')}</option>
			<option value="skill">{$t('resources.categories.skill')}</option>
			<option value="other">{$t('resources.categories.other')}</option>
		</select>

		<select class="input" bind:value={filterInstance} onchange={applyFilters}>
			<option value="">{$t('federation.all_instances')}</option>
			{#each instances as inst}
				<option value={String(inst.id)}>{inst.name}</option>
			{/each}
		</select>
	</div>

	{#if loading}
		<div class="resource-grid" role="status" aria-busy="true">
			<span class="sr-only">{$t('common.loading')}</span>
			{#each [1, 2, 3, 4] as n (n)}
				<div class="skeleton skeleton-card" style="height: 8.5rem" aria-hidden="true"></div>
			{/each}
		</div>
	{:else if resources.length === 0}
		<div class="empty-state">
			<span class="empty-icon"><Icon name="globe" size={26} /></span>
			<p>{$t('federation.no_federated_resources')}</p>
		</div>
	{:else}
		<div class="resource-grid">
			{#each resources as res}
				<div class="card resource-card">
					<div class="card-header">
						<h3>{res.title}</h3>
						<span class="badge badge-primary">{$t('resources.categories.' + res.category, { default: res.category })}</span>
					</div>
					{#if res.description}
						<p class="card-desc">{res.description}</p>
					{/if}
					<div class="card-meta">
						{#if res.condition}
							<span class="meta-item">{$t('resources.conditions.' + res.condition, { default: res.condition })}</span>
						{/if}
						{#if res.community_name}
							<span class="meta-item">{res.community_name}</span>
						{/if}
					</div>
					<div class="card-footer">
						<span class="owner">{$t('common.by')} {res.owner_display_name}</span>
						<span class="source">{res.instance_name}</span>
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

	.resource-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
		gap: 1rem;
	}

	.resource-card:hover {
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
		.resource-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
