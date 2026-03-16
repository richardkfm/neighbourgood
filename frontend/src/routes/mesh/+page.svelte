<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { isLoggedIn, token } from '$lib/stores/auth';
	import { isOnline } from '$lib/stores/offline';
	import { t } from 'svelte-i18n';
	import {
		meshStatus,
		meshDeviceName,
		meshMessages,
		meshPeers,
		meshPeerCount,
		meshIsSupported,
		connectToMesh,
		disconnectFromMesh,
		clearMeshMessages,
		getMeshMessages,
		broadcastHeartbeat,
		meshRelayEnabled,
		meshRelayCount,
		toggleRelay
	} from '$lib/stores/mesh';
	import { api } from '$lib/api';
	import type { MeshStatus } from '$lib/stores/mesh';
	import type { NGMeshMessage } from '$lib/bluetooth/protocol';

	let error = $state('');
	let syncStatus = $state<'idle' | 'syncing' | 'done' | 'error'>('idle');
	let syncResult = $state<{ synced: number; duplicates: number; errors: number } | null>(null);
	let lastSyncTime = $state<string | null>(null);
	let heartbeatInterval: ReturnType<typeof setInterval> | null = null;

	// Reactive derivations
	let status: MeshStatus = $derived($meshStatus);
	let deviceName: string | null = $derived($meshDeviceName);
	let messages: NGMeshMessage[] = $derived($meshMessages);
	let peerCount: number = $derived($meshPeerCount);
	let supported: boolean = $derived($meshIsSupported);
	let peers: Set<string> = $derived($meshPeers);
	let relayEnabled: boolean = $derived($meshRelayEnabled);
	let relayCount: number = $derived($meshRelayCount);

	onMount(() => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}
		// Restore last sync time from session
		lastSyncTime = sessionStorage.getItem('ng_mesh_last_sync');
	});

	onDestroy(() => {
		if (heartbeatInterval) clearInterval(heartbeatInterval);
	});

	async function handleConnect() {
		error = '';
		try {
			await connectToMesh();
		} catch (err: any) {
			if (err?.name === 'NotFoundError') {
				// User cancelled the device picker
				return;
			}
			error = err?.message || $t('mesh.connection_lost');
		}
	}

	function handleDisconnect() {
		if (heartbeatInterval) {
			clearInterval(heartbeatInterval);
			heartbeatInterval = null;
		}
		disconnectFromMesh();
	}

	async function handleSync() {
		if (messages.length === 0) return;
		syncStatus = 'syncing';
		syncResult = null;
		try {
			const result = await api<{ synced: number; duplicates: number; errors: number }>(
				'/mesh/sync',
				{
					method: 'POST',
					body: { messages },
					auth: true
				}
			);
			syncResult = result;
			syncStatus = 'done';
			lastSyncTime = new Date().toLocaleTimeString();
			sessionStorage.setItem('ng_mesh_last_sync', lastSyncTime);
			// Clear synced messages if all succeeded or were duplicates
			if (result.errors === 0) {
				clearMeshMessages();
			}
		} catch (err: any) {
			syncStatus = 'error';
			error = err?.message || 'Sync failed';
		}
	}

	function messageTypeLabel(type: string): string {
		const labels: Record<string, string> = {
			emergency_ticket: 'Emergency Ticket',
			ticket_comment: 'Ticket Comment',
			crisis_vote: 'Crisis Vote',
			crisis_status: 'Crisis Status',
			direct_message: 'Direct Message',
			heartbeat: 'Heartbeat'
		};
		return labels[type] || type;
	}

	function messageTypeIcon(type: string): string {
		const icons: Record<string, string> = {
			emergency_ticket: '🚨',
			ticket_comment: '💬',
			crisis_vote: '🗳️',
			crisis_status: '🔄',
			direct_message: '✉️',
			heartbeat: '💓'
		};
		return icons[type] || '📡';
	}

	function formatTime(ts: number): string {
		return new Date(ts).toLocaleTimeString(undefined, {
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit'
		});
	}

	function statusColor(s: MeshStatus): string {
		switch (s) {
			case 'connected': return 'var(--color-success)';
			case 'scanning':
			case 'connecting':
			case 'reconnecting': return 'var(--color-warning)';
			default: return 'var(--color-text-muted)';
		}
	}
