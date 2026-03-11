<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { page } from "$app/stores";
  import ForceGraph from "$lib/graph/ForceGraph.svelte";
  import { getGraphStore } from "$lib/graph/graphStore.svelte";
  import { computeSubgraph } from "$lib/graph/subgraph";
  import type { GraphData, GraphNode, GraphLink } from "$lib/graph/graphStore.svelte";
  import {
    GRAPH_CHANNEL,
    type GraphMessage,
  } from "$lib/graph/protocol";
  import { loadSettings, saveSettings } from "$lib/state/persistence";
  import DepthWidget from "$lib/ui/DepthWidget.svelte";

  const EMPTY_MESSAGE =
    "Please select an object and adjust the Subgraph Depth option above.";

  let branchId = $state<string | null>(null);
  let projectId = $state<string | null>(null);
  let branchName = $state<string | null>(null);
  let projectName = $state<string | null>(null);
  let revision = $state<number | null>(null);
  let globalId = $state<string | null>(null);
  let subgraphDepth = $state(1);

  const graphStore = getGraphStore();

  let channel: BroadcastChannel | null = null;
  let contextRetryTimeout: ReturnType<typeof setTimeout> | null = null;
  let contextRetryInterval: ReturnType<typeof setInterval> | null = null;
  let lastFetchedBranchId = $state<string | null>(null);
  let lastFetchedRevision = $state<number | null>(null);

  function applyContextFromUrl() {
    const url = $page.url;
    const b = url.searchParams.get("branchId");
    const p = url.searchParams.get("projectId");
    const r = url.searchParams.get("revision");
    const g = url.searchParams.get("globalId");
    const d = url.searchParams.get("subgraphDepth");
    if (b != null && b !== "") branchId = b;
    if (p != null && p !== "") projectId = p;
    if (r != null && r !== "") {
      const parsed = Number(r);
      revision = Number.isNaN(parsed) ? null : parsed;
    }
    if (g != null && g !== "") globalId = g;
    if (d != null && d !== "") {
      const parsed = Number(d);
      if (!Number.isNaN(parsed) && parsed >= 0) subgraphDepth = parsed;
    }
  }

  function applyContextFallbackFromSettings() {
    const settings = loadSettings();
    if (!settings) return;
    if (branchId == null && settings.activeBranchId != null) {
      branchId = settings.activeBranchId;
    }
    if (projectId == null && settings.activeProjectId != null) {
      projectId = settings.activeProjectId;
    }
    if (revision == null && settings.activeRevision != null) {
      revision = settings.activeRevision;
    }
    if (globalId == null && settings.activeGlobalId != null) {
      globalId = settings.activeGlobalId;
    }
    if (settings.subgraphDepth != null && settings.subgraphDepth >= 0) {
      subgraphDepth = settings.subgraphDepth;
    }
  }

  function handleIncomingMessage(e: MessageEvent<GraphMessage>) {
    const msg = e.data;
    if (msg.type === "context") {
      branchId = msg.branchId;
      projectId = msg.projectId;
      branchName = msg.branchName ?? null;
      projectName = msg.projectName ?? null;
      revision = msg.revision;
      globalId = msg.globalId;
      subgraphDepth = msg.subgraphDepth;

      const params = new URLSearchParams($page.url.searchParams);
      if (branchId != null) params.set("branchId", String(branchId));
      else params.delete("branchId");
      if (projectId != null) params.set("projectId", String(projectId));
      else params.delete("projectId");
      if (revision != null) params.set("revision", String(revision));
      else params.delete("revision");
      if (globalId != null) params.set("globalId", String(globalId));
      else params.delete("globalId");
      params.set("subgraphDepth", String(subgraphDepth));
      window.history.replaceState(
        null,
        "",
        `${$page.url.pathname}?${params.toString()}`,
      );

      if (contextRetryInterval != null) {
        clearInterval(contextRetryInterval);
        contextRetryInterval = null;
      }
    }
  }

  function requestContext() {
    channel?.postMessage({ type: "request-context" } satisfies GraphMessage);
  }

  function handleNodeClick(id: string) {
    channel?.postMessage({
      type: "selection-changed",
      globalId: id,
    } satisfies GraphMessage);
  }

  /** Map selected node to owning product when it is a synthetic IfcShapeRepresentation. */
  function effectiveSelectedId(graph: GraphData, selectedId: string): string {
    for (const link of graph.links) {
      const src =
        typeof link.source === "object"
          ? (link.source as { id: string }).id
          : link.source;
      const tgt =
        typeof link.target === "object"
          ? (link.target as { id: string }).id
          : link.target;
      if (link.relType === "HasShapeRepresentation" && tgt === selectedId) {
        return src;
      }
    }
    return selectedId;
  }

  function filterGraphToIds(
    graph: GraphData,
    ids: Set<string>,
  ): GraphData {
    const linkSrc = (l: GraphLink) =>
      typeof l.source === "object"
        ? (l.source as { id: string }).id
        : l.source;
    const linkTgt = (l: GraphLink) =>
      typeof l.target === "object"
        ? (l.target as { id: string }).id
        : l.target;
    return {
      nodes: graph.nodes.filter((n: GraphNode) => ids.has(n.id)),
      links: graph.links.filter(
        (l: GraphLink) => ids.has(linkSrc(l)) && ids.has(linkTgt(l)),
      ),
    };
  }

  const filteredGraphData = $derived.by(() => {
    const full = graphStore.data;
    const sel = globalId;
    const depth = subgraphDepth;
    console.log(
      "[Graph popup] derive filteredGraphData",
      "fullNodes=",
      full.nodes.length,
      "fullLinks=",
      full.links.length,
      "globalId=",
      sel,
      "depth=",
      depth,
    );
    if (!sel) {
      return { nodes: [], links: [] } as GraphData;
    }
    const effectiveId = effectiveSelectedId(full, sel);
    const ids = computeSubgraph(full, effectiveId, depth);
    const filtered = filterGraphToIds(full, ids);
    console.log(
      "[Graph popup] filteredGraphData",
      "nodes=",
      filtered.nodes.length,
      "links=",
      filtered.links.length,
    );
    return filtered;
  });

  const graphEmptyMessage = $derived.by(() => (!globalId ? EMPTY_MESSAGE : undefined));

  /**
   * Data passed to ForceGraph:
   * - loading: undefined -> component shows store-based loading/error UI
   * - no selection: empty graph + instructional message (no nodes/edges rendered)
   * - selection: depth-limited subgraph when available, otherwise fall back to full graph
   */
  const graphDataProp = $derived.by(() => {
    if (graphStore.loading) return undefined;
    const full = graphStore.data;
    console.log(
      "[Graph popup] graphDataProp derive",
      "fullNodes=",
      full.nodes.length,
      "fullLinks=",
      full.links.length,
      "globalId=",
      globalId,
      "filteredNodes=",
      filteredGraphData.nodes.length,
      "filteredLinks=",
      filteredGraphData.links.length,
    );
    if (!full.nodes.length) return undefined;
    if (!globalId) {
      // No selection: do not render any graph elements, only the emptyMessage overlay.
      return { nodes: [], links: [] } as GraphData;
    }
    if (!filteredGraphData.nodes.length) return full;
    return filteredGraphData;
  });

  $effect(() => {
    const b = branchId;
    const r = revision;
    if (!b) return;
    if (graphStore.loading) return;
    if (lastFetchedBranchId === b && lastFetchedRevision === r) return;
    lastFetchedBranchId = b;
    lastFetchedRevision = r;
    graphStore.fetchGraph(b, r ?? undefined);
  });

  // Persist graph-related settings (including depth) whenever they change
  $effect(() => {
    if (typeof window === "undefined") return;
    saveSettings({
      activeProjectId: projectId,
      activeBranchId: branchId,
      activeRevision: revision,
      activeGlobalId: globalId,
      subgraphDepth,
      activeView: "graph",
    });
  });

  // Keep URL in sync with current depth for sharable links
  $effect(() => {
    const url = $page.url;
    const params = new URLSearchParams(url.searchParams);
    params.set("subgraphDepth", String(subgraphDepth));
    window.history.replaceState(
      null,
      "",
      `${url.pathname}?${params.toString()}`,
    );
  });

  onMount(() => {
    applyContextFromUrl();
    applyContextFallbackFromSettings();

    channel = new BroadcastChannel(GRAPH_CHANNEL);
    channel.onmessage = handleIncomingMessage;

    requestContext();

    contextRetryTimeout = setTimeout(() => {
      if (branchId == null && projectId == null) {
        requestContext();
      }
      contextRetryTimeout = null;
    }, 1500);

    if (branchId == null && projectId == null) {
      let attempts = 0;
      contextRetryInterval = setInterval(() => {
        if (branchId != null || projectId != null || attempts >= 8) {
          if (contextRetryInterval != null) {
            clearInterval(contextRetryInterval);
            contextRetryInterval = null;
          }
          return;
        }
        requestContext();
        attempts += 1;
      }, 1000);
    }
  });

  onDestroy(() => {
    channel?.close();
    if (contextRetryTimeout != null) clearTimeout(contextRetryTimeout);
    if (contextRetryInterval != null) clearInterval(contextRetryInterval);
  });
