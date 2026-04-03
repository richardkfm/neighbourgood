<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { api } from '$lib/api';
	import { isLoggedIn, user } from '$lib/stores/auth';
	import { goto } from '$app/navigation';
	import { _ } from 'svelte-i18n';
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

	const isOwner = $derived(
		$isLoggedIn && skill !== null && $user?.id === skill.owner_id
	);

	const CATEGORY_ICONS: Record<string, string> = {
		tutoring: '📚', repairs: '🔧', cooking: '🍳', languages: '🌐',
		music: '🎵', gardening: '🌱', tech: '💻', crafts: '✂️',
		fitness: '💪', other: '⭐'
	};

	const BADGE_ICONS: Record<string, string> = {
		reliable_borrower: '🤝',
		trusted_lender: '📦',
		skilled_helper: '⭐'
	};

	function renderStars(rating: number): string {
		return '★'.repeat(Math.floor(rating)) + '☆'.repeat(5 - Math.floor(rating));
	}

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
			reviewError = err instanceof Error ? err.message : 'Failed to submit review';
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
			error = err instanceof Error ? err.message : 'Skill not found';
		} finally {
			loading = false;
		}
	});

	async function deleteSkill() {
		if (!skill || !confirm('Delete this skill listing?')) return;
		try {
			await api(`/skills/${skill.id}`, {
				method: 'DELETE', auth: true,
				offline: { label: `Delete skill: ${skill.title}` }
			});
			goto('/skills');
		} catch (err) {
			error = err instanceof Error ? err.message : 'Delete failed';
		}
	}

	function startConversation(ownerId: number, skillId: number) {
		goto(`/messages?partner=${ownerId}&skill=${skillId}`);
	}
</script>

