<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isLoggedIn, user } from '$lib/stores/auth';
	import { api } from '$lib/api';
	import type { Webhook } from '$lib/types';
	import { t } from 'svelte-i18n';

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
			telegramState.error = err instanceof Error ? err.message : 'Telegram not configured on this instance';
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
			telegramState.success = 'Telegram unlinked.';
			setTimeout(() => { telegramState.success = ''; }, 3000);
		} catch (err) {
			telegramState.error = err instanceof Error ? err.message : 'Failed to unlink';
		} finally {
			telegramState.unlinking = false;
		}
	}

	async function addWebhook(e: Event) {
		e.preventDefault();
		webhookForm.error = '';
		if (!webhookForm.url || !webhookForm.secret || webhookForm.event_types.length === 0) {
			webhookForm.error = 'URL, secret, and at least one event type are required';
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
			webhookForm.error = err instanceof Error ? err.message : 'Failed to add webhook';
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

	async function handlePasswordChange(e: Event) {
		e.preventDefault();
		passwordForm.error = '';
		passwordForm.success = false;

		if (!passwordForm.current_password || !passwordForm.new_password) {
			passwordForm.error = 'All fields are required';
			return;
		}

		if (passwordForm.new_password !== passwordForm.confirm_password) {
			passwordForm.error = 'New passwords do not match';
			return;
		}

		if (passwordForm.new_password === passwordForm.current_password) {
			passwordForm.error = 'New password must be different from current password';
			return;
		}

		passwordForm.loading = true;

		try {
			await api('/users/me/change-password', {
				method: 'POST',
				body: {
					current_password: passwordForm.current_password,
					new_password: passwordForm.new_password
				},
				auth: true
			});

			passwordForm.success = true;
			passwordForm.current_password = '';
			passwordForm.new_password = '';
			passwordForm.confirm_password = '';

			setTimeout(() => {
				passwordForm.success = false;
			}, 3000);
		} catch (err) {
			passwordForm.error = err instanceof Error ? err.message : 'Failed to change password';
		} finally {
			passwordForm.loading = false;
		}
	}

	async function handleEmailChange(e: Event) {
		e.preventDefault();
		emailForm.error = '';
		emailForm.success = false;

		if (!emailForm.new_email || !emailForm.password) {
			emailForm.error = 'Email and password are required';
			return;
		}

		if (emailForm.new_email === $user?.email) {
			emailForm.error = 'New email must be different from current email';
			return;
		}

		emailForm.loading = true;

		try {
			const updatedUser = await api('/users/me/change-email', {
				method: 'POST',
				body: {
					new_email: emailForm.new_email,
					password: emailForm.password
				},
				auth: true
			});

			user.set(updatedUser);
			emailForm.success = true;
			emailForm.new_email = '';
			emailForm.password = '';

			setTimeout(() => {
				emailForm.success = false;
			}, 3000);
		} catch (err) {
			emailForm.error = err instanceof Error ? err.message : 'Failed to change email';
		} finally {
			emailForm.loading = false;
		}
	}
</script>

<svelte:head>
	<title>Settings - NeighbourGood</title>
</svelte:head>

<div class="settings-page">
	<h1>{$t('settings.title')}</h1>

	<div class="settings-section">
		<h2>{$t('settings.account_info')}</h2>
		<div class="info-group">
			<label>{$t('settings.display_name')}</label>
			<p class="info-value">{$user?.display_name}</p>
		</div>

		<div class="info-group">
			<label>{$t('settings.email')}</label>
			<p class="info-value">{$user?.email}</p>
		</div>

		<div class="info-group">
			<label>{$t('settings.neighbourhood')}</label>
			<p class="info-value">{$user?.neighbourhood || $t('common.not_set')}</p>
			<p class="info-hint"><a href="/communities">{$t('settings.manage_communities')}</a></p>
		</div>

		<div class="info-group">
			<label>{$t('settings.member_since')}</label>
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

		<form class="form" onsubmit={handlePasswordChange}>
			<div class="form-group">
				<label for="current-password">{$t('settings.current_password')}</label>
				<input
					id="current-password"
					type="password"
					bind:value={passwordForm.current_password}
					required
					disabled={passwordForm.loading}
				/>
			</div>

			<div class="form-group">
				<label for="new-password">{$t('settings.new_password')}</label>
				<input
					id="new-password"
					type="password"
					bind:value={passwordForm.new_password}
					required
					disabled={passwordForm.loading}
					placeholder="Min 8 chars, 1 uppercase, 1 lowercase, 1 digit"
				/>
			</div>

			<div class="form-group">
				<label for="confirm-password">{$t('settings.confirm_password')}</label>
				<input
					id="confirm-password"
					type="password"
					bind:value={passwordForm.confirm_password}
					required
					disabled={passwordForm.loading}
				/>
			</div>

			<button type="submit" class="btn btn-primary" disabled={passwordForm.loading}>
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

		<form class="form" onsubmit={handleEmailChange}>
			<div class="form-group">
				<label for="new-email">{$t('settings.new_email')}</label>
				<input
					id="new-email"
					type="email"
					bind:value={emailForm.new_email}
					required
					disabled={emailForm.loading}
				/>
			</div>

			<div class="form-group">
				<label for="email-password">{$t('settings.password_confirm_label')}</label>
				<input
					id="email-password"
					type="password"
					bind:value={emailForm.password}
					required
					disabled={emailForm.loading}
				/>
			</div>

			<button type="submit" class="btn btn-primary" disabled={emailForm.loading}>
				{emailForm.loading ? $t('settings.changing') : $t('settings.change_email')}
			</button>
		</form>
	</div>

	<hr class="section-divider" />

	<div class="settings-section">
		<h2>{$t('settings.telegram')}</h2>
		<p class="section-desc">
			Link your Telegram account to receive instant alerts for messages, bookings, and community events.
		</p>

		{#if telegramState.success}
			<div class="alert alert-success">{telegramState.success}</div>
		{:else if telegramState.error}
			<div class="alert alert-error">{telegramState.error}</div>
		{/if}

		{#if ($user as any)?.telegram_chat_id}
			<div class="telegram-linked">
				<span class="linked-badge">{$t('settings.telegram_linked')}</span>
				<button
					class="btn btn-danger"
					onclick={unlinkTelegram}
					disabled={telegramState.unlinking}
				>
					{telegramState.unlinking ? $t('settings.changing') : $t('settings.telegram_unlink')}
				</button>
			</div>
		{:else if telegramState.botUrl}
			<div class="telegram-link-step">
				<p>Open the link below in Telegram and press Start:</p>
				<a href={telegramState.botUrl} target="_blank" rel="noopener" class="btn btn-telegram">
					Open in Telegram
				</a>
				<p class="info-hint">After pressing Start in Telegram, reload this page to confirm the link.</p>
			</div>
		{:else}
			<button
				class="btn btn-telegram"
				onclick={startTelegramLink}
				disabled={telegramState.loading}
			>
				{telegramState.loading ? $t('settings.changing') : $t('settings.telegram_link')}
			</button>
		{/if}
	</div>

	<hr class="section-divider" />

	<div class="settings-section">
		<h2>{$t('settings.webhooks')}</h2>
		<p class="section-desc">
			Register URLs to receive signed HTTP POST callbacks when events happen — for Slack, Discord, or any custom integration.
		</p>

		{#if webhooks.length > 0}
			<div class="webhook-list">
				{#each webhooks as wh}
					<div class="webhook-row">
						<div class="webhook-info">
							<span class="webhook-url">{wh.url}</span>
							<span class="webhook-events">{wh.event_types.join(', ')}</span>
						</div>
						<button class="btn-icon-danger" onclick={() => deleteWebhook(wh.id)} title="Delete webhook">
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg>
						</button>
					</div>
				{/each}
			</div>
		{/if}

		<form class="form webhook-form" onsubmit={addWebhook}>
			{#if webhookForm.error}
				<div class="alert alert-error">{webhookForm.error}</div>
			{/if}
			<div class="form-group">
				<label for="webhook-url">{$t('settings.webhook_url')}</label>
				<input id="webhook-url" type="url" bind:value={webhookForm.url} placeholder="https://..." required disabled={webhookForm.loading} />
			</div>
			<div class="form-group">
				<label for="webhook-secret">{$t('settings.webhook_secret')}</label>
				<input id="webhook-secret" type="text" bind:value={webhookForm.secret} placeholder="Min 8 characters" required disabled={webhookForm.loading} />
				<span class="form-hint">Used to generate the X-NeighbourGood-Signature header so you can verify deliveries.</span>
			</div>
			<div class="form-group">
				<label>{$t('settings.webhook_events')}</label>
				<div class="event-grid">
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
</div>

<style>
	.settings-page {
		max-width: 600px;
	}

	h1 {
		font-size: 1.9rem;
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

	.info-group label {
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

	.form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.form-group {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.form-group label {
		font-size: 0.9rem;
		font-weight: 600;
		color: var(--color-text);
	}

	.form-group input {
		padding: 0.75rem 1rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		font-size: 0.95rem;
		background: var(--color-surface);
		color: var(--color-text);
		transition: border-color var(--transition-fast);
	}

	.form-group input:focus {
		outline: none;
		border-color: var(--color-primary);
		box-shadow: 0 0 0 2px var(--color-primary-light);
	}

	.form-group input:disabled {
		background: var(--color-border);
		cursor: not-allowed;
		opacity: 0.6;
	}

	.btn {
		padding: 0.75rem 1.5rem;
		border: none;
		border-radius: var(--radius-sm);
		font-size: 0.95rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.btn-primary {
		background: var(--color-primary);
		color: white;
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--color-primary-hover);
		box-shadow: var(--shadow-md);
		transform: translateY(-2px);
	}

	.btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.alert {
		padding: 1rem;
		border-radius: var(--radius-sm);
		margin-bottom: 1rem;
		font-size: 0.95rem;
	}

	.alert-success {
		background-color: rgba(34, 197, 94, 0.1);
		border: 1px solid rgba(34, 197, 94, 0.3);
		color: var(--color-success);
	}

	.alert-error {
		background-color: rgba(239, 68, 68, 0.1);
		border: 1px solid rgba(239, 68, 68, 0.3);
		color: var(--color-error);
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

	.linked-badge {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.35rem 0.75rem;
		background: rgba(34, 197, 94, 0.1);
		border: 1px solid rgba(34, 197, 94, 0.3);
		border-radius: var(--radius-sm);
		color: var(--color-success);
		font-size: 0.85rem;
		font-weight: 600;
	}

	.telegram-link-step {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.btn-telegram {
		background: #0088cc;
		color: white;
		border: none;
		border-radius: var(--radius-sm);
		padding: 0.7rem 1.4rem;
		font-size: 0.95rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
		text-decoration: none;
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		width: fit-content;
	}

	.btn-telegram:hover:not(:disabled) {
		background: #006fa8;
		box-shadow: var(--shadow-md);
		text-decoration: none;
	}

	.btn-telegram:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-danger {
		background: none;
		border: 1px solid var(--color-error);
		color: var(--color-error);
		border-radius: var(--radius-sm);
		padding: 0.4rem 0.9rem;
		font-size: 0.85rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.btn-danger:hover:not(:disabled) {
		background: var(--color-error);
		color: white;
	}

	.btn-danger:disabled {
		opacity: 0.6;
		cursor: not-allowed;
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
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
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
		background: none;
		border: none;
		color: var(--color-text-muted);
		cursor: pointer;
		padding: 0.3rem;
		border-radius: var(--radius-sm);
		transition: all var(--transition-fast);
		flex-shrink: 0;
	}

	.btn-icon-danger:hover {
		color: var(--color-error);
		background: var(--color-error-bg, rgba(239, 68, 68, 0.1));
	}

	.webhook-form {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		padding: 1.25rem;
		background: var(--color-surface);
	}

	.form-hint {
		font-size: 0.8rem;
		color: var(--color-text-muted);
		margin-top: 0.25rem;
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

	@media (max-width: 600px) {
		h1 {
			font-size: 1.5rem;
		}

		.event-grid {
			grid-template-columns: 1fr 1fr;
		}
	}
</style>
