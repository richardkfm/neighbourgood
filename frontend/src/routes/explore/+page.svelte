<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isLoggedIn } from '$lib/stores/auth';
	import { t } from 'svelte-i18n';
	import { api } from '$lib/api';
	import CommunityMap from '$lib/components/CommunityMap.svelte';
	import type { MapCommunity } from '$lib/types';

	function activityScore(c: MapCommunity): number {
		return c.member_count + c.resource_count * 2 + c.skill_count * 2;
	}

	function activityLevel(c: MapCommunity): 'high' | 'medium' | 'low' {
		const s = activityScore(c);
		if (s >= 10) return 'high';
		if (s >= 4) return 'medium';
		return 'low';
	}

	let communities = $state<MapCommunity[]>([]);
	let loading = $state(true);
	let error = $state('');

	onMount(async () => {
		// /explore is the public discovery page; members get the full
		// community page (same map and list, plus memberships/federation).
		if ($isLoggedIn) {
			goto('/communities', { replaceState: true });
			return;
		}

		try {
			communities = await api<MapCommunity[]>('/communities/map');
		} catch {
			error = $t('common.error');
		} finally {
			loading = false;
		}
	});

	const sortedCommunities = $derived(
		[...communities].sort((a, b) => activityScore(b) - activityScore(a))
	);
</script>

<svelte:head>
	<title>{$t('explore.title')} - NeighbourGood</title>
</svelte:head>

