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

<div class="card auth-card">
	<h1>{$t('auth.reset_title')}</h1>

	{#if done}
		<p class="alert alert-success" role="status">{$t('auth.reset_success')}</p>
		<p class="action"><a class="btn btn-primary" href="/login">{$t('auth.login_btn')}</a></p>
	{:else if !resetToken}
		<p class="alert alert-error" role="alert">{$t('auth.reset_missing_token')}</p>
		<p class="action"><a class="btn btn-primary" href="/forgot-password">{$t('auth.reset_request_new')}</a></p>
	{:else}
		<p class="subtitle">{$t('auth.reset_subtitle')}</p>

		{#if error}
			<p class="alert alert-error" role="alert">{error}</p>
		{/if}

		<form class="form-stack" onsubmit={handleSubmit}>
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
				<small id="reset-password-hint" class="field-hint">{$t('auth.password_hint')}</small>
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
			<button type="submit" class="btn btn-primary btn-block" class:is-loading={loading} disabled={loading}>
				{loading ? $t('auth.resetting') : $t('auth.reset_submit')}
			</button>
		</form>

		<p class="auth-switch"><a href="/login">{$t('auth.back_to_login')}</a></p>
	{/if}
</div>

<style>
	.action {
		margin-top: 1.25rem;
		text-align: center;
	}
</style>
