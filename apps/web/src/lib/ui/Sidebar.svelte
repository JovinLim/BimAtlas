<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    children,
  }: {
    children?: Snippet;
  } = $props();

  let open = $state(false);
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
    background: color-mix(in srgb, var(--color-bg-surface) 15%, var(--color-brand-500));
  }

  .sidebar {
    inset: 0;
    height: 100%;
    background: var(--color-brand-500);
    border-right: 1px solid color-mix(in srgb, var(--color-bg-surface) 12%, var(--color-brand-500));
    display: flex;
    flex-direction: column;
    overflow: hidden;
    color: color-mix(in srgb, var(--color-bg-surface) 90%, transparent);
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
    background: var(--color-brand-500);
    border: 1px solid color-mix(in srgb, var(--color-bg-surface) 20%, var(--color-brand-500));
    border-radius: 0 0.25rem 0.25rem 0;
    color: color-mix(in srgb, var(--color-bg-surface) 80%, transparent);
    cursor: pointer;
    padding: 0;
    z-index: 2;
    box-shadow: 2px 0 4px color-mix(in srgb, var(--color-text-primary) 20%, transparent);
    transition:
      background 0.15s,
      color 0.15s;
  }

  .toggle-btn:hover {
    background: var(--color-brand-400);
    color: var(--color-bg-surface);
  }

  .sidebar-content {
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    overflow-y: auto;
    overflow-x: hidden;
  }

  /* Sidebar content overrides for dark brand background */
  .sidebar :global(.sidebar-section-heading) {
    color: color-mix(in srgb, var(--color-bg-surface) 70%, transparent);
  }

  .sidebar :global(.toolbar-btn) {
    background: color-mix(in srgb, var(--color-bg-surface) 12%, var(--color-brand-500));
    border-color: color-mix(in srgb, var(--color-bg-surface) 20%, var(--color-brand-500));
    color: color-mix(in srgb, var(--color-bg-surface) 95%, transparent);
  }

  .sidebar :global(.toolbar-btn:hover) {
    background: color-mix(in srgb, var(--color-bg-surface) 20%, var(--color-brand-500));
    color: var(--color-bg-surface);
  }

  .sidebar :global(.revision-filter-group-header),
  .sidebar :global(.revision-filter-checkbox),
  .sidebar :global(.filter-row-label) {
    color: color-mix(in srgb, var(--color-bg-surface) 80%, transparent);
  }

  .sidebar :global(.revision-filter-group-header:hover) {
    color: color-mix(in srgb, var(--color-bg-surface) 95%, transparent);
  }

  .sidebar :global(.revision-filter-input),
  .sidebar :global(.revision-date-input) {
    background: color-mix(in srgb, var(--color-bg-surface) 8%, var(--color-brand-500));
    border-color: color-mix(in srgb, var(--color-bg-surface) 18%, var(--color-brand-500));
    color: color-mix(in srgb, var(--color-bg-surface) 95%, transparent);
  }

  .sidebar :global(.revision-filter-input::placeholder),
  .sidebar :global(.revision-date-input::placeholder) {
    color: color-mix(in srgb, var(--color-bg-surface) 50%, transparent);
  }

  .sidebar :global(.revision-filter-input:focus),
  .sidebar :global(.revision-date-input:focus) {
    border-color: color-mix(in srgb, var(--color-bg-surface) 35%, var(--color-brand-500));
  }

  .sidebar :global(.revision-loading),
  .sidebar :global(.revision-empty),
  .sidebar :global(.revision-results-heading) {
    color: color-mix(in srgb, var(--color-bg-surface) 60%, transparent);
  }

  .sidebar :global(.revision-item) {
    background: color-mix(in srgb, var(--color-bg-surface) 8%, var(--color-brand-500));
    color: color-mix(in srgb, var(--color-bg-surface) 90%, transparent);
  }

  .sidebar :global(.revision-item:hover) {
    background: color-mix(in srgb, var(--color-bg-surface) 15%, var(--color-brand-500));
  }

  .sidebar :global(.revision-item--current) {
    background: color-mix(in srgb, var(--color-action-primary) 25%, var(--color-brand-500));
    border-color: color-mix(in srgb, var(--color-action-primary) 50%, var(--color-brand-500));
    color: var(--color-bg-surface);
  }

  .sidebar :global(.revision-current-label),
  .sidebar :global(.revision-item--current .revision-seq) {
    color: color-mix(in srgb, var(--color-bg-surface) 90%, transparent);
  }

  .sidebar :global(.revision-seq),
  .sidebar :global(.revision-filename),
  .sidebar :global(.revision-label),
  .sidebar :global(.revision-author) {
    color: color-mix(in srgb, var(--color-bg-surface) 85%, transparent);
  }

  .sidebar :global(.revision-current-not-in-filter) {
    color: color-mix(in srgb, var(--color-bg-surface) 60%, transparent);
  }

  .sidebar :global(.revision-filter-checkbox input) {
    accent-color: var(--color-action-primary);
  }

  .sidebar :global(.depth-widget .label) {
    color: color-mix(in srgb, var(--color-bg-surface) 70%, transparent);
  }

  .sidebar :global(.depth-widget .stepper) {
    background: color-mix(in srgb, var(--color-bg-surface) 10%, var(--color-brand-500));
    border-color: color-mix(in srgb, var(--color-bg-surface) 20%, var(--color-brand-500));
  }

  .sidebar :global(.depth-widget .step-btn) {
    color: color-mix(in srgb, var(--color-bg-surface) 90%, transparent);
  }

  .sidebar :global(.depth-widget .step-btn:hover:not(:disabled)) {
    background: color-mix(in srgb, var(--color-bg-surface) 18%, var(--color-brand-500));
    color: var(--color-bg-surface);
  }

  .sidebar :global(.depth-widget .value-input) {
    color: color-mix(in srgb, var(--color-bg-surface) 95%, transparent);
  }
</style>
