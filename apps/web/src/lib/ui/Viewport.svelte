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
</script>

<div class="viewport" bind:this={viewportEl}>
  <canvas bind:this={canvas}></canvas>
</div>

<style>
  .viewport {
    width: 100%;
    height: 100%;
    overflow: hidden;
  }

  canvas {
    width: 100%;
    height: 100%;
    display: block;
  }
</style>
