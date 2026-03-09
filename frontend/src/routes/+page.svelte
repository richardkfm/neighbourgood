<script lang="ts">
	import { onMount } from 'svelte';
	import { isLoggedIn } from '$lib/stores/auth';
	import { bandwidth, platformMode } from '$lib/stores/theme';
	import { t } from 'svelte-i18n';

	interface PlatformStatus {
		status: string;
		version: string;
		mode: 'blue' | 'red';
	}

	let platformStatus: PlatformStatus | null = $state(null);
	let error: string | null = $state(null);

	onMount(async () => {
		try {
			const res = await fetch('/api/status');
			if (res.ok) {
				platformStatus = await res.json();
			} else {
				error = $t('home.status_unavailable');
			}
		} catch {
			error = $t('home.status_unavailable');
		}
	});

	const modeLabel = $derived(
		$platformMode === 'red' ? $t('home.status_red_sky') : $t('home.status_blue_sky')
	);
	const modeClass = $derived($platformMode === 'red' ? 'mode-red' : 'mode-blue');
</script>

<main class="landing">
	<section class="hero slide-up">
		<div class="hero-badge">{$t('home.hero_title')}</div>
		<h1>{$t('home.hero_tag1')}<br />{$t('home.hero_tag2')}<br /><span class="hero-accent">{$t('home.hero_tag3')}</span></h1>
		<p class="hero-subtitle">
			{$t('home.hero_subtitle')}
		</p>
		<div class="hero-actions">
			{#if $isLoggedIn}
				<a href="/resources" class="btn-hero">{$t('home.browse_resources')}</a>
			{:else}
				<a href="/explore" class="btn-hero">{$t('home.get_started')}</a>
				<a href="/login" class="btn-hero-secondary">{$t('nav.login')}</a>
			{/if}
		</div>
	</section>

	{#if $bandwidth !== 'low'}
		<section class="hero-image slide-up" style="animation-delay: 0.05s">
			<img
				src="https://repository-images.githubusercontent.com/1157105951/d1f4dfb1-a28b-4cd3-8994-c4f2906d0354"
				alt="NeighbourGood – a local network for neighbours to share stuff and skills"
				class="social-preview"
			/>
		</section>
	{/if}

	<section class="features">
		<div class="feature-grid">
			<div class="feature-card slide-up" style="animation-delay: 0.05s">
				<div class="feature-icon">
					<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
				</div>
				<h3>{$t('home.feat_resources_title')}</h3>
				<p>{$t('home.feat_resources_desc')}</p>
			</div>
			<div class="feature-card slide-up" style="animation-delay: 0.1s">
				<div class="feature-icon">
					<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
				</div>
				<h3>{$t('home.feat_skills_title')}</h3>
				<p>{$t('home.feat_skills_desc')}</p>
			</div>
			<div class="feature-card slide-up" style="animation-delay: 0.15s">
				<div class="feature-icon">
					<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
				</div>
				<h3>{$t('home.feat_crisis_title')}</h3>
				<p>{$t('home.feat_crisis_desc')}</p>
			</div>
			<div class="feature-card slide-up" style="animation-delay: 0.2s">
				<div class="feature-icon">
					<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="11" width="20" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
				</div>
				<h3>{$t('home.feat_hosted_title')}</h3>
				<p>{$t('home.feat_hosted_desc')}</p>
			</div>
			<div class="feature-card slide-up" style="animation-delay: 0.25s">
				<div class="feature-icon">
					<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
				</div>
				<h3>{$t('home.feat_groups_title')}</h3>
				<p>{$t('home.feat_groups_desc')}</p>
			</div>
			<div class="feature-card slide-up" style="animation-delay: 0.3s">
				<div class="feature-icon">
					<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
				</div>
				<h3>{$t('home.feat_messaging_title')}</h3>
				<p>{$t('home.feat_messaging_desc')}</p>
			</div>
		</div>
	</section>

	{#if error}
		<section class="status-banner status-error fade-in">
			<span class="status-icon">!</span>
			<div>
				<p class="status-text">{error}</p>
				<p class="status-hint">Make sure the backend is running on port 8300.</p>
			</div>
		</section>
	{:else if platformStatus}
		<section class="status-banner status-ok fade-in">
			<span class="status-dot"></span>
			<span class="status-text">
				v{platformStatus.version} &middot; <span class={modeClass}>{modeLabel}</span>
			</span>
		</section>
	{/if}
</main>

<style>
	.landing {
		max-width: 800px;
		margin: 0 auto;
	}

	.hero {
		text-align: center;
		padding: 3.5rem 0 2.5rem;
		position: relative;
	}

	/* Subtle gradient background */
	.hero::before {
		content: '';
		position: absolute;
		inset: 0;
		background: linear-gradient(180deg, var(--color-primary-light) 0%, transparent 70%);
		opacity: 0.5;
		pointer-events: none;
		border-radius: var(--radius-xl);
	}

	.hero > * {
		position: relative;
	}

	.hero-badge {
		display: inline-block;
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--color-primary);
		background: var(--color-primary-light);
		border: 1px solid var(--color-border);
		padding: 0.3rem 0.9rem;
		border-radius: 999px;
		margin-bottom: 1.25rem;
	}

	.hero h1 {
		font-size: 3rem;
		font-weight: 400;
		line-height: 1.15;
		letter-spacing: -0.01em;
		color: var(--color-text);
		margin-bottom: 1.25rem;
		font-family: Georgia, 'Times New Roman', serif;
	}

	.hero-accent {
		background: linear-gradient(135deg, var(--color-primary), var(--color-accent));
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		background-clip: text;
	}

	.hero-subtitle {
		font-size: 1.1rem;
		color: var(--color-text-muted);
		max-width: 500px;
		margin: 0 auto 2rem;
		line-height: 1.7;
	}

	.hero-actions {
		display: flex;
		justify-content: center;
		gap: 0.75rem;
	}

	.btn-hero {
		display: inline-flex;
		align-items: center;
		padding: 0.7rem 1.5rem;
		background: var(--color-primary);
		color: white;
		border-radius: var(--radius);
		font-size: 0.95rem;
		font-weight: 600;
		text-decoration: none;
		transition: all var(--transition-fast);
		box-shadow: var(--shadow);
	}

	.btn-hero:hover {
		background: var(--color-primary-hover);
		box-shadow: var(--shadow-lg);
		transform: translateY(-2px);
		text-decoration: none;
	}

	.btn-hero-secondary {
		display: inline-flex;
		align-items: center;
		padding: 0.7rem 1.5rem;
		background: var(--color-surface);
		color: var(--color-text);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.95rem;
		font-weight: 500;
		text-decoration: none;
		transition: all var(--transition-fast);
	}

	.btn-hero-secondary:hover {
		border-color: var(--color-primary);
		color: var(--color-primary);
		text-decoration: none;
	}

	.features {
		margin-bottom: 2rem;
	}

	.hero-image {
		margin-bottom: 2rem;
		text-align: center;
	}

	.social-preview {
		width: 100%;
		max-width: 700px;
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-lg);
		border: 1px solid var(--color-border);
	}

	.feature-grid {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 1rem;
	}

	@media (max-width: 640px) {
		.feature-grid {
			grid-template-columns: 1fr;
		}
	}

	.feature-card {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 1.5rem;
		transition: all var(--transition);
		box-shadow: var(--shadow-sm);
	}

	.feature-card:hover {
		box-shadow: var(--shadow-md);
		border-color: var(--color-border-hover);
		transform: translateY(-2px);
	}

	.feature-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 48px;
		height: 48px;
		border-radius: var(--radius);
		background: var(--color-primary-light);
		color: var(--color-primary);
		margin-bottom: 1rem;
	}

	.feature-card h3 {
		font-size: 1rem;
		font-weight: 500;
		margin-bottom: 0.4rem;
		color: var(--color-text);
	}

	.feature-card p {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		line-height: 1.6;
	}

	.status-banner {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.75rem 1.25rem;
		border-radius: var(--radius);
		font-size: 0.85rem;
	}

	.status-ok {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		color: var(--color-text-muted);
	}

	.status-error {
		background: var(--color-error-bg);
		border: 1px solid var(--color-error);
		color: var(--color-error);
	}

	.status-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--color-success);
		flex-shrink: 0;
	}

	.status-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 22px;
		height: 22px;
		border-radius: 50%;
		background: var(--color-error);
		color: white;
		font-weight: 700;
		font-size: 0.75rem;
		flex-shrink: 0;
	}

	.status-text { font-weight: 500; }
	.status-hint { font-size: 0.8rem; opacity: 0.8; margin-top: 0.15rem; }
	.mode-blue { color: var(--color-primary); }
	.mode-red { color: var(--color-error); }
</style>