</script>

<svelte:head>
	<title>{$t('mesh.title')} — NeighbourGood</title>
</svelte:head>

<div class="mesh-page">
	<header class="mesh-header">
		<div class="mesh-title-row">
			<h1>{$t('mesh.title')}</h1>
			{#if status !== 'disconnected'}
				<span class="status-chip" style="background: {statusColor(status)}">
					<span class="status-dot"></span>
					{$t(`mesh.${status}`)}
				</span>
			{/if}
		</div>
		<p class="mesh-subtitle">{$t('mesh.subtitle')}</p>
	</header>

	{#if !supported}
		<div class="mesh-card mesh-unsupported">
			<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
			<p>{$t('mesh.not_supported')}</p>
		</div>
	{:else}
		<!-- Connection Card -->
		<div class="mesh-card">
			<h2 class="card-title">
				<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/></svg>
				{$t('mesh.connection')}
			</h2>

			{#if status === 'disconnected'}
				<button class="btn btn-primary" onclick={handleConnect}>
					<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.55a11 11 0 0 1 14.08 0"/><line x1="12" y1="20" x2="12.01" y2="20"/></svg>
					{$t('mesh.connect')}
				</button>
			{:else if status === 'scanning'}
				<div class="status-message">
					<span class="spinner"></span>
					{$t('mesh.scanning')}
				</div>
			{:else if status === 'connecting'}
				<div class="status-message">
					<span class="spinner"></span>
					{$t('mesh.connecting')}
				</div>
			{:else if status === 'reconnecting'}
				<div class="status-message">
					<span class="spinner"></span>
					{$t('mesh.reconnecting')}
				</div>
			{:else}
				<!-- Connected -->
				<div class="connection-info">
					<div class="device-row">
						<span class="device-label">{$t('mesh.device')}</span>
						<span class="device-name">{deviceName || $t('mesh.unknown_device')}</span>
					</div>
					<div class="device-row">
						<span class="device-label">{$t('mesh.peers')}</span>
						<span class="peer-count">
							{peerCount} {$t('mesh.peers_nearby')}
							{#if peerCount > 0}
								<span class="peer-names">({[...peers].join(', ')})</span>
							{/if}
						</span>
					</div>
				</div>
				<div class="relay-row">
					<label class="relay-toggle">
						<input type="checkbox" checked={relayEnabled} onchange={toggleRelay} />
						<span>{$t('mesh.relay_mode')}</span>
					</label>
					{#if relayCount > 0}
						<span class="relay-count">{$t('mesh.relayed', { values: { count: relayCount } })}</span>
					{/if}
				</div>
				<button class="btn btn-outline btn-danger" onclick={handleDisconnect}>
					{$t('mesh.disconnect')}
				</button>
			{/if}

			{#if error}
				<p class="error-message">{error}</p>
			{/if}
		</div>

		<!-- Message Queue Card -->
		<div class="mesh-card">
			<h2 class="card-title">
				<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
				{$t('mesh.message_queue')}
				{#if messages.length > 0}
					<span class="queue-badge">{messages.length}</span>
				{/if}
			</h2>

			{#if messages.length === 0}
				<p class="empty-state">{$t('mesh.no_messages')}</p>
			{:else}
				<div class="message-list">
					{#each messages as msg (msg.id)}
						<div class="message-item">
							<span class="msg-icon">{messageTypeIcon(msg.type)}</span>
							<div class="msg-content">
								<span class="msg-type">{messageTypeLabel(msg.type)}</span>
								<span class="msg-sender">{$t('common.by')} {msg.sender_name}</span>
								{#if msg.type === 'emergency_ticket' && msg.data.title}
									<span class="msg-detail">{msg.data.title}</span>
								{:else if msg.type === 'direct_message' && msg.data.body}
									<span class="msg-detail">{String(msg.data.body).slice(0, 80)}{String(msg.data.body).length > 80 ? '…' : ''}</span>
								{:else if msg.type === 'ticket_comment' && msg.data.body}
									<span class="msg-detail">{String(msg.data.body).slice(0, 80)}{String(msg.data.body).length > 80 ? '…' : ''}</span>
								{:else if msg.type === 'crisis_vote'}
									<span class="msg-detail">{$t('mesh.vote')}: {msg.data.vote_type}</span>
								{/if}
							</div>
							<span class="msg-time">{formatTime(msg.ts)}</span>
						</div>
					{/each}
				</div>

				<!-- Sync controls -->
				<div class="sync-controls">
					{#if $isOnline}
						<button
							class="btn btn-primary"
							onclick={handleSync}
							disabled={syncStatus === 'syncing'}
						>
							{#if syncStatus === 'syncing'}
								<span class="spinner spinner-sm"></span>
								{$t('mesh.syncing')}
							{:else}
								<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
								{$t('mesh.sync_messages', { values: { count: messages.length } })}
							{/if}
						</button>
					{:else}
						<p class="sync-offline-hint">{$t('mesh.sync_when_online')}</p>
					{/if}

					{#if syncResult}
						<div class="sync-result" class:sync-success={syncResult.errors === 0} class:sync-partial={syncResult.errors > 0}>
							{$t('mesh.sync_result', { values: { synced: syncResult.synced, duplicates: syncResult.duplicates, errors: syncResult.errors } })}
						</div>
					{/if}

					{#if lastSyncTime}
						<p class="last-sync">{$t('mesh.last_sync')}: {lastSyncTime}</p>
					{/if}
				</div>
			{/if}
		</div>

		<!-- How It Works Card -->
		<div class="mesh-card mesh-info">
			<h2 class="card-title">
				<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
				{$t('mesh.how_it_works')}
			</h2>
			<ol class="info-list">
				<li>{$t('mesh.step_1')}</li>
				<li>{$t('mesh.step_2')}</li>
				<li>{$t('mesh.step_3')}</li>
				<li>{$t('mesh.step_4')}</li>
			</ol>
		</div>
	{/if}
</div>

<style>
	.mesh-page {
		max-width: 700px;
		margin: 0 auto;
	}

	.mesh-header {
		margin-bottom: 1.5rem;
	}

	.mesh-title-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.mesh-title-row h1 {
		font-family: Georgia, 'Times New Roman', serif;
		font-weight: 400;
		font-size: 1.6rem;
		color: var(--color-text);
		margin: 0;
	}

	.mesh-subtitle {
		color: var(--color-text-muted);
		font-size: 0.92rem;
		margin-top: 0.25rem;
	}

	.status-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.78rem;
		font-weight: 600;
		color: white;
		padding: 0.2rem 0.65rem;
		border-radius: 999px;
	}

	.status-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: white;
		animation: pulse 1.5s ease-in-out infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.5; }
	}

	.mesh-card {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		padding: 1.25rem;
		margin-bottom: 1rem;
	}

	.mesh-unsupported {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		color: var(--color-error);
	}

	.card-title {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 1rem;
		font-weight: 600;
		color: var(--color-text);
		margin: 0 0 1rem;
	}

	.queue-badge {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 20px;
		height: 20px;
		padding: 0 6px;
		border-radius: 999px;
		background: var(--color-primary);
		color: white;
		font-size: 0.72rem;
		font-weight: 700;
	}

	.btn {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.5rem 1rem;
		border-radius: var(--radius-sm);
		font-size: 0.88rem;
		font-weight: 600;
		cursor: pointer;
		border: 1px solid transparent;
		transition: all var(--transition-fast);
	}

	.btn-primary {
		background: var(--color-primary);
		color: white;
	}

	.btn-primary:hover {
		background: var(--color-primary-hover);
		box-shadow: var(--shadow-sm);
	}

	.btn-primary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-outline {
		background: transparent;
		border: 1px solid var(--color-border);
		color: var(--color-text);
	}

	.btn-outline:hover {
		border-color: var(--color-text-muted);
	}

	.btn-danger {
		color: var(--color-error);
		border-color: var(--color-error);
	}

	.btn-danger:hover {
		background: var(--color-error);
		color: white;
	}

	.status-message {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		color: var(--color-text-muted);
		font-size: 0.9rem;
	}

	.spinner {
		display: inline-block;
		width: 18px;
		height: 18px;
		border: 2px solid var(--color-border);
		border-top-color: var(--color-primary);
		border-radius: 50%;
		animation: spin 0.7s linear infinite;
	}

	.spinner-sm {
		width: 14px;
		height: 14px;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.connection-info {
		margin-bottom: 1rem;
	}

	.device-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.4rem 0;
		font-size: 0.88rem;
	}

	.device-row + .device-row {
		border-top: 1px solid var(--color-border);
	}

	.device-label {
		color: var(--color-text-muted);
		font-weight: 500;
	}

	.device-name {
		font-weight: 600;
		color: var(--color-text);
	}

	.peer-count {
		color: var(--color-text);
		font-weight: 500;
	}

	.peer-names {
		color: var(--color-text-muted);
		font-size: 0.82rem;
		font-weight: 400;
	}

	.relay-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.5rem 0;
		margin-bottom: 0.5rem;
		border-top: 1px solid var(--color-border);
	}

	.relay-toggle {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.88rem;
		color: var(--color-text);
		cursor: pointer;
	}

	.relay-toggle input {
		accent-color: var(--color-primary);
	}

	.relay-count {
		font-size: 0.78rem;
		color: var(--color-text-muted);
		background: var(--color-primary-light);
		padding: 0.15rem 0.5rem;
		border-radius: 999px;
	}

	.error-message {
		color: var(--color-error);
		font-size: 0.85rem;
		margin-top: 0.75rem;
	}

	.empty-state {
		color: var(--color-text-muted);
		font-size: 0.9rem;
		text-align: center;
		padding: 1rem 0;
	}

	.message-list {
		max-height: 400px;
		overflow-y: auto;
		margin-bottom: 1rem;
	}

	.message-item {
		display: flex;
		align-items: flex-start;
		gap: 0.6rem;
		padding: 0.6rem 0;
		border-bottom: 1px solid var(--color-border);
	}

	.message-item:last-child {
		border-bottom: none;
	}

	.msg-icon {
		font-size: 1.1rem;
		flex-shrink: 0;
		margin-top: 0.1rem;
	}

	.msg-content {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
	}

	.msg-type {
		font-size: 0.85rem;
		font-weight: 600;
		color: var(--color-text);
	}

	.msg-sender {
		font-size: 0.78rem;
		color: var(--color-text-muted);
	}

	.msg-detail {
		font-size: 0.82rem;
		color: var(--color-text-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.msg-time {
		font-size: 0.75rem;
		color: var(--color-text-muted);
		white-space: nowrap;
		flex-shrink: 0;
	}

	.sync-controls {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.75rem;
	}

	.sync-offline-hint {
		color: var(--color-warning);
		font-size: 0.85rem;
		font-style: italic;
	}

	.sync-result {
		font-size: 0.82rem;
		padding: 0.3rem 0.7rem;
		border-radius: var(--radius-sm);
	}

	.sync-success {
		background: var(--color-success-bg, rgba(16, 185, 129, 0.1));
		color: var(--color-success);
	}

	.sync-partial {
		background: var(--color-warning-bg, rgba(245, 158, 11, 0.1));
		color: var(--color-warning);
	}

	.last-sync {
		font-size: 0.78rem;
		color: var(--color-text-muted);
		margin-left: auto;
	}

	.mesh-info {
		background: var(--color-primary-light);
		border-color: var(--color-primary);
	}

	.info-list {
		margin: 0;
		padding-left: 1.25rem;
		color: var(--color-text-muted);
		font-size: 0.88rem;
		line-height: 1.7;
	}

	@media (max-width: 768px) {
		.mesh-title-row h1 {
			font-size: 1.3rem;
		}

		.sync-controls {
			flex-direction: column;
			align-items: stretch;
		}

		.last-sync {
			margin-left: 0;
		}
	}
</style>
