<script lang="ts">
  import type { Snippet } from "svelte";

  let { children }: { children: Snippet } = $props();
</script>

<svelte:head>
  <title>Views • BimAtlas</title>
</svelte:head>

{@render children()}
