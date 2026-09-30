<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { isLoggedIn, user } from '$lib/stores/auth';
	import { isOnline } from '$lib/stores/offline';
	import { meshEnabled, MESH_COMMUNITY_KEY } from '$lib/stores/mesh-settings';
	import { api } from '$lib/api';
	import { t } from 'svelte-i18n';
	import Icon, { type IconName } from '$lib/components/Icon.svelte';
	import {
		meshStatus,
		meshDeviceName,
		meshMessages,
		meshPeers,
		meshPeerCount,
		meshIsSupported,
		connectToMesh,
		disconnectFromMesh,
		syncMeshMessagesToServer,
		startHeartbeat,
		stopHeartbeat,
		meshRelayEnabled,
		meshRelayCount,
		meshAckStatus,
		toggleRelay
	} from '$lib/stores/mesh';
	import type { MeshStatus } from '$lib/stores/mesh';
	import type { NGMeshMessage } from '$lib/bluetooth/protocol';
	import type { CommunityOut, MeshSyncResult } from '$lib/types';
	import {
		currentMeshKeyId,
		ensureMeshKeyRegistered,
		listMeshKeys,
		revokeMeshKey,
		type MeshKeyInfo
	} from '$lib/mesh-keys';

	let error = $state('');
	let syncStatus = $state<'idle' | 'syncing' | 'done' | 'error'>('idle');
	let syncResult = $state<MeshSyncResult | null>(null);
	let lastSyncTime = $state<string | null>(null);

	// The community heartbeats announce and the offline triage view is scoped to.
	// Remembered locally so it is known offline too.
	let communities = $state<CommunityOut[]>([]);
	let communityId = $state<number | null>(null);

	let keys = $state<MeshKeyInfo[]>([]);
	let thisKeyId = $state<string | null>(null);
	let keysError = $state('');

	// Reactive derivations
	let status: MeshStatus = $derived($meshStatus);
	let deviceName: string | null = $derived($meshDeviceName);
	let messages: NGMeshMessage[] = $derived($meshMessages);
	let peerCount: number = $derived($meshPeerCount);
	let supported: boolean = $derived($meshIsSupported);
	let peers: Set<string> = $derived($meshPeers);
	let relayEnabled: boolean = $derived($meshRelayEnabled);
	let relayCount: number = $derived($meshRelayCount);
	let ackStatus: Map<string, 'pending' | 'acked'> = $derived($meshAckStatus);

	onMount(() => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}
		// Restore last sync time from session
		lastSyncTime = sessionStorage.getItem('ng_mesh_last_sync');
		try {
			const stored = Number(localStorage.getItem(MESH_COMMUNITY_KEY));
			if (stored) communityId = stored;
		} catch {
			// storage unavailable
		}
		if (!$meshEnabled) return;
		loadCommunities();
		loadKeys();
	});

	onDestroy(() => {
		stopHeartbeat();
	});

	// Announce ourselves to nearby peers while connected
	$effect(() => {
		const name = $user?.display_name;
		if ($meshEnabled && status === 'connected' && communityId && name) {
			startHeartbeat(communityId, name);
			return () => stopHeartbeat();
		}
	});

	async function loadCommunities() {
		try {
			communities = await api<CommunityOut[]>('/communities/my/memberships', { auth: true });
		} catch {
			return; // offline: keep the remembered community
		}
		if (!communities.some((c) => c.id === communityId)) {
			const initial = communities.find((c) => (c.effective_mode ?? c.mode) === 'red') ?? communities[0];
			selectCommunity(initial?.id ?? null);
		}
	}

	function selectCommunity(id: number | null) {
		communityId = id;
		try {
			if (id) localStorage.setItem(MESH_COMMUNITY_KEY, String(id));
			else localStorage.removeItem(MESH_COMMUNITY_KEY);
		} catch {
			// storage unavailable
		}
	}

	async function loadKeys() {
		const uid = $user?.id;
		if (!$isOnline || !uid) return;
		keysError = '';
		try {
			await ensureMeshKeyRegistered(uid);
			thisKeyId = await currentMeshKeyId(uid);
			keys = await listMeshKeys();
		} catch (e) {
			keysError = e instanceof Error ? e.message : String(e);
		}
	}

	async function handleRevoke(keyId: string) {
		keysError = '';
		try {
			await revokeMeshKey(keyId);
			// Revoking this browser's own key: register a fresh one right away
			await loadKeys();
		} catch (e) {
			keysError = e instanceof Error ? e.message : String(e);
		}
	}

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
		disconnectFromMesh();
	}

	async function handleSync() {
		if (messages.length === 0) return;
		syncStatus = 'syncing';
		syncResult = null;
		try {
			// Batches of 100; synced messages are removed from the queue only if the server reported no errors
			const result = await syncMeshMessagesToServer();
			if (!result) {
				syncStatus = 'idle';
				return;
			}
			syncResult = result;
			syncStatus = 'done';
			lastSyncTime = new Date().toLocaleTimeString();
			sessionStorage.setItem('ng_mesh_last_sync', lastSyncTime);
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

	function messageTypeIcon(type: string): IconName {
		const icons: Record<string, IconName> = {
			emergency_ticket: 'alert',
			ticket_comment: 'message',
			crisis_vote: 'vote',
			crisis_status: 'refresh',
			direct_message: 'mail',
			heartbeat: 'activity'
		};
		return icons[type] || 'radio';
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
				<span class="badge status-chip" style="color: {statusColor(status)}">
					<span class="status-dot"></span>
					{$t(`mesh.${status}`)}
				</span>
			{/if}
		</div>
		<p class="mesh-subtitle">{$t('mesh.subtitle')}</p>
	</header>

	{#if !$meshEnabled}
		<div class="card mesh-card mesh-disabled">
			<p>{$t('mesh.disabled_notice')}</p>
			<a href="/settings" class="btn btn-primary">{$t('mesh.enable_in_settings')}</a>
		</div>
	{:else if !supported}
		<div class="card mesh-card mesh-unsupported">
			<Icon name="alert" size={24} />
			<p>{$t('mesh.not_supported')}</p>
		</div>
	{:else}
		<!-- Connection Card -->
		<div class="card mesh-card">
			<h2 class="card-title">
				<Icon name="radio" size={20} />
				{$t('mesh.connection')}
			</h2>

			{#if status === 'disconnected'}
				<button class="btn btn-primary" onclick={handleConnect}>
					<Icon name="radio" size={16} />
					{$t('mesh.connect')}
				</button>
			{:else if status === 'scanning'}
				<div class="status-message">
					<span class="btn-spin" aria-hidden="true"></span>
					{$t('mesh.scanning')}
				</div>
			{:else if status === 'connecting'}
				<div class="status-message">
					<span class="btn-spin" aria-hidden="true"></span>
					{$t('mesh.connecting')}
				</div>
			{:else if status === 'reconnecting'}
				<div class="status-message">
					<span class="btn-spin" aria-hidden="true"></span>
					{$t('mesh.reconnecting')}
				</div>
			{:else}
				<!-- Connected -->
				<div class="connection-info">
					{#if communities.length > 1}
						<label class="device-row">
							<span class="device-label">{$t('mesh.community')}</span>
							<select class="input" value={communityId} onchange={(e) => selectCommunity(Number(e.currentTarget.value))}>
								{#each communities as c (c.id)}
									<option value={c.id}>{c.name}</option>
								{/each}
							</select>
						</label>
					{/if}
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
				<button class="btn btn-danger-outline" onclick={handleDisconnect}>
					{$t('mesh.disconnect')}
				</button>
			{/if}

			{#if error}
				<p class="alert alert-error" role="alert">{error}</p>
			{/if}
		</div>

		<!-- Message Queue Card -->
		<div class="card mesh-card">
			<h2 class="card-title">
				<Icon name="message" size={20} />
				{$t('mesh.message_queue')}
				{#if messages.length > 0}
					<span class="badge badge-solid">{messages.length}</span>
				{/if}
			</h2>

			{#if messages.length === 0}
				<div class="empty-state compact">
					<span class="empty-icon"><Icon name="inbox" size={22} /></span>
					<p>{$t('mesh.no_messages')}</p>
				</div>
			{:else}
				<div class="message-list">
					{#each messages as msg (msg.id)}
						<div class="message-item">
							<span class="msg-icon"><Icon name={messageTypeIcon(msg.type)} size={18} /></span>
							<div class="msg-content">
								<span class="msg-type">
									{messageTypeLabel(msg.type)}
									{#if msg.sig}
										<span class="badge badge-success signed-badge" title={$t('mesh.signed_hint')}>{$t('mesh.signed')}</span>
									{/if}
								</span>
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
							<div class="msg-meta">
								{#if ackStatus.get(msg.id) === 'acked'}
									<span class="ack-badge acked" title="Delivered"><Icon name="check" size={14} /></span>
								{:else if ackStatus.get(msg.id) === 'pending'}
									<span class="ack-badge pending" title="Pending"><Icon name="clock" size={14} /></span>
								{/if}
								<span class="msg-time">{formatTime(msg.ts)}</span>
							</div>
						</div>
					{/each}
				</div>

				<!-- Sync controls -->
				<div class="sync-controls">
					{#if $isOnline}
						<button
							class="btn btn-primary"
							class:is-loading={syncStatus === 'syncing'}
							onclick={handleSync}
							disabled={syncStatus === 'syncing'}
						>
							{#if syncStatus === 'syncing'}
								{$t('mesh.syncing')}
							{:else}
								<Icon name="refresh" size={16} />
								{$t('mesh.sync_messages', { values: { count: messages.length } })}
							{/if}
						</button>
					{:else}
						<p class="sync-offline-hint">{$t('mesh.sync_when_online')}</p>
					{/if}
				</div>
			{/if}

			<!-- Shown after the queue empties too, so the outcome of a sync stays visible -->
			{#if syncResult}
				<div class="sync-result" class:sync-success={syncResult.errors === 0} class:sync-partial={syncResult.errors > 0}>
					{$t('mesh.sync_result', { values: { synced: syncResult.synced, duplicates: syncResult.duplicates, errors: syncResult.errors } })}
					{#if syncResult.verified}
						· {$t('mesh.sync_verified', { values: { count: syncResult.verified } })}
					{/if}
					{#if syncResult.rejected}
						· {$t('mesh.sync_rejected', { values: { count: syncResult.rejected } })}
					{/if}
				</div>
			{/if}

			{#if lastSyncTime}
				<p class="last-sync">{$t('mesh.last_sync')}: {lastSyncTime}</p>
			{/if}
		</div>

		<!-- Offline Triage Link -->
		<a href="/mesh/triage" class="card card-interactive mesh-card triage-link">
			<Icon name="clipboard" size={20} />
			<div>
				<strong>{$t('mesh.offline_triage')}</strong>
				<p>{$t('mesh.offline_triage_hint')}</p>
			</div>
		</a>

		<!-- Device keys: which browsers can sign mesh messages for this account -->
		<div class="card mesh-card">
			<h2 class="card-title"><Icon name="key" size={20} />{$t('mesh.keys_title')}</h2>
			<p class="keys-hint">{$t('mesh.keys_hint')}</p>
			{#if !$isOnline}
				<p class="sync-offline-hint">{$t('mesh.keys_offline')}</p>
			{:else if keys.length === 0}
				<div class="empty-state compact">
					<span class="empty-icon"><Icon name="key" size={22} /></span>
					<p>{$t('mesh.keys_none')}</p>
				</div>
			{:else}
				<ul class="key-list">
					{#each keys as k (k.key_id)}
						<li class="key-item" class:revoked={k.revoked_at}>
							<div class="key-info">
								<strong>{k.device_name || $t('mesh.unknown_device')}</strong>
								{#if k.key_id === thisKeyId}<span class="badge badge-success signed-badge">{$t('mesh.keys_this_device')}</span>{/if}
								<span class="key-meta">
									{k.key_id.slice(0, 12)}… ·
									{k.revoked_at
										? $t('mesh.keys_revoked')
										: $t('mesh.keys_added', { values: { date: new Date(k.created_at).toLocaleDateString() } })}
								</span>
							</div>
							{#if !k.revoked_at}
								<button class="btn btn-danger-outline btn-sm" onclick={() => handleRevoke(k.key_id)}>
									{$t('mesh.keys_revoke')}
								</button>
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
			{#if keysError}
				<p class="alert alert-error" role="alert">{keysError}</p>
			{/if}
		</div>

		<!-- How It Works Card -->
		<div class="card mesh-card mesh-info">
			<h2 class="card-title">
				<Icon name="activity" size={20} />
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
	.mesh-disabled {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 0.75rem;
	}

	.signed-badge {
		margin-inline-start: 0.35rem;
	}

	.key-info .signed-badge {
		align-self: flex-start;
		margin-inline-start: 0;
	}

	.keys-hint {
		color: var(--color-text-muted);
		font-size: 0.85rem;
		margin: 0 0 0.75rem;
	}

	.key-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.key-item {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.5rem 0;
		border-bottom: 1px solid var(--color-border);
	}

	.key-item.revoked {
		opacity: 0.6;
	}

	.key-info {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		min-width: 0;
	}

	.key-meta {
		color: var(--color-text-muted);
		font-size: 0.75rem;
		overflow-wrap: anywhere;
	}

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
		font-family: var(--font-heading);
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
		font-size: 0.78rem;
	}

	.status-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: currentColor;
		animation: pulse 1.5s ease-in-out infinite;
	}

	.mesh-card {
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

	.status-message {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		color: var(--color-text-muted);
		font-size: 0.9rem;
	}

	.btn-spin {
		display: inline-block;
		width: 18px;
		height: 18px;
		border: 2px solid var(--color-border);
		border-top-color: var(--color-primary);
		border-radius: 50%;
		animation: btn-spin 0.7s linear infinite;
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

	.empty-state.compact {
		padding: 1.5rem 1rem;
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
		display: inline-flex;
		color: var(--color-primary-text);
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

	.msg-meta {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 0.2rem;
		flex-shrink: 0;
	}

	.msg-time {
		font-size: 0.75rem;
		color: var(--color-text-muted);
		white-space: nowrap;
	}

	.ack-badge {
		display: inline-flex;
	}

	.ack-badge.acked {
		color: var(--color-success);
	}

	.ack-badge.pending {
		color: var(--color-text-muted);
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
		margin-inline-start: auto;
	}

	.triage-link {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.triage-link:hover {
		border-color: var(--color-primary);
	}

	.triage-link strong {
		font-size: 0.92rem;
	}

	.triage-link p {
		font-size: 0.82rem;
		color: var(--color-text-muted);
		margin: 0.15rem 0 0;
	}

	.mesh-info {
		background: var(--color-primary-light);
		border-color: var(--color-primary);
	}

	.info-list {
		margin: 0;
		padding-inline-start: 1.25rem;
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
			margin-inline-start: 0;
		}
	}
</style>
