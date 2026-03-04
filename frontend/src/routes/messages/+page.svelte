<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { t } from 'svelte-i18n';
	import { api } from '$lib/api';
	import { isLoggedIn, user } from '$lib/stores/auth';

	interface UserInfo {
		id: number;
		display_name: string;
		email: string;
	}

	interface Conversation {
		partner: UserInfo;
		last_message_body: string;
		last_message_at: string;
		unread_count: number;
	}

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

	// New message modal state
	let showNewMessage = $state(false);
	let contacts: UserInfo[] = $state([]);
	let loadingContacts = $state(false);
	let contactSearch = $state('');

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
		showNewMessage = true;
		contactSearch = '';
		await loadContacts();
	}

	function selectContact(contact: UserInfo) {
		showNewMessage = false;
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
				}
			});
			messages = [...messages, msg];
			newMessage = '';
			await loadConversations();
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to send');
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
					selectedPartner = { id: pid, display_name: 'User', email: '' };
				}
				messages = [];
			}
		}
	});
</script>

{#if !$isLoggedIn}
	<div class="empty-state">
		<p>{$t('messages.login_required')}</p>
	</div>
{:else}
	<div class="messages-page">
		<div class="page-header">
			<h1>{$t('messages.title')}</h1>
			<button class="new-msg-btn" onclick={openNewMessage}>
				<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
				{$t('messages.new_message')}
			</button>
		</div>

		<div class="messages-layout">
			<!-- Conversation list -->
			<div class="conv-list">
				{#if loading}
					<p class="loading">{$t('common.loading')}</p>
				{:else if conversations.length === 0}
					<p class="empty-text">{$t('messages.no_conversations')}</p>
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
									<span class="unread-badge">{conv.unread_count}</span>
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
						<p>{$t('messages.select_conversation')}</p>
					</div>
				{:else}
					<div class="thread-header">
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
					<div class="thread-input">
						<textarea
							bind:value={newMessage}
							placeholder={$t("messages.type_message")}
							rows="2"
							onkeydown={handleKeydown}
						></textarea>
						<button
							class="send-btn"
							onclick={sendMessage}
							disabled={sending || !newMessage.trim()}
						>
							{$t("messages.send")}
						</button>
					</div>
				{/if}
			</div>
		</div>
	</div>

	<!-- New message modal -->
	{#if showNewMessage}
		<div class="modal-overlay" role="presentation" onclick={() => showNewMessage = false}>
			<div class="modal" role="dialog" onclick={(e) => e.stopPropagation()}>
				<div class="modal-header">
					<h2>{$t("messages.new_message")}</h2>
					<button class="modal-close" onclick={() => showNewMessage = false} aria-label="Close">&times;</button>
				</div>
				<div class="modal-body">
					<input
						type="text"
						class="contact-search"
						placeholder={$t("messages.search_contacts")}
						bind:value={contactSearch}
					/>
					{#if loadingContacts}
						<p class="loading">{$t("messages.loading_contacts")}</p>
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
										<span class="contact-email">{contact.email}</span>
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

	.page-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 1rem;
	}

	h1 {
		font-size: 1.9rem;
		font-weight: 400;
		margin: 0;
	}

	.new-msg-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		background: var(--color-primary);
		color: white;
		border: none;
		border-radius: var(--radius-sm);
		padding: 0.5rem 1rem;
		font-size: 0.88rem;
		font-weight: 600;
		cursor: pointer;
		transition: all var(--transition-fast);
	}

	.new-msg-btn:hover {
		background: var(--color-primary-hover);
		box-shadow: var(--shadow-md);
		transform: translateY(-1px);
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
		border-right: 1px solid var(--color-border);
		overflow-y: auto;
	}

	.conv-item {
		display: block;
		width: 100%;
		text-align: left;
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
		background: var(--color-primary);
		color: white;
		font-size: 0.7rem;
		font-weight: 700;
		border-radius: 10px;
		padding: 0.1rem 0.45rem;
		margin-left: 0.5rem;
	}

	.thread {
		display: flex;
		flex-direction: column;
		background: var(--color-bg);
	}

	.thread-empty {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100%;
		color: var(--color-text-muted);
	}

	.thread-header {
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
		color: var(--color-primary);
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
		color: white;
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
		text-align: right;
	}

	.thread-input {
		display: flex;
		gap: 0.5rem;
		padding: 0.75rem 1rem;
		border-top: 1px solid var(--color-border);
		background: var(--color-surface);
	}

	.thread-input textarea {
		flex: 1;
		resize: none;
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		padding: 0.5rem;
		font-size: 0.85rem;
		font-family: inherit;
	}

	.send-btn {
		background: var(--color-primary);
		color: white;
		border: none;
		border-radius: var(--radius);
		padding: 0.5rem 1rem;
		cursor: pointer;
		font-size: 0.85rem;
		align-self: flex-end;
	}

	.send-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.send-btn:not(:disabled):hover {
		background: var(--color-primary-hover);
	}

	.loading, .empty-text {
		padding: 1.5rem;
		text-align: center;
		color: var(--color-text-muted);
		font-size: 0.85rem;
	}

	.empty-state {
		text-align: center;
		padding: 3rem 1rem;
		color: var(--color-text-muted);
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
		background: var(--color-surface);
		border-radius: var(--radius);
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

	.modal-close {
		background: none;
		border: none;
		font-size: 1.5rem;
		color: var(--color-text-muted);
		cursor: pointer;
		padding: 0;
		line-height: 1;
	}

	.modal-close:hover {
		color: var(--color-text);
	}

	.modal-body {
		padding: 1rem 1.25rem;
		overflow-y: auto;
	}

	.contact-search {
		width: 100%;
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		font-size: 0.9rem;
		margin-bottom: 0.75rem;
		background: var(--color-bg);
		color: var(--color-text);
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
		text-align: left;
		transition: background var(--transition-fast);
	}

	.contact-item:hover {
		background: var(--color-primary-light);
	}

	.contact-name {
		font-weight: 600;
	}

	.contact-email {
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	/* ── Responsive ───────────────────────────────────────────── */

	@media (max-width: 640px) {
		.messages-layout {
			grid-template-columns: 1fr;
			height: auto;
		}

		.conv-list {
			border-right: none;
			border-bottom: 1px solid var(--color-border);
			max-height: 200px;
		}

		.thread {
			min-height: 300px;
		}
	}
</style>
