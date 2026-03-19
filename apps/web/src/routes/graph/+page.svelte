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
  import { getWorkspaceState } from "$lib/state/workspace.svelte";
  import { client, PROJECTS_QUERY } from "$lib/api/client";
  import DepthWidget from "$lib/ui/DepthWidget.svelte";

  const NO_FILTER_MATCHES_MESSAGE = "No entities match the current filters.";

  const workspace = getWorkspaceState();  // Phase 4: derive from shared shell workspace (decoupled from main viewer)

  let branchId = $state<string | null>(null);
  let projectId = $state<string | null>(null);
  let branchName = $state<string | null>(null);
  let projectName = $state<string | null>(null);
  let revision = $state<number | null>(null);
  let globalId = $state<string | null>(null);
  let subgraphDepth = $state(1);
  let filteredGlobalIds = $state<string[]>([]);

  const graphStore = getGraphStore();

  // Phase 4: sync from shared workspace shell (decouples from main viewer page)
  $effect(() => {
    // Popup routes have independent runtime state; do not clobber URL/channel context with null workspace values.
    if (workspace.activeBranchId != null) branchId = workspace.activeBranchId;
    if (workspace.activeRevision !== undefined) revision = workspace.activeRevision;
    if (workspace.activeGlobalId !== undefined) globalId = workspace.activeGlobalId;
    if (workspace.subgraphDepth != null) subgraphDepth = workspace.subgraphDepth;
  });

  let channel: BroadcastChannel | null = null;
  let contextRetryTimeout: ReturnType<typeof setTimeout> | null = null;
  let contextRetryInterval: ReturnType<typeof setInterval> | null = null;
  let reloadToken = $state(0);
  let reloadOverlayVisible = $state(false);
  let reloadEntitiesCurrent = $state(0);
  let reloadEntitiesTotal = $state(0);
  let reloadRelationsCurrent = $state(0);
  let reloadRelationsTotal = $state(0);
  let reloadOverlayStartedAt = $state<number | null>(null);
  const RELOAD_OVERLAY_MIN_MS = 1000;
  const RELOAD_OVERLAY_FADE_MS = 220;
  let reloadProgressTimer: ReturnType<typeof setInterval> | null = null;
  let overlayMounted = $state(false);
  let overlayVisible = $state(false);
  let overlayHideTimer: ReturnType<typeof setTimeout> | null = null;
  let lastFetchedBranchId = $state<string | null>(null);
  let lastFetchedRevision = $state<number | null>(null);
  let lastSentSelectionId: string | null = null;
  let lastResolvedContextKey: string | null = null;
  let resolvingNames = false;

  const reloadPercent = $derived.by(() => {
    const total = reloadEntitiesTotal + reloadRelationsTotal;
    const current = reloadEntitiesCurrent + reloadRelationsCurrent;
    if (total <= 0) return 0;
    return Math.max(
      0,
      Math.min(100, Math.round((current / total) * 100)),
    );
  });

  function clearReloadProgressTimer() {
    if (reloadProgressTimer != null) {
      clearInterval(reloadProgressTimer);
      reloadProgressTimer = null;
    }
  }

  function clearOverlayTimers() {
    if (overlayHideTimer != null) {
      clearTimeout(overlayHideTimer);
      overlayHideTimer = null;
    }
  }

  $effect(() => {
    const isLoading = reloadOverlayVisible;
    if (isLoading) {
      clearOverlayTimers();
      if (!overlayMounted) {
        overlayMounted = true;
        requestAnimationFrame(() => {
          overlayVisible = true;
        });
      } else {
        overlayVisible = true;
      }
      return;
    }

    if (!overlayMounted) return;
    overlayVisible = false;
    overlayHideTimer = setTimeout(() => {
      overlayMounted = false;
      overlayHideTimer = null;
    }, RELOAD_OVERLAY_FADE_MS);
  });

  function startReloadOverlay(entityGuess: number, relationGuess: number) {
    const entityTotal = entityGuess > 0 ? entityGuess : graphStore.data.nodes.length;
    const relationTotal = relationGuess > 0 ? relationGuess : graphStore.data.links.length;
    reloadOverlayVisible = true;
    reloadEntitiesTotal = Math.max(0, entityTotal);
    reloadRelationsTotal = Math.max(0, relationTotal);
    reloadEntitiesCurrent = 0;
    reloadRelationsCurrent = 0;
    reloadOverlayStartedAt = Date.now();
    clearReloadProgressTimer();
    reloadProgressTimer = setInterval(() => {
      const entityCap = Math.max(1, Math.floor(reloadEntitiesTotal * 0.9));
      const relCap = Math.max(1, Math.floor(reloadRelationsTotal * 0.9));

      if (reloadEntitiesCurrent < entityCap) {
        reloadEntitiesCurrent += Math.max(1, Math.floor(reloadEntitiesTotal * 0.08));
      }
      if (reloadEntitiesCurrent > entityCap) reloadEntitiesCurrent = entityCap;

      if (reloadRelationsCurrent < relCap) {
        reloadRelationsCurrent += Math.max(1, Math.floor(reloadRelationsTotal * 0.08));
      }
      if (reloadRelationsCurrent > relCap) reloadRelationsCurrent = relCap;
    }, 90);
  }

  async function finishReloadOverlay(finalEntityCount: number, finalRelationCount: number) {
    reloadEntitiesTotal = Math.max(reloadEntitiesTotal, finalEntityCount, 0);
    reloadRelationsTotal = Math.max(reloadRelationsTotal, finalRelationCount, 0);
    reloadEntitiesCurrent = Math.max(0, Math.min(reloadEntitiesTotal, finalEntityCount));
    reloadRelationsCurrent = Math.max(
      0,
      Math.min(reloadRelationsTotal, finalRelationCount),
    );
    clearReloadProgressTimer();
    const elapsed = reloadOverlayStartedAt == null ? RELOAD_OVERLAY_MIN_MS : Date.now() - reloadOverlayStartedAt;
    const wait = Math.max(0, RELOAD_OVERLAY_MIN_MS - elapsed);
    if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
    reloadOverlayVisible = false;
    reloadOverlayStartedAt = null;
  }

  async function resolveNamesFromProjects() {
    if (!projectId || !branchId) return;
    if (projectName && branchName) return;
    const lookupKey = `${projectId}:${branchId}`;
    if (lookupKey === lastResolvedContextKey || resolvingNames) return;
    resolvingNames = true;
    try {
      const result = await client.query(PROJECTS_QUERY, {}).toPromise();
      const project = result.data?.projects?.find(
        (p: { id: string; name: string; branches: { id: string; name: string }[] }) =>
          p.id === projectId,
      );
      if (project) {
        projectName = project.name ?? projectName;
        const branch = project.branches?.find(
          (b: { id: string; name: string }) => b.id === branchId,
        );
        if (branch) {
          branchName = branch.name ?? branchName;
          lastResolvedContextKey = lookupKey;
        }
      }
    } catch {
      // Non-blocking fallback; keep IDs if name lookup fails.
    } finally {
      resolvingNames = false;
    }
  }

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
      const contextChanged =
        branchId !== msg.branchId ||
        projectId !== msg.projectId ||
        branchName !== (msg.branchName ?? null) ||
        projectName !== (msg.projectName ?? null) ||
        revision !== msg.revision ||
        globalId !== msg.globalId ||
        subgraphDepth !== msg.subgraphDepth;

      branchId = msg.branchId;
      projectId = msg.projectId;
      branchName = msg.branchName ?? null;
      projectName = msg.projectName ?? null;
      revision = msg.revision;
      globalId = msg.globalId;
      subgraphDepth = msg.subgraphDepth;
      filteredGlobalIds = (msg as { filteredGlobalIds?: string[] }).filteredGlobalIds ?? [];

      if (contextChanged) syncUrlWithState();

      if (!msg.projectName || !msg.branchName) {
        void resolveNamesFromProjects();
      }

      if (contextRetryInterval != null) {
        clearInterval(contextRetryInterval);
        contextRetryInterval = null;
      }
    } else if ((msg as { type: string }).type === "reload") {
      lastFetchedBranchId = null;
      lastFetchedRevision = null;
      reloadToken += 1;
    }
  }

  function requestContext() {
    channel?.postMessage({ type: "request-context" } satisfies GraphMessage);
  }

  function handleNodeClick(id: string) {
    if (lastSentSelectionId === id) return;
    lastSentSelectionId = id;
    channel?.postMessage({
      type: "selection-changed",
      globalId: id,
    } satisfies GraphMessage);
  }

  function syncUrlWithState() {
    if (typeof window === "undefined") return;
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
    const nextQuery = params.toString();
    const currentQuery = $page.url.searchParams.toString();
    if (nextQuery === currentQuery) return;
    window.history.replaceState(null, "", `${$page.url.pathname}?${nextQuery}`);
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
    if (!sel) {
      return { nodes: [], links: [] } as GraphData;
    }
    const effectiveId = effectiveSelectedId(full, sel);
    const ids = computeSubgraph(full, effectiveId, depth);
    return filterGraphToIds(full, ids);
  });

  const graphEmptyMessage = $derived.by(() => {
    if (globalId) return undefined;
    if (!filteredGlobalIds.length) return undefined;
    return graphDataProp?.nodes.length ? undefined : NO_FILTER_MATCHES_MESSAGE;
  });

  /**
   * Data passed to ForceGraph:
   * - loading: undefined -> component shows store-based loading/error UI
   * - no selection: empty graph + instructional message (no nodes/edges rendered)
   * - selection: depth-limited subgraph when available, otherwise fall back to full graph
   */
  const graphDataProp = $derived.by(() => {
    if (graphStore.loading) return undefined;
    const full = graphStore.data;
    if (!full.nodes.length) return undefined;
    if (!globalId) {
      if (!filteredGlobalIds.length) return full;
      const ids = new Set(filteredGlobalIds);
      return filterGraphToIds(full, ids);
    }
    if (!filteredGraphData.nodes.length) return full;
    return filteredGraphData;
  });

  $effect(() => {
    void reloadToken;
    const b = branchId;
    const r = revision;
    if (!b) return;
    if (graphStore.loading) return;
    if (lastFetchedBranchId === b && lastFetchedRevision === r) return;
    lastFetchedBranchId = b;
    lastFetchedRevision = r;
    startReloadOverlay(filteredGlobalIds.length || graphStore.data.nodes.length, graphStore.data.links.length);
    graphStore.fetchGraph(b, r ?? undefined);
  });

  $effect(() => {
    if (!reloadOverlayVisible) return;
    if (graphStore.loading) return;
    void finishReloadOverlay(graphStore.data.nodes.length, graphStore.data.links.length);
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
    void subgraphDepth;
    syncUrlWithState();
  });

  $effect(() => {
    void projectId;
    void branchId;
    if (!projectName || !branchName) {
      void resolveNamesFromProjects();
    }
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
    clearReloadProgressTimer();
    clearOverlayTimers();
    if (contextRetryTimeout != null) clearTimeout(contextRetryTimeout);
    if (contextRetryInterval != null) clearInterval(contextRetryInterval);
  });
