/**
 * Shared TypeScript interfaces matching backend schemas.
 * Import these instead of redefining locally in each page.
 */

export interface UserInfo {
	id: number;
	display_name: string;
	email: string;
	neighbourhood?: string | null;
	role?: string;
	language_code?: string;
	created_at?: string;
}

export interface Resource {
	id: number;
	title: string;
	description: string | null;
	category: string;
	condition: string | null;
	image_url: string | null;
	is_available: boolean;
	owner_id: number;
	community_id: number | null;
	owner: UserInfo;
	quantity_total: number;
	quantity_available: number;
	reorder_threshold: number | null;
	low_stock: boolean;
	created_at: string;
	updated_at?: string;
}

export interface EmergencyTicket {
	id: number;
	community_id: number;
	author: UserInfo;
	ticket_type: string;
	title: string;
	description: string;
	status: string;
	urgency: string;
	due_at: string | null;
	triage_score: number;
	assigned_to: UserInfo | null;
	created_at: string;
	updated_at: string;
}

export interface Booking {
	id: number;
	resource_id: number;
	resource_title: string | null;
	borrower_id: number;
	borrower: UserInfo;
	start_date: string;
	end_date: string;
	message: string | null;
	status: string;
	created_at: string;
}

export interface CommunityOut {
	id: number;
	name: string;
	description: string | null;
	postal_code: string;
	city: string;
	country_code: string;
	primary_language?: string | null;
	mode: string;
	latitude: number | null;
	longitude: number | null;
	member_count: number;
	is_active: boolean;
	merged_into_id: number | null;
	created_by?: UserInfo;
	created_at?: string;
}

export interface CommunityMember {
	id: number;
	user: UserInfo;
	role: string;
	joined_at: string;
}

export interface MergeSuggestion {
	source: CommunityOut;
	target: CommunityOut;
	reason: string;
}

export interface Conversation {
	partner: UserInfo;
	last_message_body: string;
	last_message_at: string;
	unread_count: number;
}

export interface MessageOut {
	id: number;
	sender_id: number;
	sender: UserInfo;
	recipient_id: number;
	recipient: UserInfo;
	booking_id: number | null;
	body: string;
	is_read: boolean;
	created_at: string;
}

export interface ActivityOut {
	id: number;
	event_type: string;
	summary: string;
	actor_id: number;
	community_id: number | null;
	actor: { id: number; display_name: string; email: string };
	created_at: string;
}

export interface ActivityList {
	items: ActivityOut[];
	total: number;
}

export type ResourceItem = Resource;

export interface CrisisStatus {
	community_id: number;
	mode: string;
	votes_to_activate: number;
	votes_to_deactivate: number;
	total_members: number;
	threshold_pct: number;
}

export interface InviteOut {
	id: number;
	community_id: number;
	code: string;
	max_uses: number | null;
	use_count: number;
	expires_at: string | null;
	created_at: string;
}

export interface TicketList {
	items: EmergencyTicket[];
	total: number;
}

export interface Webhook {
	id: number;
	owner_type: string;
	owner_id: number;
	url: string;
	event_types: string[];
	is_active: boolean;
	created_at: string;
}

// ── Mesh networking types (BitChat BLE gateway) ──────────────────────────────

export type NGMeshMessageType =
	| 'emergency_ticket'
	| 'ticket_comment'
	| 'crisis_vote'
	| 'crisis_status'
	| 'direct_message'
	| 'heartbeat';

export interface NGMeshMessage {
	ng: 1;
	type: NGMeshMessageType;
	community_id: number;
	sender_name: string;
	ts: number;
	id: string;
	data: Record<string, unknown>;
}

export interface MeshTicketData {
	title: string;
	description: string;
	ticket_type: 'request' | 'offer' | 'emergency_ping';
	urgency: 'low' | 'medium' | 'high' | 'critical';
}

export interface MeshVoteData {
	vote_type: 'activate' | 'deactivate';
}

export interface MeshSyncResult {
	synced: number;
	duplicates: number;
	errors: number;
}

/**
 * Status color utility – maps booking/resource status to CSS variable names.
 */
export function statusColor(status: string): string {
	switch (status) {
		case 'approved':
			return 'var(--color-success)';
		case 'pending':
			return 'var(--color-warning)';
		case 'rejected':
		case 'cancelled':
			return 'var(--color-error)';
		case 'completed':
		default:
			return 'var(--color-text-muted)';
	}
}
