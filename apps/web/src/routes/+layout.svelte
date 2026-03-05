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
    --color-brand-500: #334155;
    --color-brand-400: #64748b;
    --color-brand-gradient-start: #1e293b;
    --color-brand-gradient-end: #475569;

    --color-bg-canvas: #f7f7f2;
    --color-bg-surface: #ffffff;
    --color-bg-elevated: #efefe9;

    --color-text-primary: #0f172a;
    --color-text-secondary: #475569;
    --color-text-muted: #94a3b8;

    --color-border-subtle: #e5e5e0;
    --color-border-default: #d4d4ce;
    --color-border-strong: #334155;

    --color-warning: #b45309;
    --color-danger: #991b1b;
    --color-danger-soft: #fee2e2;
    --color-info: #0369a1;

    --color-success: #166534;
    --color-accent-bronze: #78350f;
  }

  :global(*),
  :global(*::-webkit-scrollbar) {
    scrollbar-width: thin;
    scrollbar-color: rgba(0, 0, 0, 0.18) transparent;
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
    background: rgba(0, 0, 0, 0.18);
    border-radius: 4px;
  }

  :global(::-webkit-scrollbar-thumb:hover) {
    background: rgba(0, 0, 0, 0.28);
  }

  :global(::-webkit-scrollbar-corner) {
    background: transparent;
  }
</style>
