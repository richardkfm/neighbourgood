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
	let markerLayer: any = null;
	let leaflet: any = $state(null);
	let userLocated = $state(false);
	let userLat = 51.1657; // Default: center of Germany
	let userLng = 10.4515;
	let centeredOnMine = false;

	async function loadLeaflet(): Promise<any> {
		if (!document.querySelector('link[href*="leaflet"]')) {
			const link = document.createElement('link');
			link.rel = 'stylesheet';
			link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
			document.head.appendChild(link);
		}
		if ((window as any).L) return (window as any).L;
		return new Promise((resolve, reject) => {
			const script = document.createElement('script');
			script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
			script.onload = () => resolve((window as any).L);
			script.onerror = reject;
			document.head.appendChild(script);
		});
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
		(async () => {
			try {
				const L = await loadLeaflet();
				const pos = await locateUser();
				if (pos) {
					userLat = pos.lat;
					userLng = pos.lng;
					userLocated = true;
					onlocate?.(pos.lat, pos.lng);
				}

				map = L.map(mapContainer).setView([userLat, userLng], userLocated ? 12 : 6);

				const tileUrl =
					get(theme) === 'dark'
						? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
						: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';
				L.tileLayer(tileUrl, {
					attribution:
						'&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
					maxZoom: 19,
					subdomains: 'abcd'
				}).addTo(map);

				if (userLocated) {
					const userIcon = L.divIcon({
						className: 'user-marker',
						html: '<div class="user-dot"></div>',
						iconSize: [20, 20],
						iconAnchor: [10, 10]
					});
					L.marker([userLat, userLng], { icon: userIcon })
						.addTo(map)
						.bindPopup(`<strong>${get(t)('communities.you_are_here')}</strong>`);
				}

				markerLayer = L.layerGroup().addTo(map);
				leaflet = L;
			} catch (e) {
				console.warn('Map initialization failed:', e);
			}
		})();

		return () => {
			map?.remove();
			map = null;
		};
	});

	// (Re)draw community markers whenever the map is ready or the data changes.
	$effect(() => {
		const L = leaflet;
		const list = communities;
		const mine = myIds;
		if (!L || !map) return;

		markerLayer.clearLayers();
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
			const icon = L.divIcon({
				className: 'community-marker',
				html: `<div class="community-dot ${ringClass}" style="background:${color};width:${size}px;height:${size}px"><span>${c.member_count}</span></div>`,
				iconSize: [size, size],
				iconAnchor: [size / 2, size / 2]
			});
			L.marker([c.latitude, c.longitude], { icon })
				.addTo(markerLayer)
				.bindPopup(`
					<strong>${c.name}</strong>${isMine ? ` (${get(t)('communities.your_community_paren')})` : ''}<br/>
					${c.city} (${c.postal_code})<br/>
					${get(t)('communities.map_popup_counts', { values: { members: c.member_count, items: c.resource_count, skills: c.skill_count } })}<br/>
					<a href="/communities/${c.id}">${get(t)('communities.view_community')}</a>
				`);
		}

		// Center on the user's own community once, when it has coordinates.
		if (!centeredOnMine) {
			const home = list.find((c) => mine.has(c.id) && c.latitude != null && c.longitude != null);
			if (home) {
				map.setView([home.latitude, home.longitude], 12);
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

	/* ── Custom Leaflet markers ──────────────── */

	:global(.user-marker) {
		background: none !important;
		border: none !important;
	}

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
		background: none !important;
		border: none !important;
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

	@media (max-width: 640px) {
		.map-container {
			height: 320px;
		}
	}
</style>
