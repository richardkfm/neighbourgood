<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { token, user } from '$lib/stores/auth';
	import type { UserProfile } from '$lib/stores/auth';
	import { hydrateLocale } from '$lib/stores/locale';
	import { t } from 'svelte-i18n';

	let email = $state('');
	let password = $state('');
	let error = $state('');
	let loading = $state(false);

	async function handleSubmit(e: Event) {
		e.preventDefault();
		error = '';
		loading = true;

		try {
			const res = await api<{ access_token: string }>('/auth/login', {
				method: 'POST',
				body: { email, password }
			});
			token.set(res.access_token);

			const profile = await api<UserProfile>('/users/me', { auth: true });
			user.set(profile);
			hydrateLocale(profile.language_code);

			// Resume an invite the visitor opened before signing in
			const pendingInvite = sessionStorage.getItem('ng_pending_invite');
			if (pendingInvite) {
				sessionStorage.removeItem('ng_pending_invite');
				goto(`/invites/${encodeURIComponent(pendingInvite)}`);
				return;
			}

			goto('/dashboard');
		} catch (err) {
			error = err instanceof Error ? err.message : 'Login failed';
		} finally {
			loading = false;
		}
	}
</script>

<div class="auth-page">
	<h1>{$t('auth.login_title')}</h1>
	<p class="subtitle">{$t('auth.login_community')}</p>

	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}

	<form onsubmit={handleSubmit}>
		<label>
			<span>{$t('auth.email')}</span>
			<input type="email" bind:value={email} required autocomplete="email" />
		</label>
		<label>
			<span>{$t('auth.password')}</span>
			<input type="password" bind:value={password} required autocomplete="current-password" />
		</label>
		<button type="submit" disabled={loading}>
			{loading ? $t('auth.logging_in') : $t('auth.login_btn')}
		</button>
	</form>

	<p class="forgot"><a href="/forgot-password">{$t('auth.forgot_password')}</a></p>

	<p class="switch">{$t('auth.no_account')} <a href="/register">{$t('nav.signup')}</a></p>
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

	label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	label span {
		font-size: 0.85rem;
		font-weight: 500;
	}

	input {
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
		color: var(--color-on-primary);
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

	.forgot {
		text-align: center;
		margin-top: 0.75rem;
		font-size: 0.9rem;
	}

	.forgot a {
		display: inline-flex;
		align-items: center;
		min-height: var(--tap-target);
		padding-inline: 0.5rem;
	}

	.switch {
		text-align: center;
		margin-top: 0.5rem;
		font-size: 0.9rem;
		color: var(--color-text-muted);
	}
</style>
