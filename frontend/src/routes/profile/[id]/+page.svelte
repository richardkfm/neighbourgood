<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { isLoggedIn, user } from '$lib/stores/auth';
	import { _ } from 'svelte-i18n';
	import type { TrustSummary, ReviewOut } from '$lib/types';

	let trust: TrustSummary | null = null;
	let reviews: ReviewOut[] = [];
	let loading = true;
	let error = '';
	let activeTab: 'received' | 'given' = 'received';
	let reviewPage = 0;
	let hasMore = true;
	let loadingMore = false;
	const PAGE_SIZE = 5;

	$: userId = Number($page.params.id);

	const BADGE_ICONS: Record<string, string> = {
		reliable_borrower: '🤝',
		trusted_lender: '📦',
		skilled_helper: '⭐'
	};

	const BADGE_COLORS: Record<string, string> = {
		reliable_borrower: 'var(--color-success)',
		trusted_lender: 'var(--color-primary)',
		skilled_helper: 'var(--color-warning)'
	};

	const LEVEL_ICONS: Record<string, string> = {
		Newcomer: '🌱',
		Neighbour: '🏠',
		Helper: '🤲',
		Trusted: '🛡️',
		Pillar: '🏛️'
	};

	function renderStars(rating: number): string {
		const full = Math.floor(rating);
		const half = rating - full >= 0.5 ? 1 : 0;
		const empty = 5 - full - half;
		return '★'.repeat(full) + (half ? '½' : '') + '☆'.repeat(empty);
	}

	async function loadTrust() {
		try {
			trust = await api<TrustSummary>(`/users/${userId}/trust`);
		} catch (e: any) {
			error = e.message || 'Failed to load profile';
		}
	}

	async function loadReviews(reset = false) {
		if (reset) {
			reviews = [];
			reviewPage = 0;
			hasMore = true;
		}
		loadingMore = true;
		try {
			const typeParam = activeTab === 'given' ? 'review_type=given' : '';
			const skip = reviewPage * PAGE_SIZE;
			const fetched = await api<ReviewOut[]>(
				`/reviews/user/${userId}?${typeParam}&skip=${skip}&limit=${PAGE_SIZE}`
			);
			reviews = [...reviews, ...fetched];
			hasMore = fetched.length === PAGE_SIZE;
			reviewPage++;
		} catch (e: any) {
			error = e.message;
		} finally {
			loadingMore = false;
		}
	}

	async function switchTab(tab: 'received' | 'given') {
		activeTab = tab;
		await loadReviews(true);
	}

	function formatDate(dateStr: string): string {
		return new Date(dateStr).toLocaleDateString(undefined, {
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		});
	}

	onMount(async () => {
		await loadTrust();
		await loadReviews();
		loading = false;
	});
</script>

<svelte:head>
	<title>{trust?.display_name ?? $_('profile.title')} — NeighbourGood</title>
</svelte:head>

