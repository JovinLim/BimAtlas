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
    /* Brand: Deep Slate & Architectural Bronze */
    --color-brand-500: #1e293b;
    --color-brand-400: #334155;
    --color-brand-gradient-start: #0f172a;
    --color-brand-gradient-end: #334155;

    /* Backgrounds: Warm Sand & Stone */
    --color-bg-canvas: #f8f8f2;
    --color-bg-surface: #ffffff;
    --color-bg-elevated: #f1f1eb;

    /* Typography: Technical Ink */
    --color-text-primary: #0f172a;
    --color-text-secondary: #64748b;
    --color-text-muted: #94a3b8;

    /* Borders & Geometry: Technical Graphite */
    --color-border-subtle: #e2e2da;
    --color-border-default: #cbd5e1;
    --color-border-strong: #1e293b;

    /* Functional: Muted Professional Tones */
    --color-action-primary: #334155;
    --color-warning: #b45309;
    --color-danger: #991b1b;
    --color-danger-soft: #fee2e2;
    --color-info: #475569;

    /* IFC & Graph Specifics */
    --color-success: #334155;
    --color-graph-node: #78350f;
    --color-graph-edge: #d4d4ce;
  }

  :global(*),
  :global(*::-webkit-scrollbar) {
    scrollbar-width: thin;
    scrollbar-color: rgba(0, 0, 0, 0.18) transparent;
  }

  :global(html) {
    color-scheme: light;
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
