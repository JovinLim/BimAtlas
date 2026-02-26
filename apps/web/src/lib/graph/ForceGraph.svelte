<script lang="ts">
  /**
   * Wraps 3d-force-graph in a Svelte 5 component.
   * Dynamically imports the library (SSR-safe), binds node clicks to the shared
   * selection state, and reacts to graph data changes from the store.
   */
  import { getSelection, getProjectState } from "$lib/state/selection.svelte";
  import { getGraphStore, type GraphNode } from "$lib/graph/graphStore.svelte";

  const selection = getSelection();
  const projectState = getProjectState();
  const graphStore = getGraphStore();

  let container: HTMLDivElement;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let graph: any;

  /** Colour map keyed by IFC class. */
  const NODE_COLORS: Record<string, string> = {
    IfcProject: "#ff9900",
    IfcSite: "#66bb6a",
    IfcBuilding: "#42a5f5",
    IfcBuildingStorey: "#ab47bc",
    IfcSpace: "#26c6da",
    IfcWall: "#8899aa",
    IfcSlab: "#78909c",
    IfcBeam: "#a1887f",
    IfcColumn: "#90a4ae",
    IfcDoor: "#ffca28",
    IfcWindow: "#4dd0e1",
    IfcRoof: "#ef5350",
    IfcStair: "#7e57c2",
    IfcRailing: "#b0bec5",
    IfcCovering: "#9e9e9e",
    IfcCurtainWall: "#80cbc4",
    IfcPlate: "#a5d6a7",
    IfcMember: "#bcaaa4",
    IfcFooting: "#8d6e63",
    IfcPile: "#6d4c41",
  };

  const SPATIAL_CLASSES = new Set([
    "IfcProject",
    "IfcSite",
    "IfcBuilding",
    "IfcBuildingStorey",
    "IfcSpace",
  ]);

  function getNodeColor(node: GraphNode): string {
    return NODE_COLORS[node.ifcClass] ?? "#8899aa";
  }

  function getNodeSize(node: GraphNode): number {
    return SPATIAL_CLASSES.has(node.ifcClass) ? 4 : 1.5;
  }

  // Initialize 3d-force-graph (dynamic import for SSR safety)
  $effect(() => {
    if (!container) return;

    let mounted = true;

    import("3d-force-graph").then(({ default: ForceGraph3D }) => {
      if (!mounted) return;

      const w = container.clientWidth || 400;
      const h = container.clientHeight || 400;

      graph = ForceGraph3D()(container)
        .nodeId("id")
        .nodeLabel(
          (node: GraphNode) => `<b>${node.ifcClass}</b><br/>${node.name}`,
        )
        .nodeColor((node: GraphNode) => getNodeColor(node))
        .nodeVal((node: GraphNode) => getNodeSize(node))
        .nodeOpacity(0.9)
        .linkDirectionalArrowLength(3.5)
        .linkDirectionalArrowRelPos(1)
        .linkColor(() => "rgba(100,130,160,0.4)")
        .linkWidth(0.5)
        .onNodeClick((node: GraphNode) => {
          selection.activeGlobalId = node.id;
        })
        .backgroundColor("#1a1a2e")
        .width(w)
        .height(h);

      // If data is already loaded, apply it
      const data = graphStore.data;
      if (data.nodes.length > 0) {
        graph.graphData(data);
      }
    });

    return () => {
      mounted = false;
      if (graph) {
        if (typeof graph._destructor === "function") {
          graph._destructor();
        }
        graph = undefined;
      }
      // Clear leftover DOM created by the library
      if (container) {
        container.innerHTML = "";
      }
    };
  });

  // React to graph data changes
  $effect(() => {
    const data = graphStore.data;
    if (graph && data.nodes.length > 0) {
      graph.graphData(data);
    }
  });

  // ResizeObserver to keep graph sized correctly
  $effect(() => {
    if (!container || !graph) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        graph?.width(width);
        graph?.height(height);
      }
    });
    ro.observe(container);
    return () => ro.disconnect();
  });
</script>

<div class="force-graph-container" bind:this={container}>
  {#if graphStore.loading}
    <div class="overlay-msg">Loading graph&hellip;</div>
  {:else if graphStore.error}
    <div class="overlay-msg error">
      <span>Failed to load graph</span>
      <button class="retry-btn" onclick={() => { if (projectState.activeBranchId) graphStore.fetchGraph(projectState.activeBranchId); }}
        >Retry</button
      >
    </div>
  {:else if graphStore.data.nodes.length === 0}
    <div class="overlay-msg">
      <span>No graph data yet</span>
      <button class="retry-btn" onclick={() => { if (projectState.activeBranchId) graphStore.fetchGraph(projectState.activeBranchId); }}
        >Load Graph</button
      >
    </div>
  {/if}
</div>

<style>
  .force-graph-container {
    width: 100%;
    height: 100%;
    position: relative;
    min-height: 0;
  }

  .overlay-msg {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    color: #999;
    font-family:
      system-ui,
      -apple-system,
      sans-serif;
    font-size: 0.9rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    z-index: 5;
    pointer-events: all;
  }

  .overlay-msg.error {
    color: #e57373;
  }

  .retry-btn {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.15);
    color: #ccc;
    padding: 0.4rem 1rem;
    border-radius: 0.3rem;
    cursor: pointer;
    font-size: 0.82rem;
  }
  .retry-btn:hover {
    background: rgba(255, 255, 255, 0.14);
    color: #fff;
  }
</style>
