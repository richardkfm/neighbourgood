<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { isLoggedIn, user } from '$lib/stores/auth';
	import { bandwidth, setPlatformMode } from '$lib/stores/theme';
	import type { ActivityOut, ActivityList, CommunityOut, CrisisStatus, EmergencyTicket as TicketOut, TicketList, CommunityMember as MemberOut, MergeSuggestion, InviteOut, Resource as ResourceItem } from '$lib/types';
	import CrisisModePanel from '$lib/components/community/CrisisModePanel.svelte';
	import MembersList from '$lib/components/community/MembersList.svelte';
	import InviteLinks from '$lib/components/community/InviteLinks.svelte';

	const CATEGORY_ICONS: Record<string, string> = {
		tool: '🔧', vehicle: '🚗', electronics: '⚡', furniture: '🪑',
		food: '🍎', clothing: '👕', skill: '💡', other: '📦'
	};

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
			// Apply the community's mode to the global theme
			if (crisisStatus) {
				setPlatformMode(crisisStatus.mode as 'blue' | 'red');
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
			error = err instanceof Error ? err.message : 'Failed to load';
		} finally {
			loading = false;
		}
	}

	function timeAgo(iso: string): string {
		const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
		if (diff < 60) return 'just now';
		if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
		if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
		return `${Math.floor(diff / 86400)}d ago`;
	}

	async function join() {
		joiningOrLeaving = true;
		error = '';
		try {
			await api(`/communities/${communityId}/join`, { method: 'POST', auth: true });
			actionMsg = 'Joined!';
			await loadData();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Could not join';
		} finally {
			joiningOrLeaving = false;
		}
	}

	async function leave() {
		joiningOrLeaving = true;
		error = '';
		try {
			await api(`/communities/${communityId}/leave`, { method: 'DELETE', auth: true });
			actionMsg = 'You left this community.';
			await loadData();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Could not leave';
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
			actionMsg = 'Communities merged! Redirecting...';
			setTimeout(() => goto(`/communities/${targetId}`), 1200);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Merge failed';
		} finally {
			merging = null;
		}
	}

	// ── Crisis mode functions ──────────────────────────

	async function toggleCrisisMode(newMode: string) {
		togglingCrisis = true;
		error = '';
		try {
			crisisStatus = await api<CrisisStatus>(`/communities/${communityId}/crisis/toggle`, {
				method: 'POST', auth: true, body: { mode: newMode }
			});
			// Apply the mode to the global theme immediately
			setPlatformMode(newMode as 'blue' | 'red');
			actionMsg = newMode === 'red' ? 'Crisis mode activated!' : 'Switched back to normal mode.';
			await loadData();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to toggle crisis mode';
		} finally {
			togglingCrisis = false;
		}
	}

	async function castVote(voteType: string) {
		votingCrisis = true;
		error = '';
		try {
			await api(`/communities/${communityId}/crisis/vote`, {
				method: 'POST', auth: true, body: { vote_type: voteType }
			});
			crisisStatus = await api<CrisisStatus>(`/communities/${communityId}/crisis/status`);
			actionMsg = `Vote recorded: ${voteType}`;
			// Reload in case mode switched
			await loadData();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to cast vote';
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
			error = err instanceof Error ? err.message : 'Failed to create ticket';
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
			error = err instanceof Error ? err.message : 'Failed to update ticket';
		}
	}

	async function promoteToLeader(userId: number) {
		promotingUser = userId;
		error = '';
		try {
			await api(`/communities/${communityId}/leaders/${userId}`, { method: 'POST', auth: true });
			actionMsg = 'User promoted to leader!';
			await loadData();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to promote';
		} finally {
			promotingUser = null;
		}
	}

	async function demoteLeader(userId: number) {
		promotingUser = userId;
		error = '';
		try {
			await api(`/communities/${communityId}/leaders/${userId}`, { method: 'DELETE', auth: true });
			actionMsg = 'User demoted from leader.';
			await loadData();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to demote';
		} finally {
			promotingUser = null;
		}
	}

	const URGENCY_COLORS: Record<string, string> = {
		low: 'var(--color-text-muted)',
		medium: 'var(--color-warning)',
		high: '#f97316',
		critical: 'var(--color-error)'
	};

	const TICKET_TYPE_LABELS: Record<string, string> = {
		request: 'Request',
		offer: 'Offer',
		emergency_ping: 'Emergency Ping'
	};

	let activeTab = $state('overview');
