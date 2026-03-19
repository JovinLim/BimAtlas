<script lang="ts">
/**
 * Dedicated viewer runtime container (Phase 3 of decoupling plan).
 * Encapsulates viewer-specific logic: SceneManager, geometry loading/abort,
 * render progress, projection mode, fit-to-content. Subscribes to workspace
 * state but does not own project/search/selection state.
 *
 * Replaces scattered logic in +page.svelte. Mounts Viewport only when needed.
 */

import { onDestroy } from "svelte";
import { createBufferGeometry } from "$lib/engine/BufferGeometryLoader";
import type { SceneManager } from "$lib/engine/SceneManager";
import type { ProductMeta } from "$lib/search/protocol";
import Viewport from "./Viewport.svelte";

let {
	workspace,
	branchId = null,
	revision = null,
	manager = $bindable<SceneManager | undefined>(undefined),
	reloadKey = 0,
}: {
	workspace: any;
	branchId?: string | null;
	revision?: number | null;
	manager?: SceneManager;
	reloadKey?: number;
} = $props();
let loadingGeometry = $state(false);
let loadingGeometryCurrent = $state(0);
let loadingGeometryTotal = $state(0);
let geometryAbortController = $state<AbortController | null>(null);
let overlayMounted = $state(false);
let overlayVisible = $state(false);
let overlayShownAt = $state<number | null>(null);
const OVERLAY_MIN_VISIBLE_MS = 1000;
const OVERLAY_FADE_MS = 220;
let overlayHideTimer: ReturnType<typeof setTimeout> | null = null;
let lastLoadSignature: string | null = null;
let activeLoadId = 0;

const loadingPercent = $derived.by(() => {
	if (!loadingGeometryTotal || loadingGeometryTotal <= 0) return 0;
	const raw = (loadingGeometryCurrent / loadingGeometryTotal) * 100;
	return Math.max(0, Math.min(100, Math.round(raw)));
});

function clearOverlayTimers() {
	if (overlayHideTimer) {
		clearTimeout(overlayHideTimer);
		overlayHideTimer = null;
	}
}

$effect(() => {
	const isLoading = loadingGeometry;
	if (isLoading) {
		clearOverlayTimers();
		if (!overlayMounted) {
			overlayMounted = true;
			requestAnimationFrame(() => {
				overlayVisible = true;
				overlayShownAt = Date.now();
			});
		} else if (!overlayVisible) {
			overlayVisible = true;
			overlayShownAt = Date.now();
		}
		return;
	}

	if (!overlayMounted) return;

	const elapsed =
		overlayShownAt == null
			? OVERLAY_MIN_VISIBLE_MS
			: Date.now() - overlayShownAt;
	const waitBeforeHide = Math.max(0, OVERLAY_MIN_VISIBLE_MS - elapsed);
	overlayHideTimer = setTimeout(() => {
		overlayVisible = false;
		overlayHideTimer = setTimeout(() => {
			overlayMounted = false;
			overlayShownAt = null;
		}, OVERLAY_FADE_MS);
	}, waitBeforeHide);
});

// Geometry loading effect (viewer-only, triggered by branch/revision + reload signals)
$effect(() => {
	void reloadKey;

	if (!manager || !branchId || revision == null) {
		loadingGeometry = false;
		return;
	}

	const loadSignature = `${branchId}:${revision}:${reloadKey}`;
	if (lastLoadSignature === loadSignature) return;
	lastLoadSignature = loadSignature;
	const loadId = ++activeLoadId;

	const abort = new AbortController();
	geometryAbortController = abort;
	loadingGeometry = true;
	loadingGeometryCurrent = 0;
	loadingGeometryTotal = 0;

	const apiBase =
		(import.meta.env.VITE_API_URL || "").replace("/graphql", "") ||
		"http://localhost:8000";
	const params = new URLSearchParams({
		branch_id: branchId,
		revision: String(revision),
	});
	const url = `${apiBase}/stream/ifc-products?${params.toString()}`;

	let cancelled = false;

	(async () => {
		try {
			const res = await fetch(url, { signal: abort.signal });
			if (!res.ok || !res.body)
				throw new Error("Failed to start geometry stream");

			manager.clearAll();
			const reader = res.body.getReader();
			const decoder = new TextDecoder();
			let buffer = "";
			const metaList: ProductMeta[] = [];
			let meshCount = 0;

			while (true) {
				const { done, value } = await reader.read();
				if (done || cancelled) break;
				if (value) buffer += decoder.decode(value, { stream: true });
				const lines = buffer.split("\n\n");
				buffer = lines.pop() ?? "";

				for (const chunk of lines) {
					const dataMatch = chunk.match(/^data:\s*(.+)$/s);
					if (!dataMatch) continue;

					const data = JSON.parse(dataMatch[1].trim());
					if (data.type === "start") {
						loadingGeometryTotal = data.total ?? 0;
					} else if (data.type === "product") {
						const p = data.product;
						loadingGeometryCurrent = data.current ?? metaList.length + 1;

						if (p.ifcClass === "IfcShapeRepresentation") continue;

						metaList.push({
							globalId: p.globalId,
							ifcClass: p.ifcClass,
							name: p.name ?? null,
							description: p.description ?? null,
							objectType: p.objectType ?? null,
							tag: p.tag ?? null,
							attributes: p.attributes ?? null,
						});

						if (p.mesh && p.mesh.vertices && p.mesh.faces) {
							try {
								const geometry = createBufferGeometry(p.mesh as any);
								manager.addElement(p.globalId, geometry);
								meshCount += 1;
							} catch (e) {
								console.warn(`Failed to load geometry for ${p.globalId}`, e);
							}
						}

						// Throttle to keep UI responsive
						await new Promise((r) => setTimeout(r, 0));
					} else if (data.type === "end") {
						break;
					}
				}
			}

			// Keep workspace products in sync for downstream consumers in popup context.
			if (typeof workspace?.setProducts === "function") {
				workspace.setProducts(metaList);
			}
			if (manager.elementCount > 0) {
				manager.fitToContent();
			}
			console.log(
				`[ViewerRuntime] Stream complete: ${metaList.length} products, ${meshCount} meshes rendered`,
			);
		} catch (err: any) {
			if (err.name !== "AbortError") {
				console.error("Geometry stream failed", err);
			}
		} finally {
			if (loadId === activeLoadId) {
				loadingGeometry = false;
				geometryAbortController = null;
			}
		}
	})();

	return () => {
		cancelled = true;
		abort.abort();
	};
});

