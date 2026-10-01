<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { t } from 'svelte-i18n';
	import { api } from '$lib/api';
	import { isLoggedIn } from '$lib/stores/auth';
	import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';
	import ErrorMessage from '$lib/components/ErrorMessage.svelte';
	import type { CommunityEvent } from '$lib/types';
	import Icon from '$lib/components/Icon.svelte';
	import { EVENT_CATEGORY_ICON } from '$lib/icons';

	let event = $state<CommunityEvent | null>(null);
	let loading = $state(true);
	let loadError = $state('');
	let rsvpError = $state('');
	let rsvpBusy = $state(false);

	const eventId = $derived(parseInt($page.params.id ?? '', 10));
	const isFull = $derived(
		!!event &&
			!event.is_attending &&
			event.max_attendees !== null &&
			event.attendee_count >= event.max_attendees
	);
	const isPast = $derived(
		!!event && new Date(event.end_at ?? event.start_at).getTime() < Date.now()
	);

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleString(undefined, {
			weekday: 'long',
			day: 'numeric',
			month: 'long',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	async function loadEvent() {
		loading = true;
		loadError = '';
		try {
			event = await api<CommunityEvent>(`/events/${eventId}`, { auth: true });
		} catch (err: unknown) {
			loadError = err instanceof Error ? err.message : $t('events.error_load');
			event = null;
		} finally {
			loading = false;
		}
	}

	async function toggleAttend() {
		if (!event || rsvpBusy) return;
		rsvpBusy = true;
		rsvpError = '';
		try {
			if (event.is_attending) {
				await api(`/events/${event.id}/attend`, { method: 'DELETE', auth: true });
			} else {
				await api(`/events/${event.id}/attend`, { method: 'POST', auth: true });
			}
			await loadEvent();
		} catch (err: unknown) {
			rsvpError = err instanceof Error ? err.message : $t('common.error');
		} finally {
			rsvpBusy = false;
		}
	}

	onMount(() => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}
		if (!Number.isFinite(eventId) || eventId <= 0) {
			loadError = $t('common.not_found');
			loading = false;
			return;
		}
		loadEvent();
	});
</script>

<svelte:head>
	<title>{event ? event.title : $t('events.title')} — NeighbourGood</title>
</svelte:head>

