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

<div class="card auth-card">
	<h1>{$t('auth.forgot_title')}</h1>

	{#if sent}
		<p class="alert alert-success" role="status">{$t('auth.forgot_sent')}</p>
	{:else}
		<p class="subtitle">{$t('auth.forgot_subtitle')}</p>

		{#if error}
			<p class="alert alert-error" role="alert">{error}</p>
		{/if}

		<form class="form-stack" onsubmit={handleSubmit}>
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
			<button type="submit" class="btn btn-primary btn-block" class:is-loading={loading} disabled={loading}>
				{loading ? $t('auth.forgot_sending') : $t('auth.forgot_submit')}
			</button>
		</form>
	{/if}

	<p class="auth-switch"><a href="/login">{$t('auth.back_to_login')}</a></p>
</div>
