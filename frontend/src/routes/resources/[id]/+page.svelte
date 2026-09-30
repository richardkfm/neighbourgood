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
	import { t } from 'svelte-i18n';

	let resource: Resource | null = $state(null);
	let bookings: Booking[] = $state([]);
	let error = $state('');
	// Errors from actions on an already-loaded resource (upload, toggle, delete) are
	// shown inline; `error` replaces the whole page and is only for load failures.
	let actionError = $state('');
	let loading = $state(true);
	let confirmDelete = $state(false);

	// Booking form
	let showBookingForm = $state(false);
	let bookStartDate = $state('');
	let bookEndDate = $state('');
	let bookMessage = $state('');
	let bookError = $state('');
	let bookQueued = $state(false);

	// Image upload
	let imageInput: HTMLInputElement;

	// Edit form (owner only)
	const EDIT_CATEGORIES = ['tool', 'vehicle', 'electronics', 'furniture', 'food', 'clothing', 'skill', 'other'];
	const EDIT_CONDITIONS = ['new', 'good', 'fair', 'worn'];
	let editing = $state(false);
	let editSaving = $state(false);
	let editError = $state('');
	let editImageInput: HTMLInputElement | undefined = $state();
	let imageVersion = $state(0);
	let editForm = $state({
		title: '',
		description: '',
		category: 'tool',
		condition: '',
		is_available: true,
		reorder_threshold: null as number | null
	});

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
			// The calendar endpoint is per month; fetch this month and next so a
			// booking for the coming weeks is not hidden when it crosses a boundary.
			const now = new Date();
			const next = new Date(now.getFullYear(), now.getMonth() + 1, 1);
			const months = [now, next];
			const results = await Promise.all(
				months.map((d) =>
					api<Booking[]>(
						`/bookings/resource/${resourceId}/calendar?month=${d.getMonth() + 1}&year=${d.getFullYear()}`
					)
				)
			);
			const seen = new Set<number>();
			bookings = results.flat().filter((b) => (seen.has(b.id) ? false : (seen.add(b.id), true)));
		} catch {
			bookings = [];
		}
	}

	async function toggleAvailability() {
		if (!resource) return;
		actionError = '';
		try {
			resource = await api<Resource>(`/resources/${resource.id}`, {
				method: 'PATCH',
				auth: true,
				body: { is_available: !resource.is_available }
			});
		} catch (err) {
			actionError = err instanceof Error ? err.message : 'Update failed';
		}
	}

	async function deleteResource() {
		if (!resource) return;
		if (!confirmDelete) { confirmDelete = true; return; }
		confirmDelete = false;
		actionError = '';
		try {
			await api(`/resources/${resource.id}`, { method: 'DELETE', auth: true });
			goto('/resources');
		} catch (err) {
			actionError = err instanceof Error ? err.message : $t('common.error');
		}
	}

	async function handleImageUpload() {
		if (!resource || !imageInput?.files?.length) return;
		actionError = '';
		try {
			resource = await apiUpload<Resource>(`/resources/${resource.id}/image`, imageInput.files[0]);
		} catch (err) {
			actionError = err instanceof Error ? err.message : 'Upload failed';
		} finally {
			// Allow re-selecting the same file after a failed upload
			if (imageInput) imageInput.value = '';
		}
	}

	function startEdit() {
		if (!resource) return;
		editForm = {
			title: resource.title,
			description: resource.description ?? '',
			category: resource.category,
			condition: resource.condition ?? '',
			is_available: resource.is_available,
			reorder_threshold: resource.reorder_threshold
		};
		editError = '';
		editing = true;
	}

	function cancelEdit() {
		editing = false;
		editError = '';
	}

	async function saveEdit(e: Event) {
		e.preventDefault();
		if (!resource) return;
		editError = '';
		editSaving = true;
		const trust = resource.owner_trust;
		const threshold = editForm.reorder_threshold as number | string | null | undefined;
		try {
			const updated = await api<Resource>(`/resources/${resource.id}`, {
				method: 'PATCH',
				auth: true,
				body: {
					title: editForm.title,
					description: editForm.description.trim() || null,
					category: editForm.category,
					condition: editForm.condition || null,
					is_available: editForm.is_available,
					reorder_threshold: threshold === null || threshold === undefined || threshold === '' ? null : Number(threshold)
				}
			});
			// The PATCH response does not carry the owner's trust summary; keep what we had.
			resource = { ...updated, owner_trust: trust };

			const file = editImageInput?.files?.[0];
			if (file) {
				try {
					const withImage = await apiUpload<Resource>(`/resources/${resource.id}/image`, file);
					resource = { ...withImage, owner_trust: trust };
					imageVersion = Date.now();
				} catch (err) {
					// The text changes are already saved; keep the form open so the photo can be retried.
					const reason = err instanceof Error ? err.message : '';
					editError = `${$t('resources.edit_image_failed')}${reason ? `: ${reason}` : ''}`;
					return;
				}
			}
			editing = false;
		} catch (err) {
			editError = err instanceof Error ? err.message : $t('resources.edit_failed');
		} finally {
			editSaving = false;
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
			<p class="meta">Listed {new Date(resource.created_at).toLocaleDateString()}</p>
		</div>

		{#if actionError}
			<p class="error" role="alert">{actionError}</p>
		{/if}

		<div class="detail-grid">
			<div class="detail-main">
				{#if resource.image_url && $bandwidth !== 'low'}
					<div class="detail-image">
						<img src="/api{resource.image_url}{imageVersion ? `?v=${imageVersion}` : ''}" alt={resource.title} />
					</div>
				{/if}

				{#if editing && isOwner}
					<form class="section-card edit-form" onsubmit={saveEdit} aria-labelledby="edit-resource-heading">
						<h3 id="edit-resource-heading">{$t('resources.edit_title')}</h3>

						{#if editError}
							<p class="error" role="alert">{editError}</p>
						{/if}

						<div class="field">
							<label for="edit-title">{$t('resources.title_label')}</label>
							<input id="edit-title" type="text" bind:value={editForm.title} required maxlength="200" disabled={editSaving} />
						</div>

						<div class="field">
							<label for="edit-description">{$t('resources.description_label')}</label>
							<textarea id="edit-description" bind:value={editForm.description} rows="4" maxlength="5000" disabled={editSaving}></textarea>
						</div>

						<div class="field-row">
							<div class="field">
								<label for="edit-category">{$t('resources.category')}</label>
								<select id="edit-category" bind:value={editForm.category} disabled={editSaving}>
									{#each EDIT_CATEGORIES as cat}
										<option value={cat}>{$t('resources.categories.' + cat)}</option>
									{/each}
								</select>
							</div>
							<div class="field">
								<label for="edit-condition">{$t('resources.condition')}</label>
								<select id="edit-condition" bind:value={editForm.condition} disabled={editSaving}>
									<option value="">{$t('resources.edit_condition_none')}</option>
									{#each EDIT_CONDITIONS as cond}
										<option value={cond}>{$t('resources.conditions.' + cond)}</option>
									{/each}
								</select>
							</div>
						</div>

						<div class="field">
							<label for="edit-threshold">{$t('resources.edit_threshold_label')}</label>
							<input
								id="edit-threshold"
								type="number"
								min="0"
								step="1"
								inputmode="numeric"
								bind:value={editForm.reorder_threshold}
								aria-describedby="edit-threshold-hint"
								disabled={editSaving}
							/>
							<small id="edit-threshold-hint" class="hint">{$t('resources.edit_threshold_hint')}</small>
						</div>

						<label class="check-row" for="edit-available">
							<input id="edit-available" type="checkbox" bind:checked={editForm.is_available} disabled={editSaving} />
							<span>{$t('resources.edit_available_label')}</span>
						</label>

						<div class="field">
							<label for="edit-image">{$t('resources.edit_image_label')}</label>
							{#if resource.image_url && $bandwidth !== 'low'}
								<img
									class="edit-image-preview"
									src="/api{resource.image_url}{imageVersion ? `?v=${imageVersion}` : ''}"
									alt={$t('resources.edit_image_current')}
								/>
							{:else if !resource.image_url}
								<p class="hint">{$t('resources.edit_image_none')}</p>
							{/if}
							<input
								id="edit-image"
								class="file-input"
								type="file"
								accept="image/jpeg,image/png,image/webp,image/gif"
								bind:this={editImageInput}
								aria-describedby="edit-image-hint"
								disabled={editSaving}
							/>
							<small id="edit-image-hint" class="hint">{$t('resources.edit_image_hint')}</small>
						</div>

						<div class="form-actions">
							<button type="submit" class="btn-primary" disabled={editSaving}>
								{editSaving ? $t('resources.edit_saving') : $t('resources.edit_save')}
							</button>
							<button type="button" class="btn-secondary" onclick={cancelEdit} disabled={editSaving}>
								{$t('common.cancel')}
							</button>
						</div>
					</form>
				{:else}
					<div class="section-card">
						<h3>About this item</h3>
						{#if resource.description}
							<p>{resource.description}</p>
						{:else}
							<p class="no-description">The owner hasn't added a description yet.</p>
						{/if}
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
			</div>

			<aside class="detail-side">
				<!-- Owner card -->
				<div class="section-card owner-card">
					<h3>Shared by</h3>
					<div class="owner-row">
						<span class="owner-avatar" aria-hidden="true">{resource.owner.display_name.charAt(0).toUpperCase()}</span>
						<div class="owner-id">
							<a href="/profile/{resource.owner_id}" class="owner-name-link">{resource.owner.display_name}</a>
							{#if resource.owner.neighbourhood}
								<p class="owner-neighbourhood">{resource.owner.neighbourhood}</p>
							{/if}
						</div>
					</div>
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

				<!-- Borrow card -->
				{#if canBook && !bookQueued}
					<div class="section-card borrow-card">
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
							<button class="btn-primary btn-borrow" onclick={() => (showBookingForm = true)}>
								Request to Borrow
							</button>
						{/if}
					</div>
				{/if}

				<!-- Owner actions -->
				{#if isOwner}
					<div class="section-card owner-panel">
						<h3>Manage Resource</h3>
						<div class="owner-actions">
							<button class="btn-secondary" onclick={startEdit} disabled={editing}>
								{$t('common.edit')}
							</button>
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
							{#if confirmDelete}
								<span class="confirm-text">{$t('common.confirm_delete')}</span>
								<button class="btn-danger" onclick={deleteResource}>{$t('common.delete')}</button>
								<button class="btn-secondary" onclick={() => confirmDelete = false}>{$t('common.cancel')}</button>
							{:else}
								<button class="btn-danger" onclick={deleteResource}>{$t('common.delete')}</button>
							{/if}
						</div>
					</div>
				{/if}
			</aside>
		</div>
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
		color: var(--color-primary-text);
	}

	.resource-detail {
		max-width: 960px;
	}

	.detail-grid {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 320px;
		gap: 2rem;
		align-items: start;
	}

	.detail-main {
		min-width: 0;
	}

	.detail-side {
		position: sticky;
		top: 5rem;
	}

	@media (max-width: 860px) {
		.detail-grid {
			grid-template-columns: 1fr;
			gap: 0;
		}

		.detail-side {
			position: static;
		}
	}

	.detail-image {
		border-radius: var(--radius-lg);
		overflow: hidden;
		margin-bottom: 1.5rem;
		max-height: 420px;
		border: 1px solid var(--color-border);
	}

	.detail-image img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	.detail-header {
		margin-bottom: 2rem;
	}

	.detail-header h1 {
		font-size: 2.1rem;
		font-weight: 400;
		margin-top: 0.65rem;
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
		color: var(--color-primary-text);
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
		border-radius: var(--radius-lg);
		padding: 1.5rem;
		margin-bottom: 1.5rem;
	}

	.section-card p {
		line-height: 1.7;
		white-space: pre-wrap;
	}

	.no-description {
		color: var(--color-text-muted);
		font-style: italic;
	}

	.section-card h3 {
		font-size: 0.8rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--color-text-muted);
		margin-bottom: 0.9rem;
	}

	.owner-row {
		display: flex;
		align-items: center;
		gap: 0.85rem;
	}

	.owner-avatar {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		border-radius: 50%;
		background: var(--color-primary);
		color: var(--color-on-primary);
		font-weight: 600;
		font-size: 1.1rem;
		flex-shrink: 0;
	}

	.owner-id {
		min-width: 0;
	}

	.owner-name-link {
		font-weight: 600;
		color: var(--color-primary-text);
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
		margin-top: 0.85rem;
		font-size: 0.85rem;
		flex-wrap: wrap;
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
		color: var(--color-primary-text);
		font-weight: 600;
		font-size: 0.75rem;
	}

	.owner-neighbourhood {
		font-size: 0.9rem;
		color: var(--color-text-muted);
	}

	.btn-message-owner {
		margin-top: 1rem;
		width: 100%;
		padding: 0.5rem 0.9rem;
		background: var(--color-surface);
		border: 1px solid var(--color-primary);
		border-radius: var(--radius);
		color: var(--color-primary-text);
		font-size: 0.85rem;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.btn-message-owner:hover {
		background: var(--color-primary);
		color: var(--color-on-primary);
	}

	.meta {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		margin-top: 0.5rem;
	}

	.owner-panel {
		background: var(--color-bg);
	}

	.owner-actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.owner-actions button,
	.owner-actions .upload-btn {
		display: inline-flex;
		align-items: center;
		min-height: var(--tap-target);
	}

	.btn-primary {
		padding: 0.55rem 1.2rem;
		background: var(--color-primary);
		color: var(--color-on-primary);
		border: none;
		border-radius: var(--radius);
		font-size: 0.9rem;
		font-weight: 600;
		cursor: pointer;
		box-shadow: var(--shadow-sm);
		transition: all var(--transition-fast);
	}

	.btn-primary:hover {
		background: var(--color-primary-hover);
		box-shadow: var(--shadow-md);
	}

	.btn-borrow {
		width: 100%;
		padding: 0.7rem 1.2rem;
		font-size: 0.95rem;
	}

	.borrow-card {
		border-color: var(--color-primary);
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
		color: var(--color-on-error);
	}

	/* Edit form */
	.edit-form {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.edit-form h3 {
		margin-bottom: 0;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		min-width: 0;
	}

	.field label,
	.check-row span {
		font-size: 0.85rem;
		font-weight: 500;
	}

	.field-row {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
		gap: 0.75rem;
	}

	@media (max-width: 480px) {
		.field-row {
			grid-template-columns: minmax(0, 1fr);
		}
	}

	.edit-form input:not([type='checkbox']),
	.edit-form select {
		min-height: var(--tap-target);
	}

	.edit-form select {
		width: 100%;
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.9rem;
		background: var(--color-surface);
		color: var(--color-text);
	}

	.check-row {
		display: flex;
		flex-direction: row;
		align-items: center;
		gap: 0.75rem;
		min-height: var(--tap-target);
		cursor: pointer;
	}

	.check-row input[type='checkbox'] {
		width: 22px;
		min-width: 22px;
		height: 22px;
		padding: 0;
		accent-color: var(--color-primary);
		cursor: pointer;
	}

	.file-input {
		padding: 0.5rem 0.75rem;
	}

	.edit-image-preview {
		max-width: 100%;
		max-height: 200px;
		object-fit: cover;
		border-radius: var(--radius);
		border: 1px solid var(--color-border);
		align-self: flex-start;
	}

	.hint {
		font-size: 0.8rem;
		color: var(--color-text-muted);
		margin: 0;
	}

	.edit-form .form-actions {
		flex-wrap: wrap;
	}

	.edit-form .btn-primary,
	.edit-form .btn-secondary {
		min-height: var(--tap-target);
	}

	.btn-secondary:disabled,
	.btn-primary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
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
		/* minmax(0, …) lets the columns shrink below the date input's large
		   intrinsic width so the second picker can't overflow the sidebar. */
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
		gap: 0.75rem;
	}

	.form-row label {
		min-width: 0;
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
		width: 100%;
		min-width: 0;
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
