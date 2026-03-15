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

	const CATEGORIES = [
		{ value: '', label: 'All Categories' },
		{ value: 'meetup', label: 'Meetup' },
		{ value: 'workshop', label: 'Workshop' },
		{ value: 'repair_cafe', label: 'Repair Café' },
		{ value: 'swap', label: 'Swap' },
		{ value: 'gardening', label: 'Gardening' },
		{ value: 'food', label: 'Food' },
		{ value: 'sport', label: 'Sport' },
		{ value: 'cultural', label: 'Cultural' },
		{ value: 'other', label: 'Other' }
	];

	let events = $state<CommunityEvent[]>([]);
	let total = $state(0);
	let loading = $state(true);
	let filterCategory = $state('');
	let filterUpcoming = $state(false);
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
	let myCommunities = $state<MyCommunity[]>([]);

	async function loadEvents() {
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
			events = data.items;
			total = data.total;
		} catch {
			events = [];
			total = 0;
		} finally {
			loading = false;
		}
	}

	async function loadMyCommunities() {
		try {
			const data = await api<MyCommunity[]>('/communities/my/memberships', { auth: true });
			myCommunities = Array.isArray(data) ? data : [];
			if (myCommunities.length > 0) newCommunityId = String(myCommunities[0].id);
		} catch {
			myCommunities = [];
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
			createError = 'Title is required.';
			return;
		}
		if (!newStartDate || !newStartTime) {
			createError = 'Start date and time are required.';
			return;
		}
		if (!newCommunityId) {
			createError = 'No community found. Please join a community first.';
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
		try {
			if (event.is_attending) {
				await api(`/events/${event.id}/attend`, { method: 'DELETE', auth: true });
			} else {
				await api(`/events/${event.id}/attend`, { method: 'POST', auth: true });
			}
			await loadEvents();
		} catch (err: unknown) {
			alert(err instanceof Error ? err.message : 'Could not update RSVP.');
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

	onMount(() => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}
		loadMyCommunities();
		loadEvents();
	});

	$effect(() => {
		filterCategory;
		filterUpcoming;
		filterCommunity;
		loadEvents();
	});
</script>

<svelte:head>
	<title>{$t('events.title')} — NeighbourGood</title>
</svelte:head>

<div class="events-page">
	<header class="page-header">
		<div>
			<h1>{$t('events.title')}</h1>
			<p class="subtitle">{$t('events.subtitle')}</p>
		</div>
		{#if $isLoggedIn}
			<button class="btn btn-primary" onclick={openCreateForm}>
				{showCreateForm ? '✕ Cancel' : $t('events.create_btn')}
			</button>
		{/if}
	</header>

	{#if showCreateForm}
		<div class="create-form card">
			<h2>Create Event</h2>
			{#if createError}
				<p class="error">{createError}</p>
			{/if}
			<div class="form-grid">
				<label>
					Title *
					<input type="text" bind:value={newTitle} maxlength="200" placeholder="Event title" />
				</label>
				<label>
					Category
					<select bind:value={newCategory}>
						{#each CATEGORIES.slice(1) as cat}
							<option value={cat.value}>{CATEGORY_ICONS[cat.value]} {cat.label}</option>
						{/each}
					</select>
				</label>
				<label>
					Start date *
					<input type="date" bind:value={newStartDate} />
				</label>
				<label>
					Start time *
					<input type="time" bind:value={newStartTime} step="900" />
				</label>
				<label>
					End date
					<input type="date" bind:value={newEndDate} min={newStartDate} />
				</label>
				<label>
					End time
					<input type="time" bind:value={newEndTime} step="900" />
				</label>
				<label>
					Location
					<input type="text" bind:value={newLocation} maxlength="300" placeholder="Where?" />
				</label>
				<label>
					Max attendees
					<input type="number" bind:value={newMaxAttendees} min="1" max="10000" placeholder="Unlimited" />
				</label>
				{#if myCommunities.length > 0}
				<p class="community-info full-width">Community: <strong>{myCommunities[0].name}</strong></p>
			{/if}
				<label class="full-width">
					Description
					<textarea bind:value={newDescription} maxlength="5000" rows="3" placeholder="Optional details…"></textarea>
				</label>
			</div>
			<button class="btn btn-primary" onclick={createEvent}>Create Event</button>
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
				<option value={cat.value}>{cat.label}</option>
			{/each}
		</select>
		<select bind:value={filterCommunity}>
			<option value="">All my communities</option>
			{#each myCommunities as c}
				<option value={String(c.id)}>{c.name}</option>
			{/each}
		</select>
		<label class="toggle-label">
			<input type="checkbox" bind:checked={filterUpcoming} />
			{$t('events.upcoming_only')}
		</label>
		{#if !loading}
			<span class="result-count">{total} event{total !== 1 ? 's' : ''}</span>
		{/if}
	</div>

	{#if loading}
		<p class="loading">{$t('common.loading')}</p>
	{:else if events.length === 0}
		<div class="empty-state">
			<p>{$isLoggedIn ? $t('events.no_events') : $t('events.no_events_guest')}</p>
		</div>
	{:else}
		<ul class="event-list">
			{#each events as event (event.id)}
				<li class="event-card card">
					<div class="event-header">
						<span class="category-icon">{CATEGORY_ICONS[event.category] ?? '📅'}</span>
						<div class="event-meta">
							<h3 class="event-title">{event.title}</h3>
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
					<div class="event-footer">
						<span class="attendee-count">
							👥 {event.attendee_count}{event.max_attendees ? `/${event.max_attendees}` : ''} {$t('events.attendees')}
						</span>
						<span class="organizer">by {event.organizer.display_name}</span>
						{#if $isLoggedIn}
							<button
								class="btn btn-sm {event.is_attending ? 'btn-secondary' : 'btn-primary'}"
								onclick={() => toggleAttend(event)}
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
		max-width: 800px;
		margin: 0 auto;
		padding: 1.5rem 1rem;
	}

	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 1.5rem;
		gap: 1rem;
	}

	h1 {
		margin: 0 0 0.25rem;
		color: var(--color-primary);
	}

	.subtitle {
		margin: 0;
		color: var(--color-text-muted);
	}

	.card {
		background: var(--color-surface);
		border-radius: 8px;
		padding: 1.25rem;
		margin-bottom: 1rem;
		border: 1px solid color-mix(in srgb, var(--color-text-muted) 20%, transparent);
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
		border: 1px solid color-mix(in srgb, var(--color-text-muted) 40%, transparent);
		border-radius: 4px;
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
		border: 1px solid color-mix(in srgb, var(--color-text-muted) 40%, transparent);
		border-radius: 4px;
		background: var(--color-surface);
		color: var(--color-text);
	}

	.filters select {
		padding: 0.45rem 0.6rem;
		border: 1px solid color-mix(in srgb, var(--color-text-muted) 40%, transparent);
		border-radius: 4px;
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

	.event-header {
		display: flex;
		gap: 0.75rem;
		align-items: flex-start;
	}

	.category-icon {
		font-size: 1.75rem;
		line-height: 1;
		flex-shrink: 0;
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
		color: var(--color-primary);
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
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.9rem;
		font-weight: 500;
		transition: opacity 0.15s;
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
		color: #fff;
	}

	.btn-secondary {
		background: color-mix(in srgb, var(--color-primary) 15%, transparent);
		color: var(--color-primary);
	}

	.loading,
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

	@media (max-width: 500px) {
		.form-grid {
			grid-template-columns: 1fr;
		}

		.page-header {
			flex-direction: column;
		}
	}
</style>
