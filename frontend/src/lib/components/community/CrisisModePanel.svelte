<script lang="ts">
  import type { CrisisStatus } from '$lib/types';

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
</script>

<section class="crisis-section slide-up">
  <div class="crisis-header">
    <div class="crisis-indicator" class:crisis-red={crisisStatus.mode === 'red'}>
      <span class="crisis-dot"></span>
      <span class="crisis-label">
        {crisisStatus.mode === 'red' ? 'Red Sky (Crisis)' : 'Blue Sky (Normal)'}
      </span>
    </div>
    {#if showToggle && isAdmin}
      {#if crisisStatus.mode === 'blue'}
        <button class="btn-crisis-activate" onclick={() => ontoggle('red')} disabled={togglingCrisis}>
          {togglingCrisis ? 'Activating...' : 'Activate Crisis Mode'}
        </button>
      {:else}
        <button class="btn-crisis-deactivate" onclick={() => ontoggle('blue')} disabled={togglingCrisis}>
          {togglingCrisis ? 'Deactivating...' : 'Deactivate Crisis Mode'}
        </button>
      {/if}
    {/if}
  </div>

  {#if isMember && !showToggle}
    <div class="vote-section">
      <div class="vote-bar">
        <div class="vote-info">
          <span>Activate votes: <strong>{crisisStatus.votes_to_activate}</strong></span>
          <span>Deactivate votes: <strong>{crisisStatus.votes_to_deactivate}</strong></span>
          <span class="vote-threshold">Threshold: {crisisStatus.threshold_pct}% of {crisisStatus.total_members} members</span>
        </div>
        <div class="vote-actions">
          <button class="btn-vote btn-vote-red" onclick={() => onvote('activate')} disabled={votingCrisis}>
            Vote to Activate
          </button>
          <button class="btn-vote btn-vote-blue" onclick={() => onvote('deactivate')} disabled={votingCrisis}>
            Vote to Deactivate
          </button>
        </div>
      </div>
    </div>
  {/if}
</section>

<style>
  .crisis-section {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: 1.25rem;
    margin-bottom: 1rem;
  }
  .crisis-red {
    border-left: 3px solid var(--color-error);
  }
  .crisis-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
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
  .btn-vote {
    padding: 0.4rem 0.9rem;
    border: none;
    border-radius: var(--radius);
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    transition: all var(--transition-fast);
    font-family: inherit;
  }
  .btn-vote:disabled { opacity: 0.6; cursor: not-allowed; }
  .btn-vote-red { background: var(--color-error); color: white; }
  .btn-vote-blue { background: var(--color-primary); color: white; }
  .btn-crisis-activate {
    padding: 0.45rem 0.9rem;
    background: var(--color-error);
    color: white;
    border: none;
    border-radius: var(--radius);
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    transition: all var(--transition-fast);
    font-family: inherit;
  }
  .btn-crisis-activate:disabled { opacity: 0.6; cursor: not-allowed; }
  .btn-crisis-deactivate {
    padding: 0.45rem 0.9rem;
    background: var(--color-primary);
    color: white;
    border: none;
    border-radius: var(--radius);
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    transition: all var(--transition-fast);
    font-family: inherit;
  }
  .btn-crisis-deactivate:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
