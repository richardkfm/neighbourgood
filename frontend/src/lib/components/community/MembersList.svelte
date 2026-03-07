<script lang="ts">
  import type { CommunityMember, UserInfo } from '$lib/types';

  let {
    members,
    isAdmin,
    currentUserId,
    promotingUser = null,
    onpromote,
    ondemote,
  }: {
    members: CommunityMember[];
    isAdmin: boolean;
    currentUserId: number | null;
    promotingUser?: number | null;
    onpromote: (userId: number) => void;
    ondemote: (userId: number) => void;
  } = $props();
</script>

<section class="members-section slide-up">
  <h2>Members</h2>
  <div class="members-list">
    {#each members as m (m.id)}
      <div class="member-row">
        <div class="member-info">
          <span class="member-name">{m.user.display_name}</span>
          {#if m.role === 'admin'}
            <span class="role-badge">Admin</span>
          {:else if m.role === 'leader'}
            <span class="role-badge role-badge-leader">Leader</span>
          {/if}
        </div>
        <div class="member-right">
          {#if isAdmin && m.user.id !== currentUserId && m.role !== 'admin'}
            {#if m.role === 'leader'}
              <button class="btn-tiny" onclick={() => ondemote(m.user.id)} disabled={promotingUser === m.user.id}>
                Demote
              </button>
            {:else}
              <button class="btn-tiny" onclick={() => onpromote(m.user.id)} disabled={promotingUser === m.user.id}>
                Make Leader
              </button>
            {/if}
          {/if}
          <span class="member-date">Joined {new Date(m.joined_at).toLocaleDateString()}</span>
        </div>
      </div>
    {/each}
  </div>
</section>

<style>
  .members-section {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: 1.25rem;
    margin-bottom: 1rem;
  }
  .members-section h2 {
    font-size: 1.05rem;
    font-weight: 500;
    margin-bottom: 1rem;
  }
  .members-list {
    display: flex;
    flex-direction: column;
    gap: 0;
  }
  .member-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.65rem 0;
    border-bottom: 1px solid var(--color-border);
  }
  .member-row:last-child { border-bottom: none; }
  .member-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .member-name { font-size: 0.92rem; font-weight: 500; }
  .role-badge {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 0.15rem 0.45rem;
    border-radius: 999px;
    background: var(--color-primary-light);
    color: var(--color-primary);
  }
  .role-badge-leader {
    background: #fef3c7;
    color: #92400e;
  }
  .member-right {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .member-date {
    font-size: 0.78rem;
    color: var(--color-text-muted);
  }
  .btn-tiny {
    padding: 0.2rem 0.55rem;
    font-size: 0.75rem;
    font-weight: 600;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-surface);
    color: var(--color-text);
    cursor: pointer;
    transition: all var(--transition-fast);
    font-family: inherit;
  }
  .btn-tiny:hover:not(:disabled) {
    background: var(--color-primary-light);
    border-color: var(--color-primary);
    color: var(--color-primary);
  }
  .btn-tiny:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
