<script lang="ts">
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();
</script>

<svelte:head>
	<title>BimAtlas</title>
	<meta name="description" content="Extensible Spatial-Graph Engine for IFC models" />
</svelte:head>

{@render children()}
