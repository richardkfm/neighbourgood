import type { IconName } from '$lib/components/Icon.svelte';

/** Category -> icon lookups shared by the list and detail pages. */

export const RESOURCE_CATEGORY_ICON: Record<string, IconName> = {
	tool: 'tool',
	vehicle: 'car',
	electronics: 'zap',
	furniture: 'armchair',
	food: 'utensils',
	clothing: 'shirt',
	skill: 'lightbulb',
	other: 'package'
};

export const SKILL_CATEGORY_ICON: Record<string, IconName> = {
	tutoring: 'book',
	repairs: 'tool',
	cooking: 'chef',
	languages: 'globe',
	music: 'music',
	gardening: 'leaf',
	tech: 'laptop',
	crafts: 'scissors',
	fitness: 'dumbbell',
	other: 'star'
};

export const EVENT_CATEGORY_ICON: Record<string, IconName> = {
	meetup: 'handshake',
	workshop: 'book',
	repair_cafe: 'tool',
	swap: 'refresh',
	gardening: 'leaf',
	food: 'utensils',
	sport: 'activity',
	cultural: 'music',
	other: 'star'
};

export const TRUST_BADGE_ICON: Record<string, IconName> = {
	reliable_borrower: 'handshake',
	trusted_lender: 'package',
	skilled_helper: 'star'
};

export const REPUTATION_LEVEL_ICON: Record<string, IconName> = {
	Newcomer: 'leaf',
	Neighbour: 'home',
	Helper: 'heart',
	Trusted: 'shield',
	Pillar: 'landmark'
};