</script>

<div class="graph-page">
  <header class="page-header">
    <div class="page-header-main">
      <h2>Graph</h2>
      {#if branchName || projectName || branchId || projectId}
        <span class="context-pill mono">
          {projectName ?? projectId ?? "—"} / {branchName ?? branchId ?? "—"}
          {#if revision != null}(rev {revision}){/if}
        </span>
      {:else}
        <span class="context-pill empty">Waiting for context…</span>
      {/if}
    </div>
    <div class="page-header-controls">
      <DepthWidget bind:value={subgraphDepth} />
    </div>
  </header>

  <div class="graph-container">
    <ForceGraph
      data={graphDataProp}
      emptyMessage={graphEmptyMessage}
      onNodeClick={handleNodeClick}
      selectedId={globalId}
    />
  </div>
</div>

<style>
  .graph-page {
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: var(--color-bg-canvas);
    color: var(--color-text-primary);
    font-family: system-ui, -apple-system, sans-serif;
    overflow: hidden;
  }

  .page-header {
    flex-shrink: 0;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .page-header-main {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .page-header h2 {
    margin: 0;
    font-size: 0.95rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--color-brand-500);
  }

  .page-header-controls {
    flex-shrink: 0;
  }

  .context-pill {
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    font-size: 0.72rem;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    color: var(--color-text-secondary);
    max-width: 60%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .context-pill.empty {
    opacity: 0.7;
    font-style: italic;
  }

  .mono {
    font-family: "SF Mono", "Fira Code", monospace;
  }

  .graph-container {
    flex: 1 1 0;
    min-height: 400px;
    position: relative;
  }
</style>
