<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isLoggedIn } from '$lib/stores/auth';
	import { isOnline } from '$lib/stores/offline';
	import { t } from 'svelte-i18n';
	import { loadOfflineTickets, type OfflineTicket } from '$lib/mesh-triage-db';

	let tickets = $state<OfflineTicket[]>([]);
	let loading = $state(true);
	let expandedTicket = $state<string | null>(null);

	onMount(async () => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}
		try {
			tickets = await loadOfflineTickets();
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
			case 'medium': return 'var(--color-primary)';
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
		<a href="/mesh" class="back-link">&larr; {$t('mesh.title')}</a>
		<h1>{$t('mesh.offline_triage')}</h1>
		<p class="triage-subtitle">{$t('mesh.offline_triage_subtitle')}</p>
		{#if !$isOnline}
			<span class="offline-badge">{$t('mesh.viewing_offline')}</span>
		{/if}
	</header>

	{#if loading}
		<p class="loading">{$t('common.loading')}</p>
	{:else if tickets.length === 0}
		<div class="empty-state">
			<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--color-text-muted)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
			<p>{$t('mesh.no_offline_tickets')}</p>
		</div>
	{:else}
		<div class="ticket-list">
			{#each tickets as ticket (ticket.id)}
				<button class="ticket-card" onclick={() => toggleTicket(ticket.id)}>
					<div class="ticket-header">
						<span class="ticket-urgency" style="background: {urgencyColor(ticket.urgency)}">{ticket.urgency}</span>
						<span class="ticket-type">{ticket.ticket_type}</span>
						{#if ticket.server_id}
							<span class="synced-badge">{$t('mesh.synced_to_server')}</span>
						{:else}
							<span class="mesh-badge">{$t('mesh.via_mesh')}</span>
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
		font-size: 0.85rem;
		color: var(--color-primary);
		text-decoration: none;
	}

	.back-link:hover {
		text-decoration: underline;
	}

	.triage-header h1 {
		font-family: Georgia, 'Times New Roman', serif;
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
		display: inline-block;
		margin-top: 0.5rem;
		font-size: 0.78rem;
		font-weight: 600;
		color: var(--color-warning);
		background: var(--color-warning-bg, rgba(245, 158, 11, 0.1));
		padding: 0.2rem 0.6rem;
		border-radius: 999px;
	}

	.loading {
		color: var(--color-text-muted);
		text-align: center;
	}

	.empty-state {
		text-align: center;
		padding: 2rem;
		color: var(--color-text-muted);
	}

	.empty-state svg {
		margin-bottom: 0.75rem;
	}

	.ticket-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.ticket-card {
		display: block;
		width: 100%;
		text-align: left;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		padding: 1rem;
		cursor: pointer;
		transition: border-color var(--transition-fast);
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
		font-size: 0.7rem;
		font-weight: 700;
		color: white;
		padding: 0.1rem 0.5rem;
		border-radius: 999px;
		text-transform: uppercase;
	}

	.ticket-type {
		font-size: 0.78rem;
		color: var(--color-text-muted);
		font-weight: 500;
	}

	.mesh-badge {
		margin-left: auto;
		font-size: 0.7rem;
		font-weight: 600;
		color: var(--color-primary);
		background: var(--color-primary-light);
		padding: 0.1rem 0.5rem;
		border-radius: 999px;
	}

	.synced-badge {
		margin-left: auto;
		font-size: 0.7rem;
		font-weight: 600;
		color: var(--color-success);
		background: var(--color-success-bg, rgba(16, 185, 129, 0.1));
		padding: 0.1rem 0.5rem;
		border-radius: 999px;
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
		margin-left: 0.5rem;
	}

	.comment-body {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		margin: 0.2rem 0 0;
	}
</style>