</script>

<div class="detail-page">
	{#if loading}
		<p class="loading-text">Loading...</p>
	{:else if error && !community}
		<div class="alert alert-error">{error}</div>
	{:else if community}
		<div class="community-header slide-up">
			<div class="header-top">
				<a href="/communities" class="back-link">&#8592; Communities</a>
				{#if !community.is_active}
					<span class="badge-merged">Merged</span>
				{/if}
			</div>

			<h1>{community.name}</h1>
			<div class="header-meta">
				<span class="tag">{community.postal_code}</span>
				<span class="tag">{community.city}</span>
				<span class="meta-sep">&middot;</span>
				<span>{community.member_count} member{community.member_count !== 1 ? 's' : ''}</span>
				<span class="meta-sep">&middot;</span>
				<span>Created {new Date(community.created_at).toLocaleDateString()}</span>
			</div>

			{#if community.description}
				<p class="description">{community.description}</p>
			{/if}

			{#if community.merged_into_id}
				<div class="alert alert-info fade-in">
					This community has been merged into <a href="/communities/{community.merged_into_id}">another community</a>.
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
						<button class="btn-secondary" onclick={leave} disabled={joiningOrLeaving}>
							{joiningOrLeaving ? 'Leaving...' : 'Leave Community'}
						</button>
					{:else}
						<button class="btn-primary" onclick={join} disabled={joiningOrLeaving}>
							{joiningOrLeaving ? 'Joining...' : 'Join Community'}
						</button>
					{/if}
				</div>
			{/if}
		</div>

		<!-- Tab navigation -->
		<nav class="community-tabs">
			<button class="community-tab" class:active={activeTab === 'overview'} onclick={() => activeTab = 'overview'}>Overview</button>
			<button class="community-tab" class:active={activeTab === 'members'} onclick={() => activeTab = 'members'}>Members ({members.length})</button>
			<button class="community-tab" class:active={activeTab === 'resources'} onclick={() => activeTab = 'resources'}>Resources ({resourceTotal})</button>
			{#if isMember}
				<button class="community-tab" class:active={activeTab === 'emergency'} onclick={() => activeTab = 'emergency'}>Emergency {ticketTotal > 0 ? `(${ticketTotal})` : ''}</button>
			{/if}
			{#if isAdmin}
				<button class="community-tab" class:active={activeTab === 'admin'} onclick={() => activeTab = 'admin'}>Admin</button>
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
				<h3 class="timeline-heading">Recent Activity</h3>
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
					<h2>Emergency Tickets ({ticketTotal})</h2>
					<button class="btn-small" onclick={() => (showTicketForm = !showTicketForm)}>
						{showTicketForm ? 'Cancel' : 'New Ticket'}
					</button>
				</div>

				{#if showTicketForm}
					<div class="ticket-form fade-in">
						<div class="ticket-form-row">
							<label>
								<span>Type</span>
								<select bind:value={ticketType}>
									<option value="request">Request</option>
									<option value="offer">Offer</option>
									{#if community?.mode === 'red'}
										<option value="emergency_ping">Emergency Ping</option>
									{/if}
								</select>
							</label>
							<label>
								<span>Urgency</span>
								<select bind:value={ticketUrgency}>
									<option value="low">Low</option>
									<option value="medium">Medium</option>
									<option value="high">High</option>
									<option value="critical">Critical</option>
								</select>
							</label>
						</div>
						<label>
							<span>Title</span>
							<input type="text" bind:value={ticketTitle} placeholder="Short description..." maxlength="300" />
						</label>
						<label>
							<span>Description (optional)</span>
							<textarea bind:value={ticketDesc} rows="3" placeholder="More details..." maxlength="5000"></textarea>
						</label>
						<button class="btn-primary" onclick={createTicket} disabled={creatingTicket || !ticketTitle.trim()}>
							{creatingTicket ? 'Creating...' : 'Create Ticket'}
						</button>
					</div>
				{/if}

				{#if tickets.length === 0}
					<p class="section-hint">No emergency tickets yet.</p>
				{:else}
					<div class="tickets-list">
						{#each tickets as t (t.id)}
							<div class="ticket-card" class:ticket-resolved={t.status === 'resolved'}>
								<div class="ticket-top">
									<span class="ticket-type-badge" style="background: {t.ticket_type === 'emergency_ping' ? 'var(--color-error)' : t.ticket_type === 'offer' ? 'var(--color-success)' : 'var(--color-primary)'}">
										{TICKET_TYPE_LABELS[t.ticket_type] ?? t.ticket_type}
									</span>
									<span class="ticket-urgency" style="color: {URGENCY_COLORS[t.urgency] ?? 'var(--color-text-muted)'}">
										{t.urgency}
									</span>
									<span class="ticket-status">{t.status.replace('_', ' ')}</span>
								</div>
								<h3>{t.title}</h3>
								{#if t.description}
									<p class="ticket-desc">{t.description}</p>
								{/if}
								<div class="ticket-footer">
									<span class="ticket-meta">by {t.author.display_name} &middot; {new Date(t.created_at).toLocaleDateString()}</span>
									{#if (isAdmin || isLeader || t.author.id === $user?.id) && t.status !== 'resolved'}
										<div class="ticket-actions">
											{#if t.status === 'open'}
												<button class="btn-tiny" onclick={() => updateTicketStatus(t.id, 'in_progress')}>Start</button>
											{/if}
											<button class="btn-tiny btn-tiny-success" onclick={() => updateTicketStatus(t.id, 'resolved')}>Resolve</button>
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
		/>
		{/if}

		{#if activeTab === 'resources'}
		<section class="resources-section slide-up" style="animation-delay: 0.1s">
			<div class="section-header">
				<h2>Shared Resources ({resourceTotal})</h2>
				{#if isMember}
					<a href="/resources" class="btn-small">Browse all</a>
				{/if}
			</div>
			{#if resources.length === 0}
				<p class="section-hint">No resources shared in this community yet.</p>
			{:else}
				<div class="resource-grid">
					{#each resources as r (r.id)}
						<a href="/resources/{r.id}" class="resource-card">
							{#if r.image_url && $bandwidth !== 'low'}
								<div class="res-image">
									<img src="/api{r.image_url}" alt={r.title} />
								</div>
							{:else}
								<div class="res-image res-placeholder">
									<span>{CATEGORY_ICONS[r.category] ?? '📦'}</span>
								</div>
							{/if}
							<div class="res-body">
								<span class="res-category">{r.category}</span>
								<h3>{r.title}</h3>
								<span class="res-owner">by {r.owner.display_name}</span>
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
				<h2>Merge Suggestions</h2>
				<p class="section-hint">These communities share your postal code or city. Merging combines members into one group.</p>
				<div class="suggestions-list">
					{#each suggestions as s (s.target.id)}
						<div class="suggestion-card">
							<div class="suggestion-info">
								<h3>{s.target.name}</h3>
								<div class="suggestion-meta">
									<span class="tag">{s.target.postal_code}</span>
									<span class="tag">{s.target.city}</span>
									<span class="member-count">{s.target.member_count} members</span>
								</div>
								<p class="suggestion-reason">{s.reason}</p>
							</div>
							<button
								class="btn-merge"
								onclick={() => merge(s.target.id)}
								disabled={merging === s.target.id}
							>
								{merging === s.target.id ? 'Merging...' : 'Merge into this'}
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

	.loading-text {
		text-align: center;
		color: var(--color-text-muted);
		padding: 3rem;
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
		color: var(--color-primary);
		border-bottom-color: var(--color-primary);
		font-weight: 600;
	}

	.back-link {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		text-decoration: none;
		transition: color var(--transition-fast);
	}

	.back-link:hover {
		color: var(--color-primary);
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

	.tag {
		font-size: 0.72rem;
		font-weight: 500;
		padding: 0.12rem 0.45rem;
		border-radius: 999px;
		background: var(--color-primary-light);
		color: var(--color-primary);
	}

	.description {
		font-size: 0.95rem;
		color: var(--color-text-muted);
		line-height: 1.6;
		margin-bottom: 1rem;
	}

	.badge-merged {
		font-size: 0.72rem;
		padding: 0.15rem 0.6rem;
		border-radius: 999px;
		background: var(--color-text-muted);
		color: white;
		font-weight: 600;
	}

	.actions {
		margin-top: 1rem;
		margin-bottom: 0.5rem;
	}

	.btn-primary {
		padding: 0.55rem 1.25rem;
		background: var(--color-primary);
		color: white;
		border: none;
		border-radius: var(--radius);
		font-size: 0.9rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--color-primary-hover);
		box-shadow: var(--shadow);
	}

	.btn-primary:disabled,
	.btn-secondary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-secondary {
		padding: 0.55rem 1.25rem;
		background: var(--color-surface);
		color: var(--color-text-muted);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.9rem;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.btn-secondary:hover:not(:disabled) {
		border-color: var(--color-error);
		color: var(--color-error);
	}

	.members-section,
	.merge-section {
		margin-top: 2rem;
	}

	.members-section h2,
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

	.members-list {
		display: flex;
		flex-direction: column;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		overflow: hidden;
	}

	.member-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.75rem 1rem;
		border-bottom: 1px solid var(--color-border);
		background: var(--color-surface);
	}

	.member-row:last-child {
		border-bottom: none;
	}

	.member-info {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.member-name {
		font-weight: 500;
		font-size: 0.92rem;
	}

	.role-badge {
		font-size: 0.68rem;
		font-weight: 600;
		padding: 0.1rem 0.4rem;
		border-radius: 999px;
		background: var(--color-primary-light);
		color: var(--color-primary);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.member-date {
		font-size: 0.8rem;
		color: var(--color-text-muted);
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
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		transition: all var(--transition-fast);
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
		padding: 0.45rem 1rem;
		background: var(--color-accent);
		color: white;
		border: none;
		border-radius: var(--radius);
		font-size: 0.82rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
		white-space: nowrap;
		flex-shrink: 0;
	}

	.btn-merge:hover:not(:disabled) {
		filter: brightness(1.1);
		box-shadow: var(--shadow);
	}

	.btn-merge:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.alert {
		padding: 0.65rem 1rem;
		border-radius: var(--radius);
		font-size: 0.9rem;
		margin-bottom: 1rem;
		margin-top: 0.75rem;
	}

	.alert-error {
		background: var(--color-error-bg);
		color: var(--color-error);
		border: 1px solid var(--color-error);
	}

	.alert-success {
		background: #ecfdf5;
		color: #065f46;
		border: 1px solid #a7f3d0;
	}

	:global([data-theme='dark']) .alert-success {
		background: #064e3b;
		color: #6ee7b7;
		border-color: #065f46;
	}

	.alert-info {
		background: var(--color-primary-light);
		color: var(--color-primary);
		border: 1px solid var(--color-primary);
	}

	.alert-info a {
		color: inherit;
		font-weight: 600;
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

	.btn-small {
		font-size: 0.8rem;
		padding: 0.3rem 0.7rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		color: var(--color-text-muted);
		text-decoration: none;
		transition: all var(--transition-fast);
	}

	.btn-small:hover {
		border-color: var(--color-primary);
		color: var(--color-primary);
	}

	.resource-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
		gap: 0.75rem;
	}

	.resource-card {
		display: flex;
		flex-direction: column;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		text-decoration: none;
		color: var(--color-text);
		overflow: hidden;
		transition: border-color var(--transition-fast);
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
		font-size: 1.8rem;
		opacity: 0.5;
	}

	.res-body {
		padding: 0.5rem 0.65rem 0.65rem;
	}

	.res-category {
		font-size: 0.65rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--color-primary);
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

	/* Invites */
	.invites-section {
		margin-top: 2rem;
	}

	.invites-section h2 {
		font-size: 1.15rem;
		font-weight: 500;
	}

	.invite-form {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 1rem 1.25rem;
		margin-bottom: 0.75rem;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.invite-form-row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.75rem;
	}

	.invite-form label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.invite-form label span {
		font-size: 0.82rem;
		font-weight: 500;
		color: var(--color-text-muted);
	}

	.invite-form input {
		padding: 0.4rem 0.6rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.85rem;
		background: var(--color-bg);
		color: var(--color-text);
	}

	.invites-list {
		display: flex;
		flex-direction: column;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		overflow: hidden;
	}

	.invite-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.75rem 1rem;
		border-bottom: 1px solid var(--color-border);
		background: var(--color-surface);
	}

	.invite-row:last-child {
		border-bottom: none;
	}

	.invite-info {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}

	.invite-code {
		font-size: 0.82rem;
		font-weight: 500;
		background: var(--color-bg);
		padding: 0.1rem 0.35rem;
		border-radius: var(--radius-sm);
	}

	.invite-meta {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}

	.invite-actions {
		display: flex;
		gap: 0.4rem;
		flex-shrink: 0;
	}

	.btn-small-danger {
		color: var(--color-error) !important;
		border-color: var(--color-error) !important;
	}

	.btn-small-danger:hover {
		background: var(--color-error) !important;
		color: white !important;
	}

	/* ── Crisis mode ────────────────────────── */

	.crisis-section {
		margin-top: 1.5rem;
		padding: 1rem 1.25rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
	}

	.crisis-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.crisis-indicator {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.crisis-dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: var(--color-primary);
	}

	.crisis-red .crisis-dot {
		background: var(--color-error);
		animation: pulse-crisis 1.5s infinite;
	}

	@keyframes pulse-crisis {
		0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
		50% { opacity: 0.8; box-shadow: 0 0 0 6px rgba(239, 68, 68, 0); }
	}

	.crisis-label {
		font-size: 0.92rem;
		font-weight: 600;
	}

	.crisis-red .crisis-label {
		color: var(--color-error);
	}

	.btn-crisis-activate {
		padding: 0.4rem 0.9rem;
		background: var(--color-error);
		color: white;
		border: none;
		border-radius: var(--radius);
		font-size: 0.82rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.btn-crisis-activate:hover:not(:disabled) {
		filter: brightness(1.1);
		box-shadow: var(--shadow);
	}

	.btn-crisis-deactivate {
		padding: 0.4rem 0.9rem;
		background: var(--color-primary);
		color: white;
		border: none;
		border-radius: var(--radius);
		font-size: 0.82rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.btn-crisis-deactivate:hover:not(:disabled) {
		filter: brightness(1.1);
	}

	.btn-crisis-activate:disabled,
	.btn-crisis-deactivate:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.vote-section {
		margin-top: 0.75rem;
		padding-top: 0.75rem;
		border-top: 1px solid var(--color-border);
	}

	.vote-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.vote-info {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		font-size: 0.82rem;
		color: var(--color-text-muted);
	}

	.vote-threshold {
		font-style: italic;
	}

	.vote-actions {
		display: flex;
		gap: 0.4rem;
	}

	.btn-vote {
		padding: 0.3rem 0.7rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.78rem;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition-fast);
		background: var(--color-surface);
	}

	.btn-vote:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-vote-red {
		color: var(--color-error);
		border-color: var(--color-error);
	}

	.btn-vote-red:hover:not(:disabled) {
		background: var(--color-error);
		color: white;
	}

	.btn-vote-blue {
		color: var(--color-primary);
		border-color: var(--color-primary);
	}

	.btn-vote-blue:hover:not(:disabled) {
		background: var(--color-primary);
		color: white;
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
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 1rem 1.25rem;
		margin-bottom: 0.75rem;
		display: flex;
		flex-direction: column;
		gap: 0.65rem;
	}

	.ticket-form-row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.65rem;
	}

	.ticket-form label {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}

	.ticket-form label span {
		font-size: 0.82rem;
		font-weight: 500;
		color: var(--color-text-muted);
	}

	.ticket-form input,
	.ticket-form textarea,
	.ticket-form select {
		padding: 0.4rem 0.6rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.85rem;
		background: var(--color-bg);
		color: var(--color-text);
	}

	.tickets-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.ticket-card {
		padding: 0.85rem 1rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		transition: all var(--transition-fast);
	}

	.ticket-card:hover {
		border-color: var(--color-border-hover);
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

	.ticket-type-badge {
		font-size: 0.65rem;
		font-weight: 600;
		padding: 0.1rem 0.4rem;
		border-radius: 999px;
		color: white;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.ticket-urgency {
		font-size: 0.72rem;
		font-weight: 600;
		text-transform: uppercase;
	}

	.ticket-status {
		font-size: 0.72rem;
		color: var(--color-text-muted);
		margin-left: auto;
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

	.btn-tiny {
		font-size: 0.72rem;
		padding: 0.2rem 0.5rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-surface);
		color: var(--color-text-muted);
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.btn-tiny:hover:not(:disabled) {
		border-color: var(--color-primary);
		color: var(--color-primary);
	}

	.btn-tiny:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-tiny-success:hover:not(:disabled) {
		border-color: var(--color-success);
		color: var(--color-success);
	}

	/* ── Leader badge ───────────────────────── */

	.role-badge-leader {
		background: var(--color-accent-light);
		color: var(--color-accent);
	}

	.member-right {
		display: flex;
		align-items: center;
		gap: 0.5rem;
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
		color: var(--color-primary);
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
		margin-left: auto;
	}
</style>
