<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    children,
  }: {
    children?: Snippet;
  } = $props();

  let open = $state(true);
  const MIN_WIDTH = 150;
  const MAX_WIDTH = 450;
  let sidebarWidth = $state(300);
  let resizing = $state(false);
  let startX = 0;
  let startWidth = 0;
  let resizeHandleEl = $state<HTMLDivElement | null>(null);

  function onResizePointerDown(e: PointerEvent) {
    if (e.button !== 0) return;
    const el = e.currentTarget as HTMLDivElement;
    el.setPointerCapture(e.pointerId);
    resizing = true;
    startX = e.clientX;
    startWidth = sidebarWidth;
  }

  function onResizePointerMove(e: PointerEvent) {
    if (!resizing) return;
    const dx = e.clientX - startX;
    sidebarWidth = Math.round(
      Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + dx)),
    );
  }

  function onResizePointerUp(e: PointerEvent) {
    if (e.button !== 0) return;
    resizing = false;
    resizeHandleEl?.releasePointerCapture?.(e.pointerId);
  }
</script>

<svelte:window
  onpointermove={onResizePointerMove}
  onpointerup={onResizePointerUp}
  onpointercancel={onResizePointerUp}
/>

<div
  class="sidebar-container"
  class:collapsed={!open}
  class:resizing
  style="width: {open ? sidebarWidth : 0}px"
>
  <aside class="sidebar">
    {#if open}
      <div class="sidebar-content">
        {#if children}{@render children()}{/if}
      </div>
    {/if}
  </aside>
  {#if open}
    <div
      bind:this={resizeHandleEl}
      class="resize-handle"
      role="separator"
      aria-label="Resize sidebar"
      tabindex="-1"
      onpointerdown={onResizePointerDown}
    ></div>
  {/if}
  <button
    class="toggle-btn"
    onclick={() => (open = !open)}
    aria-label={open ? "Collapse sidebar" : "Expand sidebar"}
  >
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      {#if open}
        <path
          d="M9 2L4 7L9 12"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      {:else}
        <path
          d="M5 2L10 7L5 12"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      {/if}
    </svg>
  </button>
</div>

<style>
  .sidebar-container {
    position: relative;
    height: 100%;
    transition: width 0.2s ease;
    pointer-events: auto;
  }

  .sidebar-container.collapsed {
    width: 0;
  }

  .sidebar-container.resizing {
    transition: none;
  }

  .resize-handle {
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    width: 6px;
    cursor: col-resize;
    z-index: 1;
  }

  .resize-handle:hover,
  .sidebar-container.resizing .resize-handle {
    background: rgba(255, 136, 102, 0.15);
  }

  .sidebar {
    inset: 0;
    height: 100%;
    background: #1a1a2e;
    border-right: 1px solid rgba(255, 255, 255, 0.06);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .toggle-btn {
    position: absolute;
    top: 50%;
    right: -24px;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #1a1a2e;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0 0.25rem 0.25rem 0;
    color: #888;
    cursor: pointer;
    padding: 0;
    z-index: 2;
    box-shadow: 2px 0 4px rgba(0, 0, 0, 0.2);
    transition:
      background 0.15s,
      color 0.15s;
  }

  .toggle-btn:hover {
    background: rgba(255, 102, 68, 0.2);
    color: #ff8866;
  }

  .sidebar-content {
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    overflow-y: auto;
    overflow-x: hidden;
  }
</style>
