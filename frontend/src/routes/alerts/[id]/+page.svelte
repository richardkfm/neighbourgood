<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { t } from 'svelte-i18n';
	import Icon from '$lib/components/Icon.svelte';
	import { api } from '$lib/api';
	import { isLoggedIn } from '$lib/stores/auth';
	import type { RedSkyAlertInfo } from '$lib/types';

	let alert = $state<RedSkyAlertInfo | null>(null);
	let loading = $state(true);
	let error = $state('');

	onMount(async () => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}
		try {
			alert = await api<RedSkyAlertInfo>(`/federation/alerts/${encodeURIComponent($page.params.id ?? '')}`, {
				auth: true
			});
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	});

	function formatDate(value: string | null | undefined): string {
		return value ? new Date(value).toLocaleString() : '—';
	}

	function severityColor(severity: string): string {
		return severity === 'critical' ? 'var(--color-error)' : severity === 'warning' ? 'var(--color-warning)' : 'var(--color-primary-text)';
	}
</script>

<svelte:head>
	<title>{alert?.title ?? $t('alerts.title')} — NeighbourGood</title>
</svelte:head>

<div class="alert-page">
	<a href="/alerts" class="back-link"><Icon name="arrow-left" size={16} class="flip-rtl" /> {$t('alerts.back')}</a>

	{#if loading}
		<div class="skeleton-stack" role="status" aria-busy="true">
			<span class="sr-only">{$t('common.loading')}</span>
			<div class="skeleton skeleton-card" style="height: 12rem" aria-hidden="true"></div>
		</div>
	{:else if error || !alert}
		<p class="alert alert-error" role="alert">{error || $t('alerts.not_found')}</p>
	{:else}
		<article class="card alert-detail" style="--sev: {severityColor(alert.severity)}">
			<span class="severity"><Icon name="alert" size={15} />{$t(`alerts.severity_${alert.severity}`)}</span>
			<h1>{alert.title}</h1>
			{#if !alert.is_active}
				<p class="inactive-note">{$t('alerts.inactive_note')}</p>
			{/if}
			{#if alert.description}
				<p class="description">{alert.description}</p>
			{/if}
			<dl>
				<dt>{$t('alerts.source')}</dt>
				<dd>{alert.source_instance_name} <span class="muted">({alert.source_instance_url})</span></dd>
				<dt>{$t('alerts.received')}</dt>
				<dd>{formatDate(alert.created_at)}</dd>
				<dt>{$t('alerts.expires')}</dt>
				<dd>{alert.expires_at ? formatDate(alert.expires_at) : $t('alerts.no_expiry')}</dd>
			</dl>
		</article>
	{/if}
</div>

<style>
	.alert-page {
		max-width: 760px;
		margin: 0 auto;
	}

	.back-link {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		margin-bottom: 1rem;
		color: var(--color-text-muted);
	}

	.muted {
		color: var(--color-text-muted);
	}

	.alert-detail {
		border-inline-start: 4px solid var(--sev);
		border-radius: var(--radius-sm);
	}

	.severity {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		color: var(--sev);
		font-size: 0.8rem;
		font-weight: 700;
		text-transform: uppercase;
	}

	h1 {
		margin: 0.25rem 0 0.75rem;
	}

	.inactive-note {
		color: var(--color-text-muted);
		font-style: italic;
	}

	.description {
		white-space: pre-wrap;
	}

	dl {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 0.4rem 1rem;
		margin: 1rem 0 0;
		font-size: 0.9rem;
	}

	dt {
		color: var(--color-text-muted);
	}

	dd {
		margin: 0;
		overflow-wrap: anywhere;
	}
</style>
