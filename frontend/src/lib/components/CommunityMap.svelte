<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { t } from 'svelte-i18n';
	import { theme } from '$lib/stores/theme';
	import type { MapCommunity } from '$lib/types';

	let {
		communities = [],
		myIds = new Set<number>(),
		loading = false,
		onlocate
	}: {
		communities?: MapCommunity[];
		myIds?: Set<number>;
		loading?: boolean;
		onlocate?: (lat: number, lng: number) => void;
	} = $props();

	let mapContainer: HTMLDivElement;
	let map: any = null;
	let markers: any[] = [];
	let maplibre: any = $state(null);
	let userLocated = $state(false);
	let userLat = 51.1657; // Default: center of Germany
	let userLng = 10.4515;
	let centeredOnMine = false;

	// OpenFreeMap: free vector tiles from OpenStreetMap data, no API key or
	// account (https://openfreemap.org). CARTO's basemaps now require a key.
	const MAPLIBRE_VERSION = '5.24.0';
	const STYLE_URLS = {
		light: 'https://tiles.openfreemap.org/styles/positron',
		dark: 'https://tiles.openfreemap.org/styles/dark'
	};

	async function loadMaplibre(): Promise<any> {
		if (!document.querySelector('link[href*="maplibre-gl"]')) {
			const link = document.createElement('link');
			link.rel = 'stylesheet';
			link.href = `https://unpkg.com/maplibre-gl@${MAPLIBRE_VERSION}/dist/maplibre-gl.css`;
			document.head.appendChild(link);
		}
		if ((window as any).maplibregl) return (window as any).maplibregl;
		return new Promise((resolve, reject) => {
			const script = document.createElement('script');
			script.src = `https://unpkg.com/maplibre-gl@${MAPLIBRE_VERSION}/dist/maplibre-gl.js`;
			script.onload = () => resolve((window as any).maplibregl);
			script.onerror = reject;
			document.head.appendChild(script);
		});
	}

	function escapeHtml(value: unknown): string {
		return String(value ?? '').replace(
			/[&<>"']/g,
			(ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]!
		);
	}

	function locateUser(): Promise<{ lat: number; lng: number } | null> {
		return new Promise((resolve) => {
			if (!navigator.geolocation) {
				resolve(null);
				return;
			}
			navigator.geolocation.getCurrentPosition(
				(pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
				() => resolve(null),
				{ timeout: 5000, enableHighAccuracy: false }
			);
		});
	}

	function activityLevel(c: MapCommunity): 'high' | 'medium' | 'low' {
		const s = c.member_count + c.resource_count * 2 + c.skill_count * 2;
		if (s >= 10) return 'high';
		if (s >= 4) return 'medium';
		return 'low';
	}

	onMount(() => {
		let unsubscribeTheme: (() => void) | undefined;

		(async () => {
			try {
				const maplibregl = await loadMaplibre();
				const pos = await locateUser();
				if (pos) {
					userLat = pos.lat;
					userLng = pos.lng;
					userLocated = true;
					onlocate?.(pos.lat, pos.lng);
				}

				let currentTheme = get(theme);
				map = new maplibregl.Map({
					container: mapContainer,
					style: STYLE_URLS[currentTheme],
					center: [userLng, userLat],
					zoom: userLocated ? 12 : 6,
					attributionControl: { compact: true }
				});
				map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');

				// Follow the light/dark toggle live. Markers are DOM overlays,
				// so swapping the style leaves them in place.
				unsubscribeTheme = theme.subscribe((value) => {
					if (!map || value === currentTheme) return;
					currentTheme = value;
					map.setStyle(STYLE_URLS[value]);
				});

				if (userLocated) {
					const el = document.createElement('div');
					el.className = 'user-dot';
					new maplibregl.Marker({ element: el })
						.setLngLat([userLng, userLat])
						.setPopup(
							new maplibregl.Popup({ offset: 12 }).setHTML(
								`<strong>${escapeHtml(get(t)('communities.you_are_here'))}</strong>`
							)
						)
						.addTo(map);
				}

				maplibre = maplibregl;
			} catch (e) {
				console.warn('Map initialization failed:', e);
			}
		})();

		return () => {
			unsubscribeTheme?.();
			map?.remove();
			map = null;
		};
	});

	// (Re)draw community markers whenever the map is ready or the data changes.
	$effect(() => {
		const maplibregl = maplibre;
		const list = communities;
		const mine = myIds;
		if (!maplibregl || !map) return;

		for (const m of markers) m.remove();
		markers = [];
		for (const c of list) {
			if (c.latitude == null || c.longitude == null) continue;
			const isMine = mine.has(c.id);
			const level = activityLevel(c);
			const size = level === 'high' ? 40 : level === 'medium' ? 34 : 28;
			const color = isMine
				? 'var(--color-success)'
				: (c.effective_mode ?? c.mode) === 'red'
					? 'var(--color-error)'
					: 'var(--color-primary)';
			const ringClass = isMine ? 'ring-mine' : level === 'high' ? 'ring-active' : '';
			const el = document.createElement('div');
			el.className = 'community-marker';
			el.innerHTML = `<div class="community-dot ${ringClass}" style="background:${color};width:${size}px;height:${size}px"><span>${c.member_count}</span></div>`;
			const popup = new maplibregl.Popup({ offset: size / 2 + 4 }).setHTML(`
				<strong>${escapeHtml(c.name)}</strong>${isMine ? ` (${escapeHtml(get(t)('communities.your_community_paren'))})` : ''}<br/>
				${escapeHtml(c.city)} (${escapeHtml(c.postal_code)})<br/>
				${escapeHtml(get(t)('communities.map_popup_counts', { values: { members: c.member_count, items: c.resource_count, skills: c.skill_count } }))}<br/>
				<a href="/communities/${c.id}">${escapeHtml(get(t)('communities.view_community'))}</a>
			`);
			markers.push(
				new maplibregl.Marker({ element: el }).setLngLat([c.longitude, c.latitude]).setPopup(popup).addTo(map)
			);
		}

		// Center on the user's own community once, when it has coordinates.
		if (!centeredOnMine) {
			const home = list.find((c) => mine.has(c.id) && c.latitude != null && c.longitude != null);
			if (home) {
				map.jumpTo({ center: [home.longitude, home.latitude], zoom: 12 });
				centeredOnMine = true;
			}
		}
	});
</script>

<div class="map-wrapper">
	<div bind:this={mapContainer} class="map-container"></div>
	{#if loading}
		<div class="map-loading">
			<p>{$t('communities.loading_map')}</p>
		</div>
	{/if}
</div>

{#if !userLocated && !loading}
	<div class="location-hint fade-in">
		<p>{$t('communities.location_error')}</p>
	</div>
{/if}

<style>
	.map-wrapper {
		position: relative;
		border-radius: var(--radius-lg);
		overflow: hidden;
		border: 1px solid var(--color-border);
		box-shadow: var(--shadow-md);
		margin-bottom: 1.5rem;
	}

	.map-container {
		width: 100%;
		height: 420px;
		background: var(--color-surface);
	}

	.map-loading {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--color-surface);
		z-index: 10;
	}

	.map-loading p {
		color: var(--color-text-muted);
		font-size: 0.9rem;
	}

	.location-hint {
		padding: 0.65rem 1rem;
		border-radius: var(--radius);
		background: var(--color-warning-bg);
		border: 1px solid var(--color-warning);
		color: var(--color-warning);
		font-size: 0.85rem;
		margin-bottom: 1.5rem;
	}

	/* ── Custom map markers ──────────────── */

	:global(.user-dot) {
		width: 16px;
		height: 16px;
		background: var(--color-primary);
		border: 3px solid white;
		border-radius: 50%;
		box-shadow:
			0 0 0 2px color-mix(in srgb, var(--color-primary) 40%, transparent),
			0 2px 8px rgba(0, 0, 0, 0.2);
		animation: pulse-dot 2s infinite;
	}

	@keyframes pulse-dot {
		0%,
		100% {
			box-shadow:
				0 0 0 2px color-mix(in srgb, var(--color-primary) 40%, transparent),
				0 2px 8px rgba(0, 0, 0, 0.2);
		}
		50% {
			box-shadow:
				0 0 0 8px color-mix(in srgb, var(--color-primary) 15%, transparent),
				0 2px 8px rgba(0, 0, 0, 0.2);
		}
	}

	:global(.community-marker) {
		cursor: pointer;
	}

	:global(.community-dot) {
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 50%;
		color: white;
		font-size: 0.7rem;
		font-weight: 700;
		box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
		border: 2px solid white;
	}

	:global(.community-dot span) {
		line-height: 1;
	}

	:global(.ring-active) {
		box-shadow:
			0 0 0 4px color-mix(in srgb, var(--color-primary) 25%, transparent),
			0 2px 6px rgba(0, 0, 0, 0.3) !important;
		animation: pulse-ring 2s infinite;
	}

	:global(.ring-mine) {
		box-shadow:
			0 0 0 5px color-mix(in srgb, var(--color-success) 30%, transparent),
			0 2px 6px rgba(0, 0, 0, 0.3) !important;
		animation: pulse-mine 2s infinite;
	}

	@keyframes pulse-ring {
		0%,
		100% {
			box-shadow:
				0 0 0 4px color-mix(in srgb, var(--color-primary) 25%, transparent),
				0 2px 6px rgba(0, 0, 0, 0.3);
		}
		50% {
			box-shadow:
				0 0 0 8px color-mix(in srgb, var(--color-primary) 10%, transparent),
				0 2px 6px rgba(0, 0, 0, 0.3);
		}
	}

	@keyframes pulse-mine {
		0%,
		100% {
			box-shadow:
				0 0 0 5px color-mix(in srgb, var(--color-success) 30%, transparent),
				0 2px 6px rgba(0, 0, 0, 0.3);
		}
		50% {
			box-shadow:
				0 0 0 10px color-mix(in srgb, var(--color-success) 10%, transparent),
				0 2px 6px rgba(0, 0, 0, 0.3);
		}
	}

	/* ── Map chrome follows the light/dark theme ──────────────── */
	/* Scoped under .map-wrapper: maplibre-gl.css is injected after this
	   stylesheet, so equal-specificity rules would lose to its white defaults. */

	.map-wrapper :global(.maplibregl-popup-content) {
		background: var(--color-surface);
		color: var(--color-text);
		border: 1px solid var(--color-border);
		border-radius: var(--radius);
		box-shadow: var(--shadow-md);
		font-family: inherit;
		font-size: 0.85rem;
		line-height: 1.5;
		padding: 0.65rem 0.9rem;
	}

	.map-wrapper :global(.maplibregl-popup-content a) {
		color: var(--color-primary-text);
	}

	.map-wrapper :global(.maplibregl-popup-close-button) {
		color: var(--color-text-muted);
	}

	.map-wrapper :global(.maplibregl-popup-anchor-bottom .maplibregl-popup-tip),
	.map-wrapper :global(.maplibregl-popup-anchor-bottom-left .maplibregl-popup-tip),
	.map-wrapper :global(.maplibregl-popup-anchor-bottom-right .maplibregl-popup-tip) {
		border-top-color: var(--color-surface);
	}

	.map-wrapper :global(.maplibregl-popup-anchor-top .maplibregl-popup-tip),
	.map-wrapper :global(.maplibregl-popup-anchor-top-left .maplibregl-popup-tip),
	.map-wrapper :global(.maplibregl-popup-anchor-top-right .maplibregl-popup-tip) {
		border-bottom-color: var(--color-surface);
	}

	.map-wrapper :global(.maplibregl-popup-anchor-left .maplibregl-popup-tip) {
		border-right-color: var(--color-surface);
	}

	.map-wrapper :global(.maplibregl-popup-anchor-right .maplibregl-popup-tip) {
		border-left-color: var(--color-surface);
	}

	.map-wrapper :global(.maplibregl-ctrl-group),
	.map-wrapper :global(.maplibregl-ctrl-attrib.maplibregl-compact) {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		box-shadow: var(--shadow-sm);
	}

	.map-wrapper :global(.maplibregl-ctrl-group button + button) {
		border-top-color: var(--color-border);
	}

	.map-wrapper :global(.maplibregl-ctrl-attrib),
	.map-wrapper :global(.maplibregl-ctrl-attrib a) {
		color: var(--color-text-muted);
	}

	.map-wrapper :global(.maplibregl-ctrl-attrib:not(.maplibregl-compact)) {
		background: color-mix(in srgb, var(--color-surface) 80%, transparent);
	}

	/* MapLibre's control icons are dark SVG backgrounds */
	:global([data-theme='dark']) .map-wrapper :global(.maplibregl-ctrl-icon),
	:global([data-theme='dark']) .map-wrapper :global(.maplibregl-ctrl-attrib-button) {
		filter: invert(1);
	}

	@media (max-width: 640px) {
		.map-container {
			height: 320px;
		}
	}
</style>
