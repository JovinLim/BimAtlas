<script lang="ts">
  import type { Snippet } from "svelte";

  let { children }: { children: Snippet } = $props();
</script>

<svelte:head>
  <title>Schema • BimAtlas</title>
</svelte:head>

{@render children()}
