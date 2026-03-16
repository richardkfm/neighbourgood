/**
 * Mesh settings store — persists the user's mesh networking preference in localStorage.
 * When disabled, all mesh UI is hidden (nav links, triage panel, etc.).
 */

import { writable } from 'svelte/store';

const STORAGE_KEY = 'ng_mesh_enabled';

function loadSetting(): boolean {
	if (typeof localStorage === 'undefined') return false;
	return localStorage.getItem(STORAGE_KEY) === 'true';
}

export const meshEnabled = writable<boolean>(loadSetting());

meshEnabled.subscribe((value) => {
	if (typeof localStorage !== 'undefined') {
		localStorage.setItem(STORAGE_KEY, String(value));
	}
});

export function toggleMeshEnabled() {
	meshEnabled.update((v) => !v);
}
