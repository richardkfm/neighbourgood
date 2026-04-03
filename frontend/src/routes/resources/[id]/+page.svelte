<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { get } from 'svelte/store';
	import { api, apiUpload } from '$lib/api';
	import { isLoggedIn, user, token } from '$lib/stores/auth';
	import { goto } from '$app/navigation';
	import { statusColor, type Resource, type Booking } from '$lib/types';
	import { bandwidth } from '$lib/stores/theme';
	import { isOnline, enqueueRequest } from '$lib/stores/offline';

	let resource: Resource | null = $state(null);
	let bookings: Booking[] = $state([]);
	let error = $state('');
	let loading = $state(true);

	// Booking form
	let showBookingForm = $state(false);
	let bookStartDate = $state('');
	let bookEndDate = $state('');
	let bookMessage = $state('');
	let bookError = $state('');
	let bookQueued = $state(false);

	// Image upload
	let imageInput: HTMLInputElement;

	const isOwner = $derived(
		$isLoggedIn && resource !== null && $user?.id === resource.owner_id
	);

	const canBook = $derived(
		$isLoggedIn && resource !== null && $user?.id !== resource.owner_id && resource.is_available
	);

	onMount(async () => {
		const id = $page.params.id;
		try {
			resource = await api<Resource>(`/resources/${id}`);
			await loadBookings(Number(id));
		} catch (err) {
			error = err instanceof Error ? err.message : 'Resource not found';
		} finally {
			loading = false;
		}
	});

	async function loadBookings(resourceId: number) {
		try {
			const now = new Date();
			const res = await api<Booking[]>(
				`/bookings/resource/${resourceId}/calendar?month=${now.getMonth() + 1}&year=${now.getFullYear()}`
			);
			bookings = res;
		} catch {
			bookings = [];
		}
	}

	async function toggleAvailability() {
		if (!resource) return;
		try {
			resource = await api<Resource>(`/resources/${resource.id}`, {
				method: 'PATCH',
				auth: true,
				body: { is_available: !resource.is_available }
			});
		} catch (err) {
			error = err instanceof Error ? err.message : 'Update failed';
		}
	}

	async function deleteResource() {
		if (!resource || !confirm('Delete this resource?')) return;
		try {
			await api(`/resources/${resource.id}`, { method: 'DELETE', auth: true });
			goto('/resources');
		} catch (err) {
			error = err instanceof Error ? err.message : 'Delete failed';
		}
	}

	async function handleImageUpload() {
		if (!resource || !imageInput?.files?.length) return;
		try {
			resource = await apiUpload<Resource>(`/resources/${resource.id}/image`, imageInput.files[0]);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Upload failed';
		}
	}

	function startConversation(ownerId: number) {
		goto(`/messages?partner=${ownerId}`);
	}

	async function handleBooking(e: Event) {
		e.preventDefault();
		if (!resource) return;
		bookError = '';

		// When offline, save the request to the queue instead of failing.
		if (!$isOnline) {
			enqueueRequest({
				method: 'POST',
				path: '/bookings',
				body: {
					resource_id: resource.id,
					start_date: bookStartDate,
					end_date: bookEndDate,
					message: bookMessage || null
				},
				authToken: get(token),
				label: `Borrow "${resource.title}": ${bookStartDate} → ${bookEndDate}`
			});
			showBookingForm = false;
			bookQueued = true;
			bookStartDate = '';
			bookEndDate = '';
			bookMessage = '';
			return;
		}

		try {
			await api('/bookings', {
				method: 'POST',
				auth: true,
				body: {
					resource_id: resource.id,
					start_date: bookStartDate,
					end_date: bookEndDate,
					message: bookMessage || null
				}
			});
			showBookingForm = false;
			bookStartDate = '';
			bookEndDate = '';
			bookMessage = '';
			await loadBookings(resource.id);
		} catch (err) {
			bookError = err instanceof Error ? err.message : 'Booking failed';
		}
	}

</script>

