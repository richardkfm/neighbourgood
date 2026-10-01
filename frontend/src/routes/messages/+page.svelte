<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { t } from 'svelte-i18n';
	import { api } from '$lib/api';
	import { isLoggedIn, user } from '$lib/stores/auth';
	import { isOnline } from '$lib/stores/offline';
	import type { UserInfo, Conversation } from '$lib/types';
	import Icon from '$lib/components/Icon.svelte';

	// Extended locally to include skill_id which the backend returns but $lib/types.MessageOut omits
	interface Message {
		id: number;
		sender_id: number;
		sender: UserInfo;
		recipient_id: number;
		recipient: UserInfo;
		booking_id: number | null;
		skill_id: number | null;
		body: string;
		is_read: boolean;
		created_at: string;
	}

	interface SkillContext {
		id: number;
		title: string;
		skill_type: string;
	}

	let conversations: Conversation[] = $state([]);
	let messages: Message[] = $state([]);
	let selectedPartner: UserInfo | null = $state(null);
	let skillContext: SkillContext | null = $state(null);
	let loading = $state(true);
	let newMessage = $state('');
	let sending = $state(false);
	let messageQueued = $state(false);
	let sendError = $state('');

	// New message modal state
	let showNewMessage = $state(false);
	let contacts: UserInfo[] = $state([]);
	let loadingContacts = $state(false);
	let contactSearch = $state('');
	let modalEl: HTMLDivElement | undefined = $state();
	let searchEl: HTMLInputElement | undefined = $state();
	let returnFocusTo: HTMLElement | null = null;

	let filteredContacts = $derived(
		contactSearch
			? contacts.filter(c =>
				c.display_name.toLowerCase().includes(contactSearch.toLowerCase())
			)
			: contacts
	);

	async function loadConversations() {
		loading = true;
		try {
			conversations = await api<Conversation[]>('/messages/conversations', { auth: true });
		} catch {
			conversations = [];
		} finally {
			loading = false;
		}
	}

	async function loadContacts() {
		loadingContacts = true;
		try {
			contacts = await api<UserInfo[]>('/messages/contacts', { auth: true });
		} catch {
			contacts = [];
		} finally {
			loadingContacts = false;
		}
	}

	async function openNewMessage() {
		returnFocusTo = document.activeElement instanceof HTMLElement ? document.activeElement : null;
		showNewMessage = true;
		contactSearch = '';
		await tick();
		searchEl?.focus();
		await loadContacts();
	}

	async function closeNewMessage() {
		showNewMessage = false;
		await tick();
		returnFocusTo?.focus();
		returnFocusTo = null;
	}

	// Escape closes; Tab stays inside the dialog (the page behind it is also inert).
	function handleWindowKeydown(e: KeyboardEvent) {
		if (!showNewMessage || !modalEl) return;
		if (e.key === 'Escape') {
			e.preventDefault();
			closeNewMessage();
			return;
		}
		if (e.key !== 'Tab') return;
		const focusable = Array.from(
			modalEl.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])')
		);
		if (focusable.length === 0) return;
		const first = focusable[0];
		const last = focusable[focusable.length - 1];
		const active = document.activeElement;
		if (e.shiftKey && (active === first || !modalEl.contains(active))) {
			e.preventDefault();
			last.focus();
		} else if (!e.shiftKey && (active === last || !modalEl.contains(active))) {
			e.preventDefault();
			first.focus();
		}
	}

	function selectContact(contact: UserInfo) {
		closeNewMessage();
		selectedPartner = contact;
		// Check if conversation already exists
		const existing = conversations.find(c => c.partner.id === contact.id);
		if (existing) {
			openConversation(existing.partner);
		} else {
			messages = [];
		}
	}

	async function openConversation(partner: UserInfo) {
		selectedPartner = partner;
		skillContext = null;
		try {
			const res = await api<{ items: Message[]; total: number }>(
				`/messages?partner_id=${partner.id}`,
				{ auth: true }
			);
			messages = res.items.reverse();

			// If no skill context set from URL, check if the oldest message carries one
			if (!skillContext) {
				const withSkill = messages.find(m => m.skill_id !== null);
				if (withSkill?.skill_id) {
					try {
						skillContext = await api<SkillContext>(`/skills/${withSkill.skill_id}`);
					} catch {
						// skill deleted — silently ignore
					}
				}
			}

			// Mark conversation as read
			await api(`/messages/conversation/${partner.id}/read`, {
				method: 'POST',
				auth: true
			});

			// Refresh unread counts
			const conv = conversations.find(c => c.partner.id === partner.id);
			if (conv) conv.unread_count = 0;
		} catch {
			messages = [];
		}
	}

	async function sendMessage() {
		if (!newMessage.trim() || !selectedPartner || sending) return;
		sending = true;
		sendError = '';
		messageQueued = false;
		// Attach skill context to the first message in a skill-initiated thread
		const isFirstMessage = messages.length === 0;
		try {
			const msg = await api<Message>('/messages', {
				method: 'POST',
				auth: true,
				body: {
					recipient_id: selectedPartner.id,
					body: newMessage.trim(),
					...(isFirstMessage && skillContext ? { skill_id: skillContext.id } : {})
				},
				offline: { label: $t('messages.offline_to', { values: { name: selectedPartner.display_name } }) }
			});
			if (msg) {
				messages = [...messages, msg];
				await loadConversations();
			} else {
				// Request was queued for offline
				messageQueued = true;
				setTimeout(() => { messageQueued = false; }, 5000);
			}
			newMessage = '';
		} catch (err) {
			sendError = err instanceof Error ? err.message : $t('common.error');
		} finally {
			sending = false;
		}
	}

	function formatTime(iso: string): string {
		const d = new Date(iso);
		const now = new Date();
		if (d.toDateString() === now.toDateString()) {
			return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
		}
		return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			sendMessage();
		}
	}

	onMount(async () => {
		if (!$isLoggedIn) {
			goto('/login');
			return;
		}
		await loadConversations();
		const partnerId = $page.url.searchParams.get('partner');
		const skillParam = $page.url.searchParams.get('skill');

		// Pre-load skill context when navigating from a skill page
		if (skillParam) {
			try {
				skillContext = await api<SkillContext>(`/skills/${skillParam}`);
			} catch {
				// skill not found — proceed without context
			}
		}

		if (partnerId) {
			const pid = Number(partnerId);
			const existing = conversations.find(c => c.partner.id === pid);
			if (existing) {
				openConversation(existing.partner);
			} else {
				// New conversation – get display name from reputation endpoint
				try {
					const rep = await api<{ user_id: number; display_name: string }>(
						`/users/${pid}/reputation`
					);
					selectedPartner = { id: pid, display_name: rep.display_name, email: '' };
				} catch {
					selectedPartner = { id: pid, display_name: $t('messages.unknown_user'), email: '' };
				}
				messages = [];
			}
		}
	});
