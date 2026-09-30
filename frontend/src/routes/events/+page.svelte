<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { t } from 'svelte-i18n';
	import { api } from '$lib/api';
	import { isLoggedIn } from '$lib/stores/auth';
	import type { CommunityEvent } from '$lib/types';

	interface MyCommunity {
		id: number;
		name: string;
		postal_code: string;
	}

	const CATEGORY_ICONS: Record<string, string> = {
		meetup: '🤝',
		workshop: '📖',
		repair_cafe: '🔧',
		swap: '🔄',
		gardening: '🌱',
		food: '🍽️',
		sport: '⚽',
		cultural: '🎵',
		other: '⭐'
	};

	const CATEGORIES = ['', 'meetup', 'workshop', 'repair_cafe', 'swap', 'gardening', 'food', 'sport', 'cultural', 'other'];

	let events = $state<CommunityEvent[]>([]);
	let total = $state(0);
	let loading = $state(true);
	let filterCategory = $state('');
	let filterUpcoming = $state(true);
	let filterCommunity = $state('');
	let searchQuery = $state('');
	let searchTimeout: ReturnType<typeof setTimeout> | null = $state(null);
	let showCreateForm = $state(false);

	// Create form state
	let newTitle = $state('');
	let newDescription = $state('');
	let newCategory = $state('meetup');
	let newStartDate = $state('');
	let newStartTime = $state('');
	let newEndDate = $state('');
	let newEndTime = $state('');
	let newLocation = $state('');
	let newMaxAttendees = $state('');
	let newCommunityId = $state('');
	let createError = $state('');
	let rsvpError = $state('');
	let myCommunities = $state<MyCommunity[]>([]);
	let myCommunitiesLoaded = $state(false);
	let requestId = 0;

	async function loadEvents() {
		const thisRequest = ++requestId;
		loading = true;
		try {
			const params = new URLSearchParams();
			if (filterCommunity) params.set('community_id', filterCommunity);
			if (filterCategory) params.set('category', filterCategory);
			if (filterUpcoming) params.set('upcoming', 'true');
			if (searchQuery.trim()) params.set('q', searchQuery.trim());
			params.set('limit', '50');

			const qs = params.toString();
			const data = await api<{ items: CommunityEvent[]; total: number }>(
				`/events${qs ? '?' + qs : ''}`,
				{ auth: true }
			);
			if (thisRequest !== requestId) return; // superseded by a newer request
			events = Array.isArray(data?.items) ? data.items : [];
			total = data?.total ?? 0;
		} catch {
			if (thisRequest !== requestId) return;
			events = [];
			total = 0;
		} finally {
			if (thisRequest === requestId) loading = false;
		}
	}

	async function loadMyCommunities() {
		try {
			const data = await api<MyCommunity[]>('/communities/my/memberships', { auth: true });
			myCommunities = Array.isArray(data) ? data : [];
			if (myCommunities.length > 0) {
				newCommunityId = String(myCommunities[0].id);
				filterCommunity = String(myCommunities[0].id);
			}
		} catch {
			myCommunities = [];
		} finally {
			myCommunitiesLoaded = true;
		}
	}

	function pad(n: number) { return String(n).padStart(2, '0'); }

	function openCreateForm() {
		if (showCreateForm) {
			showCreateForm = false;
			return;
		}
		const now = new Date();
		now.setMinutes(now.getMinutes() < 30 ? 30 : 60, 0, 0);
		newStartDate = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
		newStartTime = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
		const end = new Date(now.getTime() + 2 * 60 * 60 * 1000);
		newEndDate = `${end.getFullYear()}-${pad(end.getMonth() + 1)}-${pad(end.getDate())}`;
		newEndTime = `${pad(end.getHours())}:${pad(end.getMinutes())}`;
		showCreateForm = true;
	}

	function onSearchInput() {
		if (searchTimeout) clearTimeout(searchTimeout);
		searchTimeout = setTimeout(loadEvents, 300);
	}

	async function createEvent() {
		createError = '';
		if (!newTitle.trim()) {
			createError = $t('events.error_title_required');
			return;
		}
		if (!newStartDate || !newStartTime) {
			createError = $t('events.error_start_required');
			return;
		}
		if (!newCommunityId) {
			createError = $t('events.error_no_community');
			return;
		}
		try {
			const startIso = new Date(`${newStartDate}T${newStartTime}`).toISOString();
			const endIso = newEndDate && newEndTime
				? new Date(`${newEndDate}T${newEndTime}`).toISOString()
				: null;
			await api('/events', {
				method: 'POST',
				auth: true,
				body: {
					title: newTitle.trim(),
					description: newDescription.trim() || null,
					category: newCategory,
					start_at: startIso,
					end_at: endIso,
					location: newLocation.trim() || null,
					max_attendees: newMaxAttendees ? parseInt(newMaxAttendees) : null,
					community_id: parseInt(newCommunityId)
				}
			});
			newTitle = '';
			newDescription = '';
			newCategory = 'meetup';
			newStartDate = '';
			newStartTime = '';
			newEndDate = '';
			newEndTime = '';
			newLocation = '';
			newMaxAttendees = '';
			showCreateForm = false;
			await loadEvents();
		} catch (err: unknown) {
			createError = err instanceof Error ? err.message : 'Could not create event.';
		}
	}

	async function toggleAttend(event: CommunityEvent) {
		rsvpError = '';
		try {
			if (event.is_attending) {
				await api(`/events/${event.id}/attend`, { method: 'DELETE', auth: true });
			} else {
				await api(`/events/${event.id}/attend`, { method: 'POST', auth: true });
			}
			await loadEvents();
		} catch (err: unknown) {
			rsvpError = err instanceof Error ? err.message : $t('common.error');
		}
	}

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleString(undefined, {
			weekday: 'short',
			day: 'numeric',
			month: 'short',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function isPast(event: CommunityEvent): boolean {
		return new Date(event.end_at ?? event.start_at).getTime() < Date.now();
	}

	onMount(() => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}
		loadMyCommunities();
	});

	$effect(() => {
		filterCategory;
		filterUpcoming;
		filterCommunity;
		if (!myCommunitiesLoaded) return;
		loadEvents();
	});
