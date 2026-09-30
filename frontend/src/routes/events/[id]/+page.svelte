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
	<a class="back-link" href="/events">{$t('events.detail.back')}</a>

	{#if loading}
		<LoadingSpinner />
	{:else if loadError || !event}
		<ErrorMessage message={loadError || $t('common.not_found')} />
	{:else}
		<div class="event-hero card">
			<div class="hero-header">
				<div class="category-icon-wrap">
					<span>{CATEGORY_ICONS[event.category] ?? '📅'}</span>
				</div>
				<div>
					<h1 class="event-title">
						{event.title}
						{#if isPast}
							<span class="past-badge">{$t('events.past_badge')}</span>
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
						<dd>📍 {event.location}</dd>
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
					👥 {event.attendee_count}{event.max_attendees ? `/${event.max_attendees}` : ''} {$t('events.attendees')}
				</span>
				{#if isFull}
					<span class="full-badge">{$t('events.detail.event_full')}</span>
				{/if}
				<button
					class="btn {event.is_attending ? 'btn-secondary' : 'btn-primary'}"
					onclick={toggleAttend}
					disabled={rsvpBusy || (isFull && !event.is_attending)}
				>
					{event.is_attending ? $t('events.unattend') : $t('events.attend')}
				</button>
			</div>

			{#if rsvpError}
				<p class="error">{rsvpError}</p>
			{/if}
		</div>

		<section class="attendees-section">
			<h2>{$t('events.detail.attendees_title')} ({event.attendee_count})</h2>
			{#if event.attendees && event.attendees.length > 0}
				<ul class="attendee-list">
					{#each event.attendees as attendee (attendee.id)}
						<li class="attendee-item">
							<a href={`/profile/${attendee.id}`}>
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
		display: inline-block;
		margin-bottom: 1rem;
		color: var(--color-primary-text);
		text-decoration: none;
		font-size: 0.9rem;
	}

	.back-link:hover {
		text-decoration: underline;
	}

	.card {
		background: var(--color-surface);
		border-radius: var(--radius-lg);
		padding: 1.5rem;
		margin-bottom: 1.25rem;
		border: 1px solid var(--color-border);
		box-shadow: var(--shadow-sm);
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
		font-size: 1.5rem;
	}

	.event-title {
		margin: 0 0 0.25rem;
	}

	.past-badge {
		display: inline-block;
		margin-left: 0.5rem;
		padding: 0.15rem 0.55rem;
		border-radius: 999px;
		background: var(--color-border);
		color: var(--color-text-muted);
		font-size: 0.7rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.03em;
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
		font-size: 0.9rem;
		color: var(--color-text-muted);
	}

	.full-badge {
		font-size: 0.8rem;
		padding: 0.25rem 0.6rem;
		border-radius: var(--radius-sm);
		background: var(--color-error-bg);
		color: var(--color-error);
	}

	.btn {
		padding: 0.5rem 1.1rem;
		border: none;
		border-radius: var(--radius);
		cursor: pointer;
		font-size: 0.9rem;
		font-weight: 500;
		transition: all var(--transition-fast);
		margin-left: auto;
	}

	.btn:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}

	.btn-primary {
		background: var(--color-primary);
		color: var(--color-on-primary, #fff);
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--color-primary-hover);
	}

	.btn-secondary {
		background: var(--color-primary-light);
		color: var(--color-primary-text);
		border: 1px solid var(--color-border);
	}

	.btn-secondary:hover:not(:disabled) {
		border-color: var(--color-primary);
	}

	.attendees-section {
		background: var(--color-surface);
		border-radius: var(--radius-lg);
		padding: 1.25rem 1.5rem;
		border: 1px solid var(--color-border);
		box-shadow: var(--shadow-sm);
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
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		text-decoration: none;
		color: var(--color-text);
		transition: border-color var(--transition-fast);
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

	.error {
		color: var(--color-error);
		font-size: 0.875rem;
		margin: 0.5rem 0 0;
	}

	@media (max-width: 640px) {
		.hero-actions {
			flex-direction: column;
			align-items: stretch;
		}

		.btn {
			margin-left: 0;
		}
	}
</style>