{#if loading}
	<p class="loading">Loading...</p>
{:else if error}
	<div class="error-page">
		<h1>Oops</h1>
		<p>{error}</p>
		<a href="/resources">Back to resources</a>
	</div>
{:else if resource}
	<article class="resource-detail">
		<a href="/resources" class="back-link">&larr; Back to resources</a>

		{#if resource.image_url && $bandwidth !== 'low'}
			<div class="detail-image">
				<img src="/api{resource.image_url}" alt={resource.title} />
			</div>
		{/if}

		<div class="detail-header">
			<div class="badges">
				<span class="category-badge">{resource.category}</span>
				{#if resource.condition}
					<span class="condition-badge">{resource.condition}</span>
				{/if}
				<span class="availability" class:available={resource.is_available}>
					{resource.is_available ? 'Available' : 'Unavailable'}
				</span>
			</div>
			<h1>{resource.title}</h1>
		</div>

		{#if resource.description}
			<div class="section-card">
				<p>{resource.description}</p>
			</div>
		{/if}

		<div class="owner-section">
			<h3>Shared by</h3>
			<a href="/profile/{resource.owner_id}" class="owner-name-link">{resource.owner.display_name}</a>
			{#if resource.owner.neighbourhood}
				<p class="owner-neighbourhood">{resource.owner.neighbourhood}</p>
			{/if}
			{#if resource.owner_trust}
				<div class="owner-trust-row">
					{#if resource.owner_trust.total_reviews > 0}
						<span class="trust-stars">★ {resource.owner_trust.average_rating.toFixed(1)}</span>
						<span class="trust-count">({resource.owner_trust.total_reviews} reviews)</span>
					{/if}
					{#each resource.owner_trust.badges as badge}
						<span class="trust-badge-mini">{badge === 'skilled_helper' ? '⭐' : badge === 'trusted_lender' ? '📦' : '🤝'}</span>
					{/each}
					<span class="trust-level">{resource.owner_trust.reputation_level}</span>
				</div>
			{/if}
			{#if $isLoggedIn && $user?.id !== resource.owner_id}
				<button class="btn-message-owner" onclick={() => startConversation(resource!.owner_id)}>
					Message Owner
				</button>
			{/if}
		</div>

		<div class="meta">
			<span>Listed {new Date(resource.created_at).toLocaleDateString()}</span>
		</div>

		<!-- Owner actions -->
		{#if isOwner}
			<div class="section-card owner-panel">
				<h3>Manage Resource</h3>
				<div class="owner-actions">
					<button class="btn-secondary" onclick={toggleAvailability}>
						{resource.is_available ? 'Mark Unavailable' : 'Mark Available'}
					</button>
					<label class="btn-secondary upload-btn">
						Upload Image
						<input
							type="file"
							accept="image/jpeg,image/png,image/webp,image/gif"
							bind:this={imageInput}
							onchange={handleImageUpload}
							hidden
						/>
					</label>
					<button class="btn-danger" onclick={deleteResource}>Delete</button>
				</div>
			</div>
		{/if}

		<!-- Booking section -->
		{#if isOwner || bookings.length > 0}
			<div class="section-card" class:owner-bookings-card={isOwner}>
				<h3>{isOwner ? 'Who Has This Item?' : 'Booked Dates'}</h3>
				{#if bookings.length > 0}
					<div class="booking-list">
						{#each bookings as b}
							{@const days = Math.ceil((new Date(b.end_date).getTime() - new Date(b.start_date).getTime()) / 86400000)}
							<div class="booking-item">
								<span class="booking-dates">{b.start_date} &rarr; {b.end_date}</span>
								<span class="booking-duration">({days} day{days !== 1 ? 's' : ''})</span>
								<span class="booking-status" style="color: {statusColor(b.status)}">{b.status}</span>
								{#if isOwner}
									<span class="booking-who">{b.borrower.display_name}</span>
								{/if}
							</div>
						{/each}
					</div>
					{#if isOwner && bookings.some(b => b.status === 'pending')}
						<p class="pending-alert">Pending requests waiting — <a href="/bookings">review in Bookings</a>.</p>
					{/if}
				{:else if isOwner}
					<p class="empty-bookings">No current bookings. Your item is available to borrow.</p>
				{/if}
			</div>
		{/if}

		{#if bookQueued}
			<div class="section-card queued-notice">
				<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>
				<div class="queued-notice-body">
					<strong>Request saved for later</strong>
					<p>Your borrow request will be sent automatically when you reconnect.</p>
				</div>
				<button class="queued-dismiss" onclick={() => (bookQueued = false)} aria-label="Dismiss">&times;</button>
			</div>
		{/if}

		{#if canBook && !bookQueued}
			<div class="section-card">
				{#if showBookingForm}
					<h3>Request to Borrow</h3>
					{#if bookError}
						<p class="error">{bookError}</p>
					{/if}
					{#if !$isOnline}
						<p class="offline-note">
							You're offline. Your request will be saved and sent when you reconnect.
						</p>
					{/if}
					<form onsubmit={handleBooking} class="booking-form">
						<div class="form-row">
							<label>
								<span>Start Date</span>
								<input type="date" bind:value={bookStartDate} required />
							</label>
							<label>
								<span>End Date</span>
								<input type="date" bind:value={bookEndDate} required />
							</label>
						</div>
						<label>
							<span>Message (optional)</span>
							<textarea bind:value={bookMessage} rows="2" placeholder="Hi! I'd like to borrow this for..."></textarea>
						</label>
						<div class="form-actions">
							<button type="submit" class="btn-primary">
								{$isOnline ? 'Send Request' : 'Queue Request'}
							</button>
							<button type="button" class="btn-secondary" onclick={() => (showBookingForm = false)}>Cancel</button>
						</div>
					</form>
				{:else}
					<button class="btn-primary" onclick={() => (showBookingForm = true)}>
						Request to Borrow
					</button>
				{/if}
			</div>
		{/if}
	</article>
{/if}

<style>
	.back-link {
		font-size: 0.9rem;
		color: var(--color-text-muted);
		text-decoration: none;
		display: inline-block;
		margin-bottom: 1rem;
	}

	.back-link:hover {
		color: var(--color-primary);
	}

	.resource-detail {
		max-width: 900px;
	}

	.detail-image {
		border-radius: var(--radius);
		overflow: hidden;
		margin-bottom: 1.5rem;
		max-height: 350px;
	}

	.detail-image img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	.detail-header {
		margin-bottom: 1.5rem;
	}

	.detail-header h1 {
		font-size: 1.9rem;
		font-weight: 400;
		margin-top: 0.5rem;
	}

	.badges {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.category-badge, .condition-badge {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		padding: 0.2rem 0.6rem;
		border-radius: 999px;
		background: var(--color-bg);
		color: var(--color-primary);
		font-weight: 600;
	}

	.condition-badge {
		color: var(--color-text-muted);
	}

	.availability {
		font-size: 0.75rem;
		padding: 0.2rem 0.6rem;
		border-radius: 999px;
		font-weight: 600;
	}

	.availability.available {
		background: var(--color-success-bg);
		color: var(--color-success);
	}

	.availability:not(.available) {
		background: var(--color-error-bg);
		color: var(--color-error);
	}

	.section-card {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		padding: 1.25rem;
		margin-bottom: 1.25rem;
	}

	.section-card p {
		line-height: 1.7;
		white-space: pre-wrap;
	}

	.section-card h3 {
		font-size: 0.85rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--color-text-muted);
		margin-bottom: 0.75rem;
	}

	.owner-section {
		margin-bottom: 1rem;
	}

	.owner-section h3 {
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--color-text-muted);
		margin-bottom: 0.25rem;
	}

	.owner-name-link {
		font-weight: 600;
		color: var(--color-primary);
		text-decoration: none;
		font-size: 1.05rem;
	}

	.owner-name-link:hover {
		text-decoration: underline;
	}

	.owner-trust-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-top: 0.35rem;
		font-size: 0.85rem;
	}

	.trust-stars {
		color: var(--color-warning);
		font-weight: 600;
	}

	.trust-count {
		color: var(--color-text-muted);
	}

	.trust-badge-mini {
		font-size: 0.9rem;
	}

	.trust-level {
		padding: 0.1rem 0.5rem;
		border-radius: 999px;
		background: var(--color-primary-light);
		color: var(--color-primary);
		font-weight: 600;
		font-size: 0.75rem;
	}

	.owner-neighbourhood {
		font-size: 0.9rem;
		color: var(--color-text-muted);
	}

	.btn-message-owner {
		margin-top: 0.5rem;
		padding: 0.4rem 0.9rem;
		background: var(--color-surface);
		border: 1px solid var(--color-primary);
		border-radius: var(--radius);
		color: var(--color-primary);
		font-size: 0.85rem;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.btn-message-owner:hover {
		background: var(--color-primary);
		color: white;
	}

	.meta {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		margin-bottom: 1.25rem;
	}

	.owner-panel {
		background: var(--color-bg);
	}

	.owner-actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.btn-primary {
		padding: 0.5rem 1rem;
		background: var(--color-primary);
		color: white;
		border: none;
		border-radius: var(--radius);
		font-size: 0.9rem;
		cursor: pointer;
	}

	.btn-primary:hover {
		background: var(--color-primary-hover);
	}

	.btn-secondary, .upload-btn {
		padding: 0.5rem 1rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		background: var(--color-surface);
		color: var(--color-text);
		cursor: pointer;
		font-size: 0.9rem;
	}

	.btn-secondary:hover, .upload-btn:hover {
		border-color: var(--color-primary);
	}

	.btn-danger {
		padding: 0.5rem 1rem;
		border: 1px solid var(--color-error);
		border-radius: var(--radius);
		background: var(--color-error-bg);
		color: var(--color-error);
		cursor: pointer;
		font-size: 0.9rem;
	}

	.btn-danger:hover {
		background: var(--color-error);
		color: white;
	}

	/* Booking list */
	.booking-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.booking-item {
		display: flex;
		align-items: center;
		gap: 1rem;
		font-size: 0.85rem;
		padding: 0.5rem 0;
		border-bottom: 1px solid var(--color-border);
	}

	.booking-item:last-child {
		border-bottom: none;
	}

	.booking-dates {
		font-weight: 500;
	}

	.booking-status {
		font-weight: 600;
		text-transform: capitalize;
	}

	.booking-duration {
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	.booking-who {
		color: var(--color-text-muted);
		margin-left: auto;
	}

	.owner-bookings-card {
		border-color: var(--color-primary);
	}

	.empty-bookings {
		font-size: 0.88rem;
		color: var(--color-text-muted);
		font-style: italic;
		margin: 0;
	}

	.pending-alert {
		font-size: 0.85rem;
		color: var(--color-warning);
		font-weight: 500;
		margin: 0.75rem 0 0 0;
		padding-top: 0.75rem;
		border-top: 1px solid var(--color-border);
	}

	.pending-alert a {
		color: var(--color-warning);
		font-weight: 600;
	}

	/* Booking form */
	.booking-form {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.form-row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.75rem;
	}

	label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	label span {
		font-size: 0.85rem;
		font-weight: 500;
	}

	input, textarea {
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.9rem;
		background: var(--color-surface);
		color: var(--color-text);
	}

	.form-actions {
		display: flex;
		gap: 0.75rem;
	}

	.error {
		color: var(--color-error);
		font-size: 0.9rem;
		margin-bottom: 0.5rem;
	}

	.loading {
		color: var(--color-text-muted);
	}

	.error-page {
		text-align: center;
		padding: 3rem 1rem;
	}

	.error-page h1 {
		color: var(--color-error);
	}

	/* ── Offline / queued states ─────────────────────────────── */

	.offline-note {
		font-size: 0.83rem;
		color: var(--color-warning, #92400e);
		background: var(--color-warning-bg, rgba(245, 158, 11, 0.08));
		border: 1px solid var(--color-warning, #f59e0b);
		border-radius: var(--radius);
		padding: 0.45rem 0.75rem;
		margin-bottom: 0.5rem;
	}

	.queued-notice {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		background: var(--color-success-bg, rgba(16, 185, 129, 0.08));
		border-color: var(--color-success, #10b981);
		color: var(--color-success, #065f46);
	}

	.queued-notice svg {
		flex-shrink: 0;
		margin-top: 0.15rem;
	}

	.queued-notice-body strong {
		display: block;
		font-size: 0.9rem;
	}

	.queued-notice-body p {
		font-size: 0.83rem;
		margin: 0.2rem 0 0;
		white-space: normal;
	}

	.queued-dismiss {
		margin-left: auto;
		background: none;
		border: none;
		font-size: 1.2rem;
		color: var(--color-success, #10b981);
		cursor: pointer;
		padding: 0;
		line-height: 1;
		opacity: 0.7;
		flex-shrink: 0;
	}

	.queued-dismiss:hover {
		opacity: 1;
	}
</style>
