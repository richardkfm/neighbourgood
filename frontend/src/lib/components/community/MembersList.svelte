<script lang="ts">
  import { t } from 'svelte-i18n';
  import type { CommunityMember, UserInfo } from '$lib/types';
  import Icon from '$lib/components/Icon.svelte';

  let {
    members,
    isAdmin,
    currentUserId,
    promotingUser = null,
    onpromote,
    ondemote,
    onmakeadmin,
  }: {
    members: CommunityMember[];
    isAdmin: boolean;
    currentUserId: number | null;
    promotingUser?: number | null;
    onpromote: (userId: number) => void;
    ondemote: (userId: number) => void;
    onmakeadmin: (userId: number) => void;
  } = $props();
</script>

<section class="card members-section slide-up">
  <h2>Members</h2>
  <div class="members-list">
    {#each members as m (m.id)}
      <div class="member-row">
        <div class="member-info">
          <span class="member-name">{m.user.display_name}</span>
          {#if m.role === 'admin'}
            <span class="badge badge-primary badge-caps">Admin</span>
          {:else if m.role === 'leader'}
            <span class="badge badge-warning badge-caps">Leader</span>
          {/if}
        </div>
        <div class="member-right">
          {#if isAdmin && m.user.id !== currentUserId && m.role !== 'admin'}
            {#if m.role === 'leader'}
              <button class="btn btn-secondary btn-sm" onclick={() => ondemote(m.user.id)} disabled={promotingUser === m.user.id}>
                Demote
              </button>
            {:else}
              <button class="btn btn-secondary btn-sm" onclick={() => onpromote(m.user.id)} disabled={promotingUser === m.user.id}>
                Make Leader
              </button>
            {/if}
            <button class="btn btn-secondary btn-sm" onclick={() => onmakeadmin(m.user.id)} disabled={promotingUser === m.user.id}>
              <Icon name="shield" size={14} />{$t('communities.make_admin')}
            </button>
          {/if}
          <span class="member-date">Joined {new Date(m.joined_at).toLocaleDateString()}</span>
        </div>
      </div>
    {/each}
  </div>
</section>

<style>
  .members-section {
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
    flex-wrap: wrap;
    gap: 0.5rem 0.75rem;
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
  .member-right {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  .member-date {
    font-size: 0.78rem;
    color: var(--color-text-muted);
  }
</style>
