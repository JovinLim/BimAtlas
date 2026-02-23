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
    background: #12121e;
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
