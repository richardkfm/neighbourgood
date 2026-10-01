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
			error = err instanceof Error ? err.message : $t('auth.login_failed');
		} finally {
			loading = false;
		}
	}
</script>

<div class="card auth-card">
	<h1>{$t('auth.login_title')}</h1>
	<p class="subtitle">{$t('auth.login_community')}</p>

	{#if error}
		<p class="alert alert-error" role="alert">{error}</p>
	{/if}

	<form class="form-stack" onsubmit={handleSubmit}>
		<label class="field">
			<span>{$t('auth.email')}</span>
			<input type="email" bind:value={email} required autocomplete="email" />
		</label>
		<label class="field">
			<span>{$t('auth.password')}</span>
			<input type="password" bind:value={password} required autocomplete="current-password" />
		</label>
		<button type="submit" class="btn btn-primary btn-block" class:is-loading={loading} disabled={loading}>
			{loading ? $t('auth.logging_in') : $t('auth.login_btn')}
		</button>
	</form>

	<p class="auth-switch forgot"><a href="/forgot-password">{$t('auth.forgot_password')}</a></p>

	<p class="auth-switch">{$t('auth.no_account')} <a href="/register">{$t('nav.signup')}</a></p>
</div>

<style>
	.forgot {
		margin-top: 0.75rem;
	}
</style>
