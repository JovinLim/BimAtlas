<script lang="ts">
  /**
   * Core 3D engine component with snippet-based extensibility.
   * Manages SceneManager lifecycle, ResizeObserver, and click-to-select binding.
   * Parent can bind to `manager` to load elements into the scene.
   */
  import { SceneManager } from "$lib/engine/SceneManager";
  import { getSelection } from "$lib/state/selection.svelte";

  let {
    manager = $bindable<SceneManager | undefined>(undefined),
  }: {
    manager?: SceneManager;
  } = $props();

  let viewportEl: HTMLDivElement;
  let canvas: HTMLCanvasElement;
  const selection = getSelection();

  // Initialize SceneManager when canvas mounts
  $effect(() => {
    if (!canvas) return;
    const mgr = new SceneManager(canvas);
    mgr.setClickCallback((globalId) => {
      selection.activeGlobalId = globalId;
    });
    manager = mgr;
    return () => {
      mgr.dispose();
      manager = undefined;
    };
  });

  // Highlight / visibility is driven by the page-level subgraph filter effect
  // via sceneManager.applySubgraphFilter(). No per-viewport highlight needed.

  // ResizeObserver for responsive canvas sizing
  $effect(() => {
    if (!viewportEl || !manager) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        manager?.resize(width, height);
      }
    });
    ro.observe(viewportEl);
    return () => ro.disconnect();
  });

  let projectionIsometric = $state(false);

  function toggleProjection(): void {
    if (!manager) return;
    projectionIsometric = !projectionIsometric;
    manager.setProjectionMode(projectionIsometric);
  }

  $effect(() => {
    if (manager) {
      projectionIsometric = manager.projectionIsometric;
    }
  });
</script>

<div class="viewport" bind:this={viewportEl}>
  <canvas bind:this={canvas}></canvas>
  {#if manager}
    <div class="gumball-controls">
      <button
        type="button"
        class="projection-toggle"
        onclick={toggleProjection}
        title={projectionIsometric ? "Switch to perspective" : "Switch to isometric"}
      >
        {projectionIsometric ? "Isometric" : "Perspective"}
      </button>
    </div>
  {/if}
</div>

<style>
  .viewport {
    width: 100%;
    height: 100%;
    overflow: hidden;
    position: relative;
  }

  canvas {
    width: 100%;
    height: 100%;
    display: block;
  }

  .gumball-controls {
    position: absolute;
    top: 16px;
    right: 16px;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 4px;
    pointer-events: auto;
  }

  .projection-toggle {
    padding: 4px 12px;
    min-width: 5.5rem;
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--color-text-muted, #64748b);
    background: color-mix(in srgb, var(--color-bg-surface, #fff) 95%, transparent);
    border: 1px solid var(--color-border-subtle, #e2e8f0);
    border-radius: 6px;
    cursor: pointer;
    transition: color 0.15s, background 0.15s;
  }

  .projection-toggle:hover {
    color: var(--color-text-primary, #0f172a);
    background: var(--color-bg-surface, #fff);
  }
</style>
