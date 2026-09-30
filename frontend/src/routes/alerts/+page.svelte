<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { t } from 'svelte-i18n';
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
		<p class="muted">{$t('common.loading')}</p>
	{:else if error}
		<p class="error">{error}</p>
	{:else if alerts.length === 0}
		<p class="muted">{$t('alerts.none')}</p>
	{:else}
		<ul class="alert-list">
			{#each alerts as alert (alert.id)}
				<li>
					<a href="/alerts/{alert.id}" class="alert-card" class:inactive={!alert.is_active} style="--sev: {severityColor(alert.severity)}">
						<span class="severity">{$t(`alerts.severity_${alert.severity}`)}</span>
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

	.subtitle,
	.muted {
		color: var(--color-text-muted);
	}

	.error {
		color: var(--color-error);
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
		border: 1px solid var(--color-border);
		border-inline-start: 4px solid var(--sev);
		border-radius: var(--radius-sm);
		background: var(--color-surface);
		color: var(--color-text);
		text-decoration: none;
	}

	.alert-card:hover {
		border-color: var(--color-border-hover);
		border-inline-start-color: var(--sev);
	}

	.alert-card.inactive {
		opacity: 0.65;
	}

	.severity {
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