<div class="profile-page">
	{#if loading}
		<div class="loading">{$_('profile.loading')}</div>
	{:else if error}
		<div class="alert alert-error">{error}</div>
	{:else if trust}
		<!-- Profile Header -->
		<section class="profile-header">
			<div class="avatar">{trust.display_name.charAt(0).toUpperCase()}</div>
			<div class="header-info">
				<h1>{trust.display_name}</h1>
				{#if trust.neighbourhood}
					<p class="neighbourhood">{trust.neighbourhood}</p>
				{/if}
				<p class="member-since">{$_('profile.member_since')} {formatDate(trust.member_since)}</p>
				<span class="level-badge">
					{LEVEL_ICONS[trust.reputation_level] ?? '🌱'}
					{trust.reputation_level}
				</span>
			</div>
		</section>

		<!-- Trust Badges -->
		{#if trust.badges.length > 0}
			<section class="badges-section">
				{#each trust.badges as badge}
					<span class="trust-badge" style="--badge-color: {BADGE_COLORS[badge.key] ?? 'var(--color-primary)'}">
						<span class="badge-icon">{BADGE_ICONS[badge.key] ?? '🏆'}</span>
						<span class="badge-label">{badge.label}</span>
						<span class="badge-desc">{badge.description}</span>
					</span>
				{/each}
			</section>
		{/if}

		<!-- Rating Overview -->
		<section class="section-card rating-overview">
			<div class="overall-rating">
				<span class="stars">{renderStars(trust.average_rating)}</span>
				<span class="rating-number">{trust.average_rating.toFixed(1)}</span>
				<span class="review-count">({trust.total_reviews} {$_('profile.reviews')})</span>
			</div>

			<div class="rating-breakdown">
				{#if trust.lender_reviews > 0}
					<div class="breakdown-row">
						<span class="breakdown-label">{$_('trust.trusted_lender')}</span>
						<span class="breakdown-stars">{renderStars(trust.lender_rating)}</span>
						<span class="breakdown-count">{trust.lender_rating.toFixed(1)} ({trust.lender_reviews})</span>
					</div>
				{/if}
				{#if trust.borrower_reviews > 0}
					<div class="breakdown-row">
						<span class="breakdown-label">{$_('trust.reliable_borrower')}</span>
						<span class="breakdown-stars">{renderStars(trust.borrower_rating)}</span>
						<span class="breakdown-count">{trust.borrower_rating.toFixed(1)} ({trust.borrower_reviews})</span>
					</div>
				{/if}
				{#if trust.skill_reviews > 0}
					<div class="breakdown-row">
						<span class="breakdown-label">{$_('trust.skilled_helper')}</span>
						<span class="breakdown-stars">{renderStars(trust.skill_rating)}</span>
						<span class="breakdown-count">{trust.skill_rating.toFixed(1)} ({trust.skill_reviews})</span>
					</div>
				{/if}
			</div>
		</section>

		<!-- Stats -->
		<section class="stats-row">
			<div class="stat-card">
				<span class="stat-value">{trust.resources_count}</span>
				<span class="stat-label">{$_('profile.resources_shared')}</span>
			</div>
			<div class="stat-card">
				<span class="stat-value">{trust.skills_count}</span>
				<span class="stat-label">{$_('profile.skills_offered')}</span>
			</div>
			<div class="stat-card">
				<span class="stat-value">{trust.reputation_score}</span>
				<span class="stat-label">{$_('profile.reputation_points')}</span>
			</div>
		</section>

		<!-- Reviews Section -->
		<section class="reviews-section">
			<nav class="browse-tabs">
				<button
					class="browse-tab"
					class:active={activeTab === 'received'}
					on:click={() => switchTab('received')}
				>
					{$_('profile.reviews_received')}
				</button>
				<button
					class="browse-tab"
					class:active={activeTab === 'given'}
					on:click={() => switchTab('given')}
				>
					{$_('profile.reviews_given')}
				</button>
			</nav>

			{#if reviews.length === 0}
				<p class="no-reviews">{$_('profile.no_reviews')}</p>
			{:else}
				<div class="review-list">
					{#each reviews as review}
						<div class="review-card">
							<div class="review-header">
								<a href="/profile/{activeTab === 'received' ? review.reviewer_id : review.reviewee_id}" class="review-author">
									{activeTab === 'received' ? review.reviewer.display_name : review.reviewee.display_name}
								</a>
								<span class="review-stars">{renderStars(review.rating)}</span>
								<span class="review-type-badge" class:skill={review.review_type === 'skill'}>
									{review.review_type === 'skill' ? $_('profile.skill_review') : $_('profile.booking_review')}
								</span>
							</div>
							{#if review.comment}
								<p class="review-comment">{review.comment}</p>
							{/if}
							<span class="review-date">{formatDate(review.created_at)}</span>
						</div>
					{/each}
				</div>
			{/if}

			{#if hasMore && reviews.length > 0}
				<button class="load-more" on:click={() => loadReviews()} disabled={loadingMore}>
					{loadingMore ? $_('profile.loading') : $_('profile.load_more')}
				</button>
			{/if}
		</section>
	{/if}
</div>

<style>
	.profile-page {
		max-width: 680px;
		margin: 2rem auto;
		padding: 0 1rem;
	}

	.loading {
		text-align: center;
		padding: 3rem;
		color: var(--color-text-muted);
	}

	/* Header */
	.profile-header {
		display: flex;
		gap: 1.25rem;
		align-items: center;
		margin-bottom: 1.5rem;
	}

	.avatar {
		width: 72px;
		height: 72px;
		border-radius: 50%;
		background: var(--color-primary);
		color: white;
		font-size: 2rem;
		font-weight: 700;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.header-info h1 {
		margin: 0 0 0.25rem;
		font-size: 1.5rem;
	}

	.neighbourhood {
		margin: 0;
		color: var(--color-text-muted);
		font-size: 0.9rem;
	}

	.member-since {
		margin: 0.15rem 0 0.5rem;
		color: var(--color-text-subtle);
		font-size: 0.82rem;
	}

	.level-badge {
		display: inline-block;
		padding: 0.2rem 0.75rem;
		border-radius: 999px;
		background: var(--color-primary-light);
		color: var(--color-primary);
		font-weight: 600;
		font-size: 0.82rem;
	}

	/* Trust Badges */
	.badges-section {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		margin-bottom: 1.5rem;
	}

	.trust-badge {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.5rem 0.85rem;
		border-radius: var(--radius);
		background: var(--color-surface);
		border: 1px solid var(--badge-color, var(--color-border));
		font-size: 0.82rem;
	}

	.badge-icon {
		font-size: 1rem;
	}

	.badge-label {
		font-weight: 600;
		color: var(--badge-color, var(--color-text));
	}

	.badge-desc {
		color: var(--color-text-muted);
		font-size: 0.78rem;
	}

	/* Rating Overview */
	.rating-overview {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		padding: 1.25rem;
		margin-bottom: 1.25rem;
	}

	.overall-rating {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.stars {
		color: var(--color-warning);
		font-size: 1.1rem;
	}

	.rating-number {
		font-size: 1.3rem;
		font-weight: 700;
		color: var(--color-text);
	}

	.review-count {
		color: var(--color-text-muted);
		font-size: 0.85rem;
	}

	.rating-breakdown {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.breakdown-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		font-size: 0.85rem;
	}

	.breakdown-label {
		min-width: 120px;
		color: var(--color-text-muted);
	}

	.breakdown-stars {
		color: var(--color-warning);
	}

	.breakdown-count {
		color: var(--color-text-muted);
		font-size: 0.8rem;
	}

	/* Stats Row */
	.stats-row {
		display: flex;
		gap: 1rem;
		margin-bottom: 1.5rem;
	}

	.stat-card {
		flex: 1;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		padding: 1rem;
		text-align: center;
	}

	.stat-value {
		display: block;
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--color-primary);
	}

	.stat-label {
		font-size: 0.78rem;
		color: var(--color-text-muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	/* Tabs */
	.browse-tabs {
		display: flex;
		gap: 0.25rem;
		border-bottom: 2px solid var(--color-border);
		margin-bottom: 1rem;
	}

	.browse-tab {
		padding: 0.6rem 1.25rem;
		font-size: 0.95rem;
		font-weight: 500;
		color: var(--color-text-muted);
		background: none;
		border: none;
		border-bottom: 3px solid transparent;
		margin-bottom: -2px;
		cursor: pointer;
		transition: all 150ms;
	}

	.browse-tab.active {
		color: var(--color-primary);
		border-bottom-color: var(--color-primary);
		font-weight: 600;
	}

	/* Review Cards */
	.review-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.review-card {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		padding: 1rem;
	}

	.review-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.5rem;
		flex-wrap: wrap;
	}

	.review-author {
		font-weight: 600;
		color: var(--color-primary);
		text-decoration: none;
	}

	.review-author:hover {
		text-decoration: underline;
	}

	.review-stars {
		color: var(--color-warning);
		font-size: 0.9rem;
	}

	.review-type-badge {
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		padding: 0.15rem 0.5rem;
		border-radius: 999px;
		background: var(--color-bg);
		color: var(--color-text-muted);
		font-weight: 600;
	}

	.review-type-badge.skill {
		background: var(--color-warning-bg);
		color: var(--color-warning);
	}

	.review-comment {
		margin: 0 0 0.4rem;
		font-size: 0.9rem;
		line-height: 1.6;
		color: var(--color-text);
	}

	.review-date {
		font-size: 0.78rem;
		color: var(--color-text-subtle);
	}

	.no-reviews {
		text-align: center;
		color: var(--color-text-muted);
		padding: 2rem;
		font-size: 0.9rem;
	}

	.load-more {
		display: block;
		margin: 1rem auto;
		padding: 0.5rem 1.5rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		color: var(--color-primary);
		font-weight: 600;
		cursor: pointer;
		transition: border-color 150ms;
	}

	.load-more:hover:not(:disabled) {
		border-color: var(--color-primary);
	}

	.load-more:disabled {
		opacity: 0.6;
		cursor: default;
	}

	.alert-error {
		padding: 1rem;
		border-radius: var(--radius-sm);
		background-color: rgba(239, 68, 68, 0.1);
		border: 1px solid rgba(239, 68, 68, 0.3);
		color: var(--color-error);
	}

	@media (max-width: 640px) {
		.profile-header {
			flex-direction: column;
			text-align: center;
		}

		.stats-row {
			flex-direction: column;
		}

		.breakdown-label {
			min-width: auto;
		}
	}
</style>
