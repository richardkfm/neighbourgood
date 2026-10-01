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
			error = err instanceof Error ? err.message : $t('invite.redeem_failed');
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		if ($isLoggedIn) {
			redeem();
		} else if (code) {
			// Login/register pick this up and come back here afterwards
			sessionStorage.setItem('ng_pending_invite', code);
		}
	});
</script>

<div class="redeem-page">
	{#if !$isLoggedIn}
		<div class="card invite-card">
			<h1>{$t('invite.title')}</h1>
			<p>{$t('invite.subtitle')}</p>
			<div class="actions">
				<a href="/login" class="btn btn-primary">{$t('invite.login')}</a>
				<a href="/register" class="btn btn-secondary">{$t('invite.sign_up')}</a>
			</div>
		</div>
	{:else if loading}
		<div class="card invite-card">
			<div class="skeleton-stack" role="status" aria-busy="true">
				<span class="sr-only">{$t('invite.redeeming')}</span>
				<span class="skeleton skeleton-line" aria-hidden="true"></span>
				<span class="skeleton skeleton-line is-short" aria-hidden="true"></span>
			</div>
		</div>
	{:else if error}
		<div class="card invite-card">
			<h1>{$t('invite.error_title')}</h1>
			<p class="alert alert-error" role="alert">{error}</p>
			<a href="/communities" class="btn btn-secondary">{$t('invite.browse')}</a>
		</div>
	{:else if result}
		<div class="card invite-card">
			<h1>{result.message}</h1>
			<p>{$t('invite.joined_msg', { values: { name: result.community_name } })}</p>
			<a href="/communities/{result.community_id}" class="btn btn-primary">{$t('invite.go_to_community')}</a>
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

	.invite-card {
		max-width: 420px;
		width: 100%;
		padding: 2rem;
		text-align: center;
	}

	.invite-card h1 {
		font-size: 1.5rem;
		margin-bottom: 0.75rem;
	}

	.invite-card > p {
		color: var(--color-text-muted);
		margin-bottom: 1.25rem;
		line-height: 1.6;
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		justify-content: center;
	}
</style>
