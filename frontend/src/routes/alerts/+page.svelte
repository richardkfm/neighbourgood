<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { t } from 'svelte-i18n';
	import Icon from '$lib/components/Icon.svelte';
	import { api } from '$lib/api';
	import { isLoggedIn } from '$lib/stores/auth';
	import type { RedSkyAlertInfo } from '$lib/types';

	let alerts = $state<RedSkyAlertInfo[]>([]);
	let showInactive = $state(false);
	let loading = $state(true);
	let error = $state('');

	async function load() {
		loading = true;
		error = '';
		try {
			alerts = await api<RedSkyAlertInfo[]>(`/federation/alerts?active_only=${!showInactive}`, { auth: true });
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}
		load();
	});

	function toggleInactive() {
		showInactive = !showInactive;
		load();
	}

	function severityColor(severity: string): string {
		return severity === 'critical' ? 'var(--color-error)' : severity === 'warning' ? 'var(--color-warning)' : 'var(--color-primary-text)';
	}
</script>

<svelte:head>
	<title>{$t('alerts.title')} — NeighbourGood</title>
</svelte:head>

<div class="alerts-page">
	<h1>{$t('alerts.title')}</h1>
	<p class="subtitle">{$t('alerts.subtitle')}</p>

	<label class="inactive-toggle">
		<input type="checkbox" checked={showInactive} onchange={toggleInactive} />
		{$t('alerts.show_inactive')}
	</label>

	{#if loading}
		<div class="skeleton-stack" role="status" aria-busy="true">
			<span class="sr-only">{$t('common.loading')}</span>
			{#each [1, 2, 3] as n (n)}
				<div class="skeleton skeleton-card" style="height: 5rem" aria-hidden="true"></div>
			{/each}
		</div>
	{:else if error}
		<p class="alert alert-error" role="alert">{error}</p>
	{:else if alerts.length === 0}
		<div class="empty-state">
			<span class="empty-icon"><Icon name="shield" size={26} /></span>
			<p>{$t('alerts.none')}</p>
		</div>
	{:else}
		<ul class="alert-list">
			{#each alerts as alert (alert.id)}
				<li>
					<a href="/alerts/{alert.id}" class="card card-interactive alert-card" class:inactive={!alert.is_active} style="--sev: {severityColor(alert.severity)}">
						<span class="severity"><Icon name="alert" size={14} />{$t(`alerts.severity_${alert.severity}`)}</span>
						<strong>{alert.title}</strong>
						<span class="meta">
							{alert.source_instance_name} · {new Date(alert.created_at).toLocaleString()}
							{#if !alert.is_active}· {$t('alerts.inactive')}{/if}
						</span>
					</a>
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.alerts-page {
		max-width: 760px;
		margin: 0 auto;
	}

	.subtitle {
		color: var(--color-text-muted);
	}

	.inactive-toggle {
		display: inline-flex;
		gap: 0.4rem;
		align-items: center;
		margin: 0.5rem 0 1rem;
		font-size: 0.9rem;
	}

	.alert-list {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.alert-card {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 0.9rem 1rem;
		border-inline-start: 4px solid var(--sev);
		border-radius: var(--radius-sm);
	}

	.alert-card:hover {
		border-inline-start-color: var(--sev);
	}

	.alert-card.inactive {
		opacity: 0.65;
	}

	.severity {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		color: var(--sev);
		font-size: 0.75rem;
		font-weight: 700;
		text-transform: uppercase;
	}

	.meta {
		color: var(--color-text-muted);
		font-size: 0.8rem;
	}
</style>
