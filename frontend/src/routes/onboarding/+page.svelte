<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { isLoggedIn } from '$lib/stores/auth';
	import { onMount } from 'svelte';
	import { t } from 'svelte-i18n';

	// ── Types ──────────────────────────────────────────────────────────────
	interface CommunityOut {
		id: number;
		name: string;
		description: string | null;
		postal_code: string;
		city: string;
		member_count: number;
		is_active: boolean;
	}

	interface Suggestion {
		label: string;
		category: string;
	}

	// ── Wizard state ───────────────────────────────────────────────────────
	let step = $state<'community' | 'skills' | 'items' | 'done'>('community');
	let communityId = $state<number | null>(null);
	let communityName = $state('');

	// ── Step 1: Community ──────────────────────────────────────────────────
	let query = $state('');
	let results = $state<CommunityOut[]>([]);
	let total = $state(0);
	let searching = $state(false);
	let searched = $state(false);
	let joining = $state<number | null>(null);
	let error = $state('');
	let showCreate = $state(false);
	let newName = $state('');
	let newPlz = $state('');
	let newCity = $state('');
	let newDesc = $state('');
	let creating = $state(false);

	// ── Step 2 & 3: Skills and Items ────────────────────────────────────────
	const skillSuggestions: Suggestion[] = $derived([
		{ label: $t('onboarding.skill_fixing_bikes'), category: 'repairs' },
		{ label: $t('onboarding.skill_basic_plumbing'), category: 'repairs' },
		{ label: $t('onboarding.skill_furniture_repair'), category: 'repairs' },
		{ label: $t('onboarding.skill_sewing'), category: 'crafts' },
		{ label: $t('onboarding.skill_baking_bread'), category: 'cooking' },
		{ label: $t('onboarding.skill_meal_prep'), category: 'cooking' },
		{ label: $t('onboarding.skill_preserving_food'), category: 'cooking' },
		{ label: $t('onboarding.skill_plant_care'), category: 'gardening' },
		{ label: $t('onboarding.skill_composting'), category: 'gardening' },
		{ label: $t('onboarding.skill_growing_veg'), category: 'gardening' },
		{ label: $t('onboarding.skill_computer_help'), category: 'tech' },
		{ label: $t('onboarding.skill_phone_setup'), category: 'tech' },
		{ label: $t('onboarding.skill_wifi'), category: 'tech' },
		{ label: $t('onboarding.skill_guitar'), category: 'music' },
		{ label: $t('onboarding.skill_piano'), category: 'music' },
		{ label: $t('onboarding.skill_singing'), category: 'music' },
		{ label: $t('onboarding.skill_yoga'), category: 'fitness' },
		{ label: $t('onboarding.skill_running'), category: 'fitness' },
		{ label: $t('onboarding.skill_knitting'), category: 'crafts' },
		{ label: $t('onboarding.skill_woodworking'), category: 'crafts' },
		{ label: $t('onboarding.skill_painting'), category: 'crafts' },
		{ label: $t('onboarding.skill_math_help'), category: 'tutoring' },
		{ label: $t('onboarding.skill_reading_kids'), category: 'tutoring' },
		{ label: $t('onboarding.skill_pet_sitting'), category: 'other' },
		{ label: $t('onboarding.skill_dog_walking'), category: 'other' },
		{ label: $t('onboarding.skill_moving_help'), category: 'other' },
		{ label: $t('onboarding.skill_driving'), category: 'other' },
	]);

	const itemSuggestions: Suggestion[] = $derived([
		{ label: $t('onboarding.item_drill'), category: 'tool' },
		{ label: $t('onboarding.item_hammer'), category: 'tool' },
		{ label: $t('onboarding.item_screwdriver'), category: 'tool' },
		{ label: $t('onboarding.item_ladder'), category: 'tool' },
		{ label: $t('onboarding.item_saw'), category: 'tool' },
		{ label: $t('onboarding.item_projector'), category: 'electronics' },
		{ label: $t('onboarding.item_speaker'), category: 'electronics' },
		{ label: $t('onboarding.item_extension_cord'), category: 'electronics' },
		{ label: $t('onboarding.item_bicycle'), category: 'vehicle' },
		{ label: $t('onboarding.item_cargo_bike'), category: 'vehicle' },
		{ label: $t('onboarding.item_folding_table'), category: 'furniture' },
		{ label: $t('onboarding.item_extra_chairs'), category: 'furniture' },
		{ label: $t('onboarding.item_moving_dolly'), category: 'furniture' },
		{ label: $t('onboarding.item_rain_boots'), category: 'clothing' },
		{ label: $t('onboarding.item_winter_jacket'), category: 'clothing' },
		{ label: $t('onboarding.item_bread_maker'), category: 'food' },
		{ label: $t('onboarding.item_slow_cooker'), category: 'food' },
		{ label: $t('onboarding.item_blender'), category: 'food' },
		{ label: $t('onboarding.item_board_games'), category: 'other' },
		{ label: $t('onboarding.item_books'), category: 'other' },
		{ label: $t('onboarding.item_camping_gear'), category: 'other' },
		{ label: $t('onboarding.item_tent'), category: 'other' },
		{ label: $t('onboarding.item_sleeping_bag'), category: 'other' },
	]);

	// Track which chips are loading, added, or errored
	let skillsAdded = $state<Set<string>>(new Set());
	let skillsLoading = $state<Set<string>>(new Set());
	let skillsError = $state('');
	let skillCustom = $state('');
	let skillsAddingCustom = $state(false);

	let itemsAdded = $state<Set<string>>(new Set());
	let itemsLoading = $state<Set<string>>(new Set());
	let itemsError = $state('');
	let itemCustom = $state('');
	let itemsAddingCustom = $state(false);

	// Derived counts
	let skillCount = $derived(skillsAdded.size);
	let itemCount = $derived(itemsAdded.size);

	onMount(() => {
		if (!$isLoggedIn) goto('/login');
	});

	// ── Helpers: encouragement text ────────────────────────────────────────
	function skillEncouragement(count: number): string {
		if (count === 0) return $t('onboarding.skills_encouragement_0');
		if (count === 1) return $t('onboarding.skills_encouragement_1');
		if (count === 2) return $t('onboarding.skills_encouragement_2');
		return $t('onboarding.skills_encouragement_3');
	}

	function itemEncouragement(count: number): string {
		if (count === 0) return $t('onboarding.items_encouragement_0');
		if (count === 1) return $t('onboarding.items_encouragement_1');
		if (count === 2) return $t('onboarding.items_encouragement_2');
		return $t('onboarding.items_encouragement_3');
	}

	// ── Step 1: Community actions ──────────────────────────────────────────
	async function search() {
		if (!query.trim()) return;
		searching = true;
		error = '';
		try {
			const param = query.trim();
			const isPlz = /^\d{3,5}$/.test(param);
			const qs = isPlz ? `postal_code=${param}` : `q=${encodeURIComponent(param)}`;
			const res = await api<{ items: CommunityOut[]; total: number }>(
				`/communities/search?${qs}`
			);
			results = res.items;
			total = res.total;
			searched = true;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Search failed';
		} finally {
			searching = false;
		}
	}

	async function joinCommunity(id: number, name: string) {
		joining = id;
		error = '';
		try {
			await api(`/communities/${id}/join`, { method: 'POST', auth: true });
			communityId = id;
			communityName = name;
			step = 'skills';
		} catch (err) {
			error = err instanceof Error ? err.message : 'Could not join';
		} finally {
			joining = null;
		}
	}

	async function createCommunity() {
		if (!newName.trim() || !newPlz.trim() || !newCity.trim()) return;
		creating = true;
		error = '';
		try {
			const created = await api<CommunityOut>('/communities', {
				method: 'POST',
				auth: true,
				body: {
					name: newName.trim(),
					postal_code: newPlz.trim(),
					city: newCity.trim(),
					description: newDesc.trim() || null,
				},
			});
			communityId = created.id;
			communityName = created.name;
			step = 'skills';
		} catch (err) {
			error = err instanceof Error ? err.message : 'Could not create community';
		} finally {
			creating = false;
		}
	}

	// ── Step 2: Skills actions ─────────────────────────────────────────────
	async function addSkill(label: string, category: string) {
		if (skillsAdded.has(label) || skillsLoading.has(label)) return;
		skillsLoading = new Set([...skillsLoading, label]);
		skillsError = '';
		try {
			await api('/skills', {
				method: 'POST',
				auth: true,
				body: {
					title: label,
					category,
					skill_type: 'offer',
					community_id: communityId,
				},
			});
			skillsAdded = new Set([...skillsAdded, label]);
		} catch (err) {
			skillsError = err instanceof Error ? err.message : 'Could not add skill';
		} finally {
			skillsLoading = new Set([...skillsLoading].filter((l) => l !== label));
		}
	}

	async function addCustomSkill() {
		const label = skillCustom.trim();
		if (!label || skillsAdded.has(label)) return;
		skillsAddingCustom = true;
		skillsError = '';
		try {
			await api('/skills', {
				method: 'POST',
				auth: true,
				body: {
					title: label,
					category: 'other',
					skill_type: 'offer',
					community_id: communityId,
				},
			});
			skillsAdded = new Set([...skillsAdded, label]);
			skillCustom = '';
		} catch (err) {
			skillsError = err instanceof Error ? err.message : 'Could not add skill';
		} finally {
			skillsAddingCustom = false;
		}
	}

	// ── Step 3: Items actions ──────────────────────────────────────────────
	async function addItem(label: string, category: string) {
		if (itemsAdded.has(label) || itemsLoading.has(label)) return;
		itemsLoading = new Set([...itemsLoading, label]);
		itemsError = '';
		try {
			await api('/resources', {
				method: 'POST',
				auth: true,
				body: {
					title: label,
					category,
					condition: 'good',
					community_id: communityId,
				},
			});
			itemsAdded = new Set([...itemsAdded, label]);
		} catch (err) {
			itemsError = err instanceof Error ? err.message : 'Could not add item';
		} finally {
			itemsLoading = new Set([...itemsLoading].filter((l) => l !== label));
		}
	}

	async function addCustomItem() {
		const label = itemCustom.trim();
		if (!label || itemsAdded.has(label)) return;
		itemsAddingCustom = true;
		itemsError = '';
		try {
			await api('/resources', {
				method: 'POST',
				auth: true,
				body: {
					title: label,
					category: 'other',
					condition: 'good',
					community_id: communityId,
				},
			});
			itemsAdded = new Set([...itemsAdded, label]);
			itemCustom = '';
		} catch (err) {
			itemsError = err instanceof Error ? err.message : 'Could not add item';
		} finally {
			itemsAddingCustom = false;
		}
	}
