<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isLoggedIn, user } from '$lib/stores/auth';
	import { api } from '$lib/api';
	import { t, locale } from 'svelte-i18n';
	import Icon from '$lib/components/Icon.svelte';
	import ExpandableItem from '$lib/components/ExpandableItem.svelte';
	import { RESOURCE_CATEGORY_ICON, EVENT_CATEGORY_ICON } from '$lib/icons';

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
		resource_id: number;
		resource_title: string;
		borrower_name: string;
		borrower_id: number;
		start_date: string;
		end_date: string;
		message: string | null;
		status: string;
	}

	interface CommunityMembership {
		id: number;
		name: string;
		mode: string;
		effective_mode?: string;
		member_count?: number;
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

	interface NearbyItem {
		id: number;
		title: string;
		category: string;
		is_available: boolean;
		owner_id: number;
		owner: { display_name: string };
	}

	interface EventItem {
		id: number;
		title: string;
		category: string;
		start_at: string;
		location: string | null;
		attendee_count: number;
	}

	let dashboard = $state<DashboardData | null>(null);
	let pendingBookings: BookingItem[] = $state([]);
	// Whose dashboard this is. Filled from the auth store or /users/me, never
	// guessed: until it is known no pending booking is classified.
	let meId: number | null = $state(null);
	const pendingIncoming = $derived(meId === null ? [] : pendingBookings.filter((b) => b.borrower_id !== meId));
	const pendingOutgoing = $derived(meId === null ? [] : pendingBookings.filter((b) => b.borrower_id === meId));
	let communities: CommunityMembership[] = $state([]);
	let assignedTickets: TicketItem[] = $state([]);
	let nearby: NearbyItem[] = $state([]);
	let communityItemCount = $state<number | null>(null);
	let nextEvent = $state<EventItem | null>(null);
	let loading = $state(true);
	let error = $state('');
	let actionError = $state('');
	let busyBooking = $state<number | null>(null);

	const community = $derived(communities[0] ?? null);
	const unread = $derived(dashboard?.messages_unread_count ?? 0);
	const needsCount = $derived(pendingIncoming.length + pendingOutgoing.length + (unread > 0 ? 1 : 0));

	async function loadBookings() {
		const bookingsData = await api<{ items: any[] }>('/bookings?status=pending', { auth: true });
		pendingBookings = (bookingsData.items ?? []).map((b) => ({
			id: b.id,
			resource_id: b.resource_id,
			resource_title: b.resource_title ?? b.resource?.title ?? $t('common.resource_number', { values: { id: b.resource_id } }),
			borrower_name: b.borrower?.display_name ?? $t('dashboard.someone'),
			borrower_id: b.borrower_id,
			start_date: b.start_date,
			end_date: b.end_date,
			message: b.message ?? null,
			status: b.status
		}));
	}

	/** Approve or decline a borrow request right here, without leaving the dashboard. */
	async function answerBooking(id: number, status: 'approved' | 'rejected') {
		actionError = '';
		busyBooking = id;
		try {
			await api(`/bookings/${id}`, { method: 'PATCH', auth: true, body: { status } });
			await loadBookings();
		} catch (err) {
			actionError = err instanceof Error ? err.message : $t('common.error');
		} finally {
			busyBooking = null;
		}
	}

	onMount(async () => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}

		try {
			// The layout loads /users/me in parallel, so $user can still be null here.
			const [dashData, commData, meData] = await Promise.all([
				api<DashboardData>('/users/me/dashboard', { auth: true }),
				api<CommunityMembership[]>('/communities/my/memberships', { auth: true }),
				$user ? Promise.resolve($user) : api<{ id: number }>('/users/me', { auth: true })
			]);
			dashboard = dashData;
			communities = commData;
			meId = meData.id;

			await loadBookings();

			// Coming up + new nearby come from the first community; failures only hide the block
			const first = commData[0];
			if (first) {
				const [eventsData, itemsData] = await Promise.all([
					api<{ items: EventItem[] }>(`/events?community_id=${first.id}&upcoming=true&limit=1`, { auth: true }).catch(() => null),
					api<{ items: NearbyItem[]; total: number }>(`/resources?community_id=${first.id}&limit=8`, { auth: true }).catch(() => null)
				]);
				nextEvent = eventsData?.items?.[0] ?? null;
				if (itemsData) {
					nearby = (itemsData.items ?? []).filter((r) => r.owner_id !== meId).slice(0, 3);
					communityItemCount = itemsData.total;
				}
			}

			// Load assigned tickets from Red Sky communities
			const redCommunities = commData.filter((c) => (c.effective_mode ?? c.mode) === 'red');
			const collected: TicketItem[] = [];
			for (const c of redCommunities) {
				try {
					const data = await api<{ items: TicketItem[] }>(`/communities/${c.id}/tickets?limit=100`, { auth: true });
					for (const tk of data.items ?? []) {
						if (tk.assigned_to?.id === meId && tk.status !== 'resolved') collected.push(tk);
					}
				} catch {
					// skip community on failure
				}
			}
			assignedTickets = collected;
		} catch (err) {
			error = err instanceof Error ? err.message : $t('dashboard.load_failed');
		} finally {
			loading = false;
		}
	});

	function greetingKey(): string {
		const h = new Date().getHours();
		if (h < 12) return 'dashboard.greeting_morning';
		if (h < 18) return 'dashboard.greeting_afternoon';
		return 'dashboard.greeting_evening';
	}

	function fmtDay(d: string): string {
		return new Intl.DateTimeFormat($locale ?? 'en', { weekday: 'short', day: 'numeric', month: 'short' }).format(new Date(d));
	}

	function fmtRange(start: string, end: string): string {
		return start === end ? fmtDay(start) : $t('dashboard.date_range', { values: { start: fmtDay(start), end: fmtDay(end) } });
	}

	function eventDay(d: string): { day: string; month: string; time: string } {
		const date = new Date(d);
		const loc = $locale ?? 'en';
		return {
			day: new Intl.DateTimeFormat(loc, { day: 'numeric' }).format(date),
			month: new Intl.DateTimeFormat(loc, { month: 'short' }).format(date),
			time: new Intl.DateTimeFormat(loc, { weekday: 'short', hour: '2-digit', minute: '2-digit' }).format(date)
		};
	}

	// Reputation tier thresholds (mirrors backend routers/users.py)
	const TIERS = [
		{ name: 'Newcomer', min: 0, max: 9 },
		{ name: 'Neighbour', min: 10, max: 39 },
		{ name: 'Helper', min: 40, max: 99 },
		{ name: 'Trusted', min: 100, max: 199 },
		{ name: 'Pillar', min: 200, max: Infinity }
	];

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
		const idx = TIERS.findIndex((tier) => score >= tier.min && (tier.max === Infinity || score <= tier.max));
		const current = TIERS[idx];
		const next = TIERS[idx + 1] ?? null;
		if (!next) return { ptsToNext: 0, progressPct: 100, nextName: null };
		const range = next.min - current.min;
		const progressPct = Math.min(100, Math.round(((score - current.min) / range) * 100));
		return { ptsToNext: next.min - score, progressPct, nextName: next.name };
	})());
