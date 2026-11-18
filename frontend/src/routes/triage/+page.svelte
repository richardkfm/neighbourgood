<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { isLoggedIn, user } from '$lib/stores/auth';
	import { api } from '$lib/api';
	import { isOnline } from '$lib/stores/offline';
	import { get } from 'svelte/store';
	import {
		meshStatus,
		meshDeviceName,
		meshMessages,
		meshPeerCount,
		meshIsSupported,
		connectToMesh,
		disconnectFromMesh,
		broadcastEmergencyTicket,
		syncMeshMessagesToServer,
		getMeshMessages
	} from '$lib/stores/mesh';
	import { isBluetoothSupported } from '$lib/bluetooth/connection';
	import { meshEnabled } from '$lib/stores/mesh-settings';
	import type { CommunityOut, NGMeshMessage } from '$lib/types';
	import { t, locale } from 'svelte-i18n';
	import Icon from '$lib/components/Icon.svelte';

	interface Ticket {
		id: number;
		community_id: number;
		author: { id: number; display_name: string };
		ticket_type: string;
		title: string;
		description: string;
		status: string;
		urgency: string;
		due_at: string | null;
		triage_score?: number;
		assigned_to: { id: number; display_name: string } | null;
		created_at: string;
		updated_at: string;
	}

	interface MemberInfo {
		user: { id: number };
		role: string;
	}

	let communities: CommunityOut[] = $state([]);
	let selectedCommunityId: number | null = $state(null);
	let tickets: Ticket[] = $state([]);
	let myRole: string = $state('member');
	let loading = $state(false);
	let loadingCommunities = $state(true);
	let error = $state('');
	let filterUrgency = $state('');
	let filterStatus = $state('');

	// New ticket form
	let showNewTicketForm = $state(false);
	let newTicketTitle = $state('');
	let newTicketDesc = $state('');
	let newTicketType = $state('request');
	let newTicketUrgency = $state('medium');
	let creatingTicket = $state(false);
	let selectedCommunityMode = $state('blue');

	let meshConnecting = $state(false);
	let meshError = $state('');
	let syncing = $state(false);

	// Filter mesh messages for the selected community
	let communityMeshTickets = $derived(
		$meshMessages.filter(
			(m) => m.type === 'emergency_ticket' && m.community_id === selectedCommunityId
		)
	);

	async function handleMeshConnect() {
		meshConnecting = true;
		meshError = '';
		try {
			await connectToMesh();
		} catch (e) {
			meshError = e instanceof Error ? e.message : $t('mesh.connect_failed');
		} finally {
			meshConnecting = false;
		}
	}

	async function handleMeshDisconnect() {
		disconnectFromMesh();
	}

	async function createTicketViaMesh() {
		if (!selectedCommunityId || !newTicketTitle.trim()) return;
		creatingTicket = true;
		error = '';
		// One ID for both copies: the mesh broadcast (synced by whoever relays it)
		// and the queued REST create resolve to the same ticket on the server
		const clientId = crypto.randomUUID();
		try {
			await broadcastEmergencyTicket(
				selectedCommunityId,
				$user?.display_name ?? 'Unknown',
				{
					title: newTicketTitle,
					description: newTicketDesc,
					ticket_type: newTicketType as 'request' | 'offer' | 'emergency_ping',
					urgency: newTicketUrgency as 'low' | 'medium' | 'high' | 'critical',
					client_id: clientId
				}
			);
			// Also send (or queue, while offline) the REST create
			await api(`/communities/${selectedCommunityId}/tickets`, {
				method: 'POST',
				auth: true,
				body: {
					ticket_type: newTicketType,
					title: newTicketTitle,
					description: newTicketDesc,
					urgency: newTicketUrgency,
					client_id: clientId
				},
				offline: { label: $t('crisis.offline_ticket', { values: { title: newTicketTitle } }) }
			});
			showNewTicketForm = false;
			newTicketTitle = '';
			newTicketDesc = '';
			newTicketType = 'request';
			newTicketUrgency = 'medium';
		} catch (e) {
			error = e instanceof Error ? e.message : $t('mesh.broadcast_failed');
		} finally {
			creatingTicket = false;
		}
	}

	async function syncMeshMessages() {
		if (getMeshMessages().length === 0) return;
		syncing = true;
		try {
			// Keeps messages in the queue when the server reported per-message errors
			const result = await syncMeshMessagesToServer();
			await loadTickets();
			if (result && result.errors > 0) {
				error = $t('mesh.sync_result', {
					values: { synced: result.synced, duplicates: result.duplicates, errors: result.errors }
				});
			}
		} catch (e) {
			error = e instanceof Error ? e.message : $t('mesh.sync_messages_failed');
		} finally {
			syncing = false;
		}
	}

	const URGENCY_ORDER = ['critical', 'high', 'medium', 'low'];

	function ticketTypeLabel(type: string): string {
		const key = type === 'emergency_ping' ? 'ping' : type;
		return $t(`crisis.ticket_types.${key}`);
	}

	function ticketStatusLabel(status: string): string {
		return $t(`crisis.status_${status}`);
	}

	function urgencyColor(urgency: string): string {
		switch (urgency) {
			case 'critical': return 'var(--urgency-critical)';
			case 'high':     return 'var(--urgency-high)';
			case 'medium':   return 'var(--urgency-medium)';
			default:         return 'var(--urgency-low)';
		}
	}

	function statusColor(status: string): string {
		switch (status) {
			case 'open':        return 'var(--color-warning)';
			case 'in_progress': return 'var(--color-primary-text)';
			case 'resolved':    return 'var(--color-success)';
			default:            return 'var(--color-text-muted)';
		}
	}

	function isOverdue(due_at: string | null): boolean {
		return due_at !== null && new Date(due_at) < new Date();
	}

	/** Red when the community or the whole instance is in Red Sky. */
	function effectiveMode(c: CommunityOut): string {
		return c.effective_mode ?? c.mode ?? 'blue';
	}

	async function loadCommunities() {
		loadingCommunities = true;
		try {
			const data = await api<CommunityOut[]>('/communities/my/memberships', { auth: true });
			communities = data ?? [];
			if (communities.length > 0) {
				// Prefer a community that is actually in Red Sky
				const initial = communities.find((c) => effectiveMode(c) === 'red') ?? communities[0];
				selectedCommunityId = initial.id;
				selectedCommunityMode = effectiveMode(initial);
				await loadTickets();
			}
		} catch {
			error = $t('crisis.load_communities_failed');
		} finally {
			loadingCommunities = false;
		}
	}

	async function loadTickets() {
		if (!selectedCommunityId) return;
		loading = true;
		error = '';
		tickets = [];
		myRole = 'member';
		try {
			// Use the member-accessible tickets endpoint in the server's triage order
			// (urgency, age and the overdue escalation), with the maximum page size so
			// older critical tickets are not cut off during a crisis.
			const data = await api<{ items: Ticket[]; total: number }>(
				`/communities/${selectedCommunityId}/tickets?limit=100&sort=priority_desc`,
				{ auth: true }
			);
			tickets = data.items ?? [];

			// Determine current user's role in this community
			try {
				const members = await api<MemberInfo[]>(
					`/communities/${selectedCommunityId}/members`
				);
				const me = members.find((m) => m.user.id === $user?.id);
				myRole = me?.role ?? 'member';
			} catch {
				myRole = 'member';
			}

			const selectedCommunity = communities.find(c => c.id === selectedCommunityId);
			selectedCommunityMode = selectedCommunity ? effectiveMode(selectedCommunity) : 'blue';
		} catch {
			error = $t('crisis.load_tickets_failed');
		} finally {
			loading = false;
		}
	}

	async function onCommunityChange() {
		await loadTickets();
	}

	async function updateTicketStatus(ticketId: number, newStatus: string) {
		try {
			await api(`/communities/${selectedCommunityId}/tickets/${ticketId}`, {
				method: 'PATCH', auth: true, body: { status: newStatus }
			});
			await loadTickets();
		} catch (e) {
			error = e instanceof Error ? e.message : $t('crisis.detail.update_failed');
		}
	}

	async function createTicket() {
		if (!selectedCommunityId || !newTicketTitle.trim()) return;
		creatingTicket = true;
		error = '';
		try {
			await api(`/communities/${selectedCommunityId}/tickets`, {
				method: 'POST', auth: true,
				body: {
					ticket_type: newTicketType,
					title: newTicketTitle,
					description: newTicketDesc,
					urgency: newTicketUrgency,
					// Replays of a queued create return the same ticket
					client_id: crypto.randomUUID()
				},
				offline: { label: $t('crisis.offline_ticket', { values: { title: newTicketTitle } }) }
			});
			showNewTicketForm = false;
			newTicketTitle = '';
			newTicketDesc = '';
			newTicketType = 'request';
			newTicketUrgency = 'medium';
			if (get(isOnline)) {
				await loadTickets();
			}
		} catch (e) {
			error = e instanceof Error ? e.message : $t('crisis.create_failed');
		} finally {
			creatingTicket = false;
		}
	}

	const isAdminOrLeader = $derived(myRole === 'admin' || myRole === 'leader');

	// Keeps the server's triage order (overdue tickets escalate to the top)
	let filtered = $derived(
		tickets.filter((t) => {
			if (filterUrgency && t.urgency !== filterUrgency) return false;
			if (filterStatus === '') {
				return t.status !== 'resolved';
			}
			return t.status === filterStatus;
		})
	);

	let selectedCommunity = $derived(communities.find((c) => c.id === selectedCommunityId) ?? null);
	let isRed = $derived(selectedCommunityMode === 'red');

	/** Label for the left-hand tag: offers say OFFER, everything else its urgency. */
	function levelKind(ticketType: string, urgency: string): string {
		return ticketType === 'offer' ? 'offer' : urgency;
	}
	function levelLabel(ticketType: string, urgency: string): string {
		return (ticketType === 'offer' ? $t('crisis.ticket_types.offer') : $t(`crisis.priority.${urgency}`)).toUpperCase();
	}

	/** Short relative time ("3 min ago") in the current UI language. */
	function timeAgo(iso: string | number): string {
		const then = typeof iso === 'number' ? iso : new Date(iso).getTime();
		const mins = Math.round((Date.now() - then) / 60000);
		const rtf = new Intl.RelativeTimeFormat($locale ?? 'en', { numeric: 'auto', style: 'short' });
		if (Math.abs(mins) < 60) return rtf.format(-mins, 'minute');
		const hours = Math.round(mins / 60);
		if (Math.abs(hours) < 24) return rtf.format(-hours, 'hour');
		return rtf.format(-Math.round(hours / 24), 'day');
	}

	let newTicketTitleInput: HTMLInputElement | undefined = $state();

	/** The big Red Sky button: open the form as a critical emergency ping. */
	async function openPing() {
		newTicketType = 'emergency_ping';
		newTicketUrgency = 'critical';
		showNewTicketForm = true;
		await tick();
		newTicketTitleInput?.focus();
	}

	onMount(async () => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}
		await loadCommunities();
	});