</script>

<div class="onboarding slide-up">

	<!-- ── Progress Steps indicator (steps 1–3) ──── -->
	{#if step !== 'done'}
		<div class="progress-steps">
			{#each [['community', $t('onboarding.step_community')], ['skills', $t('onboarding.step_skills')], ['items', $t('onboarding.step_items')]] as [s, label] (s)}
				{@const stepIndex = ['community', 'skills', 'items'].indexOf(s as string)}
				{@const currentIndex = ['community', 'skills', 'items'].indexOf(step)}
				{@const isDone = stepIndex < currentIndex}
				{@const isCurrent = stepIndex === currentIndex}
				<div class="progress-step {isDone ? 'done' : isCurrent ? 'current' : 'upcoming'}">
					<div class="step-circle">
						{#if isDone}
							<span class="check">✓</span>
						{:else}
							<span>{stepIndex + 1}</span>
						{/if}
					</div>
					<span class="step-label">{label}</span>
				</div>
				{#if stepIndex < 2}
					<div class="step-connector {isDone ? 'done' : ''}"></div>
				{/if}
			{/each}
		</div>
	{/if}

	<!-- ══════════════════════════════════════════ -->
	<!-- STEP 1: Community                          -->
	<!-- ══════════════════════════════════════════ -->
	{#if step === 'community'}
		<div class="step-content fade-in">
			<div class="onboarding-header">
				<h1>{$t('onboarding.title')}</h1>
				<p class="subtitle">
					{$t('onboarding.find_subtitle')}
				</p>
			</div>

			{#if error}
				<div class="alert alert-error fade-in">{error}</div>
			{/if}

			<form class="search-form" onsubmit={(e) => { e.preventDefault(); search(); }}>
				<div class="search-input-group">
					<input
						type="text"
						bind:value={query}
						placeholder="e.g. Kreuzberg, 10999, Berlin..."
						class="search-input"
					/>
					<button type="submit" class="btn-search" disabled={searching || !query.trim()}>
						{searching ? 'Searching...' : 'Search'}
					</button>
				</div>
			</form>

			{#if searched}
				<div class="results-section fade-in">
					{#if results.length > 0}
						<p class="results-count">{total} communit{total === 1 ? 'y' : 'ies'} found</p>
						<div class="results-list">
							{#each results as community (community.id)}
								<div class="community-card slide-up">
									<div class="card-info">
										<h3>{community.name}</h3>
										<div class="card-meta">
											<span class="tag">{community.postal_code}</span>
											<span class="tag">{community.city}</span>
											<span class="member-count">{community.member_count} member{community.member_count !== 1 ? 's' : ''}</span>
										</div>
										{#if community.description}
											<p class="card-desc">{community.description}</p>
										{/if}
									</div>
									<button
										class="btn-join"
										onclick={() => joinCommunity(community.id, community.name)}
										disabled={joining === community.id}
									>
										{joining === community.id ? 'Joining...' : 'Join'}
									</button>
								</div>
							{/each}
						</div>
					{:else}
						<div class="no-results">
							<p>No communities found for "{query}".</p>
							<p class="hint">Be the first to create one for your area!</p>
						</div>
					{/if}
				</div>
			{/if}

			<div class="divider"><span>or</span></div>

			{#if !showCreate}
				<button class="btn-create-toggle" onclick={() => (showCreate = true)}>
					Create a new community
				</button>
			{:else}
				<div class="create-form fade-in">
					<h2>Create a new community</h2>
					<form onsubmit={(e) => { e.preventDefault(); createCommunity(); }}>
						<label>
							<span>Community Name</span>
							<input type="text" bind:value={newName} required placeholder="e.g. Nachbarschaft Kreuzberg" />
						</label>
						<div class="form-row">
							<label class="flex-1">
								<span>Postal Code</span>
								<input type="text" bind:value={newPlz} required placeholder="e.g. 10999" />
							</label>
							<label class="flex-2">
								<span>City</span>
								<input type="text" bind:value={newCity} required placeholder="e.g. Berlin" />
							</label>
						</div>
						<label>
							<span>Description (optional)</span>
							<textarea bind:value={newDesc} rows="3" placeholder="What's this community about?"></textarea>
						</label>
						<div class="form-actions">
							<button type="button" class="btn-cancel" onclick={() => (showCreate = false)}>Cancel</button>
							<button
								type="submit"
								class="btn-primary"
								disabled={creating || !newName.trim() || !newPlz.trim() || !newCity.trim()}
							>
								{creating ? 'Creating...' : 'Create Community'}
							</button>
						</div>
					</form>
				</div>
			{/if}

			<div class="skip-section">
				<a href="/dashboard" class="skip-link">Skip for now</a>
			</div>
		</div>

	<!-- ══════════════════════════════════════════ -->
	<!-- STEP 2: Skills                             -->
	<!-- ══════════════════════════════════════════ -->
	{:else if step === 'skills'}
		<div class="step-content fade-in">
			<div class="onboarding-header">
				<h1>What are you good at?</h1>
				<p class="subtitle">
					No need to teach a class — just let neighbours know what you can help with.
				</p>
			</div>

			<div class="progress-counter">
				<div class="counter-dots">
					{#each [0, 1, 2] as i (i)}
						<div class="counter-dot {skillCount > i ? 'filled' : ''}"></div>
					{/each}
				</div>
				<p class="encouragement">{skillEncouragement(skillCount)}</p>
			</div>

			{#if skillsError}
				<div class="alert alert-error fade-in">{skillsError}</div>
			{/if}

			<div class="chip-grid">
				{#each skillSuggestions as s (s.label)}
					{@const isAdded = skillsAdded.has(s.label)}
					{@const isLoading = skillsLoading.has(s.label)}
					<button
						class="chip {isAdded ? 'added' : ''} {isLoading ? 'loading' : ''}"
						onclick={() => addSkill(s.label, s.category)}
						disabled={isAdded || isLoading}
					>
						{#if isAdded}<span class="chip-check">✓</span>{/if}
						{s.label}
					</button>
				{/each}
			</div>

			<div class="custom-add">
				<input
					type="text"
					bind:value={skillCustom}
					placeholder="Something else you're good at..."
					maxlength="200"
					onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCustomSkill(); } }}
				/>
				<button
					class="btn-add"
					onclick={addCustomSkill}
					disabled={!skillCustom.trim() || skillsAddingCustom || skillsAdded.has(skillCustom.trim())}
				>
					{skillsAddingCustom ? '...' : 'Add'}
				</button>
			</div>

			<div class="step-actions">
				<button class="btn-continue" onclick={() => (step = 'items')}>
					{skillCount >= 3 ? 'Continue →' : 'Continue — you can add more later'}
				</button>
			</div>
		</div>

	<!-- ══════════════════════════════════════════ -->
	<!-- STEP 3: Items                              -->
	<!-- ══════════════════════════════════════════ -->
	{:else if step === 'items'}
		<div class="step-content fade-in">
			<div class="onboarding-header">
				<h1>What do you have at home?</h1>
				<p class="subtitle">
					Just let people know it exists — no commitment to lend right now.
				</p>
			</div>

			<div class="progress-counter">
				<div class="counter-dots">
					{#each [0, 1, 2] as i (i)}
						<div class="counter-dot {itemCount > i ? 'filled' : ''}"></div>
					{/each}
				</div>
				<p class="encouragement">{itemEncouragement(itemCount)}</p>
			</div>

			{#if itemsError}
				<div class="alert alert-error fade-in">{itemsError}</div>
			{/if}

			<div class="chip-grid">
				{#each itemSuggestions as s (s.label)}
					{@const isAdded = itemsAdded.has(s.label)}
					{@const isLoading = itemsLoading.has(s.label)}
					<button
						class="chip {isAdded ? 'added' : ''} {isLoading ? 'loading' : ''}"
						onclick={() => addItem(s.label, s.category)}
						disabled={isAdded || isLoading}
					>
						{#if isAdded}<span class="chip-check">✓</span>{/if}
						{s.label}
					</button>
				{/each}
			</div>

			<div class="custom-add">
				<input
					type="text"
					bind:value={itemCustom}
					placeholder="Something else you could share..."
					maxlength="200"
					onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCustomItem(); } }}
				/>
				<button
					class="btn-add"
					onclick={addCustomItem}
					disabled={!itemCustom.trim() || itemsAddingCustom || itemsAdded.has(itemCustom.trim())}
				>
					{itemsAddingCustom ? '...' : 'Add'}
				</button>
			</div>

			<div class="step-actions">
				<button class="btn-continue" onclick={() => (step = 'done')}>
					{itemCount >= 3 ? 'Finish →' : 'Finish — you can add more later'}
				</button>
			</div>
		</div>

	<!-- ══════════════════════════════════════════ -->
	<!-- DONE: Celebration                          -->
	<!-- ══════════════════════════════════════════ -->
	{:else if step === 'done'}
		<div class="step-content done-screen fade-in">
			<div class="celebration-icon">🎉</div>
			<h1>You're all set!</h1>
			<p class="subtitle">
				You shared <strong>{skillCount} skill{skillCount !== 1 ? 's' : ''}</strong>
				and <strong>{itemCount} item{itemCount !== 1 ? 's' : ''}</strong>
				with <strong>{communityName}</strong>.
			</p>
			<p class="subtitle-muted">
				Your neighbours can now see what you bring to the community.
			</p>
			<div class="done-actions">
				<button class="btn-continue" onclick={() => goto(`/communities/${communityId}`)}>
					Go to your community →
				</button>
				<a href="/dashboard" class="skip-link">Go to dashboard</a>
			</div>
		</div>
	{/if}

</div>

<style>
	/* ── Layout ─────────────────────────────────────────── */
	.onboarding {
		max-width: 600px;
		margin: 0 auto;
	}

	.step-content {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	/* ── Progress steps bar ──────────────────────────────── */
	.progress-steps {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0;
		margin-bottom: 2rem;
	}

	.progress-step {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.3rem;
	}

	.step-circle {
		width: 2rem;
		height: 2rem;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.8rem;
		font-weight: 700;
		transition: all var(--transition);
	}

	.progress-step.done .step-circle {
		background: var(--color-primary);
		color: white;
	}

	.progress-step.current .step-circle {
		background: var(--color-primary);
		color: white;
		box-shadow: 0 0 0 3px var(--color-primary-light);
	}

	.progress-step.upcoming .step-circle {
		background: var(--color-surface);
		color: var(--color-text-muted);
		border: 2px solid var(--color-border);
	}

	.step-label {
		font-size: 0.7rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}

	.progress-step.done .step-label,
	.progress-step.current .step-label {
		color: var(--color-primary);
	}

	.progress-step.upcoming .step-label {
		color: var(--color-text-muted);
	}

	.step-connector {
		flex: 1;
		height: 2px;
		background: var(--color-border);
		min-width: 2.5rem;
		max-width: 5rem;
		margin-bottom: 1.35rem;
		transition: background var(--transition);
	}

	.step-connector.done {
		background: var(--color-primary);
	}

	/* ── Header ─────────────────────────────────────────── */
	.onboarding-header {
		text-align: center;
	}

	.onboarding-header h1 {
		font-size: 2rem;
		font-weight: 700;
		letter-spacing: -0.02em;
		margin-bottom: 0.5rem;
	}

	.subtitle {
		color: var(--color-text-muted);
		font-size: 1rem;
		line-height: 1.6;
	}

	/* ── Progress counter (skills/items steps) ───────────── */
	.progress-counter {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.85rem 1rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
	}

	.counter-dots {
		display: flex;
		gap: 0.4rem;
		flex-shrink: 0;
	}

	.counter-dot {
		width: 0.85rem;
		height: 0.85rem;
		border-radius: 50%;
		background: var(--color-border);
		transition: background var(--transition-spring), transform var(--transition-spring);
	}

	.counter-dot.filled {
		background: var(--color-primary);
		transform: scale(1.1);
	}

	.encouragement {
		font-size: 0.9rem;
		color: var(--color-text-muted);
		line-height: 1.4;
	}

	/* ── Suggestion chips ────────────────────────────────── */
	.chip-grid {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0.4rem 0.85rem;
		background: var(--color-surface);
		color: var(--color-text);
		border: 1px solid var(--color-border);
		border-radius: 999px;
		font-size: 0.88rem;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition-fast);
		white-space: nowrap;
		font-family: inherit;
	}

	.chip:hover:not(:disabled):not(.added) {
		background: var(--color-primary-light);
		border-color: var(--color-primary);
		color: var(--color-primary);
		transform: translateY(-1px);
		box-shadow: var(--shadow);
	}

	.chip.added {
		background: var(--color-primary);
		border-color: var(--color-primary);
		color: white;
		cursor: default;
		transform: scale(1.04);
	}

	.chip.loading {
		opacity: 0.6;
		cursor: wait;
	}

	.chip-check {
		font-size: 0.75rem;
		font-weight: 700;
	}

	/* ── Custom add row ──────────────────────────────────── */
	.custom-add {
		display: flex;
		gap: 0.5rem;
	}

	.custom-add input {
		flex: 1;
		padding: 0.6rem 0.9rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.92rem;
		background: var(--color-surface);
		color: var(--color-text);
		font-family: inherit;
		transition: border-color var(--transition-fast);
	}

	.custom-add input:focus {
		outline: none;
		border-color: var(--color-primary);
		box-shadow: 0 0 0 3px var(--color-primary-light);
	}

	.btn-add {
		padding: 0.6rem 1.1rem;
		background: var(--color-surface);
		color: var(--color-primary);
		border: 1px solid var(--color-primary);
		border-radius: var(--radius);
		font-size: 0.88rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
		white-space: nowrap;
		font-family: inherit;
	}

	.btn-add:hover:not(:disabled) {
		background: var(--color-primary-light);
	}

	.btn-add:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}

	/* ── Step navigation ────────────────────────────────── */
	.step-actions {
		margin-top: 0.5rem;
	}

	.btn-continue {
		width: 100%;
		padding: 0.85rem 1.5rem;
		background: var(--color-primary);
		color: white;
		border: none;
		border-radius: var(--radius);
		font-size: 1rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
		font-family: inherit;
	}

	.btn-continue:hover {
		background: var(--color-primary-hover);
		box-shadow: var(--shadow-md);
		transform: translateY(-1px);
	}

	/* ── Completion / done screen ───────────────────────── */
	.done-screen {
		text-align: center;
		padding-top: 2rem;
		gap: 1rem;
	}

	.celebration-icon {
		font-size: 3.5rem;
		line-height: 1;
	}

	.done-screen h1 {
		font-size: 2.2rem;
		font-weight: 700;
		letter-spacing: -0.02em;
	}

	.subtitle-muted {
		font-size: 0.95rem;
		color: var(--color-text-subtle);
		line-height: 1.5;
	}

	.done-actions {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
		margin-top: 1rem;
	}

	.done-actions .btn-continue {
		max-width: 300px;
	}

	/* ── Community search (step 1) ──────────────────────── */
	.search-form {
		margin: 0;
	}

	.search-input-group {
		display: flex;
		gap: 0.5rem;
	}

	.search-input {
		flex: 1;
		padding: 0.65rem 1rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 1rem;
		background: var(--color-surface);
		color: var(--color-text);
		font-family: inherit;
		transition: border-color var(--transition-fast);
	}

	.search-input:focus {
		outline: none;
		border-color: var(--color-primary);
		box-shadow: 0 0 0 3px var(--color-primary-light);
	}

	.btn-search {
		padding: 0.65rem 1.25rem;
		background: var(--color-primary);
		color: white;
		border: none;
		border-radius: var(--radius);
		font-size: 0.95rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
		white-space: nowrap;
		font-family: inherit;
	}

	.btn-search:hover:not(:disabled) {
		background: var(--color-primary-hover);
		box-shadow: var(--shadow-md);
	}

	.btn-search:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.results-section {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.results-count {
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.results-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.community-card {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 1rem 1.25rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		transition: all var(--transition-fast);
	}

	.community-card:hover {
		border-color: var(--color-border-hover);
		box-shadow: var(--shadow-md);
	}

	.card-info h3 {
		font-size: 1rem;
		font-weight: 600;
		margin-bottom: 0.35rem;
	}

	.card-meta {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.tag {
		font-size: 0.75rem;
		font-weight: 500;
		padding: 0.15rem 0.5rem;
		border-radius: 999px;
		background: var(--color-primary-light);
		color: var(--color-primary);
	}

	.member-count {
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	.card-desc {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		margin-top: 0.35rem;
		line-height: 1.5;
	}

	.btn-join {
		padding: 0.5rem 1.25rem;
		background: var(--color-primary);
		color: white;
		border: none;
		border-radius: var(--radius);
		font-size: 0.88rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
		white-space: nowrap;
		flex-shrink: 0;
		font-family: inherit;
	}

	.btn-join:hover:not(:disabled) {
		background: var(--color-primary-hover);
		transform: translateY(-1px);
		box-shadow: var(--shadow);
	}

	.btn-join:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.no-results {
		text-align: center;
		padding: 1.5rem;
		background: var(--color-surface);
		border: 1px dashed var(--color-border);
		border-radius: var(--radius-lg);
	}

	.no-results p {
		margin-bottom: 0.25rem;
	}

	.hint {
		color: var(--color-text-muted);
		font-size: 0.9rem;
	}

	.divider {
		display: flex;
		align-items: center;
		gap: 1rem;
		color: var(--color-text-muted);
		font-size: 0.85rem;
	}

	.divider::before,
	.divider::after {
		content: '';
		flex: 1;
		height: 1px;
		background: var(--color-border);
	}

	.btn-create-toggle {
		width: 100%;
		padding: 0.75rem;
		background: var(--color-surface);
		color: var(--color-primary);
		border: 1px dashed var(--color-primary);
		border-radius: var(--radius);
		font-size: 0.95rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
		font-family: inherit;
	}

	.btn-create-toggle:hover {
		background: var(--color-primary-light);
	}

	.create-form {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 1.5rem;
	}

	.create-form h2 {
		font-size: 1.15rem;
		font-weight: 600;
		margin-bottom: 1rem;
	}

	.create-form form {
		display: flex;
		flex-direction: column;
		gap: 0.85rem;
	}

	.create-form label {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}

	.create-form label span {
		font-size: 0.82rem;
		font-weight: 500;
		color: var(--color-text-muted);
	}

	.create-form input,
	.create-form textarea {
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		font-size: 0.95rem;
		background: var(--color-bg);
		color: var(--color-text);
		font-family: inherit;
	}

	.create-form input:focus,
	.create-form textarea:focus {
		outline: none;
		border-color: var(--color-primary);
		box-shadow: 0 0 0 3px var(--color-primary-light);
	}

	.form-row {
		display: flex;
		gap: 0.75rem;
	}

	.flex-1 { flex: 1; }
	.flex-2 { flex: 2; }

	.form-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.5rem;
		margin-top: 0.5rem;
	}

	.btn-cancel {
		padding: 0.5rem 1rem;
		background: none;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		color: var(--color-text-muted);
		font-size: 0.88rem;
		cursor: pointer;
		transition: all var(--transition-fast);
		font-family: inherit;
	}

	.btn-cancel:hover {
		border-color: var(--color-text-muted);
	}

	.btn-primary {
		padding: 0.5rem 1.25rem;
		background: var(--color-primary);
		color: white;
		border: none;
		border-radius: var(--radius);
		font-size: 0.88rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
		font-family: inherit;
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--color-primary-hover);
	}

	.btn-primary:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	/* ── Alerts ─────────────────────────────────────────── */
	.alert {
		padding: 0.65rem 1rem;
		border-radius: var(--radius);
		font-size: 0.9rem;
	}

	.alert-error {
		background: var(--color-error-bg);
		color: var(--color-error);
		border: 1px solid var(--color-error);
	}

	/* ── Skip link ──────────────────────────────────────── */
	.skip-section {
		text-align: center;
		padding-top: 0.5rem;
	}

	.skip-link {
		font-size: 0.88rem;
		color: var(--color-text-muted);
		text-decoration: none;
		transition: color var(--transition-fast);
	}

	.skip-link:hover {
		color: var(--color-primary);
	}

	/* ── Check icon (global needed for :global in Svelte 5) ─ */
	.check {
		font-weight: 700;
	}
</style>
