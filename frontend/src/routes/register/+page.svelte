<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { token, user } from '$lib/stores/auth';
	import type { UserProfile } from '$lib/stores/auth';
	import { currentLocale } from '$lib/stores/locale';
	import { get } from 'svelte/store';
	import { t } from 'svelte-i18n';

	let email = $state('');
	let password = $state('');
	let displayName = $state('');
	let neighbourhood = $state('');
	let error = $state('');
	let loading = $state(false);

	async function handleSubmit(e: Event) {
		e.preventDefault();
		error = '';
		loading = true;

		try {
			const res = await api<{ access_token: string }>('/auth/register', {
				method: 'POST',
				body: {
					email,
					password,
					display_name: displayName,
					neighbourhood: neighbourhood || null,
					language_code: get(currentLocale)
				}
			});
			token.set(res.access_token);

			const profile = await api<UserProfile>('/users/me', { auth: true });
			user.set(profile);

			// Resume an invite the visitor opened before signing up
			const pendingInvite = sessionStorage.getItem('ng_pending_invite');
			if (pendingInvite) {
				sessionStorage.removeItem('ng_pending_invite');
				goto(`/invites/${encodeURIComponent(pendingInvite)}`);
				return;
			}

			goto('/onboarding');
		} catch (err) {
			error = err instanceof Error ? err.message : 'Registration failed';
		} finally {
			loading = false;
		}
	}
</script>

<div class="auth-page">
	<h1>{$t('auth.register_title')}</h1>
	<p class="subtitle">{$t('auth.register_community')}</p>

	{#if error}
		<p class="error">{error}</p>
	{/if}

	<form onsubmit={handleSubmit}>
		<label>
			<span>{$t('auth.email')}</span>
			<input type="email" bind:value={email} required />
		</label>
		<label>
			<span>{$t('auth.password')}</span>
			<input type="password" bind:value={password} required minlength="8" />
		</label>
		<label>
			<span>{$t('auth.display_name')}</span>
			<input type="text" bind:value={displayName} required />
		</label>
		<label>
			<span>{$t('auth.neighbourhood')}</span>
			<input type="text" bind:value={neighbourhood} placeholder="e.g. Kreuzberg, Friedrichshain" />
		</label>
		<button type="submit" disabled={loading}>
			{loading ? $t('auth.creating_account') : $t('auth.register_btn')}
		</button>
	</form>

	<p class="switch">{$t('auth.have_account')} <a href="/login">{$t('auth.login_btn')}</a></p>
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

	.switch {
		text-align: center;
		margin-top: 1.5rem;
		font-size: 0.9rem;
		color: var(--color-text-muted);
	}
</style>
