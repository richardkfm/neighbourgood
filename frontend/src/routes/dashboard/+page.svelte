<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isLoggedIn, user } from '$lib/stores/auth';
	import { api } from '$lib/api';
	import { t } from 'svelte-i18n';

	interface DashboardData {
		resources_count: number;
		skills_count: number;
		bookings_count: number;
		messages_unread_count: number;
		reputation_score: number;
		reputation_level: string;
	}

	interface BookingItem {
		id: number;
		resource_title: string;
		borrower_name: string;
		start_date: string;
		end_date: string;
		status: string;
		is_owner: boolean;
	}

	interface CommunityMembership {
		id: number;
		name: string;
		mode: string;
	}

	interface TicketItem {
		id: number;
		title: string;
		ticket_type: string;
		status: string;
		urgency: string;
		community_id: number;
		assigned_to: { id: number; display_name: string } | null;
	}

	let dashboard: DashboardData | null = $state(null);
	let pendingIncoming: BookingItem[] = $state([]);
	let pendingOutgoing: BookingItem[] = $state([]);
	let communities: CommunityMembership[] = $state([]);
	let assignedTickets: TicketItem[] = $state([]);
	let loading = $state(true);
	let error = $state('');

	onMount(async () => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}

		try {
			const [dashData, commData] = await Promise.all([
				api<DashboardData>('/users/me/dashboard', { auth: true }),
				api<CommunityMembership[]>('/communities/my/memberships', { auth: true })
			]);
			dashboard = dashData;
			communities = commData;

			// Fetch pending bookings for "needs attention" section
			const bookingsData = await api<{ items: any[] }>('/bookings?status=pending', { auth: true });
			if (bookingsData.items) {
				for (const b of bookingsData.items) {
					const item: BookingItem = {
						id: b.id,
						resource_title: b.resource?.title ?? `Resource #${b.resource_id}`,
						borrower_name: b.borrower?.display_name ?? 'Someone',
						start_date: b.start_date,
						end_date: b.end_date,
						status: b.status,
						is_owner: b.borrower_id !== $user?.id
					};
					if (item.is_owner) {
						pendingIncoming.push(item);
					} else {
						pendingOutgoing.push(item);
					}
				}
				// Trigger reactivity
				pendingIncoming = [...pendingIncoming];
				pendingOutgoing = [...pendingOutgoing];
			}

			// Load assigned tickets from Red Sky communities
			const redCommunities = commData.filter(c => c.mode === 'red');
			const collected: TicketItem[] = [];
			for (const c of redCommunities) {
				try {
					const data = await api<{ items: TicketItem[] }>(
						`/communities/${c.id}/tickets`, { auth: true }
					);
					for (const t of data.items ?? []) {
						if (t.assigned_to?.id === $user?.id && t.status !== 'resolved') {
							collected.push(t);
						}
					}
				} catch {
					// skip community on failure
				}
			}
			assignedTickets = collected;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load dashboard';
		} finally {
			loading = false;
		}
	});

	const hasPendingActions = $derived(
		pendingIncoming.length > 0 ||
		pendingOutgoing.length > 0 ||
		(dashboard?.messages_unread_count ?? 0) > 0
	);

	// Reputation tier thresholds (mirrors backend routers/users.py)
	const TIERS = [
		{ name: 'Newcomer', min: 0, max: 9 },
		{ name: 'Neighbour', min: 10, max: 39 },
		{ name: 'Helper', min: 40, max: 99 },
		{ name: 'Trusted', min: 100, max: 199 },
		{ name: 'Pillar', min: 200, max: Infinity }
	];

	// Map API tier name → i18n key
	const TIER_KEYS: Record<string, string> = {
		Newcomer: 'dashboard.level_newcomer',
		Neighbour: 'dashboard.level_neighbour',
		Helper: 'dashboard.level_helper',
		Trusted: 'dashboard.level_trusted',
		Pillar: 'dashboard.level_pillar'
	};

	const repProgress = $derived((() => {
		if (!dashboard) return null;
		const score = dashboard.reputation_score;
		const idx = TIERS.findIndex(t => score >= t.min && (t.max === Infinity || score <= t.max));
		const current = TIERS[idx];
		const next = TIERS[idx + 1] ?? null;
		if (!next) return { ptsToNext: 0, progressPct: 100, nextName: null };
		const range = next.min - current.min;
		const progressPct = Math.min(100, Math.round(((score - current.min) / range) * 100));
		return { ptsToNext: next.min - score, progressPct, nextName: next.name };
	})());
