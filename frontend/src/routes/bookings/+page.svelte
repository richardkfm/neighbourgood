<script lang="ts">
	import { onMount } from 'svelte';
	import { t } from 'svelte-i18n';
	import { api } from '$lib/api';
	import { isLoggedIn, user } from '$lib/stores/auth';
	import { statusColor, type Booking } from '$lib/types';
	import { offlineQueue, removeFromQueue, type QueuedRequest } from '$lib/stores/offline';

	interface ReviewOut {
		id: number;
		booking_id: number;
		reviewer_id: number;
		rating: number;
		comment: string | null;
	}

	let bookings: Booking[] = $state([]);
	let total = $state(0);
	let loading = $state(true);
	let roleFilter = $state('');
	let statusFilter = $state('');

	// Review state
	let reviewingBookingId = $state<number | null>(null);
	let reviewRating = $state(5);
	let reviewComment = $state('');
	let submittingReview = $state(false);
	let reviewedBookings = $state<Set<number>>(new Set());

	async function loadBookings() {
		loading = true;
		try {
			const params = new URLSearchParams();
			if (roleFilter) params.set('role', roleFilter);
			if (statusFilter) params.set('status', statusFilter);
			const res = await api<{ items: Booking[]; total: number }>(
				`/bookings?${params.toString()}`,
				{ auth: true }
			);
			bookings = res.items;
			total = res.total;
			const completedIds = bookings.filter(b => b.status === 'completed').map(b => b.id);
			if (completedIds.length > 0) {
				loadReviewStatus(completedIds);
			}
		} catch {
			bookings = [];
		} finally {
			loading = false;
		}
	}

	async function updateStatus(bookingId: number, newStatus: string) {
		try {
			await api(`/bookings/${bookingId}`, {
				method: 'PATCH',
				auth: true,
				body: { status: newStatus }
			});
			await loadBookings();
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to update booking');
		}
	}

	function isOwnerOf(b: Booking): boolean {
		return b.borrower_id !== $user?.id;
	}

	function isBorrowerOf(b: Booking): boolean {
		return b.borrower_id === $user?.id;
	}

	async function loadReviewStatus(bookingIds: number[]) {
		const reviewed = new Set<number>();
		for (const id of bookingIds) {
			try {
				const reviews = await api<ReviewOut[]>(`/reviews/booking/${id}`);
				if (reviews.some(r => r.reviewer_id === $user?.id)) {
					reviewed.add(id);
				}
			} catch {
				// ignore
			}
		}
		reviewedBookings = reviewed;
	}

	async function submitReview() {
		if (!reviewingBookingId || submittingReview) return;
		submittingReview = true;
		try {
			await api('/reviews', {
				method: 'POST',
				auth: true,
				body: {
					booking_id: reviewingBookingId,
					rating: reviewRating,
					comment: reviewComment || null,
				},
			});
			reviewedBookings = new Set([...reviewedBookings, reviewingBookingId]);
			reviewingBookingId = null;
			reviewRating = 5;
			reviewComment = '';
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to submit review');
		} finally {
			submittingReview = false;
		}
	}

	onMount(loadBookings);

	$effect(() => {
		roleFilter;
		statusFilter;
		loadBookings();
	});
</script>

