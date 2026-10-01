<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { isLoggedIn, user } from '$lib/stores/auth';
	import { isOnline } from '$lib/stores/offline';
	import { bandwidth, refreshPlatformMode } from '$lib/stores/theme';
	import type { ActivityOut, ActivityList, CommunityOut, CrisisStatus, EmergencyTicket as TicketOut, TicketList, CommunityMember as MemberOut, MergeSuggestion, InviteOut, Resource as ResourceItem } from '$lib/types';
	import CrisisModePanel from '$lib/components/community/CrisisModePanel.svelte';
	import MembersList from '$lib/components/community/MembersList.svelte';
	import InviteLinks from '$lib/components/community/InviteLinks.svelte';
	import { t } from 'svelte-i18n';
	import Icon from '$lib/components/Icon.svelte';
	import { RESOURCE_CATEGORY_ICON } from '$lib/icons';

	let community = $state<CommunityOut | null>(null);
	let members = $state<MemberOut[]>([]);
	let suggestions = $state<MergeSuggestion[]>([]);
	let resources = $state<ResourceItem[]>([]);
	let resourceTotal = $state(0);
	let loading = $state(true);
	let error = $state('');
	let actionMsg = $state('');
	let isAdmin = $state(false);
	let isLeader = $state(false);
	let isMember = $state(false);
	let joiningOrLeaving = $state(false);
	let merging = $state<number | null>(null);

	// Crisis mode state
	let crisisStatus = $state<CrisisStatus | null>(null);
	let togglingCrisis = $state(false);
	let votingCrisis = $state(false);
	let tickets = $state<TicketOut[]>([]);
	let ticketTotal = $state(0);
	let showTicketForm = $state(false);
	let ticketTitle = $state('');
	let ticketDesc = $state('');
	let ticketType = $state('request');
	let ticketUrgency = $state('medium');
	let creatingTicket = $state(false);
	let promotingUser = $state<number | null>(null);

	// Invite state
	let invites = $state<InviteOut[]>([]);
	let activities = $state<ActivityOut[]>([]);

	const communityId = $derived(Number($page.params.id));

	onMount(() => loadData());

	async function loadData() {
		loading = true;
		error = '';
		try {
			community = await api<CommunityOut>(`/communities/${communityId}`);
			members = await api<MemberOut[]>(`/communities/${communityId}/members`);

			const resData = await api<{ items: ResourceItem[]; total: number }>(
				`/resources?community_id=${communityId}`
			);
			resources = resData.items;
			resourceTotal = resData.total;

			// Load crisis status (public)
			try {
				crisisStatus = await api<CrisisStatus>(`/communities/${communityId}/crisis/status`);
			// Viewing a community must not change the global theme (that is derived
			// from the viewer's own memberships); re-sync it in case this page's
			// data shows a mode change (own vote/toggle, or a stale layout).
			if (crisisStatus) {
				refreshPlatformMode();
			}
			} catch {
				crisisStatus = null;
			}

			if ($isLoggedIn && $user) {
				const me = members.find((m) => m.user.id === $user!.id);
				isMember = !!me;
				isAdmin = me?.role === 'admin';
				isLeader = me?.role === 'leader';

				if (isMember) {
					try {
						invites = await api<InviteOut[]>(
							`/invites?community_id=${communityId}`,
							{ auth: true }
						);
					} catch {
						invites = [];
					}
					// Load tickets
					try {
						const ticketData = await api<TicketList>(
							`/communities/${communityId}/tickets`,
							{ auth: true }
						);
						tickets = ticketData.items;
						ticketTotal = ticketData.total;
					} catch {
						tickets = [];
					}
				}

				if (isAdmin) {
					suggestions = await api<MergeSuggestion[]>(
						`/communities/merge/suggestions?community_id=${communityId}`,
						{ auth: true }
					);
				}
			}
		// Load activity feed (public endpoint, no auth required)
		try {
			const activityData = await api<ActivityList>(
				`/activity?community_id=${communityId}&limit=20`
			);
			activities = activityData.items;
		} catch {
			activities = [];
		}
		} catch (err) {
			error = err instanceof Error ? err.message : $t('common.load_failed');
		} finally {
			loading = false;
		}
	}

	function timeAgo(iso: string): string {
		const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
		if (diff < 60) return $t('common.just_now');
		if (diff < 3600) return $t('common.minutes_ago', { values: { n: Math.floor(diff / 60) } });
		if (diff < 86400) return $t('common.hours_ago', { values: { n: Math.floor(diff / 3600) } });
		return $t('common.days_ago', { values: { n: Math.floor(diff / 86400) } });
	}

	async function join() {
		joiningOrLeaving = true;
		error = '';
		try {
			await api(`/communities/${communityId}/join`, {
				method: 'POST', auth: true,
				offline: { label: $t('communities.offline_join', { values: { name: community?.name ?? communityId } }) }
			});
			actionMsg = $isOnline ? $t('communities.joined_msg') : $t('communities.join_queued');
			if ($isOnline) await loadData();
		} catch (err) {
			error = err instanceof Error ? err.message : $t('communities.join_failed');
		} finally {
			joiningOrLeaving = false;
		}
	}

	async function leave() {
		joiningOrLeaving = true;
		error = '';
		try {
			await api(`/communities/${communityId}/leave`, { method: 'DELETE', auth: true });
			actionMsg = $t('communities.left_msg');
			await loadData();
		} catch (err) {
			error = err instanceof Error ? err.message : $t('communities.leave_failed');
		} finally {
			joiningOrLeaving = false;
		}
	}

	async function merge(targetId: number) {
		merging = targetId;
		error = '';
		try {
			await api('/communities/merge', {
				method: 'POST',
				auth: true,
				body: { source_id: communityId, target_id: targetId },
			});
			actionMsg = $t('communities.merged_msg');
			setTimeout(() => goto(`/communities/${targetId}`), 1200);
		} catch (err) {
			error = err instanceof Error ? err.message : $t('communities.merge_failed');
		} finally {
			merging = null;
		}
	}

	// ── Crisis mode functions ──────────────────────────

	async function toggleCrisisMode(newMode: string) {
		togglingCrisis = true;
		error = '';
		actionMsg = '';
		try {
			crisisStatus = await api<CrisisStatus>(`/communities/${communityId}/crisis/toggle`, {
				method: 'POST', auth: true, body: { mode: newMode }
			});
			// Re-derive the global theme (another of the user's communities may still be red)
			await refreshPlatformMode();
			actionMsg = newMode === 'red' ? $t('crisis.activated_msg') : $t('crisis.deactivated_msg');
			await loadData();
		} catch (err) {
			error = err instanceof Error ? err.message : $t('crisis.toggle_failed');
		} finally {
			togglingCrisis = false;
		}
	}

	async function castVote(voteType: string) {
		votingCrisis = true;
		error = '';
		actionMsg = '';
		try {
			await api(`/communities/${communityId}/crisis/vote`, {
				method: 'POST', auth: true, body: { vote_type: voteType },
				offline: { label: $t('crisis.offline_vote', { values: { vote: voteType } }) }
			});
			if ($isOnline) {
				crisisStatus = await api<CrisisStatus>(`/communities/${communityId}/crisis/status`);
				await loadData();
			}
			actionMsg = $isOnline ? $t('crisis.vote_recorded', { values: { vote: voteType } }) : $t('crisis.vote_queued');
		} catch (err) {
			error = err instanceof Error ? err.message : $t('crisis.vote_failed');
		} finally {
			votingCrisis = false;
		}
	}

	async function createTicket() {
		creatingTicket = true;
		error = '';
		try {
			await api(`/communities/${communityId}/tickets`, {
				method: 'POST', auth: true,
				body: { ticket_type: ticketType, title: ticketTitle, description: ticketDesc, urgency: ticketUrgency }
			});
			showTicketForm = false;
			ticketTitle = '';
			ticketDesc = '';
			ticketType = 'request';
			ticketUrgency = 'medium';
			const ticketData = await api<TicketList>(`/communities/${communityId}/tickets`, { auth: true });
			tickets = ticketData.items;
			ticketTotal = ticketData.total;
		} catch (err) {
			error = err instanceof Error ? err.message : $t('crisis.create_failed');
		} finally {
			creatingTicket = false;
		}
	}

	async function updateTicketStatus(ticketId: number, newStatus: string) {
		try {
			await api(`/communities/${communityId}/tickets/${ticketId}`, {
				method: 'PATCH', auth: true, body: { status: newStatus }
			});
			const ticketData = await api<TicketList>(`/communities/${communityId}/tickets`, { auth: true });
			tickets = ticketData.items;
			ticketTotal = ticketData.total;
		} catch (err) {
			error = err instanceof Error ? err.message : $t('crisis.detail.update_failed');
		}
	}

	async function promoteToLeader(userId: number) {
		promotingUser = userId;
		error = '';
		actionMsg = '';
		try {
			await api(`/communities/${communityId}/leaders/${userId}`, { method: 'POST', auth: true });
			actionMsg = $t('communities.leader_promoted');
			await loadData();
		} catch (err) {
			error = err instanceof Error ? err.message : $t('communities.promote_failed');
		} finally {
			promotingUser = null;
		}
	}

	async function makeAdmin(userId: number) {
		promotingUser = userId;
		error = '';
		actionMsg = '';
		try {
			await api(`/communities/${communityId}/members/${userId}/promote`, { method: 'POST', auth: true });
			actionMsg = $t('communities.admin_made');
			await loadData();
		} catch (err) {
			error = err instanceof Error ? err.message : $t('communities.promote_failed');
		} finally {
			promotingUser = null;
		}
	}

	async function demoteLeader(userId: number) {
		promotingUser = userId;
		error = '';
		actionMsg = '';
		try {
			await api(`/communities/${communityId}/leaders/${userId}`, { method: 'DELETE', auth: true });
			actionMsg = $t('communities.leader_demoted');
			await loadData();
		} catch (err) {
			error = err instanceof Error ? err.message : $t('communities.demote_failed');
		} finally {
			promotingUser = null;
		}
	}

	const URGENCY_COLORS: Record<string, string> = {
		low: 'var(--color-text-muted)',
		medium: 'var(--color-warning)',
		high: 'var(--color-warning)',
		critical: 'var(--color-error)'
	};

	function ticketTypeLabel(type: string): string {
		const key = type === 'emergency_ping' ? 'ping' : type;
		return $t(`crisis.ticket_types.${key}`);
	}

	let activeTab = $state('overview');
