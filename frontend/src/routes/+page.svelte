<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isLoggedIn } from '$lib/stores/auth';
	import { bandwidth, platformMode } from '$lib/stores/theme';
	import { t } from 'svelte-i18n';
	import { api } from '$lib/api';
	import MeshBackground from '$lib/components/MeshBackground.svelte';

	interface PlatformStatus {
		status: string;
		version: string;
		mode: 'blue' | 'red';
	}

	let platformStatus: PlatformStatus | null = $state(null);
	let error: string | null = $state(null);

	onMount(async () => {
		// Returning users land in the app, not on the marketing page.
		if ($isLoggedIn) {
			goto('/dashboard', { replaceState: true });
			return;
		}
		try {
			platformStatus = await api<PlatformStatus>('/status');
		} catch {
			error = $t('home.status_unavailable');
		}
	});

	const modeLabel = $derived(
		$platformMode === 'red' ? $t('home.status_red_sky') : $t('home.status_blue_sky')
	);
	const modeClass = $derived($platformMode === 'red' ? 'mode-red' : 'mode-blue');

	const FEATURES = [
		{ key: 'resources', icon: 'M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z' },
		{ key: 'skills', icon: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0z' },
		{ key: 'crisis', icon: 'M13 2 3 14h9l-1 8 10-12h-9l1-8z' },
		{ key: 'hosted', icon: 'M19 11H5a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2zM7 11V7a5 5 0 0 1 10 0v4' },
		{ key: 'groups', icon: 'M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM9 22V12h6v10' },
		{ key: 'messaging', icon: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z' }
	];
</script>

<main class="landing">
	<section class="hero">
		{#if $bandwidth !== 'low'}
			<MeshBackground />
		{/if}
		<div class="hero-copy slide-up">
			<p class="hero-eyebrow">{$t('home.hero_title')}</p>
			<h1>{$t('home.hero_tag1')}<br />{$t('home.hero_tag2')}<br /><em class="hero-accent">{$t('home.hero_tag3')}</em></h1>
			<p class="hero-subtitle">
				{$t('home.hero_subtitle')}
			</p>
			<div class="hero-actions">
				<a href="/explore" class="btn-hero">{$t('home.get_started')}</a>
				<a href="/login" class="btn-hero-secondary">{$t('nav.login')}</a>
			</div>
		</div>

		{#if $bandwidth !== 'low'}
			<div class="hero-panel" aria-hidden="true">
				<div class="mock-card mock-card-1 slide-up" style="animation-delay: 0.15s">
					<span class="mock-icon">🔧</span>
					<span class="mock-text">{$t('home.hero_activity_1')}</span>
					<span class="mock-dot mock-dot-green"></span>
				</div>
				<div class="mock-card mock-card-2 slide-up" style="animation-delay: 0.35s">
					<span class="mock-icon">🚲</span>
					<span class="mock-text">{$t('home.hero_activity_2')}</span>
					<span class="mock-dot mock-dot-green"></span>
				</div>
				<div class="mock-card mock-card-3 slide-up" style="animation-delay: 0.55s">
					<span class="mock-icon">🎹</span>
					<span class="mock-text">{$t('home.hero_activity_3')}</span>
					<span class="mock-dot mock-dot-violet"></span>
				</div>
				<div class="mock-bubble slide-up" style="animation-delay: 0.75s">
					<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
					<span class="mock-bubble-text">{$t('home.hero_activity_message')}</span>
				</div>
			</div>
		{/if}
	</section>

	<section class="features">
		<h2 class="features-heading">{$t('home.features_title')}</h2>
		<div class="feature-grid">
			{#each FEATURES as feature, i}
				<div class="feature-card slide-up" style="animation-delay: {0.05 * (i + 1)}s">
					<div class="feature-card-top">
						<span class="feature-index">0{i + 1}</span>
						<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="feature-mark"><path d={feature.icon}/></svg>
					</div>
					<h3>{$t(`home.feat_${feature.key}_title`)}</h3>
					<p>{$t(`home.feat_${feature.key}_desc`)}</p>
				</div>
			{/each}
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
		max-width: 960px;
		margin: 0 auto;
	}

	/* ── Hero: asymmetric editorial split ─────────────────────────── */

	.hero {
		position: relative;
		display: grid;
		grid-template-columns: 1.15fr 0.85fr;
		align-items: center;
		gap: 3rem;
		padding: 3.5rem 0 4rem;
		overflow: hidden;
	}

	/* Explicit stacking so the mesh background canvas (an absolutely
	   positioned, non-grid sibling painted first) stays behind these
	   grid items instead of on top of them. */
	.hero-copy {
		position: relative;
		z-index: 1;
	}

	.hero-eyebrow {
		font-family: 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace;
		font-size: 0.75rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.12em;
		color: var(--color-accent);
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 1.5rem;
	}

	.hero-eyebrow::before {
		content: '';
		width: 2rem;
		height: 1px;
		background: var(--color-accent);
		flex-shrink: 0;
	}

	.hero h1 {
		font-size: clamp(2.5rem, 6vw, 3.4rem);
		line-height: 1.08;
		color: var(--color-text);
		margin-bottom: 1.25rem;
	}

	.hero-accent {
		font-style: italic;
		color: var(--color-primary);
	}

	.hero-subtitle {
		font-size: 1.05rem;
		color: var(--color-text-muted);
		max-width: 30rem;
		margin-bottom: 2rem;
		line-height: 1.7;
	}

	.hero-actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
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

	/* ── Hero panel: text-free listing-card composition ───────────── */

	.hero-panel {
		position: relative;
		z-index: 1;
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
		padding: 1.5rem 0;
	}

	.hero-panel::before {
		content: '';
		position: absolute;
		inset: -2rem;
		background: radial-gradient(closest-side, var(--color-primary-light), transparent);
		opacity: 0.65;
		pointer-events: none;
	}

	.mock-card {
		position: relative;
		display: flex;
		align-items: center;
		gap: 0.9rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 0.9rem 1.1rem;
		box-shadow: var(--shadow-md);
	}

	.mock-card-1 { transform: rotate(-1.2deg) translateX(-0.5rem); }
	.mock-card-2 { transform: rotate(0.8deg) translateX(1rem); }
	.mock-card-3 { transform: rotate(-0.6deg); }

	.mock-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 40px;
		height: 40px;
		border-radius: var(--radius);
		background: var(--color-primary-light);
		font-size: 1.15rem;
		flex-shrink: 0;
	}

	.mock-text {
		flex: 1;
		font-size: 0.85rem;
		font-weight: 500;
		color: var(--color-text);
		line-height: 1.4;
	}

	.mock-dot {
		width: 9px;
		height: 9px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.mock-dot-green { background: var(--color-success); }
	.mock-dot-violet { background: var(--color-primary); }

	.mock-bubble {
		position: relative;
		align-self: flex-end;
		display: flex;
		align-items: center;
		gap: 0.6rem;
		background: var(--color-primary);
		color: white;
		border-radius: 999px;
		padding: 0.55rem 1rem;
		box-shadow: var(--shadow-md);
		transform: rotate(1.5deg) translateX(-0.75rem);
	}

	.mock-bubble-text {
		font-size: 0.82rem;
		font-weight: 500;
		white-space: nowrap;
	}

	/* ── Features: flat editorial cards ───────────────────────────── */

	.features {
		margin-bottom: 2.5rem;
	}

	.features-heading {
		font-size: 1.15rem;
		margin-bottom: 1.5rem;
		color: var(--color-text);
	}

	.feature-grid {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 1.25rem;
	}

	.feature-card {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 1.4rem 1.5rem 1.5rem;
		transition: border-color var(--transition), transform var(--transition), box-shadow var(--transition);
	}

	.feature-card:hover {
		border-color: var(--color-border-hover);
		box-shadow: var(--shadow-md);
		transform: translateY(-2px);
	}

	.feature-card-top {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		border-bottom: 1px solid var(--color-border);
		padding-bottom: 0.75rem;
		margin-bottom: 0.9rem;
	}

	.feature-index {
		font-family: var(--font-heading);
		font-style: italic;
		font-size: 1rem;
		color: var(--color-text-subtle);
	}

	.feature-mark {
		color: var(--color-primary);
		align-self: center;
	}

	.feature-card h3 {
		font-size: 1rem;
		margin-bottom: 0.4rem;
		color: var(--color-text);
	}

	.feature-card p {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		line-height: 1.6;
	}

	/* ── Status banner ─────────────────────────────────────────────── */

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
		color: var(--color-on-error);
		font-weight: 700;
		font-size: 0.75rem;
		flex-shrink: 0;
	}

	.status-text { font-weight: 500; }
	.status-hint { font-size: 0.8rem; opacity: 0.8; margin-top: 0.15rem; }
	.mode-blue { color: var(--color-primary); }
	.mode-red { color: var(--color-error); }

	/* ── Responsive ────────────────────────────────────────────────── */

	@media (max-width: 860px) {
		.hero {
			grid-template-columns: 1fr;
			gap: 2.5rem;
			padding: 2rem 0 3rem;
		}

		.hero-panel {
			max-width: 24rem;
		}

		.feature-grid {
			grid-template-columns: repeat(2, 1fr);
		}
	}

	@media (max-width: 560px) {
		.feature-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