</script>

<svelte:head>
	<title>{$t('events.title')} — NeighbourGood</title>
</svelte:head>

<div class="events-page">
	<div class="page-header">
		<div>
			<h1>{$t('events.title')}</h1>
			<p class="subtitle">{$t('events.subtitle')}</p>
		</div>
		{#if $isLoggedIn}
			<button class="btn btn-primary" onclick={openCreateForm}>
				{showCreateForm ? $t('events.cancel_form') : $t('events.create_btn')}
			</button>
		{/if}
	</div>

	{#if showCreateForm}
		<div class="create-form card">
			<h2>{$t('events.form_title')}</h2>
			{#if createError}
				<p class="error">{createError}</p>
			{/if}
			<div class="form-grid">
				<label>
					{$t('events.form.title_label')} *
					<input type="text" bind:value={newTitle} maxlength="200" placeholder={$t('events.form.title_placeholder')} />
				</label>
				<label>
					{$t('events.form.category_label')}
					<select bind:value={newCategory}>
						{#each CATEGORIES.slice(1) as cat}
							<option value={cat}>{CATEGORY_ICONS[cat]} {$t('events.categories.' + cat)}</option>
						{/each}
					</select>
				</label>
				<label>
					{$t('events.form.start_date_label')} *
					<input type="date" bind:value={newStartDate} />
				</label>
				<label>
					{$t('events.form.start_time_label')} *
					<input type="time" bind:value={newStartTime} step="900" />
				</label>
				<label>
					{$t('events.form.end_date_label')}
					<input type="date" bind:value={newEndDate} min={newStartDate} />
				</label>
				<label>
					{$t('events.form.end_time_label')}
					<input type="time" bind:value={newEndTime} step="900" />
				</label>
				<label>
					{$t('events.form.location_label')}
					<input type="text" bind:value={newLocation} maxlength="300" placeholder={$t('events.form.location_placeholder')} />
				</label>
				<label>
					{$t('events.form.max_attendees_label')}
					<input type="number" bind:value={newMaxAttendees} min="1" max="10000" placeholder={$t('events.form.max_attendees_placeholder')} />
				</label>
				{#if myCommunities.length > 1}
				<p class="community-info full-width">{$t('events.community_label')} <strong>{myCommunities[0].name}</strong></p>
			{/if}
				<label class="full-width">
					{$t('events.form.description_label')}
					<textarea bind:value={newDescription} maxlength="5000" rows="3" placeholder={$t('events.form.description_placeholder')}></textarea>
				</label>
			</div>
			<button class="btn btn-primary" onclick={createEvent}>{$t('events.form_submit')}</button>
		</div>
	{/if}

	<div class="filters">
		<input
			class="search-input"
			type="search"
			bind:value={searchQuery}
			oninput={onSearchInput}
			placeholder={$t('events.search_placeholder')}
		/>
		<select bind:value={filterCategory}>
			{#each CATEGORIES as cat}
				<option value={cat}>
					{cat === '' ? $t('events.all_categories') : $t('events.categories.' + cat)}
				</option>
			{/each}
		</select>
		{#if myCommunities.length > 1}
		<select bind:value={filterCommunity}>
			{#each myCommunities as c}
				<option value={String(c.id)}>{c.name}</option>
			{/each}
		</select>
		{/if}
		<label class="toggle-label">
			<input type="checkbox" bind:checked={filterUpcoming} />
			{$t('events.upcoming_only')}
		</label>
		{#if !loading}
			<span class="result-count">
				{$t(total === 1 ? 'events.event_count_one' : 'events.event_count_other', { values: { count: total } })}
			</span>
		{/if}
	</div>

	{#if rsvpError}
		<div class="error-banner" role="alert">{rsvpError}</div>
	{/if}

	{#if loading}
		<p class="loading-text">{$t('common.loading')}</p>
	{:else if events.length === 0}
		<div class="empty-state">
			<p>{$isLoggedIn ? $t('events.no_events') : $t('events.no_events_guest')}</p>
		</div>
	{:else}
		<ul class="event-list">
			{#each events as event (event.id)}
				<li class="event-card card" class:event-past={isPast(event)}>
					<a class="event-link" href={`/events/${event.id}`}>
						<div class="event-header">
							<div class="category-icon-wrap">
								<span>{CATEGORY_ICONS[event.category] ?? '📅'}</span>
							</div>
							<div class="event-meta">
								<h3 class="event-title">
									{event.title}
									{#if isPast(event)}
										<span class="past-badge">{$t('events.past_badge')}</span>
									{/if}
								</h3>
								<p class="event-date">{formatDate(event.start_at)}
									{#if event.end_at} — {formatDate(event.end_at)}{/if}
								</p>
								{#if event.location}
									<p class="event-location">📍 {event.location}</p>
								{/if}
							</div>
						</div>
						{#if event.description}
							<p class="event-description">{event.description}</p>
						{/if}
					</a>
					<div class="event-footer">
						<span class="attendee-count">
							👥 {event.attendee_count}{event.max_attendees ? `/${event.max_attendees}` : ''} {$t('events.attendees')}
						</span>
						<span class="organizer">{$t('events.organizer_by', { values: { name: event.organizer.display_name } })}</span>
						{#if $isLoggedIn}
							<button
								class="btn btn-sm {event.is_attending ? 'btn-secondary' : 'btn-primary'}"
								onclick={(e) => { e.preventDefault(); e.stopPropagation(); toggleAttend(event); }}
								disabled={!event.is_attending && event.max_attendees !== null && event.attendee_count >= event.max_attendees}
							>
								{event.is_attending ? $t('events.unattend') : $t('events.attend')}
							</button>
						{/if}
					</div>
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.events-page {
		max-width: 900px;
	}

	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
		margin-bottom: 1.5rem;
		flex-wrap: wrap;
	}

	.page-header h1 {
		margin: 0 0 0.25rem;
	}

	.subtitle {
		margin: 0;
		color: var(--color-text-muted);
		font-size: 0.95rem;
	}


	.card {
		background: var(--color-surface);
		border-radius: var(--radius-lg);
		padding: 1.25rem;
		margin-bottom: 1rem;
		border: 1px solid var(--color-border);
		box-shadow: var(--shadow-sm);
		transition: all var(--transition);
	}

	.create-form h2 {
		margin-top: 0;
	}

	.community-info {
		margin: 0;
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}

	.form-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.75rem;
		margin-bottom: 1rem;
	}

	.form-grid label {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}

	.form-grid .full-width {
		grid-column: 1 / -1;
	}

	.form-grid input,
	.form-grid select,
	.form-grid textarea {
		padding: 0.45rem 0.6rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-bg);
		color: var(--color-text);
		font-size: 0.9rem;
	}

	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 0.6rem;
		margin-bottom: 1.25rem;
		align-items: center;
	}

	.search-input {
		flex: 1;
		min-width: 160px;
		padding: 0.45rem 0.7rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-surface);
		color: var(--color-text);
	}

	.filters select {
		padding: 0.45rem 0.6rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-surface);
		color: var(--color-text);
	}

	.toggle-label {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.875rem;
		cursor: pointer;
	}

	.result-count {
		font-size: 0.8rem;
		color: var(--color-text-muted);
		margin-left: auto;
	}

	.event-list {
		list-style: none;
		padding: 0;
		margin: 0;
	}

	.event-card {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.event-card:hover {
		box-shadow: var(--shadow-md);
		border-color: var(--color-border-hover);
		transform: translateY(-2px);
	}

	.event-card.event-past {
		opacity: 0.6;
	}

	.past-badge {
		display: inline-block;
		margin-left: 0.5rem;
		padding: 0.1rem 0.5rem;
		border-radius: 999px;
		background: var(--color-border);
		color: var(--color-text-muted);
		font-size: 0.7rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		vertical-align: middle;
	}

	.event-link {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		text-decoration: none;
		color: inherit;
	}

	.event-link:hover .event-title {
		color: var(--color-primary-text);
	}

	.event-header {
		display: flex;
		gap: 0.75rem;
		align-items: flex-start;
	}

	.category-icon-wrap {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		flex-shrink: 0;
		border-radius: var(--radius);
		background: var(--color-primary-light);
		font-size: 1.25rem;
		line-height: 1;
	}

	.event-meta {
		flex: 1;
	}

	.event-title {
		margin: 0 0 0.2rem;
		font-size: 1.05rem;
	}

	.event-date {
		margin: 0;
		font-size: 0.875rem;
		color: var(--color-primary-text);
	}

	.event-location {
		margin: 0.15rem 0 0;
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.event-description {
		margin: 0;
		font-size: 0.9rem;
		color: var(--color-text-muted);
		white-space: pre-wrap;
	}

	.event-footer {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
		margin-top: 0.25rem;
	}

	.attendee-count {
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.organizer {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		margin-left: auto;
	}

	.btn {
		padding: 0.5rem 1rem;
		border: none;
		border-radius: var(--radius);
		cursor: pointer;
		font-size: 0.9rem;
		font-weight: 500;
		transition: all var(--transition-fast);
	}

	.btn:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}

	.btn-sm {
		padding: 0.3rem 0.7rem;
		font-size: 0.8rem;
	}

	.btn-primary {
		background: var(--color-primary);
		color: var(--color-on-primary, #fff);
		box-shadow: var(--shadow-sm);
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--color-primary-hover);
		box-shadow: var(--shadow);
		transform: translateY(-1px);
	}

	.btn-secondary {
		background: var(--color-primary-light);
		color: var(--color-primary-text);
		border: 1px solid var(--color-border);
	}

	.btn-secondary:hover:not(:disabled) {
		border-color: var(--color-primary);
	}

	.empty-state {
		text-align: center;
		color: var(--color-text-muted);
		padding: 3rem 1rem;
	}

	.error {
		color: var(--color-error);
		font-size: 0.875rem;
		margin: 0 0 0.5rem;
	}

	.error-banner {
		padding: 0.75rem 1rem;
		border-radius: var(--radius);
		background: var(--color-error-bg);
		color: var(--color-error);
		border: 1px solid var(--color-error);
		font-size: 0.9rem;
		margin-bottom: 1rem;
	}

	@media (max-width: 640px) {
		.form-grid {
			grid-template-columns: 1fr;
		}

		.page-header {
			flex-direction: column;
		}
	}
</style>