</script>

<svelte:head>
	<title>{$t('nav.home')} - NeighbourGood</title>
</svelte:head>

<div class="dashboard">
	<header class="dash-head">
		<div>
			{#if community}
				<p class="kicker">
					{community.member_count
						? $t('dashboard.community_line', { values: { community: community.name, count: community.member_count } })
						: community.name}
				</p>
			{/if}
			<h1>{$t(greetingKey(), { values: { name: $user?.display_name ?? '' } })}</h1>
		</div>
		{#if community}
			<a href="/resources?new=1" class="btn btn-primary"><Icon name="plus" size={16} />{$t('dashboard.share_something')}</a>
		{/if}
	</header>

	{#if loading}
		<div class="skeleton-stack" role="status" aria-busy="true">
			<span class="sr-only">{$t('dashboard.loading')}</span>
			<div class="skeleton skeleton-card" style="height: 9rem"></div>
			<div class="skeleton-grid">
				<div class="skeleton skeleton-card"></div>
				<div class="skeleton skeleton-card"></div>
			</div>
		</div>
	{:else if error}
		<div class="alert alert-error">{error}</div>
	{:else}
		{#if communities.length === 0}
			<div class="card nudge">
				<span class="nudge-icon"><Icon name="users" size={20} /></span>
				<div class="nudge-text">
					<strong>{$t('dashboard.join_title')}</strong>
					<span>{$t('dashboard.join_desc')}</span>
				</div>
				<a href="/onboarding" class="btn btn-primary">{$t('dashboard.find_community')}</a>
			</div>
		{/if}

		{#if community && (community.effective_mode ?? community.mode) === 'red'}
			<a href="/triage" class="crisis-line">
				<Icon name="alert" size={16} />
				<span>{$t('dashboard.crisis_active')} · {community.name}</span>
				<Icon name="arrow-right" size={16} class="flip-rtl" />
			</a>
		{/if}

		{#if assignedTickets.length > 0}
			<section>
				<h2 class="section-title">{$t('dashboard.assigned_tickets')} <span class="section-count">{assignedTickets.length}</span></h2>
				<div class="list-panel">
					{#each assignedTickets as ticket (ticket.id)}
						<ExpandableItem
							title={ticket.title}
							meta="{$t(`crisis.ticket_types.${ticket.ticket_type === 'emergency_ping' ? 'ping' : ticket.ticket_type}`)} · {$t(`crisis.status_${ticket.status}`)}"
							icon="alert"
							tone={ticket.urgency === 'critical' ? 'error' : 'warning'}
						>
							{#snippet aside()}<span class="meta-text">{$t(`crisis.priority.${ticket.urgency}`)}</span>{/snippet}
							<div class="xp-actions">
								<a href="/triage/{ticket.id}" class="btn btn-primary btn-sm">{$t('dashboard.open_ticket')}</a>
							</div>
						</ExpandableItem>
					{/each}
				</div>
			</section>
		{/if}

		{#if community}
			<section>
				<h2 class="section-title">{$t('dashboard.needs_you')} {#if needsCount > 0}<span class="section-count">{needsCount}</span>{/if}</h2>
				{#if actionError}<p class="alert alert-error" role="alert">{actionError}</p>{/if}
				{#if needsCount === 0}
					<p class="calm-empty">{$t('dashboard.nothing_needed')}</p>
				{:else}
					<div class="list-panel">
						{#each pendingIncoming as booking, i (booking.id)}
							<ExpandableItem
								title={$t('dashboard.wants_to_borrow', { values: { name: booking.borrower_name, resource: booking.resource_title } })}
								meta={fmtRange(booking.start_date, booking.end_date)}
								icon="tool"
								open={i === 0}
							>
								{#if booking.message}<p>“{booking.message}”</p>{/if}
								<p>{$t('dashboard.incoming_detail', { values: { name: booking.borrower_name } })}</p>
								<div class="xp-actions">
									<button class="btn btn-primary btn-sm" class:is-loading={busyBooking === booking.id} disabled={busyBooking !== null} onclick={() => answerBooking(booking.id, 'approved')}>{$t('bookings.approve')}</button>
									<button class="btn btn-secondary btn-sm" disabled={busyBooking !== null} onclick={() => answerBooking(booking.id, 'rejected')}>{$t('bookings.reject')}</button>
									<a href="/messages?partner={booking.borrower_id}" class="btn btn-secondary btn-sm">{$t('dashboard.message_name', { values: { name: booking.borrower_name } })}</a>
								</div>
							</ExpandableItem>
						{/each}
						{#each pendingOutgoing as booking (booking.id)}
							<ExpandableItem
								title={$t('dashboard.request_waiting', { values: { resource: booking.resource_title } })}
								meta={fmtRange(booking.start_date, booking.end_date)}
								icon="clock"
								tone="warning"
							>
								<p>{$t('dashboard.outgoing_detail')}</p>
								<div class="xp-actions">
									<a href="/resources/{booking.resource_id}" class="btn btn-secondary btn-sm">{$t('dashboard.view_item')}</a>
									<a href="/bookings" class="btn btn-secondary btn-sm">{$t('dashboard.open_bookings')}</a>
								</div>
							</ExpandableItem>
						{/each}
						{#if unread > 0}
							<ExpandableItem
								title={$t('dashboard.unread_title', { values: { count: unread } })}
								meta={$t('dashboard.unread_meta')}
								icon="message"
								tone="neutral"
							>
								<div class="xp-actions">
									<a href="/messages" class="btn btn-primary btn-sm">{$t('dashboard.open_messages')}</a>
								</div>
							</ExpandableItem>
						{/if}
					</div>
				{/if}
			</section>

			<div class="cols">
				<section>
					<h2 class="section-title">{$t('dashboard.coming_up')} <a href="/events">{$t('dashboard.see_all')}</a></h2>
					{#if nextEvent}
						{@const d = eventDay(nextEvent.start_at)}
						<a href="/events/{nextEvent.id}" class="card card-interactive event-card">
							<span class="date-block"><b>{d.day}</b><span>{d.month}</span></span>
							<span class="event-text">
								<strong>{nextEvent.title}</strong>
								<span class="meta-text">
									{d.time}{nextEvent.location ? ` · ${nextEvent.location}` : ''} · {$t('dashboard.going', { values: { count: nextEvent.attendee_count } })}
								</span>
							</span>
						</a>
					{:else}
						<p class="calm-empty">{$t('dashboard.no_events')} <a href="/events">{$t('dashboard.plan_event')}</a></p>
					{/if}
				</section>

				<section>
					<h2 class="section-title">{$t('dashboard.new_nearby')} <a href="/resources">{$t('dashboard.see_all')}</a></h2>
					{#if nearby.length > 0}
						<div class="list-panel">
							{#each nearby as item (item.id)}
								<a href="/resources/{item.id}" class="mini-row">
									<span class="mini-icon"><Icon name={RESOURCE_CATEGORY_ICON[item.category] ?? 'package'} size={16} /></span>
									<span class="mini-text">
										<strong>{item.title}</strong>
										<span class="meta-text">{item.owner.display_name}</span>
									</span>
									<span class="status-text" class:status-ok={item.is_available} class:status-off={!item.is_available}>
										{item.is_available ? $t('resources.available') : $t('resources.unavailable')}
									</span>
								</a>
							{/each}
						</div>
					{:else}
						<p class="calm-empty">{$t('dashboard.no_new_items')}</p>
					{/if}
				</section>
			</div>
		{/if}

		{#if dashboard}
			<div class="footer-stats">
				{#if community && communityItemCount !== null}
					<p class="statline">
						{$t('dashboard.community_stats', { values: { items: communityItemCount, community: community.name, members: community.member_count ?? 0 } })}
					</p>
				{/if}
				<p class="statline">
					{$t('dashboard.your_stats', { values: { items: dashboard.resources_count, skills: dashboard.skills_count } })}
				</p>
			</div>

			<section>
				<div class="list-panel">
					<ExpandableItem
						title={$t('dashboard.reputation_line', { values: { level: $t(TIER_KEYS[dashboard.reputation_level] ?? dashboard.reputation_level), score: dashboard.reputation_score } })}
						meta={repProgress?.nextName
							? $t('dashboard.pts_to_level', { values: { pts: repProgress.ptsToNext, level: $t(TIER_KEYS[repProgress.nextName] ?? repProgress.nextName) } })
							: $t('dashboard.top_tier')}
						icon="star"
						tone="neutral"
					>
						{#snippet aside()}
							{#if $user?.role === 'admin'}<span class="meta-text">{$t('dashboard.admin')}</span>{/if}
						{/snippet}
						{#if repProgress}
							<div class="rep-bar" role="presentation"><div class="rep-fill" style="width: {repProgress.progressPct}%"></div></div>
						{/if}
						<div class="rep-tiers">
							{#each TIERS as tier}
								<span class="rep-tier" class:rep-tier-active={tier.name === dashboard.reputation_level}>
									{$t(TIER_KEYS[tier.name])} <span class="meta-text">{tier.min}+</span>
								</span>
							{/each}
						</div>
						<p><strong>{$t('dashboard.how_to_earn')}</strong></p>
						<ul class="rep-list">
							<li>{$t('dashboard.earn_lend')}</li>
							<li>{$t('dashboard.earn_borrow')}</li>
							<li>{$t('dashboard.earn_share')}</li>
							<li>{$t('dashboard.earn_skill_offer')}</li>
							<li>{$t('dashboard.earn_skill_request')}</li>
						</ul>
					</ExpandableItem>
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
		gap: 1.75rem;
	}

	.dash-head {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-end;
		justify-content: space-between;
		gap: 1rem;
	}

	h1 {
		font-size: 1.9rem;
		font-weight: 400;
		color: var(--color-text);
		margin: 0;
	}

	.calm-empty {
		margin: 0;
		font-size: 0.85rem;
		color: var(--color-text-subtle);
	}

	/* ── Onboarding nudge (no stripe, no gradient) ─────────── */

	.nudge {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 1rem;
	}

	.nudge-icon {
		display: grid;
		place-items: center;
		width: 2.5rem;
		height: 2.5rem;
		border-radius: var(--radius-sm);
		background: var(--color-primary-light);
		color: var(--color-primary-text);
		flex: none;
	}

	.nudge-text {
		display: grid;
		gap: 0.15rem;
		flex: 1;
		min-width: 12rem;
	}

	.nudge-text strong {
		font-size: 0.95rem;
	}

	.nudge-text span {
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.crisis-line {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.7rem 1rem;
		border: 1px solid var(--color-primary);
		border-radius: var(--radius-md, 0.75rem);
		background: var(--color-primary-light);
		color: var(--color-primary-text);
		font-weight: 600;
		font-size: 0.88rem;
		text-decoration: none;
	}

	.crisis-line span {
		flex: 1;
	}

	/* ── Coming up / New nearby ─────────────────────────────── */

	.cols {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 1.75rem;
	}

	.cols section {
		min-width: 0;
	}

	.event-card {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		gap: 0.9rem;
		align-items: center;
		padding: 0.9rem 1rem;
		box-shadow: none;
	}

	.date-block {
		display: grid;
		justify-items: center;
		width: 3.25rem;
		padding: 0.35rem 0;
		border-radius: var(--radius-sm);
		background: var(--color-accent-light);
		color: var(--color-accent);
	}

	.date-block b {
		font-family: var(--font-heading);
		font-size: 1.4rem;
		font-weight: 500;
		line-height: 1;
	}

	.date-block span {
		font-size: 0.7rem;
		font-weight: 600;
		text-transform: uppercase;
	}

	.event-text {
		display: grid;
		gap: 0.15rem;
		min-width: 0;
	}

	.event-text strong {
		font-size: 0.9rem;
		color: var(--color-text);
	}

	.mini-row {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr) auto;
		gap: 0.7rem;
		align-items: center;
		padding: 0.65rem 1rem;
		color: inherit;
		text-decoration: none;
	}

	.mini-row + .mini-row {
		border-top: 1px solid var(--color-border);
	}

	.mini-row:hover {
		background: var(--color-surface-raised);
		text-decoration: none;
	}

	.mini-icon {
		display: grid;
		place-items: center;
		width: 2rem;
		height: 2rem;
		border-radius: var(--radius-sm);
		background: var(--color-surface-raised);
		color: var(--color-text-muted);
	}

	.mini-text {
		display: grid;
		min-width: 0;
	}

	.mini-text strong {
		font-size: 0.88rem;
		color: var(--color-text);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	/* ── Stats + reputation ─────────────────────────────────── */

	.footer-stats {
		display: grid;
		gap: 0.2rem;
	}

	.statline {
		margin: 0;
		font-size: 0.82rem;
		color: var(--color-text-subtle);
	}

	.rep-bar {
		height: 6px;
		border-radius: 999px;
		background: var(--color-surface-raised);
		overflow: hidden;
	}

	.rep-fill {
		height: 100%;
		background: var(--color-primary);
	}

	.rep-tiers {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem 0.9rem;
		font-size: 0.8rem;
	}

	.rep-tier-active {
		color: var(--color-primary-text);
		font-weight: 600;
	}

	.rep-list {
		margin: 0;
		padding-inline-start: 1.1rem;
		display: grid;
		gap: 0.15rem;
	}

	@media (max-width: 720px) {
		.cols {
			grid-template-columns: 1fr;
		}

		h1 {
			font-size: 1.6rem;
		}

		.dash-head .btn {
			display: none;
		}
	}
</style>
