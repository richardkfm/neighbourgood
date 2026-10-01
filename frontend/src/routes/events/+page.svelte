<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { t } from 'svelte-i18n';
	import { api } from '$lib/api';
	import { isLoggedIn } from '$lib/stores/auth';
	import type { CommunityEvent } from '$lib/types';
	import Icon from '$lib/components/Icon.svelte';
	import { EVENT_CATEGORY_ICON } from '$lib/icons';

	interface MyCommunity {
		id: number;
		name: string;
		postal_code: string;
	}

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
			createError = err instanceof Error ? err.message : $t('events.create_failed');
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
			<button class="btn btn-primary" onclick={openCreateForm} aria-expanded={showCreateForm}>
				{showCreateForm ? $t('events.cancel_form') : $t('events.create_btn')}
			</button>
		{/if}
	</div>

	{#if showCreateForm}
		<div class="create-form card">
			<h2>{$t('events.form_title')}</h2>
			{#if createError}
				<p class="alert alert-error" role="alert">{createError}</p>
			{/if}
			<div class="field-row form-grid">
				<label class="field">
					{$t('events.form.title_label')} *
					<input type="text" bind:value={newTitle} maxlength="200" placeholder={$t('events.form.title_placeholder')} />
				</label>
				<label class="field">
					{$t('events.form.category_label')}
					<select bind:value={newCategory}>
						{#each CATEGORIES.slice(1) as cat}
							<option value={cat}>{$t('events.categories.' + cat)}</option>
						{/each}
					</select>
				</label>
				<label class="field">
					{$t('events.form.start_date_label')} *
					<input type="date" bind:value={newStartDate} />
				</label>
				<label class="field">
					{$t('events.form.start_time_label')} *
					<input type="time" bind:value={newStartTime} step="900" />
				</label>
				<label class="field">
					{$t('events.form.end_date_label')}
					<input type="date" bind:value={newEndDate} min={newStartDate} />
				</label>
				<label class="field">
					{$t('events.form.end_time_label')}
					<input type="time" bind:value={newEndTime} step="900" />
				</label>
				<label class="field">
					{$t('events.form.location_label')}
					<input type="text" bind:value={newLocation} maxlength="300" placeholder={$t('events.form.location_placeholder')} />
				</label>
				<label class="field">
					{$t('events.form.max_attendees_label')}
					<input type="number" bind:value={newMaxAttendees} min="1" max="10000" placeholder={$t('events.form.max_attendees_placeholder')} />
				</label>
				{#if myCommunities.length > 1}
				<p class="community-info full-width">{$t('events.community_label')} <strong>{myCommunities[0].name}</strong></p>
			{/if}
				<label class="field full-width">
					{$t('events.form.description_label')}
					<textarea bind:value={newDescription} maxlength="5000" rows="3" placeholder={$t('events.form.description_placeholder')}></textarea>
				</label>
			</div>
			<button class="btn btn-primary" onclick={createEvent}>{$t('events.form_submit')}</button>
		</div>
	{/if}

	<div class="filter-bar">
		<input
			class="input input-grow"
			type="search"
			bind:value={searchQuery}
			oninput={onSearchInput}
			placeholder={$t('events.search_placeholder')}
		/>
		<select class="input" bind:value={filterCategory}>
			{#each CATEGORIES as cat}
				<option value={cat}>
					{cat === '' ? $t('events.all_categories') : $t('events.categories.' + cat)}
				</option>
			{/each}
		</select>
		{#if myCommunities.length > 1}
		<select class="input" bind:value={filterCommunity}>
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
		<div class="alert alert-error" role="alert">{rsvpError}</div>
	{/if}

	{#if loading}
		<ul class="event-list" role="status" aria-busy="true">
			<span class="sr-only">{$t('common.loading')}</span>
			{#each [1, 2, 3] as n (n)}
				<li class="card event-card" aria-hidden="true">
					<span class="skeleton skeleton-line" style="width: 55%; height: 1.1rem"></span>
					<span class="skeleton skeleton-line is-short"></span>
					<span class="skeleton skeleton-line"></span>
				</li>
			{/each}
		</ul>
	{:else if events.length === 0}
		<div class="empty-state">
			<span class="empty-icon"><Icon name="calendar" size={26} /></span>
			<p>{$isLoggedIn ? $t('events.no_events') : $t('events.no_events_guest')}</p>
			{#if $isLoggedIn}
				<button class="btn btn-primary" onclick={() => { if (!showCreateForm) openCreateForm(); window.scrollTo({ top: 0, behavior: 'smooth' }); }}>
					<Icon name="plus" size={16} />{$t('events.create_btn')}
				</button>
			{:else}
				<a href="/login" class="btn btn-primary">{$t('nav.login')}</a>
			{/if}
		</div>
	{:else}
		<ul class="event-list">
			{#each events as event (event.id)}
				<li class="event-card card" class:event-past={isPast(event)}>
					<a class="event-link" href={`/events/${event.id}`}>
						<div class="event-header">
							<div class="category-icon-wrap">
								<Icon name={EVENT_CATEGORY_ICON[event.category] ?? 'calendar'} size={22} />
							</div>
							<div class="event-meta">
								<h3 class="event-title">
									{event.title}
									{#if isPast(event)}
										<span class="badge badge-caps past-badge">{$t('events.past_badge')}</span>
									{/if}
								</h3>
								<p class="event-date">{formatDate(event.start_at)}
									{#if event.end_at} — {formatDate(event.end_at)}{/if}
								</p>
								{#if event.location}
									<p class="event-location"><Icon name="pin" size={14} /> {event.location}</p>
								{/if}
							</div>
						</div>
						{#if event.description}
							<p class="event-description">{event.description}</p>
						{/if}
					</a>
					<div class="event-footer">
						<span class="attendee-count">
							<Icon name="users" size={15} /> {event.attendee_count}{event.max_attendees ? `/${event.max_attendees}` : ''} {$t('events.attendees')}
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

	.page-header h1 {
		margin: 0 0 0.25rem;
	}

	.card {
		margin-bottom: 1rem;
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
		margin-bottom: 1rem;
	}

	.form-grid .full-width {
		grid-column: 1 / -1;
	}

	.filter-bar {
		margin-bottom: 1.25rem;
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
		margin-inline-start: auto;
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
	}

	.event-card.event-past {
		opacity: 0.6;
	}

	.past-badge {
		margin-inline-start: 0.5rem;
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
		color: var(--color-primary-text);
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
		display: flex;
		align-items: center;
		gap: 0.3rem;
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
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.organizer {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		margin-inline-start: auto;
	}

	@media (max-width: 640px) {
		.page-header {
			flex-direction: column;
		}
	}
</style>
