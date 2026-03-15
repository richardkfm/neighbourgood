<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { t } from 'svelte-i18n';
	import { api } from '$lib/api';
	import { isLoggedIn, user } from '$lib/stores/auth';
	import type { KnownInstance, RedSkyAlertInfo } from '$lib/types';

	let instances = $state<KnownInstance[]>([]);
	let alerts = $state<RedSkyAlertInfo[]>([]);
	let loading = $state(true);
	let addUrl = $state('');
	let addError = $state('');
	let adding = $state(false);
	let refreshing = $state(false);
	let syncMessage = $state('');

	const isAdmin = $derived($user?.role === 'admin');

	async function loadData() {
		loading = true;
		try {
			const [instData, alertData] = await Promise.all([
				api<KnownInstance[]>('/federation/directory', { auth: true }),
				api<RedSkyAlertInfo[]>('/federation/alerts?active_only=true', { auth: true })
			]);
			instances = instData;
			alerts = alertData;
		} catch {
			// Errors handled by empty state
		} finally {
			loading = false;
		}
	}

	async function addInstance() {
		if (!addUrl.trim()) return;
		adding = true;
		addError = '';
		try {
			await api<KnownInstance>('/federation/directory', {
				method: 'POST',
				body: { url: addUrl.trim() },
				auth: true
			});
			addUrl = '';
			await loadData();
		} catch (e: unknown) {
			addError = e instanceof Error ? e.message : $t('federation.add_error');
		} finally {
			adding = false;
		}
	}

	async function removeInstance(id: number) {
		try {
			await api(`/federation/directory/${id}`, { method: 'DELETE', auth: true });
			instances = instances.filter((i) => i.id !== id);
		} catch {
			// ignore
		}
	}

	async function refreshAll() {
		refreshing = true;
		try {
			instances = await api<KnownInstance[]>('/federation/directory/refresh', {
				method: 'POST',
				auth: true
			});
		} catch {
			// ignore
		} finally {
			refreshing = false;
		}
	}

	async function triggerSync() {
		syncMessage = '';
		try {
			const result = await api<{
				instances_attempted: number;
				instances_ok: number;
				total_resources_synced: number;
				total_skills_synced: number;
			}>('/federation/sync/pull', { method: 'POST', auth: true });
			syncMessage = `${$t('federation.synced')}: ${result.total_resources_synced} ${$t('federation.resources_label')}, ${result.total_skills_synced} ${$t('federation.skills_label')} (${result.instances_ok}/${result.instances_attempted} ${$t('federation.instances_ok')})`;
		} catch {
			syncMessage = $t('federation.sync_error');
		}
	}

	function modeClass(mode: string) {
		return mode === 'red' ? 'mode-red' : 'mode-blue';
	}

	onMount(() => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}
		loadData();
	});
</script>

<svelte:head>
	<title>{$t('federation.title')} — NeighbourGood</title>
</svelte:head>

