<script lang="ts">
	import { page } from '$app/stores';
	import { api } from '$lib/api';
	import { t } from 'svelte-i18n';

	// The emailed link is /reset-password?token=...
	const resetToken = $derived($page.url.searchParams.get('token') ?? '');

	let password = $state('');
	let confirm = $state('');
	let error = $state('');
	let loading = $state(false);
	let done = $state(false);

	async function handleSubmit(e: Event) {
		e.preventDefault();
		error = '';
		if (password !== confirm) {
			error = $t('auth.passwords_no_match');
			return;
		}
		loading = true;
		try {
			await api('/auth/password-reset/confirm', {
				method: 'POST',
				body: { token: resetToken, new_password: password }
			});
			done = true;
			password = '';
			confirm = '';
		} catch (err) {
			error = err instanceof Error ? err.message : $t('common.error');
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>{$t('auth.reset_title')} - NeighbourGood</title>
	<!-- The reset token is in the URL: never leak it through the Referer header. -->
	<meta name="referrer" content="no-referrer" />
</svelte:head>

<div class="auth-page">
	<h1>{$t('auth.reset_title')}</h1>

	{#if done}
		<p class="success" role="status">{$t('auth.reset_success')}</p>
		<p class="action"><a class="btn-link" href="/login">{$t('auth.login_btn')}</a></p>
	{:else if !resetToken}
		<p class="error" role="alert">{$t('auth.reset_missing_token')}</p>
		<p class="action"><a class="btn-link" href="/forgot-password">{$t('auth.reset_request_new')}</a></p>
	{:else}
		<p class="subtitle">{$t('auth.reset_subtitle')}</p>

		{#if error}
			<p class="error" role="alert">{error}</p>
		{/if}

		<form onsubmit={handleSubmit}>
			<div class="field">
				<label for="reset-password">{$t('auth.reset_new_password')}</label>
				<input
					id="reset-password"
					type="password"
					bind:value={password}
					required
					minlength="8"
					maxlength="128"
					autocomplete="new-password"
					aria-describedby="reset-password-hint"
					disabled={loading}
				/>
				<small id="reset-password-hint" class="hint">{$t('auth.password_hint')}</small>
			</div>
			<div class="field">
				<label for="reset-confirm">{$t('auth.reset_confirm_password')}</label>
				<input
					id="reset-confirm"
					type="password"
					bind:value={confirm}
					required
					minlength="8"
					maxlength="128"
					autocomplete="new-password"
					disabled={loading}
				/>
			</div>
			<button type="submit" disabled={loading}>
				{loading ? $t('auth.resetting') : $t('auth.reset_submit')}
			</button>
		</form>

		<p class="switch"><a href="/login">{$t('auth.back_to_login')}</a></p>
	{/if}
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

	.hint {
		font-size: 0.8rem;
		color: var(--color-text-muted);
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

	button,
	.btn-link {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-height: var(--tap-target);
		padding: 0.6rem 1.25rem;
		background: var(--color-primary);
		color: var(--color-on-primary);
		border: none;
		border-radius: var(--radius);
		font-size: 1rem;
		cursor: pointer;
		text-decoration: none;
	}

	button {
		margin-top: 0.5rem;
	}

	button:hover:not(:disabled),
	.btn-link:hover {
		background: var(--color-primary-hover);
	}

	button:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.action {
		margin-top: 1.25rem;
		text-align: center;
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
