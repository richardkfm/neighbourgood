<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isLoggedIn, token, user, logout, type UserProfile } from '$lib/stores/auth';
	import { api } from '$lib/api';
	import type { Webhook } from '$lib/types';
	import { meshEnabled } from '$lib/stores/mesh-settings';
	import { t } from 'svelte-i18n';
	import Icon from '$lib/components/Icon.svelte';

	let passwordForm = $state({
		current_password: '',
		new_password: '',
		confirm_password: '',
		error: '',
		success: false,
		loading: false
	});

	let emailForm = $state({
		new_email: '',
		password: '',
		error: '',
		success: false,
		loading: false
	});

	let telegramState = $state({
		botUrl: '',
		loading: false,
		unlinking: false,
		error: '',
		success: ''
	});

	let webhooks = $state<Webhook[]>([]);
	let webhookForm = $state({
		url: '',
		secret: '',
		event_types: [] as string[],
		error: '',
		loading: false
	});

	let exportState = $state({ loading: false, error: '', success: false });

	let deleteForm = $state({
		confirming: false,
		password: '',
		error: '',
		loading: false
	});

	const ALL_EVENTS = [
		'message.new', 'booking.created', 'booking.status_changed',
		'crisis.mode_changed', 'ticket.created', 'ticket.assigned',
		'resource.shared', 'skill.created', 'member.joined'
	];

	onMount(async () => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}
		// Reload profile to get fresh telegram_chat_id
		try {
			const profile = await api('/users/me', { auth: true });
			user.set(profile as any);
		} catch {
			// Ignore – stale data fine
		}
		// Load webhooks
		try {
			webhooks = await api<Webhook[]>('/webhooks', { auth: true });
		} catch {
			// Leave empty
		}
	});

	async function startTelegramLink() {
		telegramState.loading = true;
		telegramState.error = '';
		telegramState.botUrl = '';
		try {
			const data = await api<{ bot_url: string }>('/users/me/telegram/start-link', {
				method: 'POST',
				auth: true
			});
			telegramState.botUrl = data.bot_url;
		} catch (err) {
			telegramState.error = err instanceof Error ? err.message : $t('settings.telegram_not_configured');
		} finally {
			telegramState.loading = false;
		}
	}

	async function unlinkTelegram() {
		telegramState.unlinking = true;
		telegramState.error = '';
		try {
			await api('/users/me/telegram', { method: 'DELETE', auth: true });
			user.update(u => u ? { ...u, telegram_chat_id: null } : u);
			telegramState.success = $t('settings.telegram_unlinked');
			setTimeout(() => { telegramState.success = ''; }, 3000);
		} catch (err) {
			telegramState.error = err instanceof Error ? err.message : $t('settings.telegram_unlink_failed');
		} finally {
			telegramState.unlinking = false;
		}
	}

	async function addWebhook(e: Event) {
		e.preventDefault();
		webhookForm.error = '';
		if (!webhookForm.url || !webhookForm.secret || webhookForm.event_types.length === 0) {
			webhookForm.error = $t('settings.webhook_required');
			return;
		}
		webhookForm.loading = true;
		try {
			const created = await api<Webhook>('/webhooks', {
				method: 'POST',
				body: {
					url: webhookForm.url,
					secret: webhookForm.secret,
					event_types: webhookForm.event_types
				},
				auth: true
			});
			webhooks = [created, ...webhooks];
			webhookForm.url = '';
			webhookForm.secret = '';
			webhookForm.event_types = [];
		} catch (err) {
			webhookForm.error = err instanceof Error ? err.message : $t('settings.webhook_add_failed');
		} finally {
			webhookForm.loading = false;
		}
	}

	async function deleteWebhook(id: number) {
		try {
			await api(`/webhooks/${id}`, { method: 'DELETE', auth: true });
			webhooks = webhooks.filter(w => w.id !== id);
		} catch {
			// Ignore
		}
	}

	function toggleEvent(event: string) {
		if (webhookForm.event_types.includes(event)) {
			webhookForm.event_types = webhookForm.event_types.filter(e => e !== event);
		} else {
			webhookForm.event_types = [...webhookForm.event_types, event];
		}
	}

	async function downloadMyData() {
		exportState.loading = true;
		exportState.error = '';
		exportState.success = false;
		try {
			const data = await api<unknown>('/federation/export/my-data', { auth: true });
			const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
			const url = URL.createObjectURL(blob);
			const link = document.createElement('a');
			link.href = url;
			link.download = `neighbourgood-data-${new Date().toISOString().slice(0, 10)}.json`;
			document.body.appendChild(link);
			link.click();
			link.remove();
			URL.revokeObjectURL(url);
			exportState.success = true;
		} catch (err) {
			exportState.error = err instanceof Error ? err.message : $t('settings.export_failed');
		} finally {
			exportState.loading = false;
		}
	}

	function beginDelete() {
		deleteForm.confirming = true;
		deleteForm.error = '';
		deleteForm.password = '';
	}

	function cancelDelete() {
		deleteForm.confirming = false;
		deleteForm.error = '';
		deleteForm.password = '';
	}

	async function handleDeleteAccount(e: Event) {
		e.preventDefault();
		if (!deleteForm.password) return;
		deleteForm.error = '';
		deleteForm.loading = true;
		try {
			// A wrong password comes back as a 400, so the session stays intact.
			await api('/users/me', {
				method: 'DELETE',
				body: { password: deleteForm.password },
				auth: true
			});
			// Also wipes this device's offline crisis data (mesh queue, triage store)
			await logout();
			await goto('/');
		} catch (err) {
			deleteForm.error = err instanceof Error ? err.message : $t('settings.delete_failed');
			deleteForm.loading = false;
		}
	}

	async function handlePasswordChange(e: Event) {
		e.preventDefault();
		passwordForm.error = '';
		passwordForm.success = false;

		if (!passwordForm.current_password || !passwordForm.new_password) {
			passwordForm.error = $t('settings.all_fields_required');
			return;
		}

		if (passwordForm.new_password !== passwordForm.confirm_password) {
			passwordForm.error = $t('settings.passwords_mismatch');
			return;
		}

		if (passwordForm.new_password === passwordForm.current_password) {
			passwordForm.error = $t('settings.password_same');
			return;
		}

		passwordForm.loading = true;

		try {
			// Changing the password signs out all other sessions; keep this one alive.
			const changed = await api<{ access_token: string }>('/users/me/change-password', {
				method: 'POST',
				body: {
					current_password: passwordForm.current_password,
					new_password: passwordForm.new_password
				},
				auth: true
			});
			token.set(changed.access_token);

			passwordForm.success = true;
			passwordForm.current_password = '';
			passwordForm.new_password = '';
			passwordForm.confirm_password = '';

			setTimeout(() => {
				passwordForm.success = false;
			}, 3000);
		} catch (err) {
			passwordForm.error = err instanceof Error ? err.message : $t('settings.password_change_failed');
		} finally {
			passwordForm.loading = false;
		}
	}

	async function handleEmailChange(e: Event) {
		e.preventDefault();
		emailForm.error = '';
		emailForm.success = false;

		if (!emailForm.new_email || !emailForm.password) {
			emailForm.error = $t('settings.email_password_required');
			return;
		}

		if (emailForm.new_email === $user?.email) {
			emailForm.error = $t('settings.email_same');
			return;
		}

		emailForm.loading = true;

		try {
			const updatedUser = await api<UserProfile & { access_token: string }>('/users/me/change-email', {
				method: 'POST',
				body: {
					new_email: emailForm.new_email,
					password: emailForm.password
				},
				auth: true
			});

			token.set(updatedUser.access_token);
			user.set(updatedUser);
			emailForm.success = true;
			emailForm.new_email = '';
			emailForm.password = '';

			setTimeout(() => {
				emailForm.success = false;
			}, 3000);
		} catch (err) {
			emailForm.error = err instanceof Error ? err.message : $t('settings.email_change_failed');
		} finally {
			emailForm.loading = false;
		}
	}
