<script lang="ts">
  import type { InviteOut } from '$lib/types';
  import { t } from 'svelte-i18n';

  let {
    communityId,
    invites,
    onrefresh,
  }: {
    communityId: number;
    invites: InviteOut[];
    onrefresh: () => void;
  } = $props();

  import { api } from '$lib/api';

  let showForm = $state(false);
  let maxUses = $state('');
  let expiresHours = $state('');
  let creating = $state(false);
  let error = $state('');
  let copiedCode = $state('');

  async function createInvite() {
    creating = true;
    error = '';
    try {
      const body: Record<string, unknown> = { community_id: communityId };
      if (maxUses) body.max_uses = Number(maxUses);
      if (expiresHours) body.expires_in_hours = Number(expiresHours);
      await api('/invites', { method: 'POST', auth: true, body });
      showForm = false;
      maxUses = '';
      expiresHours = '';
      onrefresh();
    } catch (err) {
      error = err instanceof Error ? err.message : $t('communities.invites.create_failed');
    } finally {
      creating = false;
    }
  }

  async function revokeInvite(inviteId: number) {
    try {
      await api(`/invites/${inviteId}`, { method: 'DELETE', auth: true });
      onrefresh();
    } catch (err) {
      error = err instanceof Error ? err.message : $t('communities.invites.revoke_failed');
    }
  }

  function copyLink(code: string) {
    const url = `${window.location.origin}/invites/${code}`;
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(url).then(
        () => {
          copiedCode = code;
          setTimeout(() => { copiedCode = ''; }, 2000);
        },
        () => window.prompt($t('communities.invites.copy_prompt'), url)
      );
    } else {
      // The Clipboard API needs a secure context; plain-http instances fall back to a prompt
      window.prompt($t('communities.invites.copy_prompt'), url);
    }
  }

  function formatExpiry(expiresAt: string | null): string {
    if (!expiresAt) return $t('communities.invites.never');
    const d = new Date(expiresAt);
    if (d < new Date()) return $t('communities.invites.expired');
    return d.toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
</script>

<section class="invites-section slide-up">
  <div class="section-header">
    <h2>{$t('communities.invites.title')}</h2>
    <button class="btn-small" onclick={() => (showForm = !showForm)}>
      {showForm ? $t('common.cancel') : $t('communities.invites.create')}
    </button>
  </div>

  {#if error}
    <div class="alert alert-error">{error}</div>
  {/if}

  {#if showForm}
    <div class="invite-form fade-in">
      <div class="invite-form-row">
        <label>
          <span>{$t('communities.invites.max_uses')}</span>
          <input type="number" min="1" bind:value={maxUses} placeholder={$t('communities.invites.unlimited')} />
        </label>
        <label>
          <span>{$t('communities.invites.expires_hours')}</span>
          <input type="number" min="1" bind:value={expiresHours} placeholder={$t('communities.invites.never')} />
        </label>
      </div>
      <button class="btn-primary" onclick={createInvite} disabled={creating}>
        {creating ? $t('communities.invites.creating') : $t('communities.invites.generate')}
      </button>
    </div>
  {/if}

  {#if invites.length === 0}
    <p class="section-hint">{$t('communities.invites.none')}</p>
  {:else}
    <div class="invites-list">
      {#each invites as inv (inv.id)}
        <div class="invite-row">
          <div class="invite-info">
            <code class="invite-code">{inv.code.slice(0, 12)}...</code>
            <span class="invite-meta">
              {$t('communities.invites.usage', { values: { uses: `${inv.use_count}${inv.max_uses ? `/${inv.max_uses}` : ''}`, expires: formatExpiry(inv.expires_at) } })}
            </span>
          </div>
          <div class="invite-actions">
            <button class="btn-small" onclick={() => copyLink(inv.code)}>
              {copiedCode === inv.code ? $t('communities.invites.copied') : $t('communities.invites.copy')}
            </button>
            <button class="btn-small btn-small-danger" onclick={() => revokeInvite(inv.id)}>
              {$t('communities.invites.revoke')}
            </button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</section>

<style>
  .invites-section {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    padding: 1.25rem;
    margin-bottom: 1rem;
  }
  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1rem;
  }
  .section-header h2 {
    font-size: 1.05rem;
    font-weight: 500;
    margin: 0;
  }
  .invite-form {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-bottom: 1rem;
    padding: 1rem;
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
  }
  .invite-form-row {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
  }
  .invite-form label {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    flex: 1;
    min-width: 140px;
  }
  .invite-form label span {
    font-size: 0.8rem;
    font-weight: 500;
    color: var(--color-text-muted);
  }
  .invite-form input {
    padding: 0.4rem 0.65rem;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    font-size: 0.9rem;
    background: var(--color-surface);
    color: var(--color-text);
    font-family: inherit;
  }
  .invites-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .invite-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.6rem 0.75rem;
    background: var(--color-bg);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    flex-wrap: wrap;
  }
  .invite-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
  }
  .invite-code {
    font-size: 0.82rem;
    background: var(--color-surface);
    padding: 0.15rem 0.4rem;
    border-radius: 4px;
    border: 1px solid var(--color-border);
  }
  .invite-meta {
    font-size: 0.78rem;
    color: var(--color-text-muted);
  }
  .invite-actions {
    display: flex;
    gap: 0.4rem;
  }
  .section-hint {
    color: var(--color-text-muted);
    font-size: 0.88rem;
    font-style: italic;
  }
  .alert {
    padding: 0.6rem 0.9rem;
    border-radius: var(--radius);
    font-size: 0.88rem;
    margin-bottom: 0.75rem;
  }
  .alert-error {
    background: var(--color-error-bg);
    color: var(--color-error);
    border: 1px solid var(--color-error);
  }
  .btn-primary {
    padding: 0.5rem 1.1rem;
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
  .btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
  .btn-small {
    padding: 0.3rem 0.75rem;
    font-size: 0.8rem;
    font-weight: 600;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-surface);
    color: var(--color-text);
    cursor: pointer;
    transition: all var(--transition-fast);
    font-family: inherit;
    white-space: nowrap;
  }
  .btn-small:hover { background: var(--color-bg); }
  .btn-small-danger {
    color: var(--color-error);
    border-color: var(--color-error);
  }
  .btn-small-danger:hover { background: var(--color-error-bg); }
</style>
