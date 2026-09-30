<script lang="ts">
  import type { CrisisStatus } from '$lib/types';
  import { t } from 'svelte-i18n';

  let {
    communityId,
    crisisStatus,
    isMember,
    isAdmin,
    votingCrisis = false,
    togglingCrisis = false,
    showToggle = false,
    onvote,
    ontoggle,
  }: {
    communityId: number;
    crisisStatus: CrisisStatus;
    isMember: boolean;
    isAdmin: boolean;
    votingCrisis?: boolean;
    togglingCrisis?: boolean;
    showToggle?: boolean;
    onvote: (voteType: string) => void;
    ontoggle: (newMode: string) => void;
  } = $props();

  // What the community behaves as (red whenever the instance is red); toggles
  // and votes act on the stored mode underneath
  const effectiveMode = $derived(crisisStatus.effective_mode ?? crisisStatus.mode);
</script>

<section class="card crisis-section slide-up">
  <div class="crisis-header">
    <div class="crisis-indicator" class:crisis-red={effectiveMode === 'red'}>
      <span class="crisis-dot"></span>
      <span class="crisis-label">
        {effectiveMode === 'red' ? 'Red Sky (Crisis)' : 'Blue Sky (Normal)'}
      </span>
    </div>
    {#if showToggle && isAdmin}
      {#if crisisStatus.mode === 'blue'}
        <button class="btn btn-danger" class:is-loading={togglingCrisis} onclick={() => ontoggle('red')} disabled={togglingCrisis}>
          {togglingCrisis ? 'Activating...' : 'Activate Crisis Mode'}
        </button>
      {:else}
        <button class="btn btn-primary" class:is-loading={togglingCrisis} onclick={() => ontoggle('blue')} disabled={togglingCrisis}>
          {togglingCrisis ? 'Deactivating...' : 'Deactivate Crisis Mode'}
        </button>
      {/if}
    {/if}
  </div>

  {#if crisisStatus.instance_red}
    <p class="alert alert-error instance-red-note" role="note">
      {$t('crisis.instance_red_notice', {
        values: { mode: crisisStatus.mode === 'red' ? $t('crisis.mode_red') : $t('crisis.mode_blue') }
      })}
    </p>
  {/if}

  {#if isMember && !showToggle}
    <div class="vote-section">
      <div class="vote-bar">
        <div class="vote-info">
          <span>Activate votes: <strong>{crisisStatus.votes_to_activate}</strong></span>
          <span>Deactivate votes: <strong>{crisisStatus.votes_to_deactivate}</strong></span>
          <span class="vote-threshold">Threshold: {crisisStatus.threshold_pct}% of {crisisStatus.total_members} members</span>
        </div>
        <div class="vote-actions">
          <!-- Only the vote that can change the stored mode ("activate" while red is a no-op) -->
          {#if crisisStatus.mode !== 'red'}
            <button class="btn btn-danger btn-sm" class:is-loading={votingCrisis} onclick={() => onvote('activate')} disabled={votingCrisis}>
              Vote to Activate
            </button>
          {:else}
            <button class="btn btn-primary btn-sm" class:is-loading={votingCrisis} onclick={() => onvote('deactivate')} disabled={votingCrisis}>
              Vote to Deactivate
            </button>
          {/if}
        </div>
      </div>
    </div>
  {/if}
</section>

<style>
  .instance-red-note {
    margin: 0.75rem 0 0;
  }
  .crisis-section {
    margin-bottom: 1rem;
  }
  .crisis-red {
    border-inline-start: 3px solid var(--color-error);
    padding-inline-start: 0.75rem;
  }
  .crisis-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 1rem;
  }
  .crisis-indicator {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .crisis-dot {
    width: 0.6rem;
    height: 0.6rem;
    border-radius: 50%;
    background: var(--color-success);
  }
  .crisis-red .crisis-dot {
    background: var(--color-error);
  }
  .crisis-label {
    font-size: 0.88rem;
    font-weight: 600;
  }
  .vote-section {
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--color-border);
  }
  .vote-bar {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .vote-info {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    font-size: 0.85rem;
    color: var(--color-text-muted);
  }
  .vote-threshold {
    font-style: italic;
  }
  .vote-actions {
    display: flex;
    gap: 0.5rem;
  }
</style>