<div class="event-detail-page">
	<a class="back-link" href="/events"><Icon name="arrow-left" size={16} class="flip-rtl" /> {$t('events.detail.back')}</a>

	{#if loading}
		<LoadingSpinner />
	{:else if loadError || !event}
		<ErrorMessage message={loadError || $t('common.not_found')} />
	{:else}
		<div class="event-hero card">
			<div class="hero-header">
				<div class="category-icon-wrap">
					<Icon name={EVENT_CATEGORY_ICON[event.category] ?? 'calendar'} size={26} />
				</div>
				<div>
					<h1 class="event-title">
						{event.title}
						{#if isPast}
							<span class="badge badge-caps past-badge">{$t('events.past_badge')}</span>
						{/if}
					</h1>
					<p class="event-category">{$t('events.categories.' + event.category)}</p>
				</div>
			</div>

			<dl class="event-info">
				<div>
					<dt>{$t('events.detail.starts')}</dt>
					<dd>{formatDate(event.start_at)}</dd>
				</div>
				{#if event.end_at}
					<div>
						<dt>{$t('events.detail.ends')}</dt>
						<dd>{formatDate(event.end_at)}</dd>
					</div>
				{/if}
				{#if event.location}
					<div>
						<dt>{$t('events.detail.location')}</dt>
						<dd class="with-icon"><Icon name="pin" size={15} /> {event.location}</dd>
					</div>
				{/if}
				<div>
					<dt>{$t('events.detail.organizer')}</dt>
					<dd>{event.organizer.display_name}</dd>
				</div>
			</dl>

			{#if event.description}
				<p class="event-description">{event.description}</p>
			{/if}

			<div class="hero-actions">
				<span class="attendee-count">
					<Icon name="users" size={16} /> {event.attendee_count}{event.max_attendees ? `/${event.max_attendees}` : ''} {$t('events.attendees')}
				</span>
				{#if isFull}
					<span class="badge badge-error">{$t('events.detail.event_full')}</span>
				{/if}
				<button
					class="btn rsvp-btn {event.is_attending ? 'btn-secondary' : 'btn-primary'}"
					onclick={toggleAttend}
					disabled={rsvpBusy || (isFull && !event.is_attending)}
				>
					{event.is_attending ? $t('events.unattend') : $t('events.attend')}
				</button>
			</div>

			{#if rsvpError}
				<p class="alert alert-error" role="alert">{rsvpError}</p>
			{/if}
		</div>

		<section class="card attendees-section">
			<h2>{$t('events.detail.attendees_title')} ({event.attendee_count})</h2>
			{#if event.attendees && event.attendees.length > 0}
				<ul class="attendee-list">
					{#each event.attendees as attendee (attendee.id)}
						<li class="attendee-item">
							<a class="card card-interactive" href={`/profile/${attendee.id}`}>
								<span class="attendee-name">{attendee.display_name}</span>
								{#if attendee.neighbourhood}
									<span class="attendee-neighbourhood">{attendee.neighbourhood}</span>
								{/if}
							</a>
						</li>
					{/each}
				</ul>
			{:else}
				<p class="empty">{$t('events.detail.no_attendees')}</p>
			{/if}
		</section>
	{/if}
</div>

<style>
	.event-detail-page {
		max-width: 900px;
	}

	.back-link {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		margin-bottom: 1rem;
		color: var(--color-primary-text);
		text-decoration: none;
		font-size: 0.9rem;
	}

	.back-link:hover {
		text-decoration: underline;
	}

	.event-hero {
		padding: 1.5rem;
		margin-bottom: 1.25rem;
	}

	.hero-header {
		display: flex;
		gap: 1rem;
		align-items: flex-start;
		margin-bottom: 1.25rem;
	}

	.category-icon-wrap {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 56px;
		height: 56px;
		flex-shrink: 0;
		border-radius: var(--radius);
		background: var(--color-primary-light);
		color: var(--color-primary-text);
	}

	.event-title {
		margin: 0 0 0.25rem;
	}

	.past-badge {
		margin-inline-start: 0.5rem;
		vertical-align: middle;
	}

	.event-category {
		margin: 0;
		color: var(--color-text-muted);
		font-size: 0.9rem;
	}

	.event-info {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
		gap: 0.75rem 1.5rem;
		margin: 0 0 1rem;
	}

	.event-info > div {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}

	.event-info dt {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--color-text-muted);
		margin: 0;
	}

	.event-info dd.with-icon {
		display: flex;
		align-items: center;
		gap: 0.3rem;
	}

	.event-info dd {
		margin: 0;
		color: var(--color-text);
		font-size: 0.95rem;
	}

	.event-description {
		margin: 0 0 1.25rem;
		color: var(--color-text);
		white-space: pre-wrap;
		line-height: 1.5;
	}

	.hero-actions {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.attendee-count {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		font-size: 0.9rem;
		color: var(--color-text-muted);
	}

	.rsvp-btn {
		margin-inline-start: auto;
	}

	.attendees-section {
		padding: 1.25rem 1.5rem;
	}

	.attendees-section h2 {
		margin: 0 0 0.75rem;
		font-size: 1.1rem;
	}

	.attendee-list {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: 0.5rem;
	}

	.attendee-item a {
		display: flex;
		flex-direction: column;
		padding: 0.5rem 0.75rem;
		border-radius: var(--radius);
		box-shadow: none;
	}

	.attendee-item a:hover {
		border-color: var(--color-primary);
	}

	.attendee-name {
		font-weight: 500;
	}

	.attendee-neighbourhood {
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	.empty {
		color: var(--color-text-muted);
		font-size: 0.9rem;
		margin: 0;
	}

	@media (max-width: 640px) {
		.hero-actions {
			flex-direction: column;
			align-items: stretch;
		}

		.rsvp-btn {
			margin-inline-start: 0;
		}
	}
</style>