</script>

<div class="detail-page">
	{#if loading}
		<div class="skeleton-stack" role="status" aria-busy="true">
			<span class="sr-only">{$t('common.loading')}</span>
			<span class="skeleton skeleton-line is-short"></span>
			<span class="skeleton" style="height: 2.2rem; width: 55%"></span>
			<div class="skeleton skeleton-card" style="margin-top: 1rem"></div>
		</div>
	{:else if error && !community}
		<div class="alert alert-error">{error}</div>
	{:else if community}
		<div class="community-header slide-up">
			<div class="header-top">
				<a href="/communities" class="back-link"><Icon name="arrow-left" size={16} class="flip-rtl" /> {$t('nav.communities')}</a>
				{#if !community.is_active}
					<span class="badge badge-caps">{$t('communities.merged_badge')}</span>
				{/if}
			</div>

			<h1>{community.name}</h1>
			<div class="header-meta">
				<span class="tag">{community.postal_code}</span>
				<span class="tag">{community.city}</span>
				<span class="meta-sep">&middot;</span>
				<span>{$t('communities.member_count', { values: { count: community.member_count } })}</span>
				<span class="meta-sep">&middot;</span>
				<span>{$t('communities.created_on', { values: { date: new Date(community.created_at).toLocaleDateString() } })}</span>
			</div>

			{#if community.description}
				<p class="description">{community.description}</p>
			{/if}

			{#if community.merged_into_id}
				<div class="alert alert-info fade-in">
					{@html $t('communities.merged_into', { values: { link: `<a href="/communities/${community.merged_into_id}">${$t('communities.merged_into_link')}</a>` } })}
				</div>
			{/if}

			{#if error}
				<div class="alert alert-error fade-in">{error}</div>
			{/if}
			{#if actionMsg}
				<div class="alert alert-success fade-in">{actionMsg}</div>
			{/if}

			{#if $isLoggedIn && community.is_active}
				<div class="actions">
					{#if isMember}
						<button class="btn btn-secondary" class:is-loading={joiningOrLeaving} onclick={leave} disabled={joiningOrLeaving}>
							{joiningOrLeaving ? $t('communities.leaving') : $t('communities.leave_community')}
						</button>
					{:else}
						<button class="btn btn-primary" class:is-loading={joiningOrLeaving} onclick={join} disabled={joiningOrLeaving}>
							{joiningOrLeaving ? $t('communities.joining') : $t('communities.join_community')}
						</button>
					{/if}
				</div>
			{/if}
		</div>

		<!-- Tab navigation -->
		<nav class="community-tabs">
			<button class="community-tab" class:active={activeTab === 'overview'} onclick={() => activeTab = 'overview'}>{$t('communities.tab_overview')}</button>
			<button class="community-tab" class:active={activeTab === 'members'} onclick={() => activeTab = 'members'}>{$t('communities.tab_members', { values: { count: members.length } })}</button>
			<button class="community-tab" class:active={activeTab === 'resources'} onclick={() => activeTab = 'resources'}>{$t('communities.tab_resources', { values: { count: resourceTotal } })}</button>
			{#if isMember}
				<button class="community-tab" class:active={activeTab === 'emergency'} onclick={() => activeTab = 'emergency'}>{$t('nav.emergency')} {ticketTotal > 0 ? `(${ticketTotal})` : ''}</button>
			{/if}
			{#if isAdmin}
				<button class="community-tab" class:active={activeTab === 'admin'} onclick={() => activeTab = 'admin'}>{$t('communities.role_admin')}</button>
			{/if}
		</nav>

		<!-- Crisis Mode Status (overview tab) -->
		{#if activeTab === 'overview'}
		{#if crisisStatus}
			<CrisisModePanel
				{communityId}
				{crisisStatus}
				{isMember}
				{isAdmin}
				{votingCrisis}
				{togglingCrisis}
				showToggle={false}
				onvote={castVote}
				ontoggle={toggleCrisisMode}
			/>
		{/if}

		{#if activities.length > 0}
			<section class="timeline slide-up" style="animation-delay: 0.06s">
				<h3 class="timeline-heading">{$t('communities.recent_activity')}</h3>
				<ul class="timeline-list">
					{#each activities as item (item.id)}
						<li class="timeline-item">
							<span class="timeline-actor">{item.actor.display_name}</span>
							<span class="timeline-summary">{item.summary}</span>
							<time class="timeline-time" datetime={item.created_at}>{timeAgo(item.created_at)}</time>
						</li>
					{/each}
				</ul>
			</section>
		{/if}
		{/if}

		<!-- Emergency Tickets -->
		{#if activeTab === 'emergency' && isMember}
			<section class="tickets-section slide-up" style="animation-delay: 0.045s">
				<div class="section-header">
					<h2>{$t('communities.tickets_heading', { values: { count: ticketTotal } })}</h2>
					<button class="btn btn-secondary btn-sm" onclick={() => (showTicketForm = !showTicketForm)} aria-expanded={showTicketForm}>
						{showTicketForm ? $t('common.cancel') : $t('communities.new_ticket')}
					</button>
				</div>

				{#if showTicketForm}
					<div class="card ticket-form fade-in">
						<div class="field-row">
							<label class="field">
								<span>{$t('crisis.form_type')}</span>
								<select bind:value={ticketType}>
									<option value="request">{$t('crisis.ticket_types.request')}</option>
									<option value="offer">{$t('crisis.ticket_types.offer')}</option>
									{#if (community?.effective_mode ?? community?.mode) === 'red'}
										<option value="emergency_ping">{$t('crisis.ticket_types.ping')}</option>
									{/if}
								</select>
							</label>
							<label class="field">
								<span>{$t('crisis.form_urgency')}</span>
								<select bind:value={ticketUrgency}>
									<option value="low">{$t('crisis.priority.low')}</option>
									<option value="medium">{$t('crisis.priority.medium')}</option>
									<option value="high">{$t('crisis.priority.high')}</option>
									<option value="critical">{$t('crisis.priority.critical')}</option>
								</select>
							</label>
						</div>
						<label class="field">
							<span>{$t('crisis.form_title_field')}</span>
							<input type="text" bind:value={ticketTitle} placeholder={$t('crisis.title_placeholder')} maxlength="300" />
						</label>
						<label class="field">
							<span>{$t('crisis.form_description_optional')}</span>
							<textarea bind:value={ticketDesc} rows="3" placeholder={$t('crisis.description_placeholder')} maxlength="5000"></textarea>
						</label>
						<button class="btn btn-primary" class:is-loading={creatingTicket} onclick={createTicket} disabled={creatingTicket || !ticketTitle.trim()}>
							{creatingTicket ? $t('crisis.creating_ticket') : $t('crisis.create_ticket')}
						</button>
					</div>
				{/if}

				{#if tickets.length === 0}
					<div class="empty-state compact">
						<span class="empty-icon"><Icon name="inbox" size={22} /></span>
						<p>{$t('communities.no_tickets_yet')}</p>
					</div>
				{:else}
					<div class="tickets-list">
						{#each tickets as ticket (ticket.id)}
							<div class="card ticket-card" class:ticket-resolved={ticket.status === 'resolved'}>
								<div class="ticket-top">
									<span class="badge badge-caps {ticket.ticket_type === 'emergency_ping' ? 'badge-error' : ticket.ticket_type === 'offer' ? 'badge-success' : 'badge-primary'}">
										{ticketTypeLabel(ticket.ticket_type)}
									</span>
									<span class="ticket-urgency" style="color: {URGENCY_COLORS[ticket.urgency] ?? 'var(--color-text-muted)'}">
										{$t(`crisis.priority.${ticket.urgency}`)}
									</span>
									<span class="ticket-status">{$t(`crisis.status_${ticket.status}`)}</span>
								</div>
								<h3>{ticket.title}</h3>
								{#if ticket.description}
									<p class="ticket-desc">{ticket.description}</p>
								{/if}
								<div class="ticket-footer">
									<span class="ticket-meta">{$t('communities.ticket_by', { values: { name: ticket.author.display_name, date: new Date(ticket.created_at).toLocaleDateString() } })}</span>
									{#if (isAdmin || isLeader || ticket.author.id === $user?.id) && ticket.status !== 'resolved'}
										<div class="ticket-actions">
											{#if ticket.status === 'open'}
												<button class="btn btn-secondary btn-sm" onclick={() => updateTicketStatus(ticket.id, 'in_progress')}>{$t('crisis.start_ticket')}</button>
											{/if}
											<button class="btn btn-secondary btn-sm" onclick={() => updateTicketStatus(ticket.id, 'resolved')}>{$t('crisis.resolve_ticket')}</button>
										</div>
									{/if}
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</section>
		{/if}

		{#if activeTab === 'members'}
		<MembersList
			{members}
			{isAdmin}
			currentUserId={$user?.id ?? null}
			{promotingUser}
			onpromote={promoteToLeader}
			ondemote={demoteLeader}
			onmakeadmin={makeAdmin}
		/>
		{/if}

		{#if activeTab === 'resources'}
		<section class="resources-section slide-up" style="animation-delay: 0.1s">
			<div class="section-header">
				<h2>{$t('communities.shared_resources', { values: { count: resourceTotal } })}</h2>
				{#if isMember}
					<a href="/resources" class="btn btn-secondary btn-sm">{$t('communities.browse_all')}</a>
				{/if}
			</div>
			{#if resources.length === 0}
				<div class="empty-state compact">
					<span class="empty-icon"><Icon name="package" size={22} /></span>
					<p>{$t('communities.no_resources_yet')}</p>
					{#if isMember}
						<a href="/resources" class="btn btn-primary btn-sm">{$t('communities.browse_all')}</a>
					{/if}
				</div>
			{:else}
				<div class="resource-grid">
					{#each resources as r (r.id)}
						<a href="/resources/{r.id}" class="card card-flush card-interactive resource-card">
							{#if r.image_url && $bandwidth !== 'low'}
								<div class="res-image">
									<img src="/api{r.image_url}" alt={r.title} />
								</div>
							{:else}
								<div class="res-image res-placeholder">
									<Icon name={RESOURCE_CATEGORY_ICON[r.category] ?? 'package'} size={30} strokeWidth={1.5} />
								</div>
							{/if}
							<div class="res-body">
								<span class="res-category">{$t('resources.categories.' + r.category)}</span>
								<h3>{r.title}</h3>
								<span class="res-owner">{$t('common.by_name', { values: { name: r.owner.display_name } })}</span>
							</div>
						</a>
					{/each}
				</div>
			{/if}
		</section>
		{/if}

		{#if activeTab === 'admin' && isAdmin}
			<!-- Crisis toggle (admin only) -->
			{#if crisisStatus}
				<CrisisModePanel
					{communityId}
					{crisisStatus}
					{isMember}
					{isAdmin}
					{votingCrisis}
					{togglingCrisis}
					showToggle={true}
					onvote={castVote}
					ontoggle={toggleCrisisMode}
				/>
			{/if}
			<InviteLinks
				{communityId}
				{invites}
				onrefresh={async () => {
					invites = await api<InviteOut[]>(`/invites?community_id=${communityId}`, { auth: true });
				}}
			/>

			{#if suggestions.length > 0}
			<section class="merge-section slide-up" style="animation-delay: 0.1s">
				<h2>{$t('communities.merge_suggestions')}</h2>
				<p class="section-hint">{$t('communities.merge_hint')}</p>
				<div class="suggestions-list">
					{#each suggestions as s (s.target.id)}
						<div class="card suggestion-card">
							<div class="suggestion-info">
								<h3>{s.target.name}</h3>
								<div class="suggestion-meta">
									<span class="tag">{s.target.postal_code}</span>
									<span class="tag">{s.target.city}</span>
									<span class="member-count">{$t('common.members', { values: { count: s.target.member_count } })}</span>
								</div>
								<p class="suggestion-reason">{s.reason}</p>
							</div>
							<button
								class="btn btn-primary btn-sm btn-merge"
								class:is-loading={merging === s.target.id}
								onclick={() => merge(s.target.id)}
								disabled={merging === s.target.id}
							>
								{merging === s.target.id ? $t('communities.merging') : $t('communities.merge_into_this')}
							</button>
						</div>
					{/each}
				</div>
			</section>
			{/if}
		{/if}
	{/if}
</div>

<style>
	.detail-page {
		max-width: 900px;
	}

	/* ── Community tabs ─────────────────────────────────────── */

	.community-tabs {
		display: flex;
		gap: 0.15rem;
		border-bottom: 2px solid var(--color-border);
		margin: 1.5rem 0 1.25rem 0;
		overflow-x: auto;
	}

	.community-tab {
		background: none;
		border: none;
		padding: 0.6rem 1rem;
		font-size: 0.88rem;
		font-weight: 500;
		color: var(--color-text-muted);
		cursor: pointer;
		border-bottom: 3px solid transparent;
		margin-bottom: -2px;
		transition: all var(--transition-fast);
		white-space: nowrap;
	}

	.community-tab:hover {
		color: var(--color-text);
	}

	.community-tab.active {
		color: var(--color-primary-text);
		border-bottom-color: var(--color-primary);
		font-weight: 600;
	}

	.back-link {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		font-size: 0.85rem;
		color: var(--color-text-muted);
		text-decoration: none;
		transition: color var(--transition-fast);
	}

	.back-link:hover {
		color: var(--color-primary-text);
	}

	.header-top {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.75rem;
	}

	.community-header h1 {
		font-size: 1.9rem;
		font-weight: 400;
		letter-spacing: -0.01em;
		margin-bottom: 0.5rem;
	}

	.header-meta {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
		font-size: 0.85rem;
		color: var(--color-text-muted);
		margin-bottom: 0.75rem;
	}

	.meta-sep {
		color: var(--color-border);
	}

	.description {
		font-size: 0.95rem;
		color: var(--color-text-muted);
		line-height: 1.6;
		margin-bottom: 1rem;
	}

	.actions {
		margin-top: 1rem;
		margin-bottom: 0.5rem;
	}

	.merge-section {
		margin-top: 2rem;
	}

	.merge-section h2 {
		font-size: 1.15rem;
		font-weight: 500;
		margin-bottom: 0.75rem;
	}

	.section-hint {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		margin-bottom: 0.75rem;
	}

	.suggestions-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.suggestion-card {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 1rem 1.25rem;
	}

	.suggestion-card:hover {
		border-color: var(--color-border-hover);
		box-shadow: var(--shadow-md);
	}

	.suggestion-info h3 {
		font-size: 0.95rem;
		font-weight: 500;
		margin-bottom: 0.3rem;
	}

	.suggestion-meta {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		flex-wrap: wrap;
	}

	.member-count {
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	.suggestion-reason {
		font-size: 0.8rem;
		color: var(--color-text-muted);
		margin-top: 0.25rem;
		font-style: italic;
	}

	.btn-merge {
		flex-shrink: 0;
	}

	/* Page-level alerts sit a little below the header */
	.community-header .alert {
		margin-top: 0.75rem;
	}

	.resources-section {
		margin-top: 2rem;
	}

	.resources-section h2 {
		font-size: 1.15rem;
		font-weight: 500;
	}

	.section-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.75rem;
	}

	.resource-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
		gap: 0.75rem;
	}

	.resource-card {
		display: flex;
		flex-direction: column;
		border-radius: var(--radius);
	}

	.resource-card:hover {
		border-color: var(--color-primary);
	}

	.res-image {
		height: 90px;
		overflow: hidden;
		background: var(--color-bg);
	}

	.res-image img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	.res-placeholder {
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--color-primary-text);
		opacity: 0.6;
	}

	.res-body {
		padding: 0.5rem 0.65rem 0.65rem;
	}

	.res-category {
		font-size: 0.65rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--color-primary-text);
		font-weight: 600;
	}

	.res-body h3 {
		font-size: 0.88rem;
		font-weight: 500;
		margin: 0.15rem 0;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.res-owner {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}

	/* ── Emergency tickets ──────────────────── */

	.tickets-section {
		margin-top: 2rem;
	}

	.tickets-section h2 {
		font-size: 1.15rem;
		font-weight: 500;
	}

	.ticket-form {
		padding: 1rem 1.25rem;
		margin-bottom: 0.75rem;
		display: flex;
		flex-direction: column;
		gap: 0.65rem;
	}

	.tickets-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.ticket-card {
		padding: 0.85rem 1rem;
		border-radius: var(--radius);
	}

	.ticket-resolved {
		opacity: 0.6;
	}

	.ticket-top {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		margin-bottom: 0.3rem;
	}

	.ticket-urgency {
		font-size: 0.72rem;
		font-weight: 600;
		text-transform: uppercase;
	}

	.ticket-status {
		font-size: 0.72rem;
		color: var(--color-text-muted);
		margin-inline-start: auto;
		text-transform: capitalize;
	}

	.ticket-card h3 {
		font-size: 0.92rem;
		font-weight: 500;
		margin-bottom: 0.15rem;
	}

	.ticket-desc {
		font-size: 0.82rem;
		color: var(--color-text-muted);
		line-height: 1.5;
		margin-bottom: 0.35rem;
	}

	.ticket-footer {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}

	.ticket-meta {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}

	.ticket-actions {
		display: flex;
		gap: 0.3rem;
	}

	/* ── Community timeline ──────────────────── */

	.timeline {
		margin-top: 1.5rem;
		padding: 1rem 1.25rem;
		background: var(--color-surface);
		border-radius: 0.75rem;
	}

	.timeline-heading {
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--color-text-muted);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		margin: 0 0 0.75rem;
	}

	.timeline-list {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
	}

	.timeline-item {
		display: flex;
		align-items: baseline;
		gap: 0.35rem;
		padding: 0.45rem 0;
		border-bottom: 1px solid color-mix(in srgb, var(--color-text-muted) 15%, transparent);
		font-size: 0.875rem;
		flex-wrap: wrap;
	}

	.timeline-item:last-child {
		border-bottom: none;
		padding-bottom: 0;
	}

	.timeline-actor {
		font-weight: 600;
		color: var(--color-primary-text);
		white-space: nowrap;
	}

	.timeline-summary {
		flex: 1;
		color: var(--color-text);
	}

	.timeline-time {
		font-size: 0.775rem;
		color: var(--color-text-muted);
		white-space: nowrap;
		margin-inline-start: auto;
	}

	.empty-state.compact {
		padding: 1.5rem 1rem;
	}
</style>
