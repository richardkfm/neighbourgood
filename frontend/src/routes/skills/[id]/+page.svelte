<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
	import { SKILL_CATEGORY_ICON, TRUST_BADGE_ICON } from '$lib/icons';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { api } from '$lib/api';
	import { isLoggedIn, user } from '$lib/stores/auth';
	import { goto } from '$app/navigation';
	import { t as _ } from 'svelte-i18n';
	import type { OwnerTrust, ReviewOut } from '$lib/types';

	interface SkillOwner {
		id: number;
		display_name: string;
		neighbourhood: string | null;
	}

	interface Skill {
		id: number;
		title: string;
		description: string | null;
		category: string;
		skill_type: string;
		owner_id: number;
		community_id: number | null;
		owner: SkillOwner;
		owner_trust?: OwnerTrust | null;
		created_at: string;
		updated_at: string;
	}

	let skill: Skill | null = $state(null);
	let error = $state('');
	let loading = $state(true);

	// Reviews
	let reviews: ReviewOut[] = $state([]);
	let reviewRating = $state(5);
	let reviewComment = $state('');
	let reviewError = $state('');
	let reviewSuccess = $state('');
	let submittingReview = $state(false);
	let hasReviewed = $state(false);
	let confirmDelete = $state(false);

	// Edit form (owner only)
	const EDIT_CATEGORIES = ['tutoring', 'repairs', 'cooking', 'languages', 'music', 'gardening', 'tech', 'crafts', 'fitness', 'other'];
	let editing = $state(false);
	let editSaving = $state(false);
	let editError = $state('');
	let editForm = $state({ title: '', description: '', category: 'other', skill_type: 'offer' });

	const isOwner = $derived(
		$isLoggedIn && skill !== null && $user?.id === skill.owner_id
	);

	function formatDate(dateStr: string): string {
		return new Date(dateStr).toLocaleDateString(undefined, {
			year: 'numeric', month: 'short', day: 'numeric'
		});
	}

	async function loadReviews(skillId: number) {
		try {
			reviews = await api<ReviewOut[]>(`/reviews/skill/${skillId}`);
			if ($isLoggedIn && $user) {
				hasReviewed = reviews.some(r => r.reviewer_id === $user?.id);
			}
		} catch {
			reviews = [];
		}
	}

	async function submitReview() {
		if (!skill) return;
		submittingReview = true;
		reviewError = '';
		reviewSuccess = '';
		try {
			await api('/reviews/skill', {
				method: 'POST',
				auth: true,
				body: {
					skill_id: skill.id,
					rating: reviewRating,
					comment: reviewComment || null
				}
			});
			reviewSuccess = $_('review.submitted');
			reviewComment = '';
			hasReviewed = true;
			await loadReviews(skill.id);
		} catch (err) {
			reviewError = err instanceof Error ? err.message : $_('skills.review_failed');
		} finally {
			submittingReview = false;
		}
	}

	onMount(async () => {
		const id = $page.params.id;
		try {
			skill = await api<Skill>(`/skills/${id}`);
			await loadReviews(skill.id);
		} catch (err) {
			error = err instanceof Error ? err.message : $_('skills.not_found');
		} finally {
			loading = false;
		}
	});

	async function deleteSkill() {
		if (!skill) return;
		if (!confirmDelete) { confirmDelete = true; return; }
		confirmDelete = false;
		try {
			await api(`/skills/${skill.id}`, {
				method: 'DELETE', auth: true,
				offline: { label: $_('skills.offline_delete', { values: { title: skill.title } }) }
			});
			goto('/skills');
		} catch (err) {
			error = err instanceof Error ? err.message : $_('common.error');
		}
	}

	function startEdit() {
		if (!skill) return;
		editForm = {
			title: skill.title,
			description: skill.description ?? '',
			category: skill.category,
			skill_type: skill.skill_type
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
		if (!skill) return;
		editError = '';
		editSaving = true;
		try {
			skill = await api<Skill>(`/skills/${skill.id}`, {
				method: 'PATCH',
				auth: true,
				body: {
					title: editForm.title,
					description: editForm.description.trim() || null,
					category: editForm.category,
					skill_type: editForm.skill_type
				}
			});
			editing = false;
		} catch (err) {
			editError = err instanceof Error ? err.message : $_('skills.edit_failed');
		} finally {
			editSaving = false;
		}
	}

	function startConversation(ownerId: number, skillId: number) {
		goto(`/messages?partner=${ownerId}&skill=${skillId}`);
	}
</script>

{#if loading}
	<div class="skeleton-stack" role="status" aria-busy="true">
		<span class="sr-only">{$_('common.loading')}</span>
		<span class="skeleton skeleton-line is-short"></span>
		<span class="skeleton" style="height: 2.4rem; width: 60%"></span>
		<div class="skeleton skeleton-card" style="height: 12rem; margin-top: 1rem"></div>
	</div>
{:else if error}
	<div class="error-page">
		<h1>{$_('common.oops')}</h1>
		<p>{error}</p>
		<a href="/skills" class="btn btn-primary">{$_('skills.back')}</a>
	</div>
{:else if skill}
	<article class="skill-detail">
		<a href="/skills" class="back-link"><Icon name="arrow-left" size={16} class="flip-rtl" /> {$_('skills.back')}</a>

		<div class="detail-header">
			<div class="icon-section">
				<span class="skill-icon"><Icon name={SKILL_CATEGORY_ICON[skill.category] ?? 'star'} size={30} strokeWidth={1.75} /></span>
			</div>
			<div class="header-content">
				<div class="badges">
					<span class="badge badge-primary badge-caps">{$_('skills.categories.' + skill.category)}</span>
					<span class="badge badge-caps" class:badge-success={skill.skill_type === 'offer'} class:badge-warning={skill.skill_type === 'request'}>
						{skill.skill_type === 'offer' ? $_('skills.offering') : $_('skills.looking_for')}
					</span>
				</div>
				<h1>{skill.title}</h1>
				<p class="meta">{$_('common.listed_on', { values: { date: formatDate(skill.created_at) } })}</p>
			</div>
		</div>

		<div class="detail-grid">
			<div class="detail-main">
				{#if editing && isOwner}
					<form class="card section-card edit-form" onsubmit={saveEdit} aria-labelledby="edit-skill-heading">
						<h3 id="edit-skill-heading">{$_('skills.edit_title')}</h3>

						{#if editError}
							<p class="alert alert-error" role="alert">{editError}</p>
						{/if}

						<div class="field">
							<label for="edit-skill-title">{$_('skills.title_label')}</label>
							<input id="edit-skill-title" type="text" bind:value={editForm.title} required maxlength="200" disabled={editSaving} />
						</div>

						<div class="field">
							<label for="edit-skill-description">{$_('skills.description_label')}</label>
							<textarea id="edit-skill-description" bind:value={editForm.description} rows="4" maxlength="5000" disabled={editSaving}></textarea>
						</div>

						<div class="field-row">
							<div class="field">
								<label for="edit-skill-category">{$_('skills.category_label')}</label>
								<select id="edit-skill-category" bind:value={editForm.category} disabled={editSaving}>
									{#each EDIT_CATEGORIES as cat}
										<option value={cat}>{$_('skills.categories.' + cat)}</option>
									{/each}
								</select>
							</div>
							<div class="field">
								<label for="edit-skill-type">{$_('skills.type_label')}</label>
								<select id="edit-skill-type" bind:value={editForm.skill_type} disabled={editSaving}>
									<option value="offer">{$_('skills.type_offering')}</option>
									<option value="request">{$_('skills.type_seeking')}</option>
								</select>
							</div>
						</div>

						<div class="form-actions">
							<button type="submit" class="btn btn-primary" class:is-loading={editSaving} disabled={editSaving}>
								{editSaving ? $_('skills.edit_saving') : $_('skills.edit_save')}
							</button>
							<button type="button" class="btn btn-secondary" onclick={cancelEdit} disabled={editSaving}>
								{$_('common.cancel')}
							</button>
						</div>
					</form>
				{:else}
					<div class="card section-card">
						<h3>{$_('skills.about')}</h3>
						{#if skill.description}
							<p>{skill.description}</p>
						{:else}
							<p class="no-description">{$_('skills.no_description')}</p>
						{/if}
					</div>
				{/if}

				<!-- Reviews Section -->
				<div class="card section-card">
					<h3>{$_('profile.reviews')} ({reviews.length})</h3>
					{#if reviews.length === 0}
						<p class="no-reviews-text">{$_('profile.no_reviews')}</p>
					{:else}
						<div class="review-list">
							{#each reviews as review}
								<div class="review-item">
									<div class="review-item-header">
										<a href="/profile/{review.reviewer_id}" class="reviewer-name">{review.reviewer.display_name}</a>
										<span class="review-item-stars">{#each [1, 2, 3, 4, 5] as s}<Icon name="star" size={14} filled={s <= Math.round(review.rating)} />{/each}</span>
										<span class="review-item-date">{formatDate(review.created_at)}</span>
									</div>
									{#if review.comment}
										<p class="review-item-comment">{review.comment}</p>
									{/if}
								</div>
							{/each}
						</div>
					{/if}
				</div>

				<!-- Leave a Review -->
				{#if $isLoggedIn && !isOwner && !hasReviewed}
					<div class="card section-card">
						<h3>{$_('review.leave_review')}</h3>
						{#if reviewError}
							<p class="alert alert-error" role="alert">{reviewError}</p>
						{/if}
						{#if reviewSuccess}
							<p class="alert alert-success" role="status">{reviewSuccess}</p>
						{/if}
						<div class="review-form">
							<div class="star-picker">
								<span class="star-label">{$_('review.your_rating')}</span>
								{#each [1, 2, 3, 4, 5] as star}
									<button
										class="star-btn"
										class:active={star <= reviewRating}
										aria-pressed={star <= reviewRating}
										onclick={() => (reviewRating = star)}
										type="button"
									><Icon name="star" size={26} filled={star <= reviewRating} /></button>
								{/each}
							</div>
							<textarea
							class="input"
							bind:value={reviewComment}
								rows="3"
								placeholder={$_('review.comment_placeholder')}
								maxlength="5000"
							></textarea>
							<button class="btn btn-primary" class:is-loading={submittingReview} onclick={submitReview} disabled={submittingReview}>
								{submittingReview ? $_('common.loading') : $_('review.submit')}
							</button>
						</div>
					</div>
				{:else if hasReviewed}
					<p class="already-reviewed">{$_('review.already_reviewed')}</p>
				{/if}
			</div>

			<aside class="detail-side">
				<!-- Owner card -->
				<div class="card section-card owner-card">
					<h3>{$_('profile.listed_by')}</h3>
					<div class="owner-row">
						<span class="owner-avatar" aria-hidden="true">{skill.owner.display_name.charAt(0).toUpperCase()}</span>
						<div class="owner-id">
							<a href="/profile/{skill.owner_id}" class="owner-name-link">{skill.owner.display_name}</a>
							{#if skill.owner.neighbourhood}
								<p class="owner-neighbourhood">{skill.owner.neighbourhood}</p>
							{/if}
						</div>
					</div>
					{#if skill.owner_trust}
						<div class="owner-trust-row">
							{#if skill.owner_trust.total_reviews > 0}
								<span class="trust-stars"><Icon name="star" size={14} />{skill.owner_trust.average_rating.toFixed(1)}</span>
								<span class="trust-count">({skill.owner_trust.total_reviews} {$_('profile.reviews')})</span>
							{/if}
							{#each skill.owner_trust.badges as badge}
								<span class="trust-badge-mini"><Icon name={TRUST_BADGE_ICON[badge] ?? 'star'} size={16} /></span>
							{/each}
							<span class="trust-level">{$_('dashboard.level_' + skill.owner_trust.reputation_level.toLowerCase(), { default: skill.owner_trust.reputation_level })}</span>
						</div>
					{/if}
					{#if $isLoggedIn && $user?.id !== skill.owner_id}
						<button class="btn btn-secondary btn-block btn-message-owner" onclick={() => startConversation(skill!.owner_id, skill!.id)}>
							<Icon name="message" size={16} />
							{skill.skill_type === 'offer' ? $_('skills.message_tutor') : $_('skills.message_requester')}
						</button>
					{/if}
				</div>

				<!-- Owner actions -->
				{#if isOwner}
					<div class="card section-card owner-panel">
						<h3>{$_('skills.manage')}</h3>
						<div class="owner-actions">
							<button class="btn btn-secondary" onclick={startEdit} disabled={editing}>
								{$_('skills.edit_btn')}
							</button>
							{#if confirmDelete}
								<span class="confirm-text">{$_('common.confirm_delete')}</span>
								<button class="btn btn-danger" onclick={deleteSkill}>{$_('common.delete')}</button>
								<button class="btn btn-secondary" onclick={() => confirmDelete = false}>{$_('common.cancel')}</button>
							{:else}
								<button class="btn btn-danger-outline" onclick={deleteSkill}>{$_('skills.delete_listing')}</button>
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
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		margin-bottom: 1rem;
	}

	.back-link:hover {
		color: var(--color-primary-text);
	}

	.skill-detail {
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

	.detail-header {
		display: flex;
		align-items: flex-start;
		gap: 1.25rem;
		margin-bottom: 2rem;
	}

	.icon-section {
		flex-shrink: 0;
	}

	.skill-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 64px;
		height: 64px;
		border-radius: var(--radius-lg);
		background: var(--color-primary-light);
		color: var(--color-primary-text);
	}

	.header-content {
		flex: 1;
	}

	.detail-header h1 {
		font-size: 2.1rem;
		margin-top: 0.65rem;
	}

	.meta {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		margin-top: 0.5rem;
	}

	.badges {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.section-card {
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

	.owner-neighbourhood {
		font-size: 0.9rem;
		color: var(--color-text-muted);
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
		display: inline-flex;
		align-items: center;
		gap: 0.2rem;
		color: var(--color-warning);
		font-weight: 600;
	}

	.trust-count {
		color: var(--color-text-muted);
	}

	.trust-badge-mini {
		display: inline-flex;
		color: var(--color-primary-text);
	}

	.trust-level {
		padding: 0.1rem 0.5rem;
		border-radius: 999px;
		background: var(--color-primary-light);
		color: var(--color-primary-text);
		font-weight: 600;
		font-size: 0.75rem;
	}

	.btn-message-owner {
		margin-top: 1rem;
	}

	/* Review list */
	.review-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.review-item {
		padding: 0.75rem 0;
		border-bottom: 1px solid var(--color-border);
	}

	.review-item:last-child {
		border-bottom: none;
	}

	.review-item-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.3rem;
		flex-wrap: wrap;
	}

	.reviewer-name {
		font-weight: 600;
		color: var(--color-primary-text);
		text-decoration: none;
		font-size: 0.9rem;
	}

	.reviewer-name:hover {
		text-decoration: underline;
	}

	.review-item-stars {
		display: inline-flex;
		color: var(--color-warning);
	}

	.review-item-date {
		color: var(--color-text-subtle);
		font-size: 0.78rem;
		margin-inline-start: auto;
	}

	.review-item-comment {
		font-size: 0.88rem;
		margin: 0;
		color: var(--color-text);
	}

	.no-reviews-text {
		color: var(--color-text-muted);
		font-size: 0.9rem;
	}

	/* Review form */
	.review-form {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.star-picker {
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}

	.star-label {
		font-size: 0.85rem;
		font-weight: 500;
		margin-inline-end: 0.5rem;
	}

	.star-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: var(--tap-target);
		min-height: var(--tap-target);
		background: none;
		border: none;
		cursor: pointer;
		color: var(--color-border-hover);
		transition: color var(--transition-fast);
		padding: 0;
	}

	.star-btn.active {
		color: var(--color-warning);
	}

	.review-form textarea {
		resize: vertical;
	}

	.already-reviewed {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		font-style: italic;
		margin-bottom: 1rem;
	}

	.owner-panel {
		background: var(--color-bg);
	}

	.owner-actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
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

	.edit-form .form-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
	}

	.error-page {
		text-align: center;
		padding: 3rem 1rem;
	}

	.error-page h1 {
		color: var(--color-error);
	}
</style>
