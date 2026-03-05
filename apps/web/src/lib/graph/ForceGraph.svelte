<script lang="ts">
  /**
   * Wraps 3d-force-graph in a Svelte 5 component.
   * Dynamically imports the library (SSR-safe), binds node clicks to the shared
   * selection state (or optional onNodeClick), and reacts to graph data from the
   * store or optional filtered data prop.
   */
  import { getSelection, getProjectState } from "$lib/state/selection.svelte";
  import { getGraphStore, type GraphNode, type GraphLink, type GraphData } from "$lib/graph/graphStore.svelte";

  let {
    data: dataProp = undefined,
    emptyMessage = undefined,
    onNodeClick = undefined,
    selectedId: selectedIdProp = undefined,
  }: {
    data?: GraphData | null;
    emptyMessage?: string;
    onNodeClick?: (id: string) => void;
    /** When provided (e.g. in popup), this id is highlighted in orange; otherwise selection.activeGlobalId is used. */
    selectedId?: string | null;
  } = $props();

  const selection = getSelection();
  const projectState = getProjectState();
  const graphStore = getGraphStore();

  /** Use prop data when provided, otherwise store data. */
  const effectiveData = $derived(dataProp !== undefined && dataProp !== null ? dataProp : graphStore.data);

  /** Resolved selected node id (prop or store). */
  const selectedNodeId = $derived(
    selectedIdProp !== undefined ? selectedIdProp : selection.activeGlobalId,
  );

  let container: HTMLDivElement;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let graph: any;
  let graphReady = $state(false);

  const NODE_COLOR_SELECTED = "#ff8866";
  const NODE_COLOR_DEFAULT = "#8899aa";
  const LINK_COLOR = "rgba(135, 206, 235, 0.8)";

  const SPATIAL_CLASSES = new Set([
    "IfcProject",
    "IfcSite",
    "IfcBuilding",
    "IfcBuildingStorey",
    "IfcSpace",
  ]);

  function getNodeColor(node: GraphNode): string {
    return node.id === selectedNodeId ? NODE_COLOR_SELECTED : NODE_COLOR_DEFAULT;
  }

  function getNodeSize(node: GraphNode): number {
    return SPATIAL_CLASSES.has(node.ifcClass) ? 4 : 1.5;
  }

  function getLinkColor(_link: GraphLink): string {
    return LINK_COLOR;
  }

  // Initialize 3d-force-graph (dynamic import for SSR safety)
  $effect(() => {
    if (!container) return;

    let mounted = true;

    Promise.all([
      import("3d-force-graph"),
      import("three-spritetext"),
    ]).then(([{ default: ForceGraph3D }, SpriteTextModule]) => {
      if (!mounted) return;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const SpriteText = (SpriteTextModule as any).default as new (text: string) => { material: { depthWrite: boolean }; textHeight: number; color: string; position: { y: number; set: (x: number, y: number, z: number) => void } };

      const w = Math.max(container.clientWidth || 0, 400);
      const h = Math.max(container.clientHeight || 0, 400);
      console.log("[ForceGraph] init container dimensions", {
        clientWidth: container.clientWidth,
        clientHeight: container.clientHeight,
        using: { w, h },
      });

      /** Multiline label: one line per attribute (ifcClass, name, id). */
      function nodeDescription(node: GraphNode): string {
        const lines: string[] = [node.ifcClass];
        if (node.name && node.name !== node.ifcClass) lines.push(node.name);
        lines.push(node.id);
        return lines.join("\n");
      }

      const ForceGraphFactory = (ForceGraph3D as any)();
      graph = ForceGraphFactory(container)
        .nodeId("id")
        .nodeLabel(
          (node: GraphNode) => `<b>${node.ifcClass}</b><br/>${node.name}`,
        )
        .nodeThreeObjectExtend(true)
        .nodeThreeObject((node: GraphNode) => {
          const sprite = new SpriteText(nodeDescription(node));
          sprite.material.depthWrite = false;
          (sprite as any).material.depthTest = false;
          sprite.textHeight = 1.2;
          sprite.color = "#e0e0e0";
          // Lift text above the node so it never intersects the sphere visually.
          sprite.position.y = getNodeSize(node) + 2.0;
          (sprite as any).renderOrder = 999;
          return sprite;
        })
        .nodeColor((node: GraphNode) => getNodeColor(node))
        .nodeVal((node: GraphNode) => getNodeSize(node))
        .nodeOpacity(0.9)
        .linkLabel((link: GraphLink) => String(link.relType))
        .linkThreeObjectExtend(true)
        .linkThreeObject((link: GraphLink) => {
          const sprite = new SpriteText(String(link.relType));
          sprite.material.depthWrite = false;
          (sprite as any).material.depthTest = false;
          sprite.textHeight = 0.8;
          sprite.color = "#87CEEB";
          (sprite as any).renderOrder = 999;
          return sprite;
        })
        .linkPositionUpdate((obj: { position: { set: (x: number, y: number, z: number) => void } }, { start, end }: { start: { x: number; y?: number; z?: number }; end: { x: number; y?: number; z?: number } }) => {
          // Keep label at edge midpoint (same coords as the link line geometry)
          const x = start.x + (end.x - start.x) / 2;
          const y = (start.y ?? 0) + ((end.y ?? 0) - (start.y ?? 0)) / 2;
          const z = (start.z ?? 0) + ((end.z ?? 0) - (start.z ?? 0)) / 2;
          obj.position.set(x, y, z);
        })
        .linkDirectionalArrowLength(3.5)
        .linkDirectionalArrowRelPos(1)
        .linkColor((link: GraphLink) => getLinkColor(link))
        .linkWidth(0.5)
        .onNodeClick((node: GraphNode) => {
          if (onNodeClick) {
            onNodeClick(node.id);
          } else {
            selection.activeGlobalId = node.id;
          }
        })
        .backgroundColor("#f7f7f2")
        .width(w)
        .height(h);

      const canvas = container.querySelector("canvas");
      console.log("[ForceGraph] canvas after init", {
        hasCanvas: !!canvas,
        canvasWidth: canvas?.getAttribute("width"),
        canvasHeight: canvas?.getAttribute("height"),
        containerClientWidth: container.clientWidth,
        containerClientHeight: container.clientHeight,
      });

      graphReady = true;
    });

    return () => {
      mounted = false;
      graphReady = false;
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

  // React to graph data and selection; re-run when graph becomes ready or selectedNodeId changes (to update node colors)
  $effect(() => {
    const ready = graphReady;
    const data = effectiveData;
    const sel = selectedNodeId;
    void sel;
    console.log(
      "[ForceGraph] effect",
      "ready=",
      ready,
      "graph=",
      !!graph,
      "nodes=",
      data.nodes.length,
      "links=",
      data.links.length,
    );
    if (ready && graph && data.nodes.length > 0) {
      const w = Math.max(container?.clientWidth ?? 0, 400);
      const h = Math.max(container?.clientHeight ?? 0, 400);
      graph.width(w).height(h);
      graph.graphData(data);
      if (typeof graph.resumeAnimation === "function") {
        graph.resumeAnimation();
      }
      if (typeof graph.cameraPosition === "function") {
        graph.cameraPosition({ x: 0, y: 0, z: 450 }, undefined, 400);
      }
      if (typeof graph.zoomToFit === "function") {
        setTimeout(() => graph.zoomToFit(400), 100);
      }
      const canvas = container?.querySelector("canvas");
      console.log(
        "[ForceGraph] applied data and dimensions",
        "nodes=",
        data.nodes.length,
        "links=",
        data.links.length,
        "w=",
        w,
        "h=",
        h,
        "canvasAttrWidth=",
        canvas?.getAttribute("width"),
        "canvasAttrHeight=",
        canvas?.getAttribute("height"),
      );
    } else if (ready && graph && data.nodes.length === 0) {
      console.log("[ForceGraph] data has zero nodes; nothing to render");
    }
  });

  // ResizeObserver to keep graph sized correctly
  $effect(() => {
    if (!container || !graph) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        const w = Math.max(width, 400);
        const h = Math.max(height, 400);
        graph?.width(w).height(h);
      }
    });
    ro.observe(container);
    return () => ro.disconnect();
  });