</script>

<svelte:head>
	<title>{$t('nav.settings')} - NeighbourGood</title>
</svelte:head>

<div class="settings-page">
	<h1>{$t('settings.title')}</h1>

	<div class="settings-section">
		<h2>{$t('settings.account_info')}</h2>
		<div class="info-group">
			<span class="info-label">{$t('settings.display_name')}</span>
			<p class="info-value">{$user?.display_name}</p>
		</div>

		<div class="info-group">
			<span class="info-label">{$t('settings.email')}</span>
			<p class="info-value">{$user?.email}</p>
		</div>

		<div class="info-group">
			<span class="info-label">{$t('settings.neighbourhood')}</span>
			<p class="info-value">{$user?.neighbourhood || $t('common.not_set')}</p>
			<p class="info-hint"><a href="/communities">{$t('settings.manage_communities')}</a></p>
		</div>

		<div class="info-group">
			<span class="info-label">{$t('settings.member_since')}</span>
			<p class="info-value">{new Date($user?.created_at || '').toLocaleDateString()}</p>
		</div>
	</div>

	<hr class="section-divider" />

	<div class="settings-section">
		<h2>{$t('settings.change_password')}</h2>

		{#if passwordForm.success}
			<div class="alert alert-success">{$t('settings.password_changed')}</div>
		{:else if passwordForm.error}
			<div class="alert alert-error">{passwordForm.error}</div>
		{/if}

		<form class="form-stack" onsubmit={handlePasswordChange}>
			<div class="field">
				<label for="current-password">{$t('settings.current_password')}</label>
				<input
					id="current-password"
					type="password"
					bind:value={passwordForm.current_password}
					required
					disabled={passwordForm.loading}
				/>
			</div>

			<div class="field">
				<label for="new-password">{$t('settings.new_password')}</label>
				<input
					id="new-password"
					type="password"
					bind:value={passwordForm.new_password}
					required
					disabled={passwordForm.loading}
					placeholder={$t('settings.password_placeholder')}
				/>
			</div>

			<div class="field">
				<label for="confirm-password">{$t('settings.confirm_password')}</label>
				<input
					id="confirm-password"
					type="password"
					bind:value={passwordForm.confirm_password}
					required
					disabled={passwordForm.loading}
				/>
			</div>

			<button type="submit" class="btn btn-primary" class:is-loading={passwordForm.loading} disabled={passwordForm.loading}>
				{passwordForm.loading ? $t('settings.changing') : $t('settings.change_password')}
			</button>
		</form>
	</div>

	<hr class="section-divider" />

	<div class="settings-section">
		<h2>{$t('settings.change_email')}</h2>

		{#if emailForm.success}
			<div class="alert alert-success">{$t('settings.email_changed')}</div>
		{:else if emailForm.error}
			<div class="alert alert-error">{emailForm.error}</div>
		{/if}

		<form class="form-stack" onsubmit={handleEmailChange}>
			<div class="field">
				<label for="new-email">{$t('settings.new_email')}</label>
				<input
					id="new-email"
					type="email"
					bind:value={emailForm.new_email}
					required
					disabled={emailForm.loading}
				/>
			</div>

			<div class="field">
				<label for="email-password">{$t('settings.password_confirm_label')}</label>
				<input
					id="email-password"
					type="password"
					bind:value={emailForm.password}
					required
					disabled={emailForm.loading}
				/>
			</div>

			<button type="submit" class="btn btn-primary" class:is-loading={emailForm.loading} disabled={emailForm.loading}>
				{emailForm.loading ? $t('settings.changing') : $t('settings.change_email')}
			</button>
		</form>
	</div>

	<hr class="section-divider" />

	<div class="settings-section">
		<h2>{$t('settings.telegram')}</h2>
		<p class="section-desc">
			{$t('settings.telegram_desc')}
		</p>

		{#if telegramState.success}
			<div class="alert alert-success">{telegramState.success}</div>
		{:else if telegramState.error}
			<div class="alert alert-error">{telegramState.error}</div>
		{/if}

		{#if ($user as any)?.telegram_chat_id}
			<div class="telegram-linked">
				<span class="badge badge-success"><Icon name="check" size={13} />{$t('settings.telegram_linked')}</span>
				<button
					class="btn btn-danger-outline"
					class:is-loading={telegramState.unlinking}
					onclick={unlinkTelegram}
					disabled={telegramState.unlinking}
				>
					{telegramState.unlinking ? $t('settings.changing') : $t('settings.telegram_unlink')}
				</button>
			</div>
		{:else if telegramState.botUrl}
			<div class="telegram-link-step">
				<p>{$t('settings.telegram_open_hint')}</p>
				<a href={telegramState.botUrl} target="_blank" rel="noopener" class="btn btn-primary">
					{$t('settings.telegram_open')}
				</a>
				<p class="info-hint">{$t('settings.telegram_reload_hint')}</p>
			</div>
		{:else}
			<button
				class="btn btn-primary"
				onclick={startTelegramLink}
				disabled={telegramState.loading}
			>
				{telegramState.loading ? $t('settings.changing') : $t('settings.telegram_link')}
			</button>
		{/if}
	</div>

	<hr class="section-divider" />

	<div class="settings-section">
		<h2>{$t('settings.mesh_networking')}</h2>
		<p class="section-desc">{$t('settings.mesh_desc')}</p>

		<label class="toggle-row">
			<input type="checkbox" bind:checked={$meshEnabled} class="toggle-checkbox" />
			<span class="toggle-label">{$t('settings.mesh_enable')}</span>
		</label>
		{#if $meshEnabled}
			<p class="info-hint">
				<a href="/mesh">{$t('settings.mesh_open_dashboard')}</a>
			</p>
		{/if}
	</div>

	<hr class="section-divider" />

	<div class="settings-section">
		<h2>{$t('settings.webhooks')}</h2>
		<p class="section-desc">
			{$t('settings.webhooks_desc')}
		</p>

		{#if webhooks.length > 0}
			<div class="webhook-list">
				{#each webhooks as wh}
					<div class="card webhook-row">
						<div class="webhook-info">
							<span class="webhook-url">{wh.url}</span>
							<span class="webhook-events">{wh.event_types.join(', ')}</span>
						</div>
						<button class="btn btn-ghost btn-sm btn-icon-danger" onclick={() => deleteWebhook(wh.id)} title={$t('settings.webhook_delete')} aria-label={$t('settings.webhook_delete')}>
							<Icon name="trash" size={16} />
						</button>
					</div>
				{/each}
			</div>
		{/if}

		<form class="card form-stack webhook-form" onsubmit={addWebhook}>
			{#if webhookForm.error}
				<div class="alert alert-error">{webhookForm.error}</div>
			{/if}
			<div class="field">
				<label for="webhook-url">{$t('settings.webhook_url')}</label>
				<input id="webhook-url" type="url" bind:value={webhookForm.url} placeholder="https://..." required disabled={webhookForm.loading} />
			</div>
			<div class="field">
				<label for="webhook-secret">{$t('settings.webhook_secret')}</label>
				<input id="webhook-secret" type="text" bind:value={webhookForm.secret} placeholder={$t('settings.webhook_secret_placeholder')} required disabled={webhookForm.loading} />
				<span class="field-hint">{$t('settings.webhook_secret_hint')}</span>
			</div>
			<div class="field">
				<span class="field-label" id="webhook-events-label">{$t('settings.webhook_events')}</span>
				<div class="event-grid" role="group" aria-labelledby="webhook-events-label">
					{#each ALL_EVENTS as evt}
						<label class="event-checkbox">
							<input
								type="checkbox"
								checked={webhookForm.event_types.includes(evt)}
								onchange={() => toggleEvent(evt)}
								disabled={webhookForm.loading}
							/>
							{evt}
						</label>
					{/each}
				</div>
			</div>
			<button type="submit" class="btn btn-primary" disabled={webhookForm.loading || webhookForm.event_types.length === 0}>
				{webhookForm.loading ? $t('settings.adding') : $t('settings.add_webhook')}
			</button>
		</form>
	</div>

	<hr class="section-divider" />

	<div class="settings-section">
		<h2>{$t('settings.export_title')}</h2>
		<p class="section-desc">{$t('settings.export_desc')}</p>

		{#if exportState.error}
			<div class="alert alert-error" role="alert">{exportState.error}</div>
		{:else if exportState.success}
			<div class="alert alert-success" role="status">{$t('settings.export_done')}</div>
		{/if}

		<button
			type="button"
			class="btn btn-secondary"
			class:is-loading={exportState.loading}
			onclick={downloadMyData}
			disabled={exportState.loading}
		>
			{#if !exportState.loading}<Icon name="download" size={16} />{/if}
			{exportState.loading ? $t('settings.exporting') : $t('settings.export_btn')}
		</button>
	</div>

	<hr class="section-divider" />

	<div class="card settings-section danger-zone" aria-labelledby="danger-zone-heading">
		<h2 id="danger-zone-heading">{$t('settings.danger_zone')}</h2>
		<h3 class="danger-title">{$t('settings.delete_title')}</h3>
		<p class="section-desc">{$t('settings.delete_desc')}</p>

		<p class="consequences-title">{$t('settings.delete_consequences_title')}</p>
		<ul class="consequences">
			<li>{$t('settings.delete_consequence_listings')}</li>
			<li>{$t('settings.delete_consequence_bookings')}</li>
			<li>{$t('settings.delete_consequence_communities')}</li>
			<li>{$t('settings.delete_consequence_kept')}</li>
		</ul>

		{#if deleteForm.confirming}
			<form class="form-stack delete-confirm" onsubmit={handleDeleteAccount}>
				<h3 class="danger-title">{$t('settings.delete_confirm_heading')}</h3>
				<p class="section-desc">{$t('settings.delete_confirm_hint')}</p>

				{#if deleteForm.error}
					<div class="alert alert-error" role="alert">{deleteForm.error}</div>
				{/if}

				<div class="field">
					<label for="delete-password">{$t('settings.delete_password_label')}</label>
					<input
						id="delete-password"
						type="password"
						bind:value={deleteForm.password}
						required
						maxlength="128"
						autocomplete="current-password"
						disabled={deleteForm.loading}
					/>
				</div>

				<div class="delete-actions">
					<button
						type="submit"
						class="btn btn-danger"
						class:is-loading={deleteForm.loading}
						disabled={deleteForm.loading || !deleteForm.password}
					>
						{deleteForm.loading ? $t('settings.deleting') : $t('settings.delete_confirm_btn')}
					</button>
					<button
						type="button"
						class="btn btn-secondary"
						onclick={cancelDelete}
						disabled={deleteForm.loading}
					>
						{$t('common.cancel')}
					</button>
				</div>
			</form>
		{:else}
			<button type="button" class="btn btn-danger-outline" onclick={beginDelete}>
				<Icon name="trash" size={16} />
				{$t('settings.delete_begin')}
			</button>
		{/if}
	</div>
</div>

<style>
	.settings-page {
		max-width: 600px;
	}

	h1 {
		font-size: 2.1rem;
		font-weight: 400;
		color: var(--color-text);
		margin: 0 0 2rem 0;
	}

	h2 {
		font-size: 1.25rem;
		font-weight: 500;
		color: var(--color-text);
		margin: 1.5rem 0 1rem 0;
	}

	.settings-section {
		margin-bottom: 1rem;
	}

	.info-group {
		margin-bottom: 1.5rem;
		padding-bottom: 1.5rem;
		border-bottom: 1px solid var(--color-border);
	}

	.info-group:last-child {
		border-bottom: none;
		padding-bottom: 0;
		margin-bottom: 0;
	}

	.info-label {
		display: block;
		font-size: 0.85rem;
		font-weight: 600;
		color: var(--color-text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 0.5rem;
	}

	.info-value {
		font-size: 1rem;
		color: var(--color-text);
		margin: 0;
		word-break: break-all;
	}

	.info-hint {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		margin: 0.5rem 0 0 0;
		font-style: italic;
	}

	.section-divider {
		border: none;
		border-top: 1px solid var(--color-border);
		margin: 2rem 0;
	}

	.danger-zone {
		border-color: var(--color-error);
		padding: 0 1.25rem 1.25rem;
	}

	.danger-zone h2 {
		color: var(--color-error);
	}

	.danger-title {
		font-size: 1rem;
		font-weight: 600;
		margin: 0 0 0.5rem 0;
		color: var(--color-text);
	}

	.consequences-title {
		font-size: 0.85rem;
		font-weight: 600;
		margin: 0 0 0.25rem 0;
		color: var(--color-text-muted);
	}

	.consequences {
		margin: 0 0 1.25rem 0;
		padding-inline-start: 1.25rem;
		font-size: 0.9rem;
		color: var(--color-text-muted);
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.delete-confirm {
		border-top: 1px solid var(--color-border);
		padding-top: 1.25rem;
	}

	.delete-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	.section-desc {
		font-size: 0.9rem;
		color: var(--color-text-muted);
		margin: 0 0 1rem 0;
	}

	.telegram-linked {
		display: flex;
		align-items: center;
		gap: 1rem;
	}

	.telegram-link-step {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.webhook-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin-bottom: 1.5rem;
	}

	.webhook-row {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.75rem 1rem;
	}

	.webhook-info {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		min-width: 0;
	}

	.webhook-url {
		font-size: 0.9rem;
		font-weight: 500;
		color: var(--color-text);
		word-break: break-all;
	}

	.webhook-events {
		font-size: 0.78rem;
		color: var(--color-text-muted);
	}

	.btn-icon-danger {
		flex-shrink: 0;
		color: var(--color-text-muted);
	}

	.btn-icon-danger:hover:not(:disabled) {
		color: var(--color-error);
		background: var(--color-error-bg);
	}

	.webhook-form {
		padding: 1.25rem;
	}

	.event-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: 0.5rem;
		padding: 0.75rem;
		background: var(--color-bg);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
	}

	.event-checkbox {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.83rem;
		color: var(--color-text);
		cursor: pointer;
	}

	.event-checkbox input[type="checkbox"] {
		width: 14px;
		height: 14px;
		cursor: pointer;
	}

	.toggle-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		cursor: pointer;
	}

	.toggle-checkbox {
		width: 18px;
		height: 18px;
		cursor: pointer;
		accent-color: var(--color-primary);
	}

	.toggle-label {
		font-size: 0.95rem;
		color: var(--color-text);
	}

	@media (max-width: 600px) {
		h1 {
			font-size: 1.5rem;
		}

		.event-grid {
			grid-template-columns: minmax(0, 1fr);
		}

		.event-checkbox {
			min-height: var(--tap-target);
			overflow-wrap: anywhere;
		}

		.event-checkbox input[type="checkbox"] {
			width: 20px;
			height: 20px;
			flex-shrink: 0;
		}
	}
</style>
