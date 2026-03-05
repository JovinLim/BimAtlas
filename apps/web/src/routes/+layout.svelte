<script lang="ts">
  import type { Snippet } from "svelte";

  let { children }: { children: Snippet } = $props();
</script>

<svelte:head>
  <title>BimAtlas</title>
  <meta
    name="description"
    content="Extensible Spatial-Graph Engine for IFC models"
  />
</svelte:head>

{@render children()}

<style>
  :root {
    --color-brand-500: #ff8866;
    --color-brand-400: #ffaa88;
    --color-brand-gradient-start: #ff6644;
    --color-brand-gradient-end: #ff9966;

    --color-bg-canvas: #12121e;
    --color-bg-surface: #1a1a2e;
    --color-bg-elevated: #1e1e30;

    --color-text-primary: #e0e0e0;
    --color-text-secondary: #ccc;
    --color-text-muted: #888;

    --color-border-subtle: rgba(255, 255, 255, 0.06);
    --color-border-default: rgba(255, 255, 255, 0.1);
    --color-border-strong: rgba(255, 136, 102, 0.3);

    --color-warning: #c9a227;
    --color-danger: #ff6b6b;
    --color-danger-soft: #ee8888;
    --color-info: #87ceeb;
  }

  /* Thin, macOS-style scrollbars globally (Firefox: all elements; WebKit: pseudo-elements below) */
  :global(*),
  :global(*::-webkit-scrollbar) {
    scrollbar-width: thin;
    scrollbar-color: rgba(128, 128, 128, 0.4) transparent;
  }

  :global(html, body) {
    margin: 0;
    padding: 0;
    height: 100%;
    overflow: hidden;
    background: var(--color-bg-canvas);
    color: var(--color-text-primary);
  }

  :global(h1, h2, h3, h4, h5, h6) {
    margin: 0;
    margin-block: 0;
  }

  :global(::-webkit-scrollbar) {
    width: 8px;
    height: 8px;
  }

  :global(::-webkit-scrollbar-track) {
    background: transparent;
  }

  :global(::-webkit-scrollbar-thumb) {
    background: rgba(128, 128, 128, 0.4);
    border-radius: 4px;
  }

  :global(::-webkit-scrollbar-thumb:hover) {
    background: rgba(128, 128, 128, 0.6);
  }

  :global(::-webkit-scrollbar-corner) {
    background: transparent;
  }
</style>