</script>

<svelte:head>
	<title>Home - NeighbourGood</title>
</svelte:head>

<div class="dashboard">
	<h1>{$t('dashboard.welcome', { values: { name: $user?.display_name ?? '' } })}</h1>

	{#if loading}
		<div class="loading">{$t('dashboard.loading')}</div>
	{:else if error}
		<div class="alert alert-error">{error}</div>
	{:else}
		<!-- Onboarding nudge -->
		{#if communities.length === 0}
			<div class="nudge-banner">
				<div class="nudge-icon">
					<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
				</div>
				<div class="nudge-text">
					<strong>{$t('dashboard.join_title')}</strong>
					<span>{$t('dashboard.join_desc')}</span>
				</div>
				<a href="/onboarding" class="nudge-btn">{$t('dashboard.find_community')}</a>
			</div>
		{/if}

		<!-- My community -->
		{#if communities.length > 0}
			<section>
				<h2>{$t('dashboard.your_community')}</h2>
				{#each communities.slice(0, 1) as c (c.id)}
					<a href="/communities/{c.id}" class="community-card-link">
						<div class="community-card-inner">
							<div class="community-info">
								<h3>{c.name}</h3>
								{#if c.mode === 'red'}
									<span class="community-crisis-badge">{$t('dashboard.crisis_active')}</span>
								{/if}
							</div>
							<span class="community-arrow">→</span>
						</div>
					</a>
				{/each}
			</section>
		{/if}

		<!-- Assigned emergency tickets (Red Sky only) -->
		{#if assignedTickets.length > 0}
			<section class="crisis-tickets-section">
				<h2>{$t('dashboard.assigned_tickets')}</h2>
				<div class="assigned-tickets-list">
					{#each assignedTickets as ticket}
						<a href="/triage/{ticket.id}" class="assigned-ticket-item">
							<span class="ticket-urgency-dot urgency-{ticket.urgency}"></span>
							<span class="assigned-ticket-title">{ticket.title}</span>
							<span class="assigned-ticket-meta">{ticket.ticket_type.replace('_', ' ')} · {ticket.status.replace('_', ' ')}</span>
							<span class="assigned-ticket-arrow">→</span>
						</a>
					{/each}
				</div>
			</section>
		{/if}

		<!-- Needs your attention -->
		{#if hasPendingActions}
			<section class="attention-section">
				<h2>{$t('dashboard.needs_attention')}</h2>
				<div class="attention-list">
					{#each pendingIncoming as booking}
						<a href="/bookings" class="attention-item">
							<span class="attention-dot attention-dot-warning"></span>
							<span class="attention-text">
								{$t('dashboard.wants_to_borrow', { values: { name: booking.borrower_name, resource: booking.resource_title } })}
							</span>
							<span class="attention-action">{$t('dashboard.review')}</span>
						</a>
					{/each}
					{#each pendingOutgoing as booking}
						<a href="/bookings" class="attention-item">
							<span class="attention-dot attention-dot-info"></span>
							<span class="attention-text">
								{$t('dashboard.request_waiting', { values: { resource: booking.resource_title } })}
							</span>
							<span class="attention-action">{$t('dashboard.view')}</span>
						</a>
					{/each}
					{#if (dashboard?.messages_unread_count ?? 0) > 0}
						<a href="/messages" class="attention-item">
							<span class="attention-dot attention-dot-primary"></span>
							<span class="attention-text">
								{$t('messages.unread', { values: { count: dashboard?.messages_unread_count } })}
							</span>
							<span class="attention-action">{$t('dashboard.read')}</span>
						</a>
					{/if}
				</div>
			</section>
		{/if}

		<!-- Quick stats -->
		{#if dashboard}
			<section>
				<h2>{$t('dashboard.your_activity')}</h2>
				<div class="overview-grid">
					<a href="/resources" class="overview-card">
						<div class="card-icon">📦</div>
						<div class="card-content">
							<div class="card-label">{$t('dashboard.stat_resources')}</div>
							<div class="card-value">{dashboard.resources_count}</div>
						</div>
					</a>

					<a href="/skills" class="overview-card">
						<div class="card-icon">🎯</div>
						<div class="card-content">
							<div class="card-label">{$t('dashboard.stat_skills')}</div>
							<div class="card-value">{dashboard.skills_count}</div>
						</div>
					</a>

					<a href="/bookings" class="overview-card">
						<div class="card-icon">📋</div>
						<div class="card-content">
							<div class="card-label">{$t('dashboard.stat_bookings')}</div>
							<div class="card-value">{dashboard.bookings_count}</div>
						</div>
					</a>

					<a href="/messages" class="overview-card">
						<div class="card-icon">💬</div>
						<div class="card-content">
							<div class="card-label">{$t('dashboard.stat_messages')}</div>
							<div class="card-value">{dashboard.messages_unread_count}</div>
						</div>
					</a>
				</div>
			</section>

			<section class="reputation-section">
				<h2>{$t('dashboard.reputation')}</h2>
				<div class="reputation-card">
					<div class="rep-top">
						<div class="reputation-score">{dashboard.reputation_score}</div>
						<div class="reputation-info">
							<div class="rep-level-row">
								<span class="reputation-level">{$t(TIER_KEYS[dashboard.reputation_level] ?? dashboard.reputation_level)}</span>
								{#if $user?.role === 'admin'}
									<span class="role-badge">{$t('dashboard.admin')}</span>
								{/if}
							</div>
							{#if repProgress?.nextName}
								<div class="reputation-subtitle">{$t('dashboard.pts_to_level', { values: { pts: repProgress.ptsToNext, level: $t(TIER_KEYS[repProgress.nextName] ?? repProgress.nextName) } })}</div>
							{:else}
								<div class="reputation-subtitle">{$t('dashboard.top_tier')}</div>
							{/if}
							{#if repProgress}
								<div class="rep-progress-bar">
									<div class="rep-progress-fill" style="width: {repProgress.progressPct}%"></div>
								</div>
							{/if}
						</div>
					</div>

					<div class="rep-details">
						<div class="rep-tiers">
							{#each TIERS as tier}
								<span class="rep-tier" class:rep-tier-active={tier.name === dashboard.reputation_level}>
									{$t(TIER_KEYS[tier.name])} <span class="rep-tier-pts">{tier.min === 0 ? '0' : tier.min}+</span>
								</span>
							{/each}
						</div>
						<div class="rep-breakdown">
							<span class="rep-breakdown-title">{$t('dashboard.how_to_earn')}</span>
							<ul class="rep-breakdown-list">
								<li>{$t('dashboard.earn_lend')}</li>
								<li>{$t('dashboard.earn_borrow')}</li>
								<li>{$t('dashboard.earn_share')}</li>
								<li>{$t('dashboard.earn_skill_offer')}</li>
								<li>{$t('dashboard.earn_skill_request')}</li>
							</ul>
						</div>
					</div>
				</div>
			</section>
		{/if}
	{/if}
</div>

<style>
	.dashboard {
		max-width: 900px;
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	h1 {
		font-size: 1.9rem;
		font-weight: 400;
		color: var(--color-text);
		margin: 0;
	}

	h2 {
		font-size: 1.2rem;
		font-weight: 500;
		color: var(--color-text);
		margin: 0 0 0.75rem 0;
	}

	.loading {
		text-align: center;
		padding: 2rem;
		color: var(--color-text-muted);
	}

	/* ── Onboarding nudge ─────────────────────────────────────── */

	.nudge-banner {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 1.25rem 1.5rem;
		background: linear-gradient(135deg, var(--color-primary-light), var(--color-surface));
		border: 1px solid var(--color-primary);
		border-radius: var(--radius-md);
	}

	.nudge-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		border-radius: var(--radius);
		background: var(--color-primary);
		color: white;
		flex-shrink: 0;
	}

	.nudge-text {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		flex: 1;
		min-width: 0;
	}

	.nudge-text strong {
		font-size: 0.95rem;
		color: var(--color-text);
	}

	.nudge-text span {
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.nudge-btn {
		padding: 0.5rem 1.2rem;
		background: var(--color-primary);
		color: white;
		border-radius: var(--radius-sm);
		font-size: 0.88rem;
		font-weight: 600;
		text-decoration: none;
		white-space: nowrap;
		transition: all var(--transition-fast);
	}

	.nudge-btn:hover {
		background: var(--color-primary-hover);
		text-decoration: none;
		box-shadow: var(--shadow-md);
	}

	/* ── Community card ───────────────────────────────────────── */

	.community-card-link {
		display: block;
		padding: 1rem 1.25rem;
		background: linear-gradient(135deg, var(--color-surface) 0%, var(--color-primary-light) 100%);
		border: 1px solid var(--color-primary);
		border-left: 4px solid var(--color-primary);
		border-radius: var(--radius-md);
		text-decoration: none;
		color: inherit;
		transition: all var(--transition-fast);
	}

	.community-card-link:hover {
		box-shadow: var(--shadow-sm);
		transform: translateY(-1px);
		text-decoration: none;
	}

	.community-card-inner {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.community-info h3 {
		font-size: 1.05rem;
		font-weight: 500;
		color: var(--color-text);
		margin: 0;
	}

	.community-crisis-badge {
		display: inline-block;
		font-size: 0.7rem;
		font-weight: 600;
		padding: 0.15rem 0.5rem;
		border-radius: 999px;
		background: var(--color-error);
		color: white;
		margin-top: 0.3rem;
	}

	.community-arrow {
		font-size: 1.1rem;
		color: var(--color-primary);
		font-weight: 600;
	}

	/* ── Assigned crisis tickets ─────────────────────────────── */

	.crisis-tickets-section {
		margin-top: 0.5rem;
	}

	.assigned-tickets-list {
		display: flex;
		flex-direction: column;
		border: 1px solid var(--color-error);
		border-radius: var(--radius-md);
		overflow: hidden;
	}

	.assigned-ticket-item {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.85rem 1.25rem;
		text-decoration: none;
		color: inherit;
		transition: background-color var(--transition-fast);
		border-bottom: 1px solid var(--color-border);
	}

	.assigned-ticket-item:last-child {
		border-bottom: none;
	}

	.assigned-ticket-item:hover {
		background: var(--color-error-bg);
		text-decoration: none;
	}

	.ticket-urgency-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.urgency-critical { background: var(--color-error); }
	.urgency-high     { background: var(--color-warning); }
	.urgency-medium   { background: var(--color-text-muted); }
	.urgency-low      { background: var(--color-border); }

	.assigned-ticket-title {
		flex: 1;
		font-size: 0.9rem;
		font-weight: 500;
		color: var(--color-text);
		min-width: 0;
	}

	.assigned-ticket-meta {
		font-size: 0.8rem;
		color: var(--color-text-muted);
		white-space: nowrap;
		text-transform: capitalize;
	}

	.assigned-ticket-arrow {
		font-size: 0.9rem;
		color: var(--color-error);
		font-weight: 600;
		flex-shrink: 0;
	}

	/* ── Needs attention ──────────────────────────────────────── */

	.attention-section {
		margin-top: 0.5rem;
	}

	.attention-list {
		display: flex;
		flex-direction: column;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		overflow: hidden;
	}

	.attention-item {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.85rem 1.25rem;
		text-decoration: none;
		color: inherit;
		transition: background-color var(--transition-fast);
		border-bottom: 1px solid var(--color-border);
	}

	.attention-item:last-child {
		border-bottom: none;
	}

	.attention-item:hover {
		background: var(--color-primary-light);
		text-decoration: none;
	}

	.attention-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.attention-dot-warning { background: var(--color-warning); }
	.attention-dot-info { background: var(--color-text-muted); }
	.attention-dot-primary { background: var(--color-primary); }

	.attention-text {
		flex: 1;
		font-size: 0.9rem;
		color: var(--color-text);
		min-width: 0;
	}

	.attention-text strong {
		font-weight: 600;
	}

	.attention-action {
		font-size: 0.82rem;
		font-weight: 600;
		color: var(--color-primary);
		white-space: nowrap;
	}

	/* ── Quick Stats Grid ─────────────────────────────────────── */

	.overview-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 1rem;
	}

	.overview-card {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 1.25rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		transition: all var(--transition-fast);
		text-decoration: none;
		color: inherit;
	}

	.overview-card:hover {
		border-color: var(--color-primary);
		box-shadow: var(--shadow-sm);
		text-decoration: none;
	}

	.card-icon {
		font-size: 1.75rem;
	}

	.card-content {
		display: flex;
		flex-direction: column;
	}

	.card-label {
		font-size: 0.8rem;
		color: var(--color-text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.card-value {
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--color-text);
	}

	/* ── Reputation ───────────────────────────────────────────── */

	.reputation-section {
		margin-top: 0.5rem;
	}

	.reputation-card {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		padding: 1.5rem 2rem;
		background: linear-gradient(135deg, var(--color-primary-light), var(--color-surface));
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
	}

	.rep-top {
		display: flex;
		align-items: center;
		gap: 2rem;
	}

	.reputation-score {
		font-size: 3rem;
		font-weight: 700;
		color: var(--color-primary);
		min-width: 70px;
		line-height: 1;
	}

	.reputation-info {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		flex: 1;
	}

	.rep-level-row {
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}

	.reputation-level {
		font-size: 1.2rem;
		font-weight: 600;
		color: var(--color-text);
	}

	.role-badge {
		font-size: 0.72rem;
		font-weight: 600;
		padding: 0.15rem 0.55rem;
		border-radius: 999px;
		background: var(--color-primary);
		color: white;
		letter-spacing: 0.03em;
		text-transform: uppercase;
	}

	.reputation-subtitle {
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.rep-progress-bar {
		height: 5px;
		background: var(--color-border);
		border-radius: 999px;
		overflow: hidden;
		max-width: 200px;
	}

	.rep-progress-fill {
		height: 100%;
		background: var(--color-primary);
		border-radius: 999px;
		transition: width var(--transition-slow);
	}

	/* Tier list + breakdown row */
	.rep-details {
		display: flex;
		gap: 2rem;
		padding-top: 1rem;
		border-top: 1px solid var(--color-border);
		flex-wrap: wrap;
	}

	.rep-tiers {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		align-items: center;
	}

	.rep-tier {
		font-size: 0.75rem;
		padding: 0.2rem 0.6rem;
		border-radius: 999px;
		background: var(--color-bg);
		color: var(--color-text-muted);
		border: 1px solid var(--color-border);
	}

	.rep-tier-active {
		background: var(--color-primary-light);
		color: var(--color-primary);
		border-color: var(--color-primary);
		font-weight: 600;
	}

	.rep-tier-pts {
		opacity: 0.65;
	}

	.rep-breakdown {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.rep-breakdown-title {
		font-size: 0.78rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--color-text-muted);
	}

	.rep-breakdown-list {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}

	.rep-breakdown-list li {
		font-size: 0.82rem;
		color: var(--color-text-muted);
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}

	.rep-pts {
		font-size: 0.78rem;
		font-weight: 700;
		color: var(--color-primary);
		min-width: 28px;
	}

	/* ── Alerts ────────────────────────────────────────────────── */

	.alert {
		padding: 1rem;
		border-radius: var(--radius-sm);
		font-size: 0.95rem;
	}

	.alert-error {
		background-color: rgba(239, 68, 68, 0.1);
		border: 1px solid rgba(239, 68, 68, 0.3);
		color: var(--color-error);
	}

	@media (max-width: 600px) {
		h1 {
			font-size: 1.5rem;
		}

		.overview-grid {
			grid-template-columns: 1fr;
		}

		.nudge-banner {
			flex-direction: column;
			text-align: center;
		}

		.rep-top {
			flex-direction: column;
			align-items: flex-start;
			gap: 0.75rem;
		}

		.reputation-score {
			font-size: 2.5rem;
		}

		.rep-progress-bar {
			max-width: 100%;
		}

		.rep-details {
			flex-direction: column;
			gap: 1rem;
		}
	}
</style>
