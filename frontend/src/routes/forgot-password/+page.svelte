<script lang="ts">
	import { api } from '$lib/api';
	import { t } from 'svelte-i18n';

	let email = $state('');
	let error = $state('');
	let loading = $state(false);
	let sent = $state(false);

	async function handleSubmit(e: Event) {
		e.preventDefault();
		error = '';
		loading = true;
		try {
			await api('/auth/password-reset/request', { method: 'POST', body: { email } });
			sent = true;
		} catch (err) {
			error = err instanceof Error ? err.message : $t('common.error');
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>{$t('auth.forgot_title')} - NeighbourGood</title>
</svelte:head>

<div class="auth-page">
	<h1>{$t('auth.forgot_title')}</h1>

	{#if sent}
		<p class="success" role="status">{$t('auth.forgot_sent')}</p>
	{:else}
		<p class="subtitle">{$t('auth.forgot_subtitle')}</p>

		{#if error}
			<p class="error" role="alert">{error}</p>
		{/if}

		<form onsubmit={handleSubmit}>
			<div class="field">
				<label for="forgot-email">{$t('auth.email')}</label>
				<input
					id="forgot-email"
					type="email"
					bind:value={email}
					required
					maxlength="254"
					autocomplete="email"
					disabled={loading}
				/>
			</div>
			<button type="submit" disabled={loading}>
				{loading ? $t('auth.forgot_sending') : $t('auth.forgot_submit')}
			</button>
		</form>
	{/if}

	<p class="switch"><a href="/login">{$t('auth.back_to_login')}</a></p>
</div>

<style>
	.auth-page {
		max-width: 420px;
		margin: 3rem auto;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 2.25rem 2rem;
		box-shadow: var(--shadow-sm);
	}

	h1 {
		font-size: 1.9rem;
		margin-bottom: 0.25rem;
	}

	.subtitle {
		color: var(--color-text-muted);
		margin-bottom: 1.75rem;
	}

	@media (max-width: 480px) {
		.auth-page {
			margin: 1rem auto;
			padding: 1.5rem 1.25rem;
		}
	}

	form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	label {
		font-size: 0.85rem;
		font-weight: 500;
	}

	input {
		min-height: var(--tap-target);
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.95rem;
		background: var(--color-surface);
		color: var(--color-text);
	}

	input:focus {
		outline: 2px solid var(--color-primary);
		outline-offset: -1px;
	}

	button {
		min-height: var(--tap-target);
		padding: 0.6rem;
		background: var(--color-primary);
		color: white;
		border: none;
		border-radius: var(--radius);
		font-size: 1rem;
		cursor: pointer;
		margin-top: 0.5rem;
	}

	button:hover:not(:disabled) {
		background: var(--color-primary-hover);
	}

	button:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.error {
		color: var(--color-error);
		background: var(--color-error-bg);
		padding: 0.5rem 0.75rem;
		border-radius: var(--radius);
		font-size: 0.9rem;
		margin-bottom: 1rem;
	}

	.success {
		color: var(--color-success);
		background: var(--color-success-bg);
		padding: 0.75rem 1rem;
		border-radius: var(--radius);
		font-size: 0.95rem;
		line-height: 1.5;
	}

	.switch {
		text-align: center;
		margin-top: 1.5rem;
		font-size: 0.9rem;
	}

	.switch a {
		display: inline-flex;
		align-items: center;
		min-height: var(--tap-target);
		padding-inline: 0.5rem;
	}
</style>