</script>

<svelte:window onkeydown={handleWindowKeydown} />

{#if !$isLoggedIn}
	<div class="empty-state">
		<p>{$t('messages.login_required')}</p>
	</div>
{:else}
	<div class="messages-page" inert={showNewMessage}>
		<div class="page-header">
			<h1>{$t('messages.title')}</h1>
			<button class="btn btn-primary" onclick={openNewMessage}>
				<Icon name="plus" size={16} />
				{$t('messages.new_message')}
			</button>
		</div>

		<div class="messages-layout" class:has-selection={selectedPartner}>
			<!-- Conversation list -->
			<div class="conv-list">
				{#if loading}
					<div class="conv-skeleton" role="status" aria-busy="true">
						<span class="sr-only">{$t('common.loading')}</span>
						{#each [1, 2, 3, 4] as n (n)}
							<div class="conv-skeleton-row" aria-hidden="true">
								<span class="skeleton skeleton-line" style="width: 50%"></span>
								<span class="skeleton skeleton-line" style="width: 85%; margin-top: 0.5rem"></span>
							</div>
						{/each}
					</div>
				{:else if conversations.length === 0}
					<div class="empty-state compact">
						<span class="empty-icon"><Icon name="message" size={22} /></span>
						<p>{$t('messages.no_conversations')}</p>
						<button class="btn btn-primary btn-sm" onclick={openNewMessage}>{$t('messages.new_message')}</button>
					</div>
				{:else}
					{#each conversations as conv}
						<button
							class="conv-item"
							class:active={selectedPartner?.id === conv.partner.id}
							onclick={() => openConversation(conv.partner)}
						>
							<div class="conv-header">
								<span class="conv-name">{conv.partner.display_name}</span>
								<span class="conv-time">{formatTime(conv.last_message_at)}</span>
							</div>
							<div class="conv-preview">
								<span class="conv-body">{conv.last_message_body}</span>
								{#if conv.unread_count > 0}
									<span class="badge badge-solid unread-badge">{conv.unread_count}</span>
								{/if}
							</div>
						</button>
					{/each}
				{/if}
			</div>

			<!-- Message thread -->
			<div class="thread">
				{#if !selectedPartner}
					<div class="thread-empty">
						<span class="empty-icon"><Icon name="message" size={22} /></span>
						<p>{$t('messages.select_conversation')}</p>
					</div>
				{:else}
					<div class="thread-header">
						<button class="thread-back" onclick={() => (selectedPartner = null)} aria-label={$t('common.back')}>
							<Icon name="arrow-left" size={20} class="flip-rtl" />
						</button>
						<strong>{selectedPartner.display_name}</strong>
					</div>
					{#if skillContext}
						<div class="skill-context-banner">
							<span class="skill-context-label">
								{skillContext.skill_type === 'offer' ? $t('messages.skill_offered') : $t('messages.skill_wanted')}:
							</span>
							<a href="/skills/{skillContext.id}" class="skill-context-link">{skillContext.title}</a>
						</div>
					{/if}
					<div class="thread-messages">
						{#each messages as msg}
							<div
								class="msg-bubble"
								class:sent={msg.sender_id === $user?.id}
								class:received={msg.sender_id !== $user?.id}
							>
								<p class="msg-body">{msg.body}</p>
								<span class="msg-time">{formatTime(msg.created_at)}</span>
							</div>
						{/each}
					</div>
					{#if messageQueued}
						<div class="queued-notice">{$t('offline.queued_confirmation')}</div>
					{/if}
					{#if sendError}
						<p class="send-error" role="alert">{sendError}</p>
					{/if}
					<div class="thread-input">
						<textarea
							class="input"
							bind:value={newMessage}
							placeholder={$t("messages.type_message")}
							rows="2"
							onkeydown={handleKeydown}
						></textarea>
						<button
							class="btn btn-primary"
							class:is-loading={sending}
							onclick={sendMessage}
							disabled={sending || !newMessage.trim()}
						>
							{$isOnline ? $t("messages.send") : $t('offline.queue_action')}
						</button>
					</div>
				{/if}
			</div>
		</div>
	</div>

	<!-- New message modal -->
	{#if showNewMessage}
		<div class="modal-overlay" role="presentation" onclick={(e) => { if (e.target === e.currentTarget) closeNewMessage(); }}>
			<div class="card card-flush modal" role="dialog" aria-modal="true" aria-labelledby="new-message-title" bind:this={modalEl}>
				<div class="modal-header">
					<h2 id="new-message-title">{$t("messages.new_message")}</h2>
					<button class="btn btn-ghost btn-sm modal-close" onclick={closeNewMessage} aria-label={$t('common.close')}><Icon name="x" size={18} /></button>
				</div>
				<div class="modal-body">
					<input
						type="text"
						class="input contact-search"
						placeholder={$t("messages.search_contacts")}
						aria-label={$t("messages.search_contacts")}
						bind:this={searchEl}
						bind:value={contactSearch}
					/>
					{#if loadingContacts}
						<p class="empty-text" role="status">{$t("messages.loading_contacts")}</p>
					{:else if contacts.length === 0}
						<p class="empty-text">{$t("messages.no_contacts")}</p>
					{:else if filteredContacts.length === 0}
						<p class="empty-text">{$t("messages.no_matching_contacts")}</p>
					{:else}
						<ul class="contact-list">
							{#each filteredContacts as contact}
								<li>
									<button class="contact-item" onclick={() => selectContact(contact)}>
										<span class="contact-name">{contact.display_name}</span>
										{#if contact.neighbourhood}
											<span class="contact-meta">{contact.neighbourhood}</span>
										{/if}
									</button>
								</li>
							{/each}
						</ul>
					{/if}
				</div>
			</div>
		</div>
	{/if}
{/if}

<style>
	.messages-page {
		max-width: 900px;
	}

	h1 {
		font-size: 2.1rem;
		font-weight: 400;
		margin: 0;
	}

	.messages-layout {
		display: grid;
		grid-template-columns: 280px 1fr;
		gap: 1px;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		overflow: hidden;
		height: 500px;
	}

	.conv-list {
		background: var(--color-surface);
		border-inline-end: 1px solid var(--color-border);
		overflow-y: auto;
	}

	.conv-item {
		display: block;
		width: 100%;
		text-align: start;
		padding: 0.75rem 1rem;
		border: none;
		border-bottom: 1px solid var(--color-border);
		background: var(--color-surface);
		cursor: pointer;
		font-size: 0.85rem;
		color: var(--color-text);
	}

	.conv-item:hover {
		background: var(--color-primary-light);
	}

	.conv-item.active {
		background: var(--color-primary-light);
	}

	.conv-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.2rem;
	}

	.conv-name {
		font-weight: 600;
		font-size: 0.9rem;
	}

	.conv-time {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}

	.conv-preview {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.conv-body {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: var(--color-text-muted);
		flex: 1;
	}

	.unread-badge {
		margin-inline-start: 0.5rem;
	}

	.conv-skeleton-row {
		padding: 0.85rem 1rem;
		border-bottom: 1px solid var(--color-border);
	}

	.thread {
		display: flex;
		flex-direction: column;
		background: var(--color-bg);
	}

	.thread-empty {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		align-items: center;
		justify-content: center;
		height: 100%;
		color: var(--color-text-muted);
	}

	.thread-back {
		display: none;
		align-items: center;
		justify-content: center;
		width: var(--tap-target);
		height: var(--tap-target);
		margin-block: -0.5rem;
		margin-inline: -0.75rem 0;
		background: none;
		border: none;
		color: var(--color-text);
		cursor: pointer;
	}

	.thread-header {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.75rem 1rem;
		border-bottom: 1px solid var(--color-border);
		background: var(--color-surface);
	}

	.skill-context-banner {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.4rem 1rem;
		background: var(--color-primary-light);
		border-bottom: 1px solid var(--color-border);
		font-size: 0.8rem;
	}

	.skill-context-label {
		color: var(--color-text-muted);
		white-space: nowrap;
	}

	.skill-context-link {
		color: var(--color-primary-text);
		font-weight: 600;
		text-decoration: none;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.skill-context-link:hover {
		text-decoration: underline;
	}

	.thread-messages {
		flex: 1;
		overflow-y: auto;
		padding: 1rem;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.msg-bubble {
		max-width: 70%;
		padding: 0.5rem 0.75rem;
		border-radius: 12px;
		font-size: 0.88rem;
	}

	.msg-bubble.sent {
		align-self: flex-end;
		background: var(--color-primary);
		color: var(--color-on-primary);
	}

	.msg-bubble.received {
		align-self: flex-start;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
	}

	.msg-body {
		margin: 0;
		white-space: pre-wrap;
		word-break: break-word;
	}

	.msg-time {
		display: block;
		font-size: 0.7rem;
		margin-top: 0.2rem;
		opacity: 0.7;
	}

	.msg-bubble.sent .msg-time {
		text-align: end;
	}

	.thread-input textarea {
		flex: 1;
		resize: none;
	}

	.thread-input {
		display: flex;
		gap: 0.5rem;
		padding: 0.75rem 1rem;
		border-top: 1px solid var(--color-border);
		background: var(--color-surface);
	}

	.queued-notice {
		padding: 0.4rem 1rem;
		font-size: 0.82rem;
		color: var(--color-success);
		background: var(--color-success-bg, rgba(34, 197, 94, 0.1));
		text-align: center;
	}

	.send-error {
		padding: 0.4rem 1rem;
		font-size: 0.82rem;
		color: var(--color-error);
		background: var(--color-error-bg);
		border-inline-start: 3px solid var(--color-error);
	}

	.empty-text {
		padding: 1.5rem;
		text-align: center;
		color: var(--color-text-muted);
		font-size: 0.85rem;
	}

	.empty-state.compact {
		padding: 2rem 1rem;
	}

	/* ── New message modal ────────────────────────────────────── */

	.modal-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.4);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 200;
	}

	.modal {
		box-shadow: var(--shadow-lg);
		width: 90%;
		max-width: 440px;
		max-height: 80vh;
		display: flex;
		flex-direction: column;
	}

	.modal-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 1rem 1.25rem;
		border-bottom: 1px solid var(--color-border);
	}

	.modal-header h2 {
		font-size: 1.1rem;
		margin: 0;
	}

	.modal-body {
		padding: 1rem 1.25rem;
		overflow-y: auto;
	}

	.contact-search {
		margin-bottom: 0.75rem;
	}

	.contact-list {
		list-style: none;
		padding: 0;
		margin: 0;
	}

	.contact-item {
		display: flex;
		align-items: center;
		justify-content: space-between;
		width: 100%;
		padding: 0.6rem 0.75rem;
		border: none;
		border-radius: var(--radius-sm);
		background: none;
		cursor: pointer;
		color: var(--color-text);
		font-size: 0.9rem;
		text-align: start;
		min-height: var(--tap-target);
		transition: background var(--transition-fast);
	}

	.contact-item:hover {
		background: var(--color-primary-light);
	}

	.contact-name {
		font-weight: 600;
	}

	.contact-meta {
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	/* ── Responsive ───────────────────────────────────────────── */

	/* Phones: classic master-detail. Show the conversation list, or the open
	   thread with a back button, never both stacked with an empty pane. */
	@media (max-width: 640px) {
		.messages-layout {
			grid-template-columns: 1fr;
			height: auto;
		}

		.conv-list {
			border-inline-end: none;
			max-height: none;
		}

		.messages-layout.has-selection .conv-list {
			display: none;
		}

		.messages-layout:not(.has-selection) .thread {
			display: none;
		}

		.messages-layout.has-selection .thread {
			height: calc(100dvh - 17rem);
			min-height: 320px;
		}

		.thread-back {
			display: inline-flex;
		}
	}
</style>
