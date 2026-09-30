<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isLoggedIn } from '$lib/stores/auth';
	import { isOnline } from '$lib/stores/offline';
	import { t } from 'svelte-i18n';
	import Icon from '$lib/components/Icon.svelte';
	import { loadOfflineTickets, type OfflineTicket } from '$lib/mesh-triage-db';
	import { meshEnabled, MESH_COMMUNITY_KEY } from '$lib/stores/mesh-settings';

	let tickets = $state<OfflineTicket[]>([]);
	let loading = $state(true);
	let expandedTicket = $state<string | null>(null);

	onMount(async () => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}
		if (!$meshEnabled) {
			loading = false;
			return;
		}
		// Scoped to the community chosen on the mesh page (remembered for offline use)
		let communityId: number | undefined;
		try {
			communityId = Number(localStorage.getItem(MESH_COMMUNITY_KEY)) || undefined;
		} catch {
			communityId = undefined;
		}
		try {
			tickets = await loadOfflineTickets(communityId);
		} catch {
			// IndexedDB unavailable
		}
		loading = false;
	});

	function formatTime(ts: number): string {
		return new Date(ts).toLocaleString(undefined, {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function urgencyColor(urgency: string): string {
		switch (urgency) {
			case 'critical': return 'var(--color-error)';
			case 'high': return 'var(--color-warning)';
			case 'medium': return 'var(--color-primary-text)';
			default: return 'var(--color-text-muted)';
		}
	}

	function toggleTicket(id: string) {
		expandedTicket = expandedTicket === id ? null : id;
	}
</script>

<svelte:head>
	<title>{$t('mesh.offline_triage')} — NeighbourGood</title>
</svelte:head>

<div class="triage-page">
	<header class="triage-header">
		<a href="/mesh" class="back-link"><Icon name="arrow-left" size={16} class="flip-rtl" /> {$t('mesh.title')}</a>
		<h1>{$t('mesh.offline_triage')}</h1>
		<p class="triage-subtitle">{$t('mesh.offline_triage_subtitle')}</p>
		{#if !$isOnline}
			<span class="badge badge-warning offline-badge">{$t('mesh.viewing_offline')}</span>
		{/if}
	</header>

	{#if !$meshEnabled}
		<div class="empty-state">
			<span class="empty-icon"><Icon name="radio" size={26} /></span>
			<p>{$t('mesh.disabled_notice')}</p>
			<a href="/settings" class="btn btn-primary">{$t('mesh.enable_in_settings')}</a>
		</div>
	{:else if loading}
		<div class="skeleton-stack" role="status" aria-busy="true">
			<span class="sr-only">{$t('common.loading')}</span>
			{#each [1, 2, 3] as n (n)}
				<div class="skeleton skeleton-card" style="height: 5.5rem" aria-hidden="true"></div>
			{/each}
		</div>
	{:else if tickets.length === 0}
		<div class="empty-state">
			<span class="empty-icon"><Icon name="inbox" size={26} /></span>
			<p>{$t('mesh.no_offline_tickets')}</p>
		</div>
	{:else}
		<div class="ticket-list">
			{#each tickets as ticket (ticket.id)}
				<button class="card card-interactive ticket-card" onclick={() => toggleTicket(ticket.id)}>
					<div class="ticket-header">
						<span class="badge badge-caps ticket-urgency" style="--u: {urgencyColor(ticket.urgency)}">{ticket.urgency}</span>
						<span class="ticket-type">{ticket.ticket_type}</span>
						{#if ticket.server_id}
							<span class="badge badge-success synced-badge">{$t('mesh.synced_to_server')}</span>
						{:else}
							<span class="badge badge-primary mesh-badge">{$t('mesh.via_mesh')}</span>
						{/if}
					</div>
					<h3 class="ticket-title">{ticket.title}</h3>
					<div class="ticket-meta">
						<span>{$t('common.by')} {ticket.sender_name}</span>
						<span>{formatTime(ticket.ts)}</span>
					</div>
					{#if expandedTicket === ticket.id}
						<div class="ticket-body">
							{#if ticket.description}
								<p>{ticket.description}</p>
							{/if}
							{#if ticket.comments.length > 0}
								<div class="comments-section">
									<h4>{$t('mesh.comments')} ({ticket.comments.length})</h4>
									{#each ticket.comments as comment (comment.id)}
										<div class="comment">
											<span class="comment-author">{comment.sender_name}</span>
											<span class="comment-time">{formatTime(comment.ts)}</span>
											<p class="comment-body">{comment.body}</p>
										</div>
									{/each}
								</div>
							{/if}
						</div>
					{/if}
				</button>
			{/each}
		</div>
	{/if}
</div>

<style>
	.triage-page {
		max-width: 700px;
		margin: 0 auto;
	}

	.triage-header {
		margin-bottom: 1.5rem;
	}

	.back-link {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		font-size: 0.85rem;
	}

	.triage-header h1 {
		font-family: var(--font-heading);
		font-weight: 400;
		font-size: 1.6rem;
		color: var(--color-text);
		margin: 0.25rem 0 0;
	}

	.triage-subtitle {
		color: var(--color-text-muted);
		font-size: 0.9rem;
		margin-top: 0.25rem;
	}

	.offline-badge {
		margin-top: 0.5rem;
	}

	.ticket-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.ticket-card {
		display: block;
		width: 100%;
		text-align: start;
		padding: 1rem;
		cursor: pointer;
		font: inherit;
		color: inherit;
	}

	.ticket-card:hover {
		border-color: var(--color-primary);
	}

	.ticket-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.4rem;
	}

	.ticket-urgency {
		color: var(--u);
		background: color-mix(in srgb, var(--u) 14%, transparent);
		border-color: color-mix(in srgb, var(--u) 45%, transparent);
	}

	.ticket-type {
		font-size: 0.78rem;
		color: var(--color-text-muted);
		font-weight: 500;
	}

	.mesh-badge,
	.synced-badge {
		margin-inline-start: auto;
	}

	.ticket-title {
		font-size: 1rem;
		font-weight: 600;
		color: var(--color-text);
		margin: 0.25rem 0;
	}

	.ticket-meta {
		display: flex;
		justify-content: space-between;
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	.ticket-body {
		margin-top: 0.75rem;
		padding-top: 0.75rem;
		border-top: 1px solid var(--color-border);
		font-size: 0.88rem;
		color: var(--color-text);
		animation: fadeIn 0.15s ease;
	}

	@keyframes fadeIn {
		from { opacity: 0; }
		to { opacity: 1; }
	}

	.ticket-body p {
		margin: 0 0 0.5rem;
	}

	.comments-section {
		margin-top: 0.75rem;
	}

	.comments-section h4 {
		font-size: 0.85rem;
		font-weight: 600;
		margin: 0 0 0.5rem;
		color: var(--color-text);
	}

	.comment {
		padding: 0.5rem 0;
		border-bottom: 1px solid var(--color-border);
	}

	.comment:last-child {
		border-bottom: none;
	}

	.comment-author {
		font-size: 0.82rem;
		font-weight: 600;
		color: var(--color-text);
	}

	.comment-time {
		font-size: 0.75rem;
		color: var(--color-text-muted);
		margin-inline-start: 0.5rem;
	}

	.comment-body {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		margin: 0.2rem 0 0;
	}
</style>
