<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { api } from '$lib/api';
  import { isLoggedIn, user } from '$lib/stores/auth';

  interface Ticket {
    id: number;
    community_id: number;
    author: { id: number; display_name: string };
    ticket_type: string;
    title: string;
    description: string;
    status: string;
    urgency: string;
    due_at: string | null;
    triage_score?: number;
    assigned_to: { id: number; display_name: string } | null;
    created_at: string;
    updated_at: string;
  }

  interface Comment {
    id: number;
    ticket_id: number;
    author: { id: number; display_name: string };
    body: string;
    created_at: string;
    updated_at: string;
  }

  interface MemberInfo {
    user: { id: number; display_name: string };
    role: string;
  }

  let ticket = $state<Ticket | null>(null);
  let comments = $state<Comment[]>([]);
  let members = $state<MemberInfo[]>([]);

  let loading = $state(true);
  let error = $state('');
  let commentText = $state('');
  let postingComment = $state(false);
  let commentError = $state('');
  let updatingTicket = $state(false);
  let assigneeId = $state<number | null>(null);

  const ticketId = $derived($page.params.id);
  const communityId = $derived($page.url.searchParams.get('community') ?? '');

  const currentUserMember = $derived(
    members.find((m) => m.user.id === $user?.id) ?? null
  );

  const currentUserRole = $derived(currentUserMember?.role ?? 'member');

  const isPrivileged = $derived(
    currentUserRole === 'admin' || currentUserRole === 'leader'
  );

  const canControlStatus = $derived(
    ticket !== null &&
      (ticket.author.id === $user?.id ||
        isPrivileged ||
        (ticket.assigned_to !== null && ticket.assigned_to.id === $user?.id))
  );

  function urgencyColor(urgency: string): string {
    switch (urgency) {
      case 'critical':
        return 'var(--color-error)';
      case 'high':
        return 'var(--color-warning)';
      case 'medium':
        return 'var(--color-primary)';
      default:
        return 'var(--color-text-muted)';
    }
  }

  function statusColor(status: string): string {
    switch (status) {
      case 'open':
        return 'var(--color-warning)';
      case 'in_progress':
        return 'var(--color-primary)';
      case 'resolved':
        return 'var(--color-success)';
      default:
        return 'var(--color-text-muted)';
    }
  }

  function formatLabel(value: string): string {
    return value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function formatDate(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
  }

  async function loadAll() {
    if (!communityId) {
      error = 'Missing community parameter.';
      loading = false;
      return;
    }
    try {
      const [t, c, m] = await Promise.all([
        api<Ticket>(`/communities/${communityId}/tickets/${ticketId}`, { auth: true }),
        api<Comment[]>(`/communities/${communityId}/tickets/${ticketId}/comments`, { auth: true }),
        api<MemberInfo[]>(`/communities/${communityId}/members`, { auth: true })
      ]);
      ticket = t;
      comments = c;
      members = m;
      assigneeId = t.assigned_to?.id ?? null;
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : 'Failed to load ticket.';
    } finally {
      loading = false;
    }
  }

  async function patchTicket(body: Record<string, unknown>) {
    if (!ticket) return;
    updatingTicket = true;
    try {
      const updated = await api<Ticket>(
        `/communities/${communityId}/tickets/${ticket.id}`,
        { method: 'PATCH', body, auth: true }
      );
      ticket = updated;
      assigneeId = updated.assigned_to?.id ?? null;
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : 'Failed to update ticket.';
    } finally {
      updatingTicket = false;
    }
  }

  async function setStatus(status: string) {
    await patchTicket({ status });
  }

  async function selfAssign() {
    if (!$user) return;
    await patchTicket({ assigned_to_id: $user.id });
  }

  async function assignMember() {
    if (assigneeId === null) return;
    await patchTicket({ assigned_to_id: assigneeId });
  }

  async function postComment() {
    if (!commentText.trim()) return;
    postingComment = true;
    commentError = '';
    try {
      const newComment = await api<Comment>(
        `/communities/${communityId}/tickets/${ticketId}/comments`,
        { method: 'POST', body: { body: commentText.trim() }, auth: true }
      );
      comments = [...comments, newComment];
      commentText = '';
    } catch (e: unknown) {
      commentError = e instanceof Error ? e.message : 'Failed to post comment.';
    } finally {
      postingComment = false;
    }
  }

  onMount(() => {
    if (!$isLoggedIn) {
      goto('/login');
      return;
    }
    loadAll();
  });
</script>

<main class="page-container">
  <nav class="breadcrumb">
    <a href="/triage">← Back to Emergency</a>
  </nav>

  {#if loading}
    <p class="loading-msg">Loading ticket…</p>
  {:else if error && !ticket}
    <p class="error-msg">{error}</p>
  {:else if ticket}
    <!-- Ticket header -->
    <header class="ticket-header">
      <div class="header-meta">
        <span
          class="badge urgency-badge"
          style="background-color: {urgencyColor(ticket.urgency)};"
        >
          {formatLabel(ticket.urgency)}
        </span>
        <span
          class="badge status-badge"
          style="background-color: {statusColor(ticket.status)};"
        >
          {formatLabel(ticket.status)}
        </span>
        <span class="type-label">{formatLabel(ticket.ticket_type)}</span>
      </div>
      <h1 class="ticket-title">{ticket.title}</h1>
      <p class="ticket-byline">
        Opened by <strong>{ticket.author.display_name}</strong> on {formatDate(ticket.created_at)}
      </p>
    </header>

    {#if error}
      <p class="error-msg inline-error">{error}</p>
    {/if}

    <!-- Description -->
    <section class="card description-card">
      <h2 class="section-heading">Description</h2>
      <p class="description-body">{ticket.description}</p>
      {#if ticket.due_at}
        <p class="due-at">
          Due: <strong>{formatDate(ticket.due_at)}</strong>
        </p>
      {/if}
      {#if ticket.triage_score !== undefined}
        <p class="triage-score">Triage score: <strong>{ticket.triage_score}</strong></p>
      {/if}
    </section>

    <!-- Assignment panel -->
    <section class="card assignment-card">
      <h2 class="section-heading">Assignment</h2>
      <div class="assignment-row">
        <div class="assignee-info">
          {#if ticket.assigned_to}
            <span class="assignee-name">{ticket.assigned_to.display_name}</span>
          {:else}
            <span class="unassigned">Unassigned</span>
          {/if}
        </div>

        <div class="assignment-actions">
          {#if !ticket.assigned_to || ticket.assigned_to.id !== $user?.id}
            <button
              class="btn btn-secondary"
              onclick={selfAssign}
              disabled={updatingTicket}
            >
              Take this
            </button>
          {/if}

          {#if isPrivileged}
            <div class="assign-form">
              <select bind:value={assigneeId} class="member-select">
                <option value={null}>— select member —</option>
                {#each members as m (m.user.id)}
                  <option value={m.user.id}>{m.user.display_name}</option>
                {/each}
              </select>
              <button
                class="btn btn-primary"
                onclick={assignMember}
                disabled={updatingTicket || assigneeId === null}
              >
                Assign
              </button>
            </div>
          {/if}
        </div>
      </div>
    </section>

    <!-- Status controls -->
    {#if canControlStatus}
      <section class="card status-card">
        <h2 class="section-heading">Actions</h2>
        <div class="status-actions">
          {#if ticket.status === 'open'}
            <button
              class="btn btn-primary"
              onclick={() => setStatus('in_progress')}
              disabled={updatingTicket}
            >
              Start
            </button>
            <button
              class="btn btn-success"
              onclick={() => setStatus('resolved')}
              disabled={updatingTicket}
            >
              Close
            </button>
          {:else if ticket.status === 'in_progress'}
            <button
              class="btn btn-success"
              onclick={() => setStatus('resolved')}
              disabled={updatingTicket}
            >
              Close
            </button>
            <button
              class="btn btn-secondary"
              onclick={() => setStatus('open')}
              disabled={updatingTicket}
            >
              Reopen
            </button>
          {:else if ticket.status === 'resolved'}
            <button
              class="btn btn-secondary"
              onclick={() => setStatus('open')}
              disabled={updatingTicket}
            >
              Reopen
            </button>
          {/if}
        </div>
      </section>
    {/if}

    <!-- Discussion -->
    <section class="discussion-section">
      <h2 class="section-heading discussion-heading">Discussion</h2>

      {#if comments.length === 0}
        <p class="no-comments">No comments yet. Be the first to respond.</p>
      {:else}
        <ol class="comment-list">
          {#each comments as comment (comment.id)}
            <li class="comment-item">
              <div class="comment-header">
                <span class="comment-author">{comment.author.display_name}</span>
                <time class="comment-time">{formatDate(comment.created_at)}</time>
              </div>
              <p class="comment-body">{comment.body}</p>
            </li>
          {/each}
        </ol>
      {/if}

      <!-- Add comment form -->
      <div class="card comment-form-card">
        <h3 class="form-label">Add a comment</h3>
        {#if commentError}
          <p class="error-msg">{commentError}</p>
        {/if}
        <textarea
          class="comment-textarea"
          bind:value={commentText}
          placeholder="Write your response here…"
          rows={4}
          maxlength={5000}
        ></textarea>
        <div class="form-footer">
          <button
            class="btn btn-primary"
            onclick={postComment}
            disabled={postingComment || !commentText.trim()}
          >
            {postingComment ? 'Posting…' : 'Post Comment'}
          </button>
        </div>
      </div>
    </section>
  {/if}
</main>

<style>
  .page-container {
    max-width: 900px;
  }

  /* Breadcrumb */
  .breadcrumb {
    margin-bottom: 1.5rem;
  }

  .breadcrumb a {
    color: var(--color-text-muted);
    text-decoration: none;
    font-size: 0.9rem;
    transition: color var(--transition-fast);
  }

  .breadcrumb a:hover {
    color: var(--color-primary);
  }

  /* State messages */
  .loading-msg {
    color: var(--color-text-muted);
    text-align: center;
    padding: 3rem 0;
  }

  .error-msg {
    color: var(--color-error);
    font-size: 0.9rem;
    margin-bottom: 1rem;
  }

  .inline-error {
    margin-bottom: 1rem;
  }

  /* Header */
  .ticket-header {
    margin-bottom: 1.5rem;
  }

  .header-meta {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-bottom: 0.75rem;
  }

  .badge {
    display: inline-block;
    padding: 0.2rem 0.65rem;
    border-radius: var(--radius-sm);
    font-size: 0.75rem;
    font-weight: 600;
    color: #fff;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .type-label {
    font-size: 0.8rem;
    color: var(--color-text-muted);
    font-style: italic;
  }

  .ticket-title {
    font-size: 1.9rem;
    font-weight: 400;
    color: var(--color-text);
    margin: 0 0 0.5rem;
    line-height: 1.25;
  }

  .ticket-byline {
    font-size: 0.875rem;
    color: var(--color-text-muted);
    margin: 0;
  }

  /* Cards */
  .card {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.25rem;
  }

  .section-heading {
    font-size: 1.2rem;
    font-weight: 500;
    color: var(--color-text);
    margin: 0 0 1rem;
  }

  /* Description */
  .description-body {
    color: var(--color-text);
    line-height: 1.7;
    margin: 0 0 0.75rem;
    white-space: pre-wrap;
  }

  .due-at,
  .triage-score {
    font-size: 0.875rem;
    color: var(--color-text-muted);
    margin: 0.25rem 0 0;
  }

  /* Assignment */
  .assignment-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
  }

  .assignee-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .assignee-name {
    font-weight: 600;
    color: var(--color-text);
  }

  .unassigned {
    color: var(--color-text-muted);
    font-style: italic;
  }

  .assignment-actions {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  .assign-form {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .member-select {
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-bg);
    color: var(--color-text);
    font-size: 0.875rem;
    cursor: pointer;
  }

  /* Status actions */
  .status-actions {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  /* Buttons */
  .btn {
    display: inline-flex;
    align-items: center;
    padding: 0.45rem 1rem;
    border: none;
    border-radius: var(--radius-sm);
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    transition: background-color var(--transition-fast), opacity var(--transition-fast);
    text-decoration: none;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-primary {
    background: var(--color-primary);
    color: #fff;
  }

  .btn-primary:not(:disabled):hover {
    background: var(--color-primary-hover);
  }

  .btn-secondary {
    background: var(--color-surface);
    color: var(--color-text);
    border: 1px solid var(--color-border);
  }

  .btn-secondary:not(:disabled):hover {
    background: var(--color-primary-light);
  }

  .btn-success {
    background: var(--color-success);
    color: #fff;
  }

  .btn-success:not(:disabled):hover {
    filter: brightness(0.92);
  }

  /* Discussion */
  .discussion-section {
    margin-top: 2rem;
  }

  .discussion-heading {
    margin-bottom: 1.25rem;
  }

  .no-comments {
    color: var(--color-text-muted);
    font-style: italic;
    margin-bottom: 1.5rem;
  }

  .comment-list {
    list-style: none;
    margin: 0 0 1.5rem;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .comment-item {
    padding: 1rem 1.25rem;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-bottom: none;
  }

  .comment-item:first-child {
    border-radius: var(--radius-md) var(--radius-md) 0 0;
  }

  .comment-item:last-child {
    border-bottom: 1px solid var(--color-border);
    border-radius: 0 0 var(--radius-md) var(--radius-md);
  }

  .comment-item:only-child {
    border-radius: var(--radius-md);
  }

  .comment-header {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
    margin-bottom: 0.5rem;
  }

  .comment-author {
    font-weight: 600;
    font-size: 0.9rem;
    color: var(--color-text);
  }

  .comment-time {
    font-size: 0.78rem;
    color: var(--color-text-muted);
  }

  .comment-body {
    color: var(--color-text);
    font-size: 0.9rem;
    line-height: 1.6;
    margin: 0;
    white-space: pre-wrap;
  }

  /* Comment form */
  .comment-form-card {
    margin-top: 0;
    border-top: none;
    border-radius: 0 0 var(--radius-md) var(--radius-md);
  }

  /* When there are no comments, the form stands alone */
  .no-comments + .card.comment-form-card {
    border-radius: var(--radius-md);
    border-top: 1px solid var(--color-border);
  }

  .form-label {
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--color-text);
    margin: 0 0 0.75rem;
  }

  .comment-textarea {
    width: 100%;
    padding: 0.65rem 0.75rem;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: var(--color-bg);
    color: var(--color-text);
    font-size: 0.9rem;
    line-height: 1.5;
    resize: vertical;
    box-sizing: border-box;
    transition: border-color var(--transition-fast);
    font-family: inherit;
  }

  .comment-textarea:focus {
    outline: none;
    border-color: var(--color-primary);
  }

  .form-footer {
    margin-top: 0.75rem;
    display: flex;
    justify-content: flex-end;
  }
</style>
