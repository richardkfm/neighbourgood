<script lang="ts">
	import { onMount, onDestroy } from 'svelte';

	let canvasEl: HTMLCanvasElement;
	let cleanup: (() => void) | undefined;

	onMount(() => {
		const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		if (prefersReducedMotion || !canvasEl.getContext) return;

		const canvas = canvasEl;
		const context = canvas.getContext('2d');
		const parent = canvas.parentElement;
		if (!context || !parent) return;
		// Re-bind to definitely-non-null consts: TS loses the narrowing on
		// `context`/`parent` once they're read inside the closures below
		// (resize/frame), since those run later via requestAnimationFrame.
		const ctx: CanvasRenderingContext2D = context;
		const host: HTMLElement = parent;

		const dpr = Math.min(window.devicePixelRatio || 1, 2);
		let W = 0;
		let H = 0;
		let nodes: { x: number; y: number; vx: number; vy: number; r: number; hub: boolean }[] = [];
		let pulses: { path: number[]; seg: number; t: number }[] = [];
		const LINK_DIST = 150;
		let running = true;
		let lastSpawn = 0;
		let lastFrame = 0;
		let rafId = 0;
		let colors = { line: '#4f46e5', node: '#4f46e5', hub: '#7a5c47', pulse: '#4f46e5' };

		function readColors() {
			const styles = getComputedStyle(document.documentElement);
			const primary = styles.getPropertyValue('--color-primary').trim() || '#4f46e5';
			const accent = styles.getPropertyValue('--color-accent').trim() || '#7a5c47';
			colors = { line: primary, node: primary, hub: accent, pulse: primary };
		}

		function initNodes() {
			nodes = [];
			pulses = [];
			const count = Math.min(40, Math.max(16, Math.round((W * H) / 26000)));
			for (let i = 0; i < count; i++) {
				nodes.push({
					x: Math.random() * W,
					y: Math.random() * H,
					vx: (Math.random() - 0.5) * 0.22,
					vy: (Math.random() - 0.5) * 0.22,
					r: 1.6 + Math.random() * 1.4,
					hub: i % 9 === 0 // every ninth node is an accent "hub"
				});
			}
		}

		function resize() {
			const w = host.offsetWidth;
			const h = host.offsetHeight;
			// ignore tiny height changes (mobile browser chrome showing/hiding)
			if (w === W && Math.abs(h - H) < 80) return;
			W = w;
			H = h;
			canvas.width = W * dpr;
			canvas.height = H * dpr;
			ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
			initNodes();
		}

		function neighboursOf(idx: number, exclude: number[]) {
			const out: number[] = [];
			for (let j = 0; j < nodes.length; j++) {
				if (j === idx || exclude.indexOf(j) !== -1) continue;
				const dx = nodes[j].x - nodes[idx].x;
				const dy = nodes[j].y - nodes[idx].y;
				if (dx * dx + dy * dy < LINK_DIST * LINK_DIST) out.push(j);
			}
			return out;
		}

		// A pulse is a message hopping node-to-node through the mesh
		function spawnPulse() {
			if (!nodes.length) return;
			const start = Math.floor(Math.random() * nodes.length);
			const path = [start];
			for (let hop = 0; hop < 4; hop++) {
				const next = neighboursOf(path[path.length - 1], path);
				if (!next.length) break;
				path.push(next[Math.floor(Math.random() * next.length)]);
			}
			if (path.length > 1) pulses.push({ path, seg: 0, t: 0 });
		}

		function frame(now: number) {
			if (!running) return;
			rafId = requestAnimationFrame(frame);

			const dt = lastFrame ? Math.min(now - lastFrame, 34) : 16;
			lastFrame = now;
			ctx.clearRect(0, 0, W, H);

			let i, j, n;

			for (i = 0; i < nodes.length; i++) {
				n = nodes[i];
				n.x += n.vx * dt * 0.048;
				n.y += n.vy * dt * 0.048;
				if (n.x < -20) n.x = W + 20;
				if (n.x > W + 20) n.x = -20;
				if (n.y < -20) n.y = H + 20;
				if (n.y > H + 20) n.y = -20;
			}

			ctx.lineWidth = 1;
			ctx.strokeStyle = colors.line;
			for (i = 0; i < nodes.length; i++) {
				for (j = i + 1; j < nodes.length; j++) {
					const dx = nodes[j].x - nodes[i].x;
					const dy = nodes[j].y - nodes[i].y;
					const d2 = dx * dx + dy * dy;
					if (d2 < LINK_DIST * LINK_DIST) {
						ctx.globalAlpha = 0.13 * (1 - Math.sqrt(d2) / LINK_DIST);
						ctx.beginPath();
						ctx.moveTo(nodes[i].x, nodes[i].y);
						ctx.lineTo(nodes[j].x, nodes[j].y);
						ctx.stroke();
					}
				}
			}

			for (i = 0; i < nodes.length; i++) {
				n = nodes[i];
				ctx.globalAlpha = n.hub ? 0.75 : 0.4;
				ctx.fillStyle = n.hub ? colors.hub : colors.node;
				ctx.beginPath();
				ctx.arc(n.x, n.y, n.hub ? n.r + 1.2 : n.r, 0, Math.PI * 2);
				ctx.fill();
			}

			if (now - lastSpawn > 1600 && pulses.length < 4) {
				spawnPulse();
				lastSpawn = now;
			}

			for (i = pulses.length - 1; i >= 0; i--) {
				const p = pulses[i];
				let a = nodes[p.path[p.seg]];
				let b = nodes[p.path[p.seg + 1]];
				p.t += dt / 850;
				if (p.t >= 1) {
					p.t = 0;
					p.seg++;
					if (p.seg >= p.path.length - 1) {
						pulses.splice(i, 1);
						continue;
					}
					a = nodes[p.path[p.seg]];
					b = nodes[p.path[p.seg + 1]];
				}
				const x = a.x + (b.x - a.x) * p.t;
				const y = a.y + (b.y - a.y) * p.t;

				// brighten the segment being travelled
				ctx.globalAlpha = 0.35;
				ctx.strokeStyle = colors.pulse;
				ctx.lineWidth = 1.4;
				ctx.beginPath();
				ctx.moveTo(a.x, a.y);
				ctx.lineTo(b.x, b.y);
				ctx.stroke();

				// glowing message dot
				const glow = ctx.createRadialGradient(x, y, 0, x, y, 9);
				glow.addColorStop(0, colors.pulse);
				glow.addColorStop(1, 'rgba(0,0,0,0)');
				ctx.globalAlpha = 0.5;
				ctx.fillStyle = glow;
				ctx.beginPath();
				ctx.arc(x, y, 9, 0, Math.PI * 2);
				ctx.fill();

				ctx.globalAlpha = 0.95;
				ctx.fillStyle = colors.pulse;
				ctx.beginPath();
				ctx.arc(x, y, 2.2, 0, Math.PI * 2);
				ctx.fill();
			}

			ctx.globalAlpha = 1;
		}

		function setRunning(active: boolean) {
			if (active && !running) {
				running = true;
				lastFrame = 0;
				rafId = requestAnimationFrame(frame);
			} else if (!active) {
				running = false;
			}
		}

		readColors();
		resize();
		window.addEventListener('resize', resize);
		rafId = requestAnimationFrame(frame);

		// repaint with the right palette when the theme changes
		const themeObserver = new MutationObserver(readColors);
		themeObserver.observe(document.documentElement, {
			attributes: true,
			attributeFilter: ['data-theme']
		});

		// pause when the hero is off-screen or the tab is hidden
		let intersectionObserver: IntersectionObserver | undefined;
		if ('IntersectionObserver' in window) {
			intersectionObserver = new IntersectionObserver((entries) => {
				setRunning(entries[0].isIntersecting && !document.hidden);
			});
			intersectionObserver.observe(host);
		}
		const onVisibility = () => setRunning(!document.hidden);
		document.addEventListener('visibilitychange', onVisibility);

		cleanup = () => {
			running = false;
			cancelAnimationFrame(rafId);
			window.removeEventListener('resize', resize);
			themeObserver.disconnect();
			intersectionObserver?.disconnect();
			document.removeEventListener('visibilitychange', onVisibility);
		};
	});

	onDestroy(() => cleanup?.());
</script>

<canvas bind:this={canvasEl} class="mesh-canvas" aria-hidden="true"></canvas>

<style>
	.mesh-canvas {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		pointer-events: none;
	}
</style>