</script>

<svelte:head>
  <title>Graph • BimAtlas</title>
</svelte:head>

<div class="graph-page">
  <header class="page-header">
    <div class="page-header-title-row">
      <h2>Graph</h2>
      {#if branchName || projectName || branchId || projectId}
        <span class="context-pill">
          {projectName ?? projectId ?? "—"} / {branchName ?? branchId ?? "—"}
          {#if revision != null}<span class="mono">(rev {revision})</span>{/if}
        </span>
      {:else}
        <span class="context-pill empty">Waiting for context…</span>
      {/if}
    </div>
  </header>

  <div class="graph-container">
    {#if overlayMounted}
      <div class="loading-overlay" class:visible={overlayVisible} role="status" aria-live="polite">
        <div class="loading-card">
          <p class="loading-title">Loading graph</p>
          <p class="loading-percent">{reloadPercent}%</p>
          <p class="loading-count">
            {#if reloadEntitiesTotal > 0}
              Entities ({reloadEntitiesCurrent}/{reloadEntitiesTotal})
            {:else}
              Entities (loading…)
            {/if}
          </p>
          <p class="loading-count">
            {#if reloadRelationsTotal > 0}
              Relationships ({reloadRelationsCurrent}/{reloadRelationsTotal})
            {:else}
              Relationships (loading…)
            {/if}
          </p>
          <div class="loading-progress" aria-hidden="true">
            <div class="loading-progress-bar" style={`width: ${reloadPercent}%`}></div>
          </div>
        </div>
      </div>
    {/if}

    <div class="graph-overlay-controls" aria-label="Graph controls">
      <DepthWidget bind:value={subgraphDepth} />
    </div>
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
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    overflow: hidden;
  }

  .graph-container {
    flex: 1 1 0;
    min-height: 400px;
    position: relative;
  }

  .loading-overlay {
    position: absolute;
    inset: 0;
    z-index: 40;
    display: flex;
    align-items: center;
    justify-content: center;
    background: color-mix(in srgb, var(--color-brand-500) 35%, transparent);
    opacity: 0;
    transition: opacity 220ms ease;
    pointer-events: none;
  }

  .loading-overlay.visible {
    opacity: 1;
  }

  .loading-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    padding: 1rem 1.25rem;
    min-width: 14rem;
    border-radius: 0.9rem;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-default);
    box-shadow: 0 10px 24px color-mix(in srgb, var(--color-brand-500) 16%, transparent);
    transform: translateY(6px) scale(0.985);
    transition: transform 220ms ease;
  }

  .loading-overlay.visible .loading-card {
    transform: translateY(0) scale(1);
  }

  .loading-title {
    margin: 0;
    font-size: 0.74rem;
    color: var(--color-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .loading-percent {
    margin: 0;
    font-size: 1.85rem;
    line-height: 1;
    font-weight: 700;
    color: var(--color-text-primary);
  }

  .loading-count {
    margin: 0;
    font-size: 0.82rem;
    color: var(--color-text-secondary);
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }

  .loading-progress {
    width: 100%;
    height: 0.375rem;
    margin-top: 0.35rem;
    border-radius: 9999px;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-subtle);
    overflow: hidden;
  }

  .loading-progress-bar {
    height: 100%;
    background: var(--color-action-primary);
    transition: width 140ms ease;
  }

  .graph-overlay-controls {
    position: absolute;
    top: 0.75rem;
    left: 0.75rem;
    z-index: 20;
    pointer-events: auto;
  }
</style>