{#if !$isLoggedIn}
	<div class="empty-state">
		<p>{$t('bookings.login_required')}</p>
	</div>
{:else}
	<div class="bookings-page">
		<h1>{$t('bookings.title')}</h1>

		{#if $offlineQueue.length > 0}
			<div class="queued-section">
				<h2 class="queued-heading">
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
						<line x1="1" y1="1" x2="23" y2="23"/>
						<path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55"/>
						<path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39"/>
						<path d="M10.71 5.05A16 16 0 0 1 22.56 9"/>
						<path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88"/>
						<path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>
						<line x1="12" y1="20" x2="12.01" y2="20"/>
					</svg>
					{$t('bookings.offline_pending')}
				</h2>
				<p class="queued-subtext">{$t('bookings.offline_hint')}</p>
				{#each $offlineQueue as req (req.id)}
					<div class="queued-row">
						<div class="queued-info">
							<span class="queued-label">{req.label}</span>
							<span class="queued-date">Queued {new Date(req.createdAt).toLocaleString()}</span>
						</div>
						<button class="btn-cancel-queued" onclick={() => removeFromQueue(req.id)} title="Remove from queue">
							Cancel
						</button>
					</div>
				{/each}
			</div>
		{/if}

		<div class="filter-bar">
			<select bind:value={roleFilter}>
				<option value="">{$t('common.all')}</option>
				<option value="borrower">{$t('bookings.my_requests')}</option>
				<option value="owner">{$t('bookings.incoming')}</option>
			</select>
			<select bind:value={statusFilter}>
				<option value="">{$t('bookings.any_status')}</option>
				<option value="pending">{$t('bookings.status_pending')}</option>
				<option value="approved">{$t('bookings.status_approved')}</option>
				<option value="rejected">{$t('bookings.status_rejected')}</option>
				<option value="cancelled">{$t('bookings.status_cancelled')}</option>
				<option value="completed">{$t('bookings.status_completed')}</option>
			</select>
			<span class="result-count">{total} booking{total !== 1 ? 's' : ''}</span>
		</div>

		{#if loading}
			<p class="loading">{$t('common.loading')}</p>
		{:else if bookings.length === 0}
			<div class="empty-state">
				<p>{$t('bookings.no_bookings')}</p>
			</div>
		{:else}
			<div class="booking-table">
				{#each bookings as b}
					<div class="booking-row">
						<div class="booking-info">
							<a href="/resources/{b.resource_id}" class="resource-link">
								{b.resource_title ?? `Resource #${b.resource_id}`}
							</a>
							<div class="booking-meta">
								<span class="dates">{b.start_date} &rarr; {b.end_date}</span>
								{#if isBorrowerOf(b)}
									<span class="role-tag">{$t('bookings.you_requested')}</span>
								{:else}
									<span class="role-tag">{$t('bookings.requested_by', { values: { name: b.borrower.display_name } })}</span>
								{/if}
							</div>
							{#if b.message}
								<p class="message">"{b.message}"</p>
							{/if}
						</div>
						<div class="booking-actions">
							<span class="status" style="color: {statusColor(b.status)}">{b.status}</span>
							{#if b.status === 'pending' && isOwnerOf(b)}
								<button class="btn-approve" onclick={() => updateStatus(b.id, 'approved')}>{$t('bookings.approve')}</button>
								<button class="btn-reject" onclick={() => updateStatus(b.id, 'rejected')}>{$t('bookings.reject')}</button>
							{/if}
							{#if b.status === 'pending' && isBorrowerOf(b)}
								<button class="btn-cancel" onclick={() => updateStatus(b.id, 'cancelled')}>{$t('bookings.cancel')}</button>
							{/if}
							{#if b.status === 'approved'}
								<button class="btn-complete" onclick={() => updateStatus(b.id, 'completed')}>{$t('bookings.mark_done')}</button>
								{#if isBorrowerOf(b)}
									<button class="btn-cancel" onclick={() => updateStatus(b.id, 'cancelled')}>{$t('bookings.cancel')}</button>
								{/if}
							{/if}
							{#if b.status === 'completed' && !reviewedBookings.has(b.id)}
								<button
									class="btn-review"
									onclick={() => { reviewingBookingId = reviewingBookingId === b.id ? null : b.id; }}
								>
									{$t('bookings.leave_review')}
								</button>
							{/if}
							{#if b.status === 'completed' && reviewedBookings.has(b.id)}
								<span class="reviewed-badge">{$t('bookings.reviewed')}</span>
							{/if}
						</div>

						{#if reviewingBookingId === b.id}
							<div class="review-form fade-in">
								<div class="star-row">
									{#each [1, 2, 3, 4, 5] as star}
										<button
											class="star-btn"
											class:active={reviewRating >= star}
											onclick={() => (reviewRating = star)}
										>&#9733;</button>
									{/each}
								</div>
								<textarea
									bind:value={reviewComment}
									placeholder={$t('bookings.comment_optional')}
									rows="2"
								></textarea>
								<div class="review-actions">
									<button class="btn-approve" onclick={submitReview} disabled={submittingReview}>
										{submittingReview ? $t('bookings.submitting') : $t('bookings.submit_review')}
									</button>
									<button class="btn-complete" onclick={() => (reviewingBookingId = null)}>{$t('bookings.cancel')}</button>
								</div>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</div>
{/if}

<style>
	.bookings-page {
		max-width: 900px;
	}

	h1 {
		font-size: 1.9rem;
		font-weight: 400;
		margin-bottom: 1.5rem;
	}

	.filter-bar {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 1.5rem;
		flex-wrap: wrap;
	}

	.filter-bar select {
		padding: 0.4rem 0.6rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.85rem;
		background: var(--color-surface);
		color: var(--color-text);
	}

	.result-count {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		margin-left: auto;
	}

	.booking-table {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.booking-row {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		padding: 1rem;
	}

	.booking-info {
		flex: 1;
		min-width: 0;
	}

	.resource-link {
		font-weight: 600;
		font-size: 1rem;
		color: var(--color-text);
		text-decoration: none;
	}

	.resource-link:hover {
		color: var(--color-primary);
	}

	.booking-meta {
		display: flex;
		gap: 0.75rem;
		font-size: 0.82rem;
		color: var(--color-text-muted);
		margin-top: 0.25rem;
	}

	.role-tag {
		font-style: italic;
	}

	.message {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		margin-top: 0.35rem;
		font-style: italic;
	}

	.booking-actions {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-shrink: 0;
	}

	.status {
		font-weight: 700;
		text-transform: capitalize;
		font-size: 0.85rem;
		min-width: 70px;
	}

	.btn-approve, .btn-reject, .btn-cancel, .btn-complete {
		padding: 0.3rem 0.65rem;
		border-radius: var(--radius);
		font-size: 0.8rem;
		cursor: pointer;
		border: 1px solid;
	}

	.btn-approve {
		background: var(--color-success-bg);
		color: var(--color-success);
		border-color: var(--color-success);
	}
	.btn-approve:hover { filter: brightness(0.95); }

	.btn-reject, .btn-cancel {
		background: var(--color-error-bg);
		color: var(--color-error);
		border-color: var(--color-error);
	}
	.btn-reject:hover, .btn-cancel:hover { filter: brightness(0.95); }

	.btn-complete {
		background: var(--color-surface);
		color: var(--color-text-muted);
		border-color: var(--color-border);
	}
	.btn-complete:hover { border-color: var(--color-border-hover); }

	.loading {
		color: var(--color-text-muted);
	}

	.empty-state {
		text-align: center;
		padding: 3rem 1rem;
		color: var(--color-text-muted);
	}

	/* Reviews */
	.btn-review {
		padding: 0.3rem 0.65rem;
		border-radius: var(--radius);
		font-size: 0.8rem;
		cursor: pointer;
		border: 1px solid var(--color-primary);
		background: var(--color-primary-light);
		color: var(--color-primary);
	}
	.btn-review:hover { background: var(--color-primary); color: white; }

	.reviewed-badge {
		font-size: 0.78rem;
		color: var(--color-success);
		font-weight: 600;
	}

	.review-form {
		width: 100%;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		padding-top: 0.75rem;
		border-top: 1px solid var(--color-border);
	}

	.star-row {
		display: flex;
		gap: 0.15rem;
	}

	.star-btn {
		background: none;
		border: none;
		font-size: 1.4rem;
		cursor: pointer;
		color: var(--color-border);
		padding: 0;
		line-height: 1;
		transition: color var(--transition-fast);
	}

	.star-btn.active {
		color: #f59e0b;
	}

	.review-form textarea {
		padding: 0.4rem 0.6rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.85rem;
		font-family: inherit;
		resize: none;
		background: var(--color-surface);
		color: var(--color-text);
	}

	.review-actions {
		display: flex;
		gap: 0.5rem;
	}

	/* ── Offline queue section ────────────────────────────────── */

	.queued-section {
		background: var(--color-warning-bg, rgba(245, 158, 11, 0.08));
		border: 1px solid var(--color-warning, #f59e0b);
		border-radius: var(--radius);
		padding: 1rem 1.25rem;
		margin-bottom: 1.5rem;
	}

	.queued-heading {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.9rem;
		font-weight: 700;
		color: var(--color-warning, #92400e);
		text-transform: uppercase;
		letter-spacing: 0.04em;
		margin-bottom: 0.25rem;
	}

	.queued-subtext {
		font-size: 0.82rem;
		color: var(--color-text-muted);
		margin-bottom: 0.75rem;
	}

	.queued-row {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 0.6rem 0;
		border-top: 1px solid var(--color-border);
	}

	.queued-info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}

	.queued-label {
		font-size: 0.88rem;
		font-weight: 500;
		color: var(--color-text);
	}

	.queued-date {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}

	.btn-cancel-queued {
		padding: 0.25rem 0.6rem;
		border-radius: var(--radius);
		font-size: 0.78rem;
		cursor: pointer;
		border: 1px solid var(--color-error);
		background: var(--color-error-bg);
		color: var(--color-error);
		flex-shrink: 0;
	}

	.btn-cancel-queued:hover {
		background: var(--color-error);
		color: white;
	}
</style>
