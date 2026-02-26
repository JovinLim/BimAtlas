<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    children,
  }: {
    children?: Snippet;
  } = $props();

  let open = $state(true);
</script>

<div class="sidebar-container" class:collapsed={!open}>
  <aside class="sidebar">
    {#if open}
      <div class="sidebar-content">
        {#if children}{@render children()}{/if}
      </div>
    {/if}
  </aside>
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
    width: 220px;
    transition: width 0.2s ease;
    pointer-events: auto;
  }

  .sidebar-container.collapsed {
    width: 0px;
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
  }
</style>