<div class="federation-page">
	<header class="page-header">
		<div>
			<h1>{$t('federation.title')}</h1>
			<p class="subtitle">{$t('federation.subtitle')}</p>
		</div>
		<div class="header-actions">
			<a href="/federation/resources" class="action-link">{$t('federation.browse_resources')}</a>
			<a href="/federation/skills" class="action-link">{$t('federation.browse_skills')}</a>
		</div>
	</header>

	{#if alerts.length > 0}
		<section class="alerts-section">
			<h2>{$t('federation.active_alerts')}</h2>
			{#each alerts as alert}
				<div class="alert-card severity-{alert.severity}">
					<span class="alert-severity">{alert.severity.toUpperCase()}</span>
					<div class="alert-content">
						<strong>{alert.title}</strong>
						{#if alert.description}
							<p>{alert.description}</p>
						{/if}
						<span class="alert-source">{$t('federation.from')} {alert.source_instance_name}</span>
					</div>
				</div>
			{/each}
		</section>
	{/if}

	{#if isAdmin}
		<section class="admin-controls">
			<form class="add-form" onsubmit={(e) => { e.preventDefault(); addInstance(); }}>
				<input
					type="url"
					bind:value={addUrl}
					placeholder={$t('federation.add_placeholder')}
					class="url-input"
					required
				/>
				<button type="submit" class="btn btn-primary" disabled={adding}>
					{adding ? $t('common.loading') : $t('federation.add_btn')}
				</button>
			</form>
			{#if addError}
				<p class="error-text">{addError}</p>
			{/if}

			<div class="admin-actions">
				<button class="btn btn-secondary" onclick={refreshAll} disabled={refreshing}>
					{refreshing ? $t('common.loading') : $t('federation.refresh_all')}
				</button>
				<button class="btn btn-secondary" onclick={triggerSync}>
					{$t('federation.sync_now')}
				</button>
			</div>
			{#if syncMessage}
				<p class="sync-message">{syncMessage}</p>
			{/if}
		</section>
	{/if}

	{#if loading}
		<p class="loading">{$t('common.loading')}</p>
	{:else if instances.length === 0}
		<div class="empty-state">
			<p>{$t('federation.no_instances')}</p>
		</div>
	{:else}
		<section class="instance-grid">
			{#each instances as inst}
				<div class="instance-card">
					<div class="instance-header">
						<h3>{inst.name}</h3>
						<span class="mode-badge {modeClass(inst.platform_mode)}">
							{inst.platform_mode === 'red' ? $t('federation.mode_red') : $t('federation.mode_blue')}
						</span>
					</div>
					{#if inst.description}
						<p class="instance-desc">{inst.description}</p>
					{/if}
					{#if inst.region}
						<p class="instance-region">{inst.region}</p>
					{/if}
					<div class="instance-stats">
						<div class="stat">
							<span class="stat-value">{inst.active_user_count}</span>
							<span class="stat-label">{$t('federation.stat_active_users')}</span>
						</div>
						<div class="stat">
							<span class="stat-value">{inst.resource_count}</span>
							<span class="stat-label">{$t('federation.stat_resources')}</span>
						</div>
						<div class="stat">
							<span class="stat-value">{inst.skill_count}</span>
							<span class="stat-label">{$t('federation.stat_skills')}</span>
						</div>
						<div class="stat">
							<span class="stat-value">{inst.event_count}</span>
							<span class="stat-label">{$t('federation.stat_events')}</span>
						</div>
						<div class="stat">
							<span class="stat-value">{inst.community_count}</span>
							<span class="stat-label">{$t('federation.stat_communities')}</span>
						</div>
						<div class="stat">
							<span class="stat-value">{inst.user_count}</span>
							<span class="stat-label">{$t('federation.stat_total_users')}</span>
						</div>
					</div>
					<div class="instance-footer">
						<span class="reachable-badge" class:unreachable={!inst.is_reachable}>
							{inst.is_reachable ? $t('federation.reachable') : $t('federation.unreachable')}
						</span>
						{#if inst.admin_contact}
							<span class="admin-contact">{inst.admin_contact}</span>
						{/if}
						{#if isAdmin}
							<button class="btn-remove" onclick={() => removeInstance(inst.id)} title={$t('common.delete')}>
								&times;
							</button>
						{/if}
					</div>
				</div>
			{/each}
		</section>
	{/if}
</div>

<style>
	.federation-page {
		max-width: 900px;
		margin: 0 auto;
	}

	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
		margin-bottom: 2rem;
		flex-wrap: wrap;
	}

	.page-header h1 {
		font-family: Georgia, 'Times New Roman', serif;
		font-weight: 400;
		font-size: 1.8rem;
		color: var(--color-text);
		margin: 0;
	}

	.subtitle {
		color: var(--color-text-muted);
		font-size: 0.95rem;
		margin: 0.25rem 0 0;
	}

	.header-actions {
		display: flex;
		gap: 0.5rem;
	}

	.action-link {
		padding: 0.4rem 0.9rem;
		border-radius: var(--radius-sm);
		background: var(--color-primary-light);
		color: var(--color-primary);
		text-decoration: none;
		font-size: 0.85rem;
		font-weight: 600;
		transition: all var(--transition-fast);
	}

	.action-link:hover {
		background: var(--color-primary);
		color: white;
		text-decoration: none;
	}

	/* Alerts */
	.alerts-section {
		margin-bottom: 1.5rem;
	}

	.alerts-section h2 {
		font-size: 1rem;
		font-weight: 600;
		margin: 0 0 0.75rem;
		color: var(--color-text);
	}

	.alert-card {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		padding: 0.75rem 1rem;
		border-radius: var(--radius);
		margin-bottom: 0.5rem;
		border-left: 4px solid;
	}

	.alert-card.severity-info {
		background: var(--color-primary-light);
		border-color: var(--color-primary);
	}

	.alert-card.severity-warning {
		background: var(--color-warning-bg, rgba(245, 158, 11, 0.1));
		border-color: var(--color-warning, #f59e0b);
	}

	.alert-card.severity-critical {
		background: var(--color-error-bg, rgba(239, 68, 68, 0.1));
		border-color: var(--color-error);
	}

	.alert-severity {
		font-size: 0.7rem;
		font-weight: 700;
		padding: 0.15rem 0.5rem;
		border-radius: 999px;
		background: var(--color-surface);
		white-space: nowrap;
	}

	.alert-content {
		flex: 1;
	}

	.alert-content p {
		margin: 0.25rem 0 0;
		font-size: 0.88rem;
		color: var(--color-text-muted);
	}

	.alert-source {
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	/* Admin controls */
	.admin-controls {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		padding: 1rem;
		margin-bottom: 1.5rem;
	}

	.add-form {
		display: flex;
		gap: 0.5rem;
	}

	.url-input {
		flex: 1;
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		font-size: 0.9rem;
		background: var(--color-bg);
		color: var(--color-text);
	}

	.url-input:focus {
		outline: none;
		border-color: var(--color-primary);
	}

	.admin-actions {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.75rem;
	}

	.error-text {
		color: var(--color-error);
		font-size: 0.85rem;
		margin: 0.5rem 0 0;
	}

	.sync-message {
		font-size: 0.85rem;
		color: var(--color-success, #10b981);
		margin: 0.5rem 0 0;
	}

	/* Buttons */
	.btn {
		padding: 0.5rem 1rem;
		border-radius: var(--radius-sm);
		font-size: 0.88rem;
		font-weight: 600;
		cursor: pointer;
		border: none;
		transition: all var(--transition-fast);
	}

	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-primary {
		background: var(--color-primary);
		color: white;
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--color-primary-hover);
	}

	.btn-secondary {
		background: var(--color-surface);
		color: var(--color-text);
		border: 1px solid var(--color-border);
	}

	.btn-secondary:hover:not(:disabled) {
		border-color: var(--color-primary);
		color: var(--color-primary);
	}

	/* Instance grid */
	.instance-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
		gap: 1rem;
	}

	.instance-card {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		padding: 1.25rem;
		transition: box-shadow var(--transition-fast);
	}

	.instance-card:hover {
		box-shadow: var(--shadow-md);
	}

	.instance-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.instance-header h3 {
		margin: 0;
		font-size: 1.05rem;
		font-weight: 600;
		color: var(--color-text);
	}

	.mode-badge {
		font-size: 0.72rem;
		font-weight: 700;
		padding: 0.15rem 0.5rem;
		border-radius: 999px;
		text-transform: uppercase;
	}

	.mode-blue {
		background: var(--color-primary-light);
		color: var(--color-primary);
	}

	.mode-red {
		background: var(--color-error-bg, rgba(239, 68, 68, 0.1));
		color: var(--color-error);
	}

	.instance-desc {
		font-size: 0.88rem;
		color: var(--color-text-muted);
		margin: 0 0 0.5rem;
	}

	.instance-region {
		font-size: 0.82rem;
		color: var(--color-text-muted);
		margin: 0 0 0.75rem;
	}

	.instance-stats {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.stat {
		text-align: center;
	}

	.stat-value {
		display: block;
		font-size: 1.1rem;
		font-weight: 700;
		color: var(--color-text);
	}

	.stat-label {
		font-size: 0.72rem;
		color: var(--color-text-muted);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.instance-footer {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding-top: 0.75rem;
		border-top: 1px solid var(--color-border);
		font-size: 0.82rem;
	}

	.reachable-badge {
		color: var(--color-success, #10b981);
		font-weight: 600;
	}

	.reachable-badge.unreachable {
		color: var(--color-text-muted);
	}

	.admin-contact {
		color: var(--color-text-muted);
		margin-left: auto;
	}

	.btn-remove {
		background: none;
		border: none;
		color: var(--color-text-muted);
		font-size: 1.2rem;
		cursor: pointer;
		padding: 0 0.25rem;
		line-height: 1;
	}

	.btn-remove:hover {
		color: var(--color-error);
	}

	/* Empty / loading states */
	.loading {
		text-align: center;
		color: var(--color-text-muted);
		padding: 2rem;
	}

	.empty-state {
		text-align: center;
		padding: 3rem 1rem;
		color: var(--color-text-muted);
	}

	@media (max-width: 768px) {
		.page-header {
			flex-direction: column;
		}

		.instance-grid {
			grid-template-columns: 1fr;
		}

		.add-form {
			flex-direction: column;
		}
	}
</style>