</script>

<div class="force-graph-container" bind:this={container}>
  {#if dataProp === undefined || dataProp === null}
    <!-- Using store: show loading/error/store-empty -->
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
        <span>{emptyMessage ?? "No graph data yet"}</span>
        {#if !emptyMessage}
          <button class="retry-btn" onclick={() => { if (projectState.activeBranchId) graphStore.fetchGraph(projectState.activeBranchId); }}
            >Load Graph</button
          >
        {/if}
      </div>
    {/if}
  {:else}
    <!-- Using prop: show custom empty message when no nodes -->
    {#if emptyMessage && effectiveData.nodes.length === 0}
      <div class="overlay-msg">
        <span>{emptyMessage}</span>
      </div>
    {/if}
  {/if}

  {#if effectiveData.nodes.length > 0}
    <div class="graph-legend" aria-label="Graph legend">
      <div class="legend-item">
        <span class="legend-swatch" style="background-color: {NODE_COLOR_SELECTED}"></span>
        <span class="legend-label">Selected</span>
      </div>
      <div class="legend-item">
        <span class="legend-swatch" style="background-color: {NODE_COLOR_DEFAULT}"></span>
        <span class="legend-label">Nodes</span>
      </div>
      <div class="legend-item">
        <span class="legend-swatch legend-swatch--line" style="background-color: {LINK_COLOR}"></span>
        <span class="legend-label">Edges</span>
      </div>
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

  .force-graph-container :global(canvas) {
    display: block;
    width: 100% !important;
    height: 100% !important;
  }

  .graph-legend {
    position: absolute;
    top: 0.75rem;
    left: 0.75rem;
    z-index: 5;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    padding: 0.5rem 0.75rem;
    background: rgba(255, 255, 255, 0.92);
    border: 1px solid var(--color-border-default);
    border-radius: 0.35rem;
    font-size: 0.75rem;
    color: var(--color-text-secondary);
    pointer-events: none;
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .legend-swatch {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .legend-swatch--line {
    border-radius: 2px;
    height: 3px;
  }

  .legend-label {
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .overlay-msg {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--color-text-muted);
    font-family:
      system-ui,
      -apple-system,
      sans-serif;
    font-size: 0.9rem;
    flex-direction: column;
    gap: 0.75rem;
    z-index: 10;
    pointer-events: all;
    text-align: center;
    padding: 1rem;
  }

  .overlay-msg.error {
    color: var(--color-danger);
  }

  .retry-btn {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    color: var(--color-text-secondary);
    padding: 0.4rem 1rem;
    border-radius: 0.3rem;
    cursor: pointer;
    font-size: 0.82rem;
  }
  .retry-btn:hover {
    background: color-mix(in srgb, var(--color-text-primary) 8%, var(--color-bg-elevated));
    color: var(--color-text-primary);
  }
</style>