{#if loading}
	<p class="loading">{$_('common.loading')}</p>
{:else if error}
	<div class="error-page">
		<h1>Oops</h1>
		<p>{error}</p>
		<a href="/skills">{$_('skills.back')}</a>
	</div>
{:else if skill}
	<article class="skill-detail">
		<a href="/skills" class="back-link">&larr; {$_('skills.back')}</a>

		<div class="detail-header">
			<div class="icon-section">
				<span class="skill-icon">{CATEGORY_ICONS[skill.category] ?? '⭐'}</span>
			</div>
			<div class="header-content">
				<div class="badges">
					<span class="category-badge">{skill.category}</span>
					<span class="type-badge" class:type-offer={skill.skill_type === 'offer'} class:type-request={skill.skill_type === 'request'}>
						{skill.skill_type === 'offer' ? 'Offering' : 'Looking for'}
					</span>
				</div>
				<h1>{skill.title}</h1>
			</div>
		</div>

		{#if skill.description}
			<div class="section-card">
				<h3>About</h3>
				<p>{skill.description}</p>
			</div>
		{/if}

		<div class="owner-section">
			<h3>{$_('profile.listed_by')}</h3>
			<a href="/profile/{skill.owner_id}" class="owner-name-link">{skill.owner.display_name}</a>
			{#if skill.owner.neighbourhood}
				<p class="owner-neighbourhood">{skill.owner.neighbourhood}</p>
			{/if}
			{#if skill.owner_trust}
				<div class="owner-trust-row">
					{#if skill.owner_trust.total_reviews > 0}
						<span class="trust-stars">★ {skill.owner_trust.average_rating.toFixed(1)}</span>
						<span class="trust-count">({skill.owner_trust.total_reviews} {$_('profile.reviews')})</span>
					{/if}
					{#each skill.owner_trust.badges as badge}
						<span class="trust-badge-mini">{BADGE_ICONS[badge] ?? '🏆'}</span>
					{/each}
					<span class="trust-level">{skill.owner_trust.reputation_level}</span>
				</div>
			{/if}
			{#if $isLoggedIn && $user?.id !== skill.owner_id}
				<button class="btn-message-owner" onclick={() => startConversation(skill!.owner_id, skill!.id)}>
					Message {skill.skill_type === 'offer' ? 'Tutor' : 'Requester'}
				</button>
			{/if}
		</div>

		<div class="meta">
			<span>Listed {formatDate(skill.created_at)}</span>
		</div>

		<!-- Reviews Section -->
		<div class="section-card">
			<h3>{$_('profile.reviews')} ({reviews.length})</h3>
			{#if reviews.length === 0}
				<p class="no-reviews-text">{$_('profile.no_reviews')}</p>
			{:else}
				<div class="review-list">
					{#each reviews as review}
						<div class="review-item">
							<div class="review-item-header">
								<a href="/profile/{review.reviewer_id}" class="reviewer-name">{review.reviewer.display_name}</a>
								<span class="review-item-stars">{renderStars(review.rating)}</span>
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
			<div class="section-card">
				<h3>{$_('review.leave_review')}</h3>
				{#if reviewError}
					<p class="error">{reviewError}</p>
				{/if}
				{#if reviewSuccess}
					<p class="success">{reviewSuccess}</p>
				{/if}
				<div class="review-form">
					<div class="star-picker">
						<span class="star-label">{$_('review.your_rating')}</span>
						{#each [1, 2, 3, 4, 5] as star}
							<button
								class="star-btn"
								class:active={star <= reviewRating}
								onclick={() => (reviewRating = star)}
								type="button"
							>★</button>
						{/each}
					</div>
					<textarea
						bind:value={reviewComment}
						rows="3"
						placeholder={$_('review.comment_placeholder')}
						maxlength="5000"
					></textarea>
					<button class="btn-primary" onclick={submitReview} disabled={submittingReview}>
						{submittingReview ? $_('common.loading') : $_('review.submit')}
					</button>
				</div>
			</div>
		{:else if hasReviewed}
			<p class="already-reviewed">{$_('review.already_reviewed')}</p>
		{/if}

		<!-- Owner actions -->
		{#if isOwner}
			<div class="section-card owner-panel">
				<h3>Manage Skill</h3>
				<div class="owner-actions">
					<button class="btn-danger" onclick={deleteSkill}>Delete Listing</button>
				</div>
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

	.skill-detail {
		max-width: 680px;
	}

	.detail-header {
		display: flex;
		gap: 1.5rem;
		margin-bottom: 1.5rem;
	}

	.icon-section {
		flex-shrink: 0;
	}

	.skill-icon {
		font-size: 3rem;
		display: block;
	}

	.header-content {
		flex: 1;
	}

	.detail-header h1 {
		font-size: 1.75rem;
		margin-top: 0.5rem;
	}

	.badges {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.category-badge, .type-badge {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		padding: 0.2rem 0.6rem;
		border-radius: 999px;
		font-weight: 600;
	}

	.category-badge {
		background: var(--color-bg);
		color: var(--color-primary);
	}

	.type-badge {
		color: white;
	}

	.type-offer {
		background: var(--color-success);
	}

	.type-request {
		background: var(--color-warning);
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

	.owner-neighbourhood {
		font-size: 0.9rem;
		color: var(--color-text-muted);
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
		color: var(--color-primary);
		text-decoration: none;
		font-size: 0.9rem;
	}

	.reviewer-name:hover {
		text-decoration: underline;
	}

	.review-item-stars {
		color: var(--color-warning);
		font-size: 0.85rem;
	}

	.review-item-date {
		color: var(--color-text-subtle);
		font-size: 0.78rem;
		margin-left: auto;
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
		margin-right: 0.5rem;
	}

	.star-btn {
		background: none;
		border: none;
		font-size: 1.5rem;
		cursor: pointer;
		color: var(--color-border);
		transition: color 100ms;
		padding: 0;
	}

	.star-btn.active {
		color: var(--color-warning);
	}

	.review-form textarea {
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.9rem;
		background: var(--color-surface);
		color: var(--color-text);
		resize: vertical;
	}

	.review-form textarea:focus {
		outline: none;
		border-color: var(--color-primary);
	}

	.btn-primary {
		background: var(--color-primary);
		color: white;
		border: none;
		border-radius: var(--radius);
		padding: 0.5rem 1rem;
		font-size: 0.9rem;
		cursor: pointer;
		align-self: flex-start;
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--color-primary-hover);
	}

	.btn-primary:disabled {
		opacity: 0.6;
		cursor: default;
	}

	.already-reviewed {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		font-style: italic;
		margin-bottom: 1rem;
	}

	.error {
		color: var(--color-error);
		font-size: 0.9rem;
		margin-bottom: 0.5rem;
	}

	.success {
		color: var(--color-success);
		font-size: 0.9rem;
		margin-bottom: 0.5rem;
	}

	.owner-panel {
		background: var(--color-bg);
	}

	.owner-actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
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
</style>