<div class="explore-page">
	<div class="explore-header slide-up">
		<div>
			<h1>{$t('explore.title')}</h1>
			<p class="subtitle">{$t('explore.subtitle')}</p>
		</div>
		{#if !$isLoggedIn}
			<a href="/register" class="btn-cta">{$t('explore.join_neighbourgood')}</a>
		{/if}
	</div>

	{#if error}
		<div class="alert alert-error fade-in">{error}</div>
	{/if}

	<CommunityMap {communities} {loading} />

	{#if communities.length === 0 && !loading && !error}
		<div class="no-communities fade-in">
			<h2>{$t('explore.no_communities')}</h2>
			<p>{$t('explore.first_community')}</p>
			<a href="/register" class="btn-primary">{$t('explore.sign_up_create')}</a>
		</div>
	{/if}

	{#if sortedCommunities.length > 0}
		<section class="community-list slide-up" style="animation-delay: 0.1s">
			<h2>{$t('explore.communities_heading')}</h2>
			<div class="list-grid">
				{#each sortedCommunities as c (c.id)}
					{@const level = activityLevel(c)}
					<a href="/register"
					   class="list-card"
					   class:card-active={level === 'high'}
					   class:card-medium={level === 'medium'}>
						<div class="list-card-header">
							<h3>{c.name}</h3>
							{#if level === 'high'}
								<span class="badge-active">{$t('explore.active_badge')}</span>
							{/if}
							{#if c.mode === 'red'}
								<span class="badge-crisis">{$t('explore.crisis_badge')}</span>
							{/if}
						</div>
						<div class="list-card-meta">
							<span class="tag">{c.postal_code}</span>
							<span class="tag">{c.city}</span>
						</div>
						<div class="list-card-stats">
							<span>{c.member_count} member{c.member_count !== 1 ? 's' : ''}</span>
							<span class="stat-sep">&middot;</span>
							<span>{c.resource_count} item{c.resource_count !== 1 ? 's' : ''}</span>
							<span class="stat-sep">&middot;</span>
							<span>{c.skill_count} skill{c.skill_count !== 1 ? 's' : ''}</span>
						</div>
					</a>
				{/each}
			</div>
		</section>
	{/if}

	{#if !$isLoggedIn}
		<section class="cta-section slide-up" style="animation-delay: 0.15s">
			<h2>{$t('explore.cta_title')}</h2>
			<p>{$t('explore.cta_desc')}</p>
			<div class="cta-actions">
				<a href="/register" class="btn-cta">{$t('auth.register_btn')}</a>
				<a href="/login" class="btn-secondary">{$t('auth.have_account')}</a>
			</div>
		</section>
	{/if}
</div>

<style>
	.explore-page {
		max-width: 900px;
		margin: 0 auto;
	}

	.explore-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 1.5rem;
	}

	.explore-header h1 {
		font-size: 1.75rem;
		font-weight: 400;
		letter-spacing: -0.02em;
	}

	.subtitle {
		color: var(--color-text-muted);
		font-size: 0.95rem;
		margin-top: 0.25rem;
	}

	/* ── Community list ──────────────────────── */

	.community-list {
		margin-bottom: 1.5rem;
	}

	.community-list h2 {
		font-size: 1.2rem;
		font-weight: 500;
		margin-bottom: 0.75rem;
	}

	.list-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
		gap: 0.75rem;
	}

	.list-card {
		display: block;
		padding: 1rem 1.25rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		text-decoration: none;
		color: var(--color-text);
		transition: all var(--transition-fast);
	}

	.list-card:hover {
		border-color: var(--color-primary);
		box-shadow: var(--shadow-md);
		transform: translateY(-2px);
		text-decoration: none;
	}

	.card-active {
		border-color: var(--color-primary);
		border-left: 3px solid var(--color-primary);
		background: linear-gradient(135deg, var(--color-surface) 0%, var(--color-primary-light) 100%);
	}

	.card-medium {
		border-left: 3px solid var(--color-accent);
	}

	.list-card-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.35rem;
	}

	.list-card-header h3 {
		font-size: 0.95rem;
		font-weight: 500;
	}

	.badge-active {
		font-size: 0.6rem;
		font-weight: 600;
		padding: 0.1rem 0.4rem;
		border-radius: 999px;
		background: var(--color-primary);
		color: white;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.badge-crisis {
		font-size: 0.65rem;
		font-weight: 600;
		padding: 0.1rem 0.4rem;
		border-radius: 999px;
		background: var(--color-error);
		color: var(--color-on-error);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.list-card-meta {
		display: flex;
		gap: 0.35rem;
		margin-bottom: 0.35rem;
	}

	.list-card-stats {
		display: flex;
		gap: 0.3rem;
		font-size: 0.78rem;
		color: var(--color-text-muted);
		margin-top: 0.15rem;
	}

	.stat-sep {
		color: var(--color-border);
	}

	/* ── No communities ──────────────────────── */

	.no-communities {
		text-align: center;
		padding: 2.5rem 1rem;
		background: var(--color-surface);
		border: 1px dashed var(--color-border);
		border-radius: var(--radius-lg);
		margin-bottom: 1.5rem;
	}

	.no-communities h2 {
		font-size: 1.2rem;
		margin-bottom: 0.4rem;
	}

	.no-communities p {
		color: var(--color-text-muted);
		margin-bottom: 1rem;
	}

	/* ── CTA section ─────────────────────────── */

	.cta-section {
		text-align: center;
		padding: 2.5rem 1.5rem;
		background: var(--color-primary-light);
		border: 1px solid var(--color-primary);
		border-radius: var(--radius-lg);
		margin-bottom: 1.5rem;
	}

	.cta-section h2 {
		font-size: 1.25rem;
		font-weight: 500;
		margin-bottom: 0.5rem;
	}

	.cta-section p {
		color: var(--color-text-muted);
		margin-bottom: 1.25rem;
		max-width: 500px;
		margin-left: auto;
		margin-right: auto;
	}

	.cta-actions {
		display: flex;
		justify-content: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	/* ── Buttons ──────────────────────────────── */

	.btn-cta {
		display: inline-flex;
		align-items: center;
		padding: 0.6rem 1.25rem;
		background: var(--color-primary);
		color: white !important;
		border-radius: var(--radius);
		font-size: 0.9rem;
		font-weight: 600;
		text-decoration: none;
		transition: all var(--transition-fast);
		box-shadow: var(--shadow);
	}

	.btn-cta:hover {
		background: var(--color-primary-hover);
		box-shadow: var(--shadow-md);
		transform: translateY(-1px);
		text-decoration: none;
	}

	.btn-primary {
		display: inline-block;
		padding: 0.5rem 1.25rem;
		background: var(--color-primary);
		color: white !important;
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

	.btn-secondary {
		display: inline-flex;
		align-items: center;
		padding: 0.6rem 1.25rem;
		background: var(--color-surface);
		color: var(--color-text);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.9rem;
		font-weight: 500;
		text-decoration: none;
		transition: all var(--transition-fast);
	}

	.btn-secondary:hover {
		border-color: var(--color-primary);
		color: var(--color-primary);
		text-decoration: none;
	}

	@media (max-width: 640px) {
		.explore-header {
			flex-direction: column;
		}

		.list-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