</script>

<svelte:head>
	<title>{$t('nav.emergency')} – NeighbourGood</title>
</svelte:head>

<div class="emergency-page" class:is-red={isRed}>
	{#if isRed && selectedCommunity}
		<div class="redband" role="status">
			<strong><Icon name="alert" size={18} /> {$t('crisis.red_active')}</strong>
			<span>{$t('crisis.red_active_detail', { values: { community: selectedCommunity.name } })}</span>
		</div>
	{/if}

	<div class="page-header">
		<h1>{$t('crisis.title')}</h1>
		<p class="subtitle">{$t('crisis.page_subtitle')}</p>
	</div>

	{#if loadingCommunities}
		<div class="skeleton-stack" role="status" aria-busy="true">
			<span class="sr-only">{$t('crisis.loading_communities')}</span>
			<div class="skeleton skeleton-card" style="height: 5rem"></div>
			<div class="skeleton skeleton-card" style="height: 6rem"></div>
			<div class="skeleton skeleton-card" style="height: 6rem"></div>
		</div>
	{:else if communities.length === 0}
		<div class="empty-state">
			<span class="empty-icon"><Icon name="users" size={26} /></span>
			<p>{$t('crisis.no_member')}</p>
			<a href="/communities" class="btn btn-primary">{$t('crisis.find_community_link')}</a>
		</div>
	{:else}
		{#if isRed}
			{#if !$isOnline || $meshStatus === 'connected'}
				<p class="meshline">
					<span class="meshline-icon"><Icon name="radio" size={18} /></span>
					<span>
						{#if !$isOnline}<b>{$t('crisis.no_internet')}</b>{/if}
						{#if $meshStatus === 'connected'}
							{$t('crisis.mesh_reachable', { values: { count: $meshPeerCount } })}
						{:else}
							{$t('crisis.offline_saved')}
						{/if}
					</span>
				</p>
			{/if}

			<button class="ping" onclick={openPing}>
				<Icon name="alert" size={20} />
				{$t('crisis.send_ping')}
			</button>
		{/if}

		{#if $meshEnabled && isBluetoothSupported() && isRed}
			<div class="mesh-bar">
				<span class="mesh-dot" class:mesh-connected={$meshStatus === 'connected'} class:mesh-scanning={$meshStatus === 'scanning' || $meshStatus === 'connecting'} class:mesh-reconnecting={$meshStatus === 'reconnecting'}></span>
				<span class="mesh-label">
					{#if $meshStatus === 'connected'}
						{$meshDeviceName ? $t('mesh.connected_to', { values: { device: $meshDeviceName } }) : $t('mesh.connected')}
						<span class="mesh-peers">{$t('mesh.peer_count', { values: { count: $meshPeerCount } })}</span>
					{:else if $meshStatus === 'reconnecting'}
						{$t('mesh.reconnecting')}
					{:else if $meshStatus === 'scanning' || $meshStatus === 'connecting'}
						{$t('mesh.scanning')}
					{:else}
						{$t('mesh.disconnected')}
					{/if}
				</span>
				<span class="mesh-actions">
					{#if $meshStatus === 'disconnected'}
						<button class="btn btn-ghost btn-sm" class:is-loading={meshConnecting} onclick={handleMeshConnect} disabled={meshConnecting}>
							{meshConnecting ? $t('mesh.connecting') : $t('mesh.connect')}
						</button>
					{:else if $meshStatus === 'connected'}
						<button class="btn btn-ghost btn-sm" onclick={handleMeshDisconnect}>{$t('mesh.disconnect')}</button>
					{/if}
					{#if $isOnline && $meshMessages.length > 0}
						<button class="btn btn-ghost btn-sm" class:is-loading={syncing} onclick={syncMeshMessages} disabled={syncing}>
							{syncing ? $t('mesh.syncing') : $t('mesh.sync_messages', { values: { count: $meshMessages.length } })}
						</button>
					{/if}
					<a href="/mesh" class="btn btn-ghost btn-sm">{$t('settings.mesh_open_dashboard')}</a>
				</span>
				{#if meshError}
					<p class="mesh-error">{meshError}</p>
				{/if}
			</div>
		{/if}

		{#if showNewTicketForm}
			<div class="card new-ticket-form">
				<h2>{newTicketType === 'emergency_ping' ? $t('crisis.send_ping') : $t('crisis.form_title')}</h2>
				<div class="field-row">
					<label class="field">
						<span>{$t('crisis.form_type')}</span>
						<select bind:value={newTicketType}>
							<option value="request">{$t('crisis.ticket_types.request')}</option>
							<option value="offer">{$t('crisis.ticket_types.offer')}</option>
							{#if isRed}
								<option value="emergency_ping">{$t('crisis.ticket_types.ping')}</option>
							{/if}
						</select>
					</label>
					<label class="field">
						<span>{$t('crisis.form_urgency')}</span>
						<select bind:value={newTicketUrgency}>
							<option value="low">{$t('crisis.priority.low')}</option>
							<option value="medium">{$t('crisis.priority.medium')}</option>
							<option value="high">{$t('crisis.priority.high')}</option>
							<option value="critical">{$t('crisis.priority.critical')}</option>
						</select>
					</label>
				</div>
				<label class="field">
					<span>{$t('crisis.form_title_field')}</span>
					<input type="text" bind:this={newTicketTitleInput} bind:value={newTicketTitle} placeholder={$t('crisis.title_placeholder')} maxlength="300" />
				</label>
				<label class="field">
					<span>{$t('crisis.form_description')}</span>
					<textarea bind:value={newTicketDesc} rows="3" placeholder={$t('crisis.description_placeholder')} maxlength="5000"></textarea>
				</label>
				<div class="form-actions">
					{#if $meshEnabled && !$isOnline && $meshStatus === 'connected'}
						<button class="btn btn-primary" class:is-loading={creatingTicket} onclick={createTicketViaMesh} disabled={creatingTicket || !newTicketTitle.trim()}>
							{creatingTicket ? $t('mesh.syncing') : $t('mesh.broadcast_ticket')}
						</button>
					{:else}
						<button class="btn btn-primary" class:is-loading={creatingTicket} onclick={createTicket} disabled={creatingTicket || !newTicketTitle.trim()}>
							{creatingTicket ? $t('crisis.creating_ticket') : $t('crisis.create_ticket')}
						</button>
					{/if}
					<button class="btn btn-ghost" onclick={() => (showNewTicketForm = false)}>{$t('common.cancel')}</button>
				</div>
			</div>
		{/if}

		{#if $meshEnabled && communityMeshTickets.length > 0}
			<section class="list-section">
				<h2 class="list-heading">{$t('mesh.mesh_tickets')} <span class="list-count">{$t('mesh.via_mesh')}</span></h2>
				<div class="tk-panel">
					{#each communityMeshTickets as msg (msg.id)}
						{@const kind = levelKind(String(msg.data.ticket_type ?? 'request'), String(msg.data.urgency ?? 'medium'))}
						<div class="tk">
							<span class="lvl lvl-{kind}">{levelLabel(String(msg.data.ticket_type ?? 'request'), String(msg.data.urgency ?? 'medium'))}</span>
							<span class="tk-main">
								<strong>{msg.data.title ?? $t('crisis.untitled')}</strong>
								<span class="tk-meta">{ticketTypeLabel(String(msg.data.ticket_type ?? 'request'))} · {$t('crisis.by_author', { values: { author: msg.sender_name } })} · {$t('mesh.badge')}</span>
								{#if msg.data.description}<span class="tk-desc">{msg.data.description}</span>{/if}
							</span>
							<time>{timeAgo(msg.ts)}</time>
						</div>
					{/each}
				</div>
			</section>
		{/if}

		<section class="list-section">
			<div class="list-head">
				<h2 class="list-heading">{$t('crisis.open_requests')} {#if !loading && !error}<span class="list-count">{filtered.length}</span>{/if}</h2>
				<button class="btn btn-sm" class:btn-primary={!isRed} class:btn-ghost={isRed} onclick={() => { newTicketType = 'request'; newTicketUrgency = 'medium'; showNewTicketForm = !showNewTicketForm; }} aria-expanded={showNewTicketForm}>
					{$t('crisis.new_ticket')}
				</button>
			</div>

			<div class="filters">
				{#if communities.length > 1}
					<label class="filter">
						<span class="sr-only">{$t('crisis.filter_community')}</span>
						<select id="community-select" class="input" bind:value={selectedCommunityId} onchange={onCommunityChange}>
							{#each communities as c}
								<option value={c.id}>{c.name}{effectiveMode(c) === 'red' ? ` · ${$t('nav.crisis_mode')}` : ''}</option>
							{/each}
						</select>
					</label>
				{/if}
				<label class="filter">
					<span class="sr-only">{$t('crisis.filter_urgency')}</span>
					<select id="urgency-filter" class="input" bind:value={filterUrgency}>
						<option value="">{$t('crisis.filter_urgency')}: {$t('crisis.filter_all')}</option>
						{#each URGENCY_ORDER as u}
							<option value={u}>{$t(`crisis.priority.${u}`)}</option>
						{/each}
					</select>
				</label>
				<label class="filter">
					<span class="sr-only">{$t('crisis.filter_status')}</span>
					<select id="status-filter" class="input" bind:value={filterStatus}>
						<option value="">{$t('crisis.filter_open_excl')}</option>
						<option value="open">{$t('crisis.filter_open')}</option>
						<option value="in_progress">{$t('crisis.filter_in_progress')}</option>
						<option value="resolved">{$t('crisis.filter_resolved')}</option>
					</select>
				</label>
			</div>

			{#if error}
				<div class="alert alert-error">{error}</div>
			{:else if loading}
				<div class="skeleton-stack" role="status" aria-busy="true">
					<span class="sr-only">{$t('crisis.loading_tickets')}</span>
					{#each [1, 2, 3] as n (n)}
						<div class="skeleton skeleton-card" style="height: 4.5rem" aria-hidden="true"></div>
					{/each}
				</div>
			{:else if filtered.length === 0}
				<div class="empty-state">
					<span class="empty-icon"><Icon name="inbox" size={26} /></span>
					<p>{tickets.length === 0 ? $t('crisis.no_tickets_yet') : $t('crisis.no_tickets')}</p>
				</div>
			{:else}
				<div class="tk-panel">
					{#each filtered as ticket (ticket.id)}
						{@const kind = levelKind(ticket.ticket_type, ticket.urgency)}
						<a href="/triage/{ticket.id}?community={selectedCommunityId}" class="tk" class:overdue={ticket.status !== 'resolved' && isOverdue(ticket.due_at)}>
							<span class="lvl lvl-{kind}">{levelLabel(ticket.ticket_type, ticket.urgency)}</span>
							<span class="tk-main">
								<strong>{ticket.title}</strong>
								<span class="tk-meta">
									{ticketTypeLabel(ticket.ticket_type)} · <span style="color: {statusColor(ticket.status)}">{ticketStatusLabel(ticket.status)}</span>
									· {ticket.author.display_name}
									{#if ticket.assigned_to}
										<Icon name="arrow-right" size={12} class="flip-rtl" /> {ticket.assigned_to.display_name}
									{:else}
										· <em>{$t('crisis.unassigned')}</em>
									{/if}
									{#if ticket.status !== 'resolved' && isOverdue(ticket.due_at)}
										· <span class="tk-overdue">{$t('crisis.overdue')}</span>
									{/if}
									{#if isAdminOrLeader && ticket.triage_score !== undefined}
										· <span title={$t('crisis.detail.triage_score')}>{$t('crisis.score', { values: { n: ticket.triage_score } })}</span>
									{/if}
								</span>
								{#if ticket.description}
									<span class="tk-desc">{ticket.description}</span>
								{/if}
								{#if ticket.status !== 'resolved' && (isAdminOrLeader || ticket.author.id === $user?.id)}
									<span class="tk-actions">
										{#if ticket.status === 'open'}
											<button class="btn btn-ghost btn-sm" onclick={(e) => { e.preventDefault(); e.stopPropagation(); updateTicketStatus(ticket.id, 'in_progress'); }}>{$t('crisis.start_ticket')}</button>
										{/if}
										<button class="btn btn-ghost btn-sm" onclick={(e) => { e.preventDefault(); e.stopPropagation(); updateTicketStatus(ticket.id, 'resolved'); }}>{$t('crisis.resolve_ticket')}</button>
									</span>
								{/if}
							</span>
							<time datetime={ticket.created_at}>{timeAgo(ticket.created_at)}</time>
						</a>
					{/each}
				</div>
			{/if}
		</section>
	{/if}
</div>

<style>
	.emergency-page {
		max-width: 820px;
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
	}

	.page-header {
		display: block;
		margin: 0;
	}

	.page-header h1 {
		font-size: 1.9rem;
		font-weight: 400;
		margin-bottom: 0.2rem;
	}

	.subtitle {
		color: var(--color-text-subtle);
		font-size: 0.85rem;
	}

	/* ── Red Sky banner, mesh line and ping button (as in the redesign mockup) ── */

	.redband {
		display: grid;
		gap: 0.2rem;
		padding: 0.9rem 1.1rem;
		border-radius: var(--radius-md, 0.75rem);
		background: var(--color-primary-light);
		border: 1px solid var(--color-primary);
	}

	.redband strong {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 1rem;
		font-weight: 700;
		color: var(--color-primary-text);
	}

	.redband span {
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.meshline {
		display: flex;
		gap: 0.6rem;
		align-items: flex-start;
		margin: 0;
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.meshline b {
		color: var(--color-text);
		font-weight: 600;
	}

	.meshline-icon {
		color: var(--color-accent);
		display: inline-flex;
		margin-top: 1px;
	}

	.ping {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.6rem;
		width: 100%;
		min-height: 3.25rem;
		padding: 0.9rem 1rem;
		border: 0;
		border-radius: var(--radius-md, 0.75rem);
		background: var(--color-primary);
		color: var(--color-on-primary);
		font: inherit;
		font-size: 1.05rem;
		font-weight: 700;
		cursor: pointer;
	}

	.ping:hover {
		background: var(--color-primary-hover);
	}

	.ping:focus-visible {
		outline: 3px solid var(--focus-ring);
		outline-offset: 2px;
	}

	/* ── Mesh connection bar ─────────────────────────── */

	.mesh-bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem 0.75rem;
		font-size: 0.82rem;
		color: var(--color-text-muted);
	}

	.mesh-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--color-text-subtle);
		flex-shrink: 0;
	}

	.mesh-dot.mesh-connected { background: var(--color-success); }
	.mesh-dot.mesh-scanning { background: var(--color-warning); animation: pulse 1.2s infinite; }
	.mesh-dot.mesh-reconnecting { background: var(--color-warning); animation: pulse 0.8s infinite; }

	.mesh-label { color: var(--color-text); font-weight: 500; }
	.mesh-peers { color: var(--color-text-subtle); margin-inline-start: 0.35rem; font-weight: 400; }

	.mesh-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
		margin-inline-start: auto;
	}

	.mesh-error {
		flex-basis: 100%;
		font-size: 0.82rem;
		color: var(--color-error);
		margin: 0;
	}

	/* ── New ticket form ─────────────────────────────── */

	.new-ticket-form {
		padding: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 0.85rem;
	}

	.new-ticket-form h2 {
		font-size: 1.05rem;
		font-weight: 600;
		margin: 0;
	}

	.form-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	/* ── Request list ────────────────────────────────── */

	.list-section {
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
	}

	.list-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
	}

	.list-heading {
		font-family: var(--font-body);
		font-size: 0.9rem;
		font-weight: 600;
		margin: 0;
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
	}

	.list-count {
		font-size: 0.8rem;
		font-weight: 500;
		color: var(--color-primary-text);
	}

	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.filter select {
		font-size: 0.82rem;
		padding-block: 0.35rem;
		min-height: 2.25rem;
		color: var(--color-text-muted);
	}

	.tk-panel {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md, 0.75rem);
		overflow: hidden;
	}

	.tk {
		display: grid;
		/* fixed label column so titles line up across rows */
		grid-template-columns: 6rem minmax(0, 1fr) auto;
		gap: 0.25rem 0.75rem;
		align-items: start;
		padding: 0.8rem 1rem;
		border-top: 1px solid var(--color-border);
		color: var(--color-text);
		text-decoration: none;
	}

	.tk:first-child { border-top: 0; }
	a.tk:hover { background: var(--color-surface-raised); text-decoration: none; }
	a.tk:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
	.tk.overdue { box-shadow: inset 3px 0 0 var(--color-error); }

	/* Urgency is a text label first; colour only reinforces it. */
	.lvl {
		font-family: var(--font-mono, ui-monospace, monospace);
		font-size: 0.66rem;
		font-weight: 600;
		letter-spacing: 0.05em;
		padding: 0.15rem 0.4rem;
		border-radius: 4px;
		border: 1px solid currentColor;
		margin-top: 0.1rem;
		justify-self: start;
		max-width: 100%;
		overflow-wrap: anywhere;
	}

	.lvl-critical { color: var(--urgency-critical); background: var(--color-error-bg); }
	.lvl-high { color: var(--urgency-high); }
	.lvl-medium { color: var(--urgency-medium); }
	.lvl-low { color: var(--urgency-low); }
	.lvl-offer { color: var(--color-success); }

	.tk-main {
		display: grid;
		gap: 0.15rem;
		min-width: 0;
	}

	.tk-main strong {
		font-weight: 600;
		font-size: 0.92rem;
	}

	.tk-meta {
		font-size: 0.78rem;
		color: var(--color-text-subtle);
		display: inline-flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.25rem;
	}

	.tk-overdue { color: var(--color-error); font-weight: 600; }

	.tk-desc {
		font-size: 0.82rem;
		color: var(--color-text-muted);
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	.tk-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
		margin-top: 0.15rem;
		margin-inline-start: -0.6rem; /* ghost buttons: align their text with the title */
	}

	.tk time {
		font-family: var(--font-mono, ui-monospace, monospace);
		font-size: 0.72rem;
		color: var(--color-text-subtle);
		white-space: nowrap;
	}

	@media (max-width: 480px) {
		.tk { grid-template-columns: 5.25rem minmax(0, 1fr); padding-inline: 0.85rem; }
		.tk time { grid-column: 2; }
		.mesh-actions { margin-inline-start: 0; }
	}
</style>
