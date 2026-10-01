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
			error = err instanceof Error ? err.message : $t('auth.register_failed');
		} finally {
			loading = false;
		}
	}
</script>

<div class="card auth-card">
	<h1>{$t('auth.register_title')}</h1>
	<p class="subtitle">{$t('auth.register_community')}</p>

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
			<input type="password" bind:value={password} required minlength="8" autocomplete="new-password" aria-describedby="pw-hint" />
			<small id="pw-hint" class="field-hint">{$t('auth.password_hint')}</small>
		</label>
		<label class="field">
			<span>{$t('auth.display_name')}</span>
			<input type="text" bind:value={displayName} required autocomplete="name" />
		</label>
		<label class="field">
			<span>{$t('auth.neighbourhood')}</span>
			<input type="text" bind:value={neighbourhood} placeholder={$t('auth.neighbourhood_placeholder')} />
		</label>
		<button type="submit" class="btn btn-primary btn-block" class:is-loading={loading} disabled={loading}>
			{loading ? $t('auth.creating_account') : $t('auth.register_btn')}
		</button>
	</form>

	<p class="auth-switch">{$t('auth.have_account')} <a href="/login">{$t('auth.login_btn')}</a></p>
</div>
