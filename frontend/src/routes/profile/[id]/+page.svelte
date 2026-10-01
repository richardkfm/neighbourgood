<script lang="ts">
	import { page } from '$app/stores';
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { isLoggedIn, user } from '$lib/stores/auth';
	import { t as _ } from 'svelte-i18n';
	import type { TrustSummary, ReviewOut } from '$lib/types';
	import Icon from '$lib/components/Icon.svelte';
	import { TRUST_BADGE_ICON, REPUTATION_LEVEL_ICON } from '$lib/icons';

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

	const BADGE_COLORS: Record<string, string> = {
		reliable_borrower: 'var(--color-success)',
		trusted_lender: 'var(--color-primary-text)',
		skilled_helper: 'var(--color-warning)'
	};

	// What a review is about: skill endorsement, or the reviewee's role in a booking
	function reviewLabel(review: ReviewOut): string {
		if (review.review_type === 'skill') return $_('profile.skill_review');
		if (review.reviewee_role === 'lender') return $_('profile.review_lending');
		if (review.reviewee_role === 'borrower') return $_('profile.review_borrowing');
		return $_('profile.review_booking');
	}

	// Backend badge descriptions are English templates; rebuild them from the trust summary
	function badgeDescription(badge: { key: string; description: string }): string {
		if (!trust) return badge.description;
		if (badge.key === 'trusted_lender')
			return $_('trust.desc_trusted_lender', { values: { avg: trust.lender_rating.toFixed(1), count: trust.lender_reviews } });
		if (badge.key === 'reliable_borrower')
			return $_('trust.desc_reliable_borrower', { values: { avg: trust.borrower_rating.toFixed(1), count: trust.borrower_reviews } });
		if (badge.key === 'skilled_helper')
			return $_('trust.desc_skilled_helper', { values: { avg: trust.skill_rating.toFixed(1), count: trust.skill_reviews } });
		return badge.description;
	}

	async function loadTrust() {
		try {
			trust = await api<TrustSummary>(`/users/${userId}/trust`);
		} catch (e: any) {
			error = e.message || $_('profile.load_failed');
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
			const page = Array.isArray(fetched) ? fetched : [];
			reviews = [...reviews, ...page];
			hasMore = page.length === PAGE_SIZE;
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

	// Reload whenever the :id param changes (e.g. following a reviewer link from
	// one profile to another) – the route component is reused, so onMount alone
	// would leave the previous user's data on screen.
	let loadedFor: number | null = null;
	async function loadProfile() {
		trust = null;
		error = '';
		loading = true;
		activeTab = 'received';
		await loadTrust();
		await loadReviews(true);
		loading = false;
	}
	$: if (browser && userId && userId !== loadedFor) {
		loadedFor = userId;
		loadProfile();
	}
</script>

<svelte:head>
	<title>{trust?.display_name ?? $_('profile.title')} — NeighbourGood</title>
</svelte:head>

{#snippet stars(rating: number, size: number)}
	<span class="star-row" aria-label={rating.toFixed(1)}>
		{#each [1, 2, 3, 4, 5] as s}
			<Icon name="star" {size} filled={s <= Math.round(rating)} />
		{/each}
	</span>
{/snippet}

<div class="profile-page">
	{#if loading}
		<div class="skeleton-stack" role="status" aria-busy="true">
			<span class="sr-only">{$_('profile.loading')}</span>
			<div class="skeleton skeleton-card" style="height: 5rem" aria-hidden="true"></div>
			<div class="skeleton skeleton-card" aria-hidden="true"></div>
		</div>
	{:else if error}
		<div class="alert alert-error" role="alert">{error}</div>
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
				<span class="badge badge-primary level-badge">
					<Icon name={REPUTATION_LEVEL_ICON[trust.reputation_level] ?? 'leaf'} size={15} />
					{$_('dashboard.level_' + trust.reputation_level.toLowerCase(), { default: trust.reputation_level })}
				</span>
			</div>
		</section>

		<!-- Trust Badges -->
		{#if trust.badges.length > 0}
			<section class="badges-section">
				{#each trust.badges as badge}
					<span class="trust-badge" style="--badge-color: {BADGE_COLORS[badge.key] ?? 'var(--color-primary-text)'}">
						<span class="badge-icon"><Icon name={TRUST_BADGE_ICON[badge.key] ?? 'star'} size={18} /></span>
						<span class="badge-label">{$_('trust.' + badge.key, { default: badge.label })}</span>
						<span class="badge-desc">{badgeDescription(badge)}</span>
					</span>
				{/each}
			</section>
		{/if}

		<!-- Rating Overview -->
		<section class="card rating-overview">
			<div class="overall-rating">
				<span class="stars">{@render stars(trust.average_rating, 18)}</span>
				<span class="rating-number">{trust.average_rating.toFixed(1)}</span>
				<span class="review-count">({trust.total_reviews} {$_('profile.reviews')})</span>
			</div>

			<div class="rating-breakdown">
				{#if trust.lender_reviews > 0}
					<div class="breakdown-row">
						<span class="breakdown-label">{$_('trust.trusted_lender')}</span>
						<span class="breakdown-stars">{@render stars(trust.lender_rating, 14)}</span>
						<span class="breakdown-count">{trust.lender_rating.toFixed(1)} ({trust.lender_reviews})</span>
					</div>
				{/if}
				{#if trust.borrower_reviews > 0}
					<div class="breakdown-row">
						<span class="breakdown-label">{$_('trust.reliable_borrower')}</span>
						<span class="breakdown-stars">{@render stars(trust.borrower_rating, 14)}</span>
						<span class="breakdown-count">{trust.borrower_rating.toFixed(1)} ({trust.borrower_reviews})</span>
					</div>
				{/if}
				{#if trust.skill_reviews > 0}
					<div class="breakdown-row">
						<span class="breakdown-label">{$_('trust.skilled_helper')}</span>
						<span class="breakdown-stars">{@render stars(trust.skill_rating, 14)}</span>
						<span class="breakdown-count">{trust.skill_rating.toFixed(1)} ({trust.skill_reviews})</span>
					</div>
				{/if}
			</div>
		</section>

		<!-- Stats -->
		<section class="stats-row">
			<div class="card stat-card">
				<span class="stat-value">{trust.resources_count}</span>
				<span class="stat-label">{$_('profile.resources_shared')}</span>
			</div>
			<div class="card stat-card">
				<span class="stat-value">{trust.skills_count}</span>
				<span class="stat-label">{$_('profile.skills_offered')}</span>
			</div>
			<div class="card stat-card">
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
						<div class="card review-card">
							<div class="review-header">
								<a href="/profile/{activeTab === 'received' ? review.reviewer_id : review.reviewee_id}" class="review-author">
									{activeTab === 'received' ? review.reviewer.display_name : review.reviewee.display_name}
								</a>
								<span class="review-stars">{@render stars(review.rating, 14)}</span>
								<span class="badge badge-caps" class:badge-warning={review.review_type === 'skill'}>
									{reviewLabel(review)}
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
				<button class="btn btn-secondary load-more" class:is-loading={loadingMore} on:click={() => loadReviews()} disabled={loadingMore}>
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
		color: var(--color-on-primary);
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
		font-size: 0.82rem;
		padding: 0.2rem 0.75rem;
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
		display: inline-flex;
		color: var(--badge-color, var(--color-primary-text));
	}

	.star-row {
		display: inline-flex;
		gap: 0.1rem;
		vertical-align: middle;
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
		padding: 1rem;
		text-align: center;
	}

	.stat-value {
		display: block;
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--color-primary-text);
	}

	.stat-label {
		font-size: 0.78rem;
		color: var(--color-text-muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	/* Review Cards */
	.review-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.review-card {
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
		color: var(--color-primary-text);
		text-decoration: none;
	}

	.review-author:hover {
		text-decoration: underline;
	}

	.review-stars {
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
		margin: 1rem auto;
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
