<!--
	One list entry in the design-A style: a compact header (icon or image,
	title, one line of meta, an optional status on the right) that opens on
	click or Enter/Space to show details and actions.

	variant="row"  — a row inside a .list-panel (dashboard, stacked lists)
	variant="card" — a standalone card for grids (resources, skills, events)

	The header is a real <button>, so nothing interactive may go into `aside`;
	put links and buttons into the `children` (details) snippet.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from './Icon.svelte';
	import type { IconName } from './Icon.svelte';

	interface Props {
		title: string;
		meta?: string;
		icon?: IconName;
		image?: string | null;
		tone?: 'primary' | 'accent' | 'warning' | 'success' | 'neutral' | 'error';
		variant?: 'row' | 'card';
		open?: boolean;
		aside?: Snippet;
		children?: Snippet;
	}

	let {
		title,
		meta = '',
		icon = 'package',
		image = null,
		tone = 'primary',
		variant = 'row',
		open = $bindable(false),
		aside,
		children
	}: Props = $props();

	const uid = `xp-${Math.random().toString(36).slice(2, 9)}`;
</script>

<div class="xp xp-{variant}" class:open>
	<button
		type="button"
		class="xp-head"
		aria-expanded={open}
		aria-controls={children ? uid : undefined}
		onclick={() => (open = !open)}
	>
		{#if image}
			<img class="xp-thumb xp-img" src={image} alt="" loading="lazy" />
		{:else}
			<span class="xp-thumb tone-{tone}" aria-hidden="true"><Icon name={icon} size={18} /></span>
		{/if}
		<span class="xp-text">
			<span class="xp-title">{title}</span>
			{#if meta}<span class="xp-meta">{meta}</span>{/if}
		</span>
		{#if aside}<span class="xp-aside">{@render aside()}</span>{/if}
		{#if children}<span class="xp-chev" aria-hidden="true"><Icon name="chevron-right" size={16} class="flip-rtl" /></span>{/if}
	</button>
	{#if children && open}
		<div class="xp-body" id={uid}>
			{@render children()}
		</div>
	{/if}
</div>

<style>
	.xp {
		min-width: 0;
	}

	.xp-row + :global(.xp-row) {
		border-top: 1px solid var(--color-border);
	}

	.xp-card {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
	}

	.xp-card:hover,
	.xp-card.open {
		border-color: var(--color-border-hover);
	}

	.xp-card.open {
		box-shadow: var(--shadow-sm);
	}

	.xp-head {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr) auto auto;
		align-items: center;
		gap: 0.75rem;
		width: 100%;
		padding: 0.8rem 1rem;
		background: none;
		border: 0;
		font: inherit;
		color: inherit;
		text-align: start;
		cursor: pointer;
		border-radius: inherit;
	}

	.xp-head:focus-visible {
		outline: 2px solid var(--focus-ring);
		outline-offset: -2px;
	}

	/* Cards are narrow: the status goes under the title instead of beside it */
	.xp-card .xp-head {
		padding: 1rem;
		grid-template-columns: auto minmax(0, 1fr) auto;
		row-gap: 0.4rem;
	}

	.xp-card .xp-thumb {
		grid-row: 1 / span 2;
		align-self: start;
	}

	.xp-card .xp-aside {
		grid-column: 2;
		grid-row: 2;
		justify-content: flex-start;
	}

	.xp-card .xp-chev {
		grid-column: 3;
		grid-row: 1;
		align-self: start;
		margin-top: 0.1rem;
	}

	.xp-thumb {
		width: 2.25rem;
		height: 2.25rem;
		border-radius: var(--radius-sm);
		display: grid;
		place-items: center;
		flex: none;
	}

	.xp-img {
		object-fit: cover;
	}

	.tone-primary { background: var(--color-primary-light); color: var(--color-primary-text); }
	.tone-accent { background: var(--color-accent-light); color: var(--color-accent); }
	.tone-warning { background: var(--color-warning-bg); color: var(--color-warning); }
	.tone-success { background: var(--color-success-bg); color: var(--color-success); }
	.tone-error { background: var(--color-error-bg); color: var(--color-error); }
	.tone-neutral { background: var(--color-surface-raised); color: var(--color-text-muted); }

	.xp-text {
		display: grid;
		gap: 0.1rem;
		min-width: 0;
	}

	.xp-title {
		font-weight: 600;
		font-size: 0.9rem;
		color: var(--color-text);
		overflow-wrap: anywhere;
	}

	.xp-meta {
		font-size: 0.78rem;
		color: var(--color-text-subtle);
		overflow-wrap: anywhere;
	}

	.xp-aside {
		display: flex;
		align-items: center;
		justify-content: flex-end;
	}

	.xp-chev {
		display: inline-flex;
		color: var(--color-text-subtle);
		transition: transform var(--transition-fast);
	}

	.open .xp-chev {
		transform: rotate(90deg);
	}

	:global([dir='rtl']) .open .xp-chev {
		transform: rotate(-90deg);
	}

	.xp-body {
		display: grid;
		gap: 0.6rem;
		margin: 0 1rem 0.9rem;
		padding-top: 0.75rem;
		border-top: 1px solid var(--color-border);
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.xp-body :global(p) {
		margin: 0;
		max-width: 62ch;
	}

	.xp-body :global(.xp-actions) {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.35rem;
	}

	@media (max-width: 480px) {
		.xp-head {
			grid-template-columns: auto minmax(0, 1fr) auto;
		}

		.xp-aside {
			grid-column: 2;
			justify-content: flex-start;
		}

		.xp-chev {
			grid-column: 3;
			grid-row: 1;
		}
	}
</style>