// Selection ghosting behavior: keep selected item highlighted and ghost the rest.
// Reuses the existing SceneManager subgraph filter implementation by passing
// a singleton subgraph containing only the selected element.
$effect(() => {
	if (!manager) return;
	const gid = workspace.activeGlobalId;
	if (!gid) {
		manager.applySubgraphFilter(null, null);
		return;
	}
	manager.applySubgraphFilter(gid, new Set([gid]));
});

// Projection / controls exposed (uses SceneManager API)
export function fitToContent() {
	manager?.fitToContent();
}

export function toggleProjection() {
	if (manager) {
		const current = manager.projectionIsometric;
		manager.setProjectionMode(!current);
	}
}

onDestroy(() => {
	geometryAbortController?.abort();
	clearOverlayTimers();
});
</script>

<div class="viewer-runtime">
  <div class="canvas-stage">
    <Viewport bind:manager={manager} />

    {#if overlayMounted}
      <div class="loading-overlay" class:visible={overlayVisible}>
        <div class="loading-card" role="status" aria-live="polite">
          <p class="loading-title">Loading IFC geometry</p>
          <p class="loading-percent">{loadingPercent}%</p>
          <p class="loading-count">({loadingGeometryCurrent}/{loadingGeometryTotal})</p>
          <div class="loading-progress" aria-hidden="true">
            <div class="loading-progress-bar" style={`width: ${loadingPercent}%`}></div>
          </div>
        </div>
      </div>
    {/if}
  </div>
</div>

<style>
  .viewer-runtime {
    width: 100%;
    height: 100%;
  }

  .canvas-stage {
    position: relative;
    width: 100%;
    height: 100%;
    overflow: hidden;
  }

  .loading-overlay {
    position: absolute;
    inset: 0;
    background: color-mix(in srgb, var(--color-brand-500) 35%, transparent);
    color: var(--color-text-primary);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 50;
    opacity: 0;
    transition: opacity 220ms ease;
    pointer-events: none;
  }

  .loading-overlay.visible {
    opacity: 1;
  }

  .loading-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    padding: 1rem 1.25rem;
    border-radius: 0.9rem;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-default);
    box-shadow: 0 10px 24px color-mix(in srgb, var(--color-brand-500) 16%, transparent);
    min-width: 14rem;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    transform: translateY(6px) scale(0.985);
    transition: transform 220ms ease;
  }

  .loading-overlay.visible .loading-card {
    transform: translateY(0) scale(1);
  }

  .loading-title {
    margin: 0;
    font-size: 0.74rem;
    color: var(--color-text-secondary);
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .loading-percent {
    margin: 0;
    font-size: 1.85rem;
    font-weight: 700;
    line-height: 1;
    color: var(--color-text-primary);
    letter-spacing: -0.02em;
  }

  .loading-count {
    margin: 0;
    font-size: 0.82rem;
    color: var(--color-text-secondary);
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }

  .loading-progress {
    width: 100%;
    height: 0.375rem;
    margin-top: 0.35rem;
    border-radius: 9999px;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-subtle);
    overflow: hidden;
  }

  .loading-progress-bar {
    height: 100%;
    background: var(--color-action-primary);
    transition: width 140ms ease;
  }
</style>
