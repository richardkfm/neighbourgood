<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { isLoggedIn } from '$lib/stores/auth';
	import { t } from 'svelte-i18n';

	interface RedeemResult {
		community_id: number;
		community_name: string;
		message: string;
	}

	let result = $state<RedeemResult | null>(null);
	let error = $state('');
	let loading = $state(false);

	const code = $derived($page.params.code);

	async function redeem() {
		loading = true;
		error = '';
		try {
			result = await api<RedeemResult>(`/invites/${code}/redeem`, {
				method: 'POST',
				auth: true,
			});
		} catch (err) {
			error = err instanceof Error ? err.message : 'Could not redeem invite';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		if ($isLoggedIn) {
			redeem();
		}
	});
</script>

<div class="redeem-page">
	{#if !$isLoggedIn}
		<div class="card">
			<h1>{$t('invite.title')}</h1>
			<p>{$t('invite.subtitle')}</p>
			<div class="actions">
				<a href="/login" class="btn-primary">{$t('invite.login')}</a>
				<a href="/register" class="btn-secondary">{$t('invite.sign_up')}</a>
			</div>
		</div>
	{:else if loading}
		<div class="card">
			<p class="loading-text">{$t('invite.redeeming')}</p>
		</div>
	{:else if error}
		<div class="card">
			<h1>{$t('invite.error_title')}</h1>
			<p class="error-text">{error}</p>
			<a href="/communities" class="btn-secondary">{$t('invite.browse')}</a>
		</div>
	{:else if result}
		<div class="card">
			<h1>{result.message}</h1>
			<p>{$t('invite.joined_msg', { values: { name: result.community_name } })}</p>
			<a href="/communities/{result.community_id}" class="btn-primary">{$t('invite.go_to_community')}</a>
		</div>
	{/if}
</div>

<style>
	.redeem-page {
		display: flex;
		align-items: center;
		justify-content: center;
		min-height: 50vh;
	}

	.card {
		max-width: 420px;
		width: 100%;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 2rem;
		text-align: center;
	}

	.card h1 {
		font-size: 1.5rem;
		margin-bottom: 0.75rem;
	}

	.card p {
		color: var(--color-text-muted);
		margin-bottom: 1.25rem;
		line-height: 1.6;
	}

	.actions {
		display: flex;
		gap: 0.75rem;
		justify-content: center;
	}

	.btn-primary {
		display: inline-block;
		padding: 0.55rem 1.25rem;
		background: var(--color-primary);
		color: white;
		border: none;
		border-radius: var(--radius);
		font-size: 0.9rem;
		font-weight: 600;
		text-decoration: none;
		transition: all var(--transition-fast);
	}

	.btn-primary:hover {
		background: var(--color-primary-hover);
		box-shadow: var(--shadow);
	}

	.btn-secondary {
		display: inline-block;
		padding: 0.55rem 1.25rem;
		background: var(--color-surface);
		color: var(--color-text-muted);
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
	}

	.loading-text {
		color: var(--color-text-muted);
	}

	.error-text {
		color: var(--color-error);
	}
</style>
