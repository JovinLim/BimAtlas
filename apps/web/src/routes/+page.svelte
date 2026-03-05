<script lang="ts">
  /**
   * Main BimAtlas page -- project/branch selector, 3D viewport, force graph, and selection panel.
   * Users first select (or create) a project, then pick a branch. All IFC data is scoped to the branch.
   */
  import Viewport from "$lib/ui/Viewport.svelte";
  import ImportModal from "$lib/ui/ImportModal.svelte";
  import Spinner from "$lib/ui/Spinner.svelte";
  import Sidebar from "$lib/ui/Sidebar.svelte";
  import DepthWidget from "$lib/ui/DepthWidget.svelte";
  import {
    AGENT_CHANNEL,
    type AgentMessage as AgentChannelMessage,
  } from "$lib/agent/protocol";
  import type { AgentBusEvent } from "$lib/agent/protocol";
  import {
    getSelection,
    getRevisionState,
    getProjectState,
    initializeFromSettings,
  } from "$lib/state/selection.svelte";
  import { getSearchState } from "$lib/state/search.svelte";
  import {
    SEARCH_CHANNEL,
    type FilterSet,
    type ProductMeta,
    type SearchFilter,
    type SearchMessage,
  } from "$lib/search/protocol";
  import {
    ATTRIBUTES_CHANNEL,
    type AttributesMessage,
  } from "$lib/attributes/protocol";
  import { getDescendantClasses } from "$lib/ifc/schema";
  import { getGraphStore } from "$lib/graph/graphStore.svelte";
  import { computeSubgraph } from "$lib/graph/subgraph";
  import { GRAPH_CHANNEL, type GraphMessage } from "$lib/graph/protocol";
  import {
    TABLE_CHANNEL,
    TABLE_PROTOCOL_VERSION,
    ENABLE_TABLE_VIEWER_SELECTION_SYNC,
    type TableMessage,
  } from "$lib/table/protocol";
  import type { SceneManager } from "$lib/engine/SceneManager";
  import {
    client,
    APPLIED_FILTER_SETS_QUERY,
    FILTER_SET_MATCHES_QUERY,
    PROJECTS_QUERY,
    CREATE_PROJECT_MUTATION,
    CREATE_BRANCH_MUTATION,
    DELETE_PROJECT_MUTATION,
    DELETE_BRANCH_MUTATION,
    REVISIONS_QUERY,
    IFC_PRODUCT_TREE_QUERY,
  } from "$lib/api/client";
  import {
    createBufferGeometry,
    type RawMeshData,
  } from "$lib/engine/BufferGeometryLoader";
  import { untrack, onMount, onDestroy, tick } from "svelte";
  import { loadSettings, saveSettings } from "$lib/state/persistence";
  import { setProductTreeFromApi } from "$lib/ifc/schema";

  const selection = getSelection();
  const revisionState = getRevisionState();
  const projectState = getProjectState();
  const graphStore = getGraphStore();
  const searchState = getSearchState();

  let sceneManager: SceneManager | undefined = $state(undefined);
  let filterSetColorsEnabled = $state(false);
  let searchPopup: Window | null = null;
  let searchChannel: BroadcastChannel | null = null;
  let attributePopup: Window | null = null;
  let attributesChannel: BroadcastChannel | null = null;
  let graphPopup: Window | null = null;
  let graphChannel: BroadcastChannel | null = null;
  let tablePopup: Window | null = null;
  let tableChannel: BroadcastChannel | null = null;

  // Load saved settings and initialize state (only in browser)
  let settingsLoaded = $state(false);
  $effect(() => {
    if (typeof window === "undefined" || settingsLoaded) return;
    const savedSettings = loadSettings();
    if (savedSettings) {
      initializeFromSettings(savedSettings);
    }
    settingsLoaded = true;
  });

  const API_BASE = import.meta.env.VITE_API_URL
    ? (import.meta.env.VITE_API_URL as string).replace("/graphql", "")
    : "/api";

  let agentPopup: Window | null = null;
  let agentChannel: BroadcastChannel | null = null;
  let agentEventSource: EventSource | null = null;

  // Agent events SSE: subscribe when branchId changes
  $effect(() => {
    const branchId = projectState.activeBranchId;
    if (agentEventSource) {
      agentEventSource.close();
      agentEventSource = null;
    }
    if (!branchId || typeof window === "undefined") return;
    const url = `${API_BASE}/stream/agent-events?branch_id=${encodeURIComponent(branchId)}`;
    const es = new EventSource(url);
    agentEventSource = es;
    es.onmessage = (e) => {
      try {
        const event: AgentBusEvent = JSON.parse(e.data);
        if (event.type === "filter-applied") {
          autoLoadAppliedFilterSets(event.branchId);
        }
      } catch {}
    };
    es.onerror = () => {
      // Reconnect is automatic with EventSource
    };
    return () => {
      es.close();
    };
  });

  let showImportModal = $state(false);
  let importing = $state(false);
  let importError = $state<string | null>(null);
  let loadingGeometry = $state(false);
  let loadingGeometryCurrent = $state(0);
  let loadingGeometryTotal = $state(0);
  let totalCountKey = $state<string | null>(null);
  let productTreeKey = $state<string | null>(null);

  // ---- Project / Branch state ----
  interface ProjectData {
    id: string;
    name: string;
    description: string | null;
    createdAt: string;
    branches: BranchData[];
  }
  interface BranchData {
    id: string;
    projectId: string;
    name: string;
    createdAt: string;
  }

  let projects = $state<ProjectData[]>([]);
  let loadingProjects = $state(true);
  let showCreateProject = $state(false);
  let showCreateBranch = $state(false);
  let newProjectName = $state("");
  let newProjectDesc = $state("");
  let newBranchName = $state("");
  let creatingProject = $state(false);
  let creatingBranch = $state(false);
  let showDeleteProject = $state(false);
  let showDeleteBranch = $state(false);
  let projectToDelete = $state<ProjectData | null>(null);
  let branchToDelete = $state<BranchData | null>(null);
  let deletingProject = $state(false);
  let deletingBranch = $state(false);

  // ---- Revision list (for search when project is active) ----
  interface RevisionRow {
    id: string;
    branchId: string;
    revisionSeq: number;
    label: string | null;
    ifcFilename: string | null;
    authorId: string | null;
    createdAt: string;
  }
  let revisionList = $state<RevisionRow[]>([]);
  /** Full list for building dropdown options (unfiltered). */
  let allRevisionsForDropdown = $state<RevisionRow[]>([]);
  let loadingRevisions = $state(false);
  let revisionSearchDebounceId: ReturnType<typeof setTimeout> | null = null;

  // Per-category revision filters: checkbox enables, text is the value; when enabled and text set, filter is applied.
  let revisionFilterAuthor = $state({ enabled: false, text: "" });
  let revisionFilterFilename = $state({ enabled: false, text: "" });
  let revisionFilterMessage = $state({ enabled: false, text: "" });
  let revisionFilterCreatedAfter = $state({ enabled: false, text: "" });
  let revisionFilterCreatedBefore = $state({ enabled: false, text: "" });
  let revisionFilterCollapsed = $state(true);

  // Derived: currently selected project and its branches
  let activeProject = $derived(
    projects.find((p) => p.id === projectState.activeProjectId) ?? null,
  );
  let activeBranch = $derived(
    activeProject?.branches.find((b) => b.id === projectState.activeBranchId) ??
      null,
  );

  /** Revision row for the currently displayed revision (for "Current revision" block). Resolved from filtered list or full list. */
  let currentRevisionRow = $derived(
    revisionState.activeRevision === null
      ? null
      : (revisionList.find(
          (r) => r.revisionSeq === revisionState.activeRevision,
        ) ??
          allRevisionsForDropdown.find(
            (r) => r.revisionSeq === revisionState.activeRevision,
          ) ??
          null),
  );

  // ---- Lifecycle ----

  // Persist settings to localStorage whenever they change (only after initial load)
  $effect(() => {
    if (typeof window === "undefined" || !settingsLoaded) return;
    saveSettings({
      activeProjectId: projectState.activeProjectId,
      activeBranchId: projectState.activeBranchId,
      activeRevision: revisionState.activeRevision,
      activeGlobalId: selection.activeGlobalId,
      subgraphDepth: selection.subgraphDepth,
      activeView: "viewport",
    });
  });

  // Load projects on mount
  $effect(() => {
    loadProjects();
  });

  // Load latest revision when branch changes
  $effect(() => {
    const branchId = projectState.activeBranchId;
    if (branchId && revisionState.activeRevision === null && !importing) {
      fetchLatestRevision(branchId);
    }
  });

  // Load revision list for active branch; apply per-category filters when checkboxes are enabled.
  $effect(() => {
    const branchId = projectState.activeBranchId;
    if (!branchId) {
      revisionList = [];
      allRevisionsForDropdown = [];
      return;
    }
    const author = revisionFilterAuthor.enabled
      ? revisionFilterAuthor.text.trim()
      : "";
    const filename = revisionFilterFilename.enabled
      ? revisionFilterFilename.text.trim()
      : "";
    const message = revisionFilterMessage.enabled
      ? revisionFilterMessage.text.trim()
      : "";
    const after = revisionFilterCreatedAfter.enabled
      ? revisionFilterCreatedAfter.text.trim()
      : "";
    const before = revisionFilterCreatedBefore.enabled
      ? revisionFilterCreatedBefore.text.trim()
      : "";

    if (revisionSearchDebounceId != null) {
      clearTimeout(revisionSearchDebounceId);
      revisionSearchDebounceId = null;
    }
    revisionSearchDebounceId = setTimeout(() => {
      fetchRevisionsListWithFilters(branchId, {
        authorSearch: author || undefined,
        ifcFilenameSearch: filename || undefined,
        commitMessageSearch: message || undefined,
        createdAfter: after || undefined,
        createdBefore: before || undefined,
      });
      revisionSearchDebounceId = null;
    }, 300);
    return () => {
      if (revisionSearchDebounceId != null)
        clearTimeout(revisionSearchDebounceId);
    };
  });

  // Load 3D geometry when revision changes and sceneManager is ready
  let lastFetchedRev: number | null = $state(null);
  let lastFetchedBranchId: string | null = $state(null);
  $effect(() => {
    const rev = revisionState.activeRevision;
    const branchId = projectState.activeBranchId;
    const mgr = sceneManager;
    if (!mgr || rev === null || !branchId) return;

    // Only fetch if revision or branchId changed
    if (rev === lastFetchedRev && branchId === lastFetchedBranchId) return;

    lastFetchedRev = rev;
    lastFetchedBranchId = branchId;

    untrack(() => {
      loadGeometryForActiveBranch(mgr, rev, branchId);
      graphStore.fetchGraph(branchId, rev);
    });
  });

  // Subgraph filter: recompute whenever selection or depth changes
  $effect(() => {
    const mgr = sceneManager;
    if (!mgr) return;

    const selectedId = selection.activeGlobalId;
    const depth = selection.subgraphDepth;

    if (selectedId) {
      // If the selected node is a synthetic IfcShapeRepresentation, map it back
      // to its owning product so that geometry highlighting works correctly.
      const graph = graphStore.data;
      let effectiveSelectedId = selectedId;
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
          effectiveSelectedId = src;
          break;
        }
      }

      const subgraphIds = computeSubgraph(graph, effectiveSelectedId, depth);
      mgr.applySubgraphFilter(effectiveSelectedId, subgraphIds);
    } else {
      mgr.applySubgraphFilter(null, null);
    }
  });

  // Keep Attribute pop-out in sync when selection or context changes
  $effect(() => {
    const branchId = projectState.activeBranchId;
    const projectId = projectState.activeProjectId;
    const revision = revisionState.activeRevision;
    const globalId = selection.activeGlobalId;
    if (!attributesChannel) return;
    attributesChannel.postMessage({
      type: "context",
      branchId,
      projectId,
      revision,
      globalId,
    } satisfies AttributesMessage);
  });

  // Keep Graph popup in sync when selection or context changes
  $effect(() => {
    const branchId = projectState.activeBranchId;
    const projectId = projectState.activeProjectId;
    const revision = revisionState.activeRevision;
    const globalId = selection.activeGlobalId;
    const subgraphDepth = selection.subgraphDepth;
    if (!graphChannel) return;
    graphChannel.postMessage({
      type: "context",
      branchId,
      projectId,
      revision,
      globalId,
      subgraphDepth,
    } satisfies GraphMessage);
  });

  // BroadcastChannels for cross-window communication
  onMount(() => {
    searchChannel = new BroadcastChannel(SEARCH_CHANNEL);
    searchChannel.onmessage = (e: MessageEvent<SearchMessage>) => {
      if (e.data.type === "apply-filters") {
        handleApplyFilters(e.data.filters);
      } else if (e.data.type === "apply-filter-sets") {
        handleApplyFilterSets(e.data.filterSets, e.data.combinationLogic);
      } else if (e.data.type === "request-branch-context") {
        sendBranchContext();
      } else if (e.data.type === "set-filter-set-colors") {
        filterSetColorsEnabled = e.data.enabled;
        handleFilterSetColorToggle();
      }
    };

    attributesChannel = new BroadcastChannel(ATTRIBUTES_CHANNEL);
    attributesChannel.onmessage = (e: MessageEvent<AttributesMessage>) => {
      if (e.data.type === "request-context") {
        sendAttributesContext();
      } else if (e.data.type === "selection-changed") {
        selection.activeGlobalId = e.data.globalId;
      }
    };

    graphChannel = new BroadcastChannel(GRAPH_CHANNEL);
    graphChannel.onmessage = (e: MessageEvent<GraphMessage>) => {
      if (e.data.type === "request-context") {
        sendGraphContext();
      } else if (e.data.type === "selection-changed") {
        selection.activeGlobalId = e.data.globalId;
      }
    };

    tableChannel = new BroadcastChannel(TABLE_CHANNEL);
    tableChannel.onmessage = (e: MessageEvent<TableMessage>) => {
      if (e.data.type === "request-context") {
        sendTableContext();
      } else if (
        ENABLE_TABLE_VIEWER_SELECTION_SYNC &&
        e.data.type === "selection-changed"
      ) {
        selection.activeGlobalId = e.data.globalId;
      }
    };

    agentChannel = new BroadcastChannel(AGENT_CHANNEL);
    agentChannel.onmessage = (e: MessageEvent<AgentChannelMessage>) => {
      if (e.data.type === "request-context") {
        sendAgentContext();
      }
    };
  });

  onDestroy(() => {
    searchChannel?.close();
    attributesChannel?.close();
    graphChannel?.close();
    tableChannel?.close();
    agentChannel?.close();
  });

  // Sync viewer selection to table popup (dormant when ENABLE_TABLE_VIEWER_SELECTION_SYNC is false).
  $effect(() => {
    if (!ENABLE_TABLE_VIEWER_SELECTION_SYNC) return;
    const globalId = selection.activeGlobalId;
    tableChannel?.postMessage({
      type: "selection-sync",
      globalId,
    } satisfies TableMessage);
  });

  function sendBranchContext() {
    const branchId = projectState.activeBranchId;
    const projectId = projectState.activeProjectId;
    if (branchId != null && projectId != null) {
      searchChannel?.postMessage({
        type: "branch-context",
        branchId,
        projectId,
      } satisfies SearchMessage);
      searchChannel?.postMessage({
        type: "filter-result-count",
        count: sceneManager?.elementCount ?? searchState.products.length,
        total: searchState.totalProductCount,
      } satisfies SearchMessage);
    }
  }

  function sendAttributesContext() {
    const branchId = projectState.activeBranchId;
    const projectId = projectState.activeProjectId;
    const revision = revisionState.activeRevision;
    const globalId = selection.activeGlobalId;
    attributesChannel?.postMessage({
      type: "context",
      branchId,
      projectId,
      revision,
      globalId,
    } satisfies AttributesMessage);
  }

  function sendGraphContext() {
    const branchId = projectState.activeBranchId;
    const projectId = projectState.activeProjectId;
    const revision = revisionState.activeRevision;
    const globalId = selection.activeGlobalId;
    const subgraphDepth = selection.subgraphDepth;
    graphChannel?.postMessage({
      type: "context",
      branchId,
      projectId,
      revision,
      globalId,
      subgraphDepth,
    } satisfies GraphMessage);
  }

  function sendTableContext() {
    const branchId = projectState.activeBranchId;
    const projectId = projectState.activeProjectId;
    const revision = revisionState.activeRevision;
    const products = searchState.products;

    // Resolve human-readable names from loaded project list
    const project = projects.find((p) => p.id === projectId) ?? null;
    const branch =
      project?.branches.find((b) => b.id === branchId) ??
      projects.flatMap((p) => p.branches).find((b) => b.id === branchId) ??
      null;

    const contextBase = {
      type: "context" as const,
      branchId,
      projectId,
      branchName: branch?.name ?? null,
      projectName: project?.name ?? null,
      revision,
      version: TABLE_PROTOCOL_VERSION,
      activeGlobalId: selection.activeGlobalId,
    };

    // Always send lean context first (small payload), then attributes in chunks.
    // This avoids postMessage size limits that cause ENTITY.* columns to show "—" when one big payload fails.
    const leanProducts = products.map((p) => ({
      globalId: p.globalId,
      ifcClass: p.ifcClass,
      name: p.name,
      description: p.description,
      objectType: p.objectType,
      tag: p.tag,
      attributes: null,
    }));
    tableChannel?.postMessage({
      ...contextBase,
      products: leanProducts,
    } satisfies TableMessage);
    // Do not send attribute chunks here; table will request them after receiving context
    // so it is guaranteed to be listening when chunks arrive (fixes chunks not reaching table).
    if (ENABLE_TABLE_VIEWER_SELECTION_SYNC) {
      tableChannel?.postMessage({
        type: "selection-sync",
        globalId: selection.activeGlobalId,
      } satisfies TableMessage);
    }
  }

  function sendAgentContext() {
    const branchId = projectState.activeBranchId;
    const projectId = projectState.activeProjectId;
    const revision = revisionState.activeRevision;
    const project = projects.find((p) => p.id === projectId) ?? null;
    const branch =
      project?.branches.find((b) => b.id === branchId) ??
      projects.flatMap((p) => p.branches).find((b) => b.id === branchId) ??
      null;
    agentChannel?.postMessage({
      type: "context",
      branchId,
      projectId,
      revision,
      projectName: project?.name ?? null,
      branchName: branch?.name ?? null,
    } satisfies AgentChannelMessage);
  }

  function openAgentPopup() {
    if (!agentPopup || agentPopup.closed) {
      const branchId = projectState.activeBranchId;
      const projectId = projectState.activeProjectId;
      const revision = revisionState.activeRevision;
      const params = new URLSearchParams();
      if (branchId != null) params.set("branchId", String(branchId));
      if (projectId != null) params.set("projectId", String(projectId));
      if (revision != null) params.set("revision", String(revision));
      const query = params.toString();
      const url = query ? `/agent?${query}` : "/agent";
      agentPopup = window.open(url, "bimatlas-agent", "width=460,height=700");
      setTimeout(sendAgentContext, 500);
    } else {
      agentPopup.focus();
      sendAgentContext();
    }
  }

  function openGraphPopup() {
    if (!graphPopup || graphPopup.closed) {
      const branchId = projectState.activeBranchId;
      const projectId = projectState.activeProjectId;
      const revision = revisionState.activeRevision;
      const globalId = selection.activeGlobalId;
      const subgraphDepth = selection.subgraphDepth;
      const params = new URLSearchParams();
      if (branchId != null) params.set("branchId", String(branchId));
      if (projectId != null) params.set("projectId", String(projectId));
      if (revision != null) params.set("revision", String(revision));
      if (globalId != null) params.set("globalId", String(globalId));
      params.set("subgraphDepth", String(subgraphDepth));
      const query = params.toString();
      const url = query ? `/graph?${query}` : "/graph";
      graphPopup = window.open(url, "bimatlas-graph", "width=800,height=700");
      setTimeout(sendGraphContext, 500);
    } else {
      graphPopup.focus();
      sendGraphContext();
    }
  }

  function openSearchPopup() {
    if (!searchPopup || searchPopup.closed) {
      const branchId = projectState.activeBranchId;
      const projectId = projectState.activeProjectId;
      const params = new URLSearchParams();
      if (branchId != null) params.set("branchId", String(branchId));
      if (projectId != null) params.set("projectId", String(projectId));
      const query = params.toString();
      const url = query ? `/search?${query}` : "/search";
      searchPopup = window.open(url, "bimatlas-search", "width=520,height=700");
      setTimeout(sendBranchContext, 500);
    } else {
      searchPopup.focus();
      sendBranchContext();
    }
  }

  function openAttributesPopup() {
    if (!attributePopup || attributePopup.closed) {
      const branchId = projectState.activeBranchId;
      const projectId = projectState.activeProjectId;
      const revision = revisionState.activeRevision;
      const globalId = selection.activeGlobalId;
      const params = new URLSearchParams();
      if (branchId != null) params.set("branchId", String(branchId));
      if (projectId != null) params.set("projectId", String(projectId));
      if (revision != null) params.set("revision", String(revision));
      if (globalId != null) params.set("globalId", String(globalId));
      const query = params.toString();
      const url = query ? `/attributes?${query}` : "/attributes";
      attributePopup = window.open(
        url,
        "bimatlas-attributes",
        "width=420,height=700",
      );
      setTimeout(sendAttributesContext, 500);
    } else {
      attributePopup.focus();
      sendAttributesContext();
    }
  }

  function openTablePopup() {
    if (!tablePopup || tablePopup.closed) {
      const branchId = projectState.activeBranchId;
      const projectId = projectState.activeProjectId;
      const revision = revisionState.activeRevision;
      const params = new URLSearchParams();
      if (branchId != null) params.set("branchId", String(branchId));
      if (projectId != null) params.set("projectId", String(projectId));
      if (revision != null) params.set("revision", String(revision));
      const query = params.toString();
      const url = query ? `/table?${query}` : "/table";
      tablePopup = window.open(
        url,
        "bimatlas-table",
        "width=900,height=700",
      );
      setTimeout(sendTableContext, 500);
    } else {
      tablePopup.focus();
      sendTableContext();
    }
  }

  function filtersToQueryVars(
    filters: SearchFilter[],
  ): Record<string, unknown> {
    const vars: Record<string, unknown> = {};
    const allClasses: string[] = [];
    const allRelations: string[] = [];

    for (const f of filters) {
      if (f.mode === "class" && f.ifcClass) {
        const descendants = getDescendantClasses(f.ifcClass);
        for (const cls of descendants) allClasses.push(cls);
      } else if (f.mode === "attribute" && f.attribute && f.value) {
        const key = f.attribute === "objectType" ? "objectType" : f.attribute;
        vars[key] = f.value;
      } else if (f.mode === "relation" && f.relation) {
        allRelations.push(f.relation);
      }
    }

    if (allClasses.length > 0) {
      vars.ifcClasses = [...new Set(allClasses)];
    }
    if (allRelations.length > 0) {
      vars.relationTypes = [...new Set(allRelations)];
    }

    return vars;
  }

  async function handleApplyFilters(filters: SearchFilter[]) {
    searchState.activeFilters = filters;
    searchState.appliedFilterSets = [];
    const mgr = sceneManager;
    const rev = revisionState.activeRevision;
    const branchId = projectState.activeBranchId;
    if (!mgr || rev === null || !branchId) return;

    const extraVars = filters.length > 0 ? filtersToQueryVars(filters) : {};
    await loadGeometry(mgr, rev, branchId, extraVars);
    await ensureTotalProductCount(branchId, rev);

    searchChannel?.postMessage({
      type: "filter-result-count",
      count: mgr.elementCount,
      total: searchState.totalProductCount,
    } satisfies SearchMessage);
  }

  function filterSetsToQueryVars(
    filterSets: FilterSet[],
    combinationLogic: "AND" | "OR",
  ): Record<string, unknown> {
    if (filterSets.length === 0) return {};

    if (filterSets.length === 1) {
      const fs = filterSets[0];
      return filtersToQueryVars(fs.filters);
    }

    // For multiple filter sets we fall back to a flat merge.
    // Full server-side compound logic would require a dedicated endpoint;
    // for now we merge all filters and use the combination logic as a hint.
    const allFilters: SearchFilter[] = [];
    for (const fs of filterSets) {
      for (const f of fs.filters) allFilters.push(f);
    }
    return filtersToQueryVars(allFilters);
  }

  async function handleApplyFilterSets(
    filterSets: FilterSet[],
    combinationLogic: "AND" | "OR",
  ) {
    searchState.appliedFilterSets = filterSets;
    searchState.combinationLogic = combinationLogic;
    searchState.activeFilters = [];
    const mgr = sceneManager;
    const rev = revisionState.activeRevision;
    const branchId = projectState.activeBranchId;
    if (!mgr || rev === null || !branchId) return;

    const extraVars =
      filterSets.length > 0
        ? filterSetsToQueryVars(filterSets, combinationLogic)
        : {};
    await loadGeometry(mgr, rev, branchId, extraVars);
    await ensureTotalProductCount(branchId, rev);

    if (filterSetColorsEnabled && filterSets.length > 0) {
      await applyFilterSetColorsToScene(mgr, branchId, rev);
    }

    searchChannel?.postMessage({
      type: "filter-result-count",
      count: mgr.elementCount,
      total: searchState.totalProductCount,
    } satisfies SearchMessage);
  }

  async function autoLoadAppliedFilterSets(branchId: string): Promise<boolean> {
    try {
      const result = await client
        .query(APPLIED_FILTER_SETS_QUERY, { branchId })
        .toPromise();
      const data = result.data?.appliedFilterSets;
      if (data && data.filterSets && data.filterSets.length > 0) {
        await handleApplyFilterSets(
          data.filterSets,
          data.combinationLogic ?? "AND",
        );
        return true;
      }
      searchState.appliedFilterSets = [];
      if (filterSetColorsEnabled) {
        sceneManager?.applyFilterSetColors(null);
      }
      return false;
    } catch (err) {
      console.error("Failed to auto-load applied filter sets:", err);
      return false;
    }
  }

  async function loadGeometryForActiveBranch(
    mgr: SceneManager,
    revision: number,
    branchId: string,
  ) {
    async function ensureProductTree(branchId: string, revision: number) {
      const key = `${branchId}:${revision}`;
      if (productTreeKey === key) return;
      try {
        const result = await client
          .query(IFC_PRODUCT_TREE_QUERY, { branchId, revision })
          .toPromise();
        setProductTreeFromApi(result.data?.ifcProductTree ?? null);
        productTreeKey = key;
      } catch (err) {
        console.warn("Failed to load IFC product tree:", err);
        setProductTreeFromApi(null);
        productTreeKey = key;
      }
    }

    await ensureProductTree(branchId, revision);

    const hasAppliedSets = await autoLoadAppliedFilterSets(branchId);
    if (!hasAppliedSets) {
      await loadGeometry(mgr, revision, branchId);
      return;
    }
    await ensureTotalProductCount(branchId, revision);
  }

  async function ensureTotalProductCount(branchId: string, revision: number) {
    const key = `${branchId}:${revision}`;
    if (totalCountKey === key) return;
    try {
      const params = streamQueryParams(branchId, revision, {});
      const url = `${API_BASE}/stream/ifc-products?${params.toString()}`;
      const res = await fetch(url);
      if (!res.ok || !res.body) return;
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() ?? "";
        for (const chunk of lines) {
          const dataMatch = chunk.match(/^data:\s*(.+)$/m);
          if (!dataMatch) continue;
          const data = JSON.parse(dataMatch[1]);
          if (data.type === "start") {
            searchState.totalProductCount = data.total ?? 0;
            totalCountKey = key;
            await reader.cancel();
            return;
          }
        }
      }
    } catch (err) {
      console.warn("Failed to fetch unfiltered total count:", err);
    }
  }

  // ---- API helpers ----

  async function loadProjects(forceNetwork = false) {
    loadingProjects = true;
    try {
      const result = await client
        .query(
          PROJECTS_QUERY,
          {},
          forceNetwork ? { requestPolicy: "network-only" } : undefined,
        )
        .toPromise();
      if (result.error) {
        // Server/GraphQL error (e.g. 500) — fall back to landing so user can retry or pick another project
        console.error("Failed to load projects:", result.error);
        projectState.activeProjectId = null;
        projectState.activeBranchId = null;
        revisionState.activeRevision = null;
        projects = [];
        return;
      }
      if (result.data?.projects) {
        projects = result.data.projects;
        if (projects.length === 0) {
          // No projects — show main landing so user can create one
          projectState.activeProjectId = null;
          projectState.activeBranchId = null;
          revisionState.activeRevision = null;
        }
      }
    } catch (err) {
      // Network or other error — fall back to main landing page for project selection
      console.error("Failed to load projects:", err);
      projectState.activeProjectId = null;
      projectState.activeBranchId = null;
      revisionState.activeRevision = null;
      projects = [];
    } finally {
      loadingProjects = false;
    }
  }

  async function handleCreateProject() {
    if (!newProjectName.trim()) return;
    creatingProject = true;
    try {
      const result = await client
        .mutation(CREATE_PROJECT_MUTATION, {
          name: newProjectName.trim(),
          description: newProjectDesc.trim() || null,
        })
        .toPromise();
      if (result.data?.createProject) {
        const proj = result.data.createProject;
        projects = [proj, ...projects];
        projectState.activeProjectId = proj.id;
        // Auto-select the main branch
        const mainBranch = proj.branches.find(
          (b: BranchData) => b.name === "main",
        );
        if (mainBranch) {
          projectState.activeBranchId = mainBranch.id;
        }
        showCreateProject = false;
        newProjectName = "";
        newProjectDesc = "";
      }
    } catch (err) {
      console.error("Failed to create project:", err);
    } finally {
      creatingProject = false;
    }
  }

  async function handleCreateBranch() {
    if (!newBranchName.trim() || !projectState.activeProjectId) return;
    creatingBranch = true;
    try {
      const result = await client
        .mutation(CREATE_BRANCH_MUTATION, {
          projectId: projectState.activeProjectId,
          name: newBranchName.trim(),
        })
        .toPromise();
      if (result.data?.createBranch) {
        const branch = result.data.createBranch;
        // Update the project's branches list
        projects = projects.map((p) =>
          p.id === projectState.activeProjectId
            ? { ...p, branches: [...p.branches, branch] }
            : p,
        );
        projectState.activeBranchId = branch.id;
        showCreateBranch = false;
        newBranchName = "";
        // Switch viewer to the new branch and update the view
        sceneManager?.clearAll();
        sendBranchContext();
        autoLoadAppliedFilterSets(branch.id);
      }
    } catch (err) {
      console.error("Failed to create branch:", err);
    } finally {
      creatingBranch = false;
    }
  }

  function selectProject(projectId: string) {
    projectState.activeProjectId = projectId;
    const proj = projects.find((p) => p.id === projectId);
    const mainBranch = proj?.branches.find((b) => b.name === "main");
    if (mainBranch) {
      projectState.activeBranchId = mainBranch.id;
    }
    sceneManager?.clearAll();
    sendBranchContext();
    if (mainBranch) {
      autoLoadAppliedFilterSets(mainBranch.id);
    }
  }

  function selectBranch(branchId: string) {
    projectState.activeBranchId = branchId;
    revisionState.activeRevision = null;
    sceneManager?.clearAll();
    sendBranchContext();
    autoLoadAppliedFilterSets(branchId);
  }

  async function handleDeleteProject() {
    if (!projectToDelete) return;
    deletingProject = true;
    try {
      const result = await client
        .mutation(DELETE_PROJECT_MUTATION, { id: projectToDelete.id })
        .toPromise();
      if (result.data?.deleteProject) {
        showDeleteProject = false;
        projectToDelete = null;
        projectState.activeProjectId = null;
        projectState.activeBranchId = null;
        revisionState.activeRevision = null;
        selection.activeGlobalId = null;
        await loadProjects(true);
      }
    } catch (err) {
      console.error("Failed to delete project:", err);
    } finally {
      deletingProject = false;
    }
  }

  async function handleDeleteBranch() {
    if (!branchToDelete) return;
    deletingBranch = true;
    try {
      const result = await client
        .mutation(DELETE_BRANCH_MUTATION, { id: branchToDelete.id })
        .toPromise();
      if (result.data?.deleteBranch) {
        showDeleteBranch = false;
        const projectId = projectState.activeProjectId;
        branchToDelete = null;
        revisionState.activeRevision = null;
        selection.activeGlobalId = null;
        await loadProjects(true);
        // Select another branch (main or first remaining)
        const proj = projects.find((p) => p.id === projectId);
        if (proj && proj.branches.length > 0) {
          const main = proj.branches.find((b) => b.name === "main");
          projectState.activeBranchId = main ? main.id : proj.branches[0].id;
          sceneManager?.clearAll();
          sendBranchContext();
          autoLoadAppliedFilterSets(projectState.activeBranchId);
        }
      }
    } catch (err) {
      console.error("Failed to delete branch:", err);
    } finally {
      deletingBranch = false;
    }
  }

  async function fetchLatestRevision(branchId: string) {
    try {
      const result = await client
        .query(REVISIONS_QUERY, { branchId })
        .toPromise();

      const revisions = result.data?.revisions || [];
      if (revisions.length > 0) {
        const latest = Math.max(
          ...revisions.map((r: { revisionSeq: number }) => r.revisionSeq),
        );
        revisionState.activeRevision = latest;
      }
    } catch (err) {
      console.error("Failed to fetch latest revision:", err);
    }
  }

  async function fetchRevisionsListWithFilters(
    branchId: string,
    filters: {
      authorSearch?: string;
      ifcFilenameSearch?: string;
      commitMessageSearch?: string;
      createdAfter?: string;
      createdBefore?: string;
    },
  ) {
    if (!branchId) return;
    loadingRevisions = true;
    try {
      const variables: Record<string, unknown> = { branchId };
      if (filters.authorSearch) variables.authorSearch = filters.authorSearch;
      if (filters.ifcFilenameSearch)
        variables.ifcFilenameSearch = filters.ifcFilenameSearch;
      if (filters.commitMessageSearch)
        variables.commitMessageSearch = filters.commitMessageSearch;
      if (filters.createdAfter) variables.createdAfter = filters.createdAfter;
      if (filters.createdBefore)
        variables.createdBefore = filters.createdBefore;
      const result = await client.query(REVISIONS_QUERY, variables).toPromise();
      const list = (result.data?.revisions ?? []) as RevisionRow[];
      revisionList = list;
      const hasAnyFilter = !!(
        filters.authorSearch ||
        filters.ifcFilenameSearch ||
        filters.commitMessageSearch ||
        filters.createdAfter ||
        filters.createdBefore
      );
      if (!hasAnyFilter) allRevisionsForDropdown = list;
    } catch (err) {
      console.error("Failed to fetch revisions:", err);
      revisionList = [];
    } finally {
      loadingRevisions = false;
    }
  }

  /** Map GraphQL-style filter vars (camelCase) to stream query params (snake_case). */
  function streamQueryParams(
    branchId: string,
    revision: number,
    filterVars: Record<string, unknown>,
  ): URLSearchParams {
    const params = new URLSearchParams();
    params.set("branch_id", String(branchId));
    params.set("revision", String(revision));
    if (filterVars.ifcClass != null)
      params.set("ifc_class", String(filterVars.ifcClass));
    if (filterVars.ifcClasses != null) {
      for (const c of filterVars.ifcClasses as string[])
        params.append("ifc_classes", c);
    }
    if (filterVars.containedIn != null)
      params.set("contained_in", String(filterVars.containedIn));
    if (filterVars.name != null) params.set("name", String(filterVars.name));
    if (filterVars.objectType != null)
      params.set("object_type", String(filterVars.objectType));
    if (filterVars.tag != null) params.set("tag", String(filterVars.tag));
    if (filterVars.description != null)
      params.set("description", String(filterVars.description));
    if (filterVars.globalId != null)
      params.set("global_id", String(filterVars.globalId));
    if (filterVars.relationTypes != null) {
      for (const r of filterVars.relationTypes as string[])
        params.append("relation_types", r);
    }
    return params;
  }

  async function loadGeometry(
    mgr: SceneManager,
    revision: number,
    branchId: string,
    filterVars: Record<string, unknown> = {},
  ) {
    if (loadingGeometry) return;
    loadingGeometry = true;
    loadingGeometryCurrent = 0;
    loadingGeometryTotal = 0;

    try {
      const params = streamQueryParams(branchId, revision, filterVars);
      const url = `${API_BASE}/stream/ifc-products?${params.toString()}`;
      const res = await fetch(url);

      if (!res.ok) {
        console.error("Failed to fetch geometry stream:", res.status);
        return;
      }

      mgr.clearAll();
      const metaList: ProductMeta[] = [];
      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let streamEnded = false;
      let startTotal = 0;
      let productEventsWithMesh = 0;

      if (!reader) {
        throw new Error("No response body");
      }

      while (!streamEnded) {
        const { done, value } = await reader.read();
        if (done && !buffer.trim()) break;
        if (value) buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() ?? "";

        for (const chunk of lines) {
          const dataMatch = chunk.match(/^data:\s*(.+)$/s);
          if (!dataMatch) continue;
          try {
            const data = JSON.parse(dataMatch[1].trim());
            if (data.type === "error") {
              console.error("Stream error:", data.message);
              return;
            }
            if (data.type === "start") {
              startTotal = data.total ?? 0;
              loadingGeometryTotal = startTotal;
              continue;
            }
            if (data.type === "product") {
              const product = data.product;
              loadingGeometryCurrent = data.current ?? metaList.length + 1;
              // Skip synthetic IfcShapeRepresentation entities; their geometry
              // is already exposed via the owning product to avoid duplicates.
              if (product.ifcClass === "IfcShapeRepresentation") {
                continue;
              }
              metaList.push({
                globalId: product.globalId,
                ifcClass: product.ifcClass,
                name: product.name ?? null,
                description: product.description ?? null,
                objectType: product.objectType ?? null,
                tag: product.tag ?? null,
                attributes: product.attributes ?? null,
              });
              if (product.mesh?.vertices && product.mesh?.faces) {
                try {
                  const geometry = createBufferGeometry(
                    product.mesh as RawMeshData,
                  );
                  mgr.addElement(product.globalId, geometry);
                  productEventsWithMesh += 1;
                } catch (err) {
                  console.warn(
                    `Failed to load geometry for ${product.globalId}:`,
                    err,
                  );
                }
              }
              await new Promise((r) => requestAnimationFrame(r));
              continue;
            }
            if (data.type === "end") {
              streamEnded = true;
              break;
            }
          } catch (e) {
            console.warn("Parse stream chunk:", e);
          }
        }
        if (done || streamEnded) break;
      }

      if (buffer.trim()) {
        const dataMatch = buffer.match(/^data:\s*(.+)$/s);
        if (dataMatch) {
          try {
            const data = JSON.parse(dataMatch[1].trim());
            if (data.type === "product") {
              const product = data.product;
              // Skip synthetic IfcShapeRepresentation entities for the final
              // buffered event as well.
              if (product.ifcClass !== "IfcShapeRepresentation") {
                metaList.push({
                  globalId: product.globalId,
                  ifcClass: product.ifcClass,
                  name: product.name ?? null,
                  description: product.description ?? null,
                  objectType: product.objectType ?? null,
                  tag: product.tag ?? null,
                  attributes: product.attributes ?? null,
                });
                if (product.mesh?.vertices && product.mesh?.faces) {
                  try {
                    const geometry = createBufferGeometry(
                      product.mesh as RawMeshData,
                    );
                    mgr.addElement(product.globalId, geometry);
                    productEventsWithMesh += 1;
                  } catch (_) {}
                }
              }
            }
          } catch (_) {}
        }
      }

      searchState.setProducts(metaList);

      // If the Table popup is open, push updated context so it sees
      // the latest filtered entities instead of only the initial snapshot.
      try {
        sendTableContext();
      } catch {
        // Best-effort; table popup might not be open yet.
      }

      if (Object.keys(filterVars).length === 0) {
        searchState.totalProductCount = metaList.length;
        totalCountKey = `${branchId}:${revision}`;
      }

      if (mgr.elementCount > 0) {
        mgr.fitToContent();
      }
    } catch (err) {
      console.error("Failed to load geometry:", err);
    } finally {
      loadingGeometry = false;
      loadingGeometryCurrent = 0;
      loadingGeometryTotal = 0;
    }
  }

  function hexToThreeColor(hex: string): number {
    return parseInt(hex.replace('#', ''), 16);
  }

  async function handleFilterSetColorToggle() {
    const mgr = sceneManager;
    const branchId = projectState.activeBranchId;
    const rev = revisionState.activeRevision;
    if (!mgr || !branchId || rev === null) return;

    if (!filterSetColorsEnabled) {
      mgr.applyFilterSetColors(null);
      return;
    }

    await applyFilterSetColorsToScene(mgr, branchId, rev);
  }

  async function applyFilterSetColorsToScene(
    mgr: SceneManager,
    branchId: string,
    revision: number,
  ) {
    try {
      const result = await client
        .query(FILTER_SET_MATCHES_QUERY, { branchId, revision }, { requestPolicy: "network-only" })
        .toPromise();
      const matches = result.data?.filterSetMatches ?? [];
      if (matches.length === 0) {
        mgr.applyFilterSetColors(null);
        return;
      }

      const colorMap = new Map<string, number>();
      for (const match of matches) {
        const colorHex = hexToThreeColor(match.color);
        for (const gid of match.globalIds) {
          if (!colorMap.has(gid)) {
            colorMap.set(gid, colorHex);
          }
        }
      }
      mgr.applyFilterSetColors(colorMap);
    } catch (err) {
      console.error("Failed to fetch filter set matches:", err);
    }
  }

  async function handleImportSubmit(file: File) {
    const branchId = projectState.activeBranchId;
    if (!branchId) return;

    showImportModal = false;
    importing = true;
    importError = null;

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("branch_id", String(branchId));

      const res = await fetch(`${API_BASE}/upload-ifc`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Upload failed (${res.status})`);
      }

      const result = await res.json();
      revisionState.activeRevision = result.revision_seq;
    } catch (err) {
      importError = err instanceof Error ? err.message : "Import failed";
    } finally {
      importing = false;
    }
  }
</script>

<main>
  <header class="app-header">
    <div class="brand">
      <button
        type="button"
        class="brand-title"
        aria-label="BimAtlas – go to project selection"
        title="Go to project selection"
        onclick={() => {
          projectState.activeProjectId = null;
          projectState.activeBranchId = null;
          revisionState.activeRevision = null;
        }}
      >
        BimAtlas
      </button>
    </div>

    <!-- Project (read-only when active; use BimAtlas button to change) -->
    {#if projectState.activeProjectId && activeProject}
      <div class="context-selector">
        <div class="selector-group selector-group--readonly">
          <span class="selector-label">Project</span>
          <span
            class="selector selector--readonly"
            title="Click BimAtlas to select another project"
          >
            {activeProject.name}
          </span>
        </div>

        <span class="separator">/</span>

        <!-- Branch selector -->
        <div class="selector-group selector-group--branch">
          <label class="selector-label" for="branch-select">Branch</label>
          <select
            id="branch-select"
            class="selector"
            value={projectState.activeBranchId}
            onchange={(e) =>
              selectBranch((e.target as HTMLSelectElement).value)}
          >
            {#each activeProject.branches as b}
              <option value={b.id}>{b.name}</option>
            {/each}
          </select>
          <button
            class="icon-btn"
            onclick={() => (showCreateBranch = true)}
            title="New branch"
          >
            +
          </button>
          <button
            type="button"
            class="icon-btn icon-btn--danger"
            title="Delete branch"
            aria-label="Delete branch {activeBranch?.name}"
            disabled={!activeProject || activeProject.branches.length <= 1}
            onclick={() => {
              if (activeBranch) {
                branchToDelete = activeBranch;
                showDeleteBranch = true;
              }
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
              <path
                d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14z"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path
                d="M10 11v6M14 11v6"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
              />
            </svg>
          </button>
        </div>
      </div>
    {/if}

    <div class="header-spacer"></div>
  </header>

  <div class="content">
    {#if loadingProjects}
      <!-- Loading projects -->
      <div class="center-message">
        <Spinner size="3rem" message="Loading projects..." />
      </div>
    {:else if !projectState.activeProjectId}
      <!-- Project picker / creator -->
      <div class="project-picker">
        <div class="picker-card">
          <h2>Welcome to BimAtlas</h2>
          <p class="picker-subtitle">
            Select an existing project or create a new one to get started.
          </p>

          {#if projects.length > 0}
            <div class="project-list">
              {#each projects as p}
                <div class="project-item">
                  <button
                    type="button"
                    class="project-item-main"
                    onclick={() => selectProject(p.id)}
                  >
                    <div class="project-item-info">
                      <span class="project-item-name">{p.name}</span>
                      {#if p.description}
                        <span class="project-item-desc">{p.description}</span>
                      {/if}
                    </div>
                    <span class="project-item-branches"
                      >{p.branches.length} branch{p.branches.length !== 1
                        ? "es"
                        : ""}</span
                    >
                  </button>
                  <button
                    type="button"
                    class="icon-btn icon-btn--danger no-background"
                    title="Delete project"
                    aria-label="Delete project {p.name}"
                    onclick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      projectToDelete = p;
                      showDeleteProject = true;
                    }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                      <path
                        d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14z"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                      <path
                        d="M10 11v6M14 11v6"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                      />
                    </svg>
                  </button>
                </div>
              {/each}
            </div>
          {:else}
            <p class="empty-msg">No projects yet.</p>
          {/if}

          {#if showCreateProject}
            <div class="create-form">
              <input
                class="input"
                type="text"
                placeholder="Project name"
                bind:value={newProjectName}
                onkeydown={(e) => e.key === "Enter" && handleCreateProject()}
              />
              <input
                class="input"
                type="text"
                placeholder="Description (optional)"
                bind:value={newProjectDesc}
              />
              <div class="form-actions">
                <button
                  class="btn btn-secondary"
                  onclick={() => (showCreateProject = false)}>Cancel</button
                >
                <button
                  class="btn btn-primary"
                  disabled={!newProjectName.trim() || creatingProject}
                  onclick={handleCreateProject}
                >
                  {creatingProject ? "Creating..." : "Create Project"}
                </button>
              </div>
            </div>
          {:else}
            <button
              class="btn btn-primary create-project-btn"
              onclick={() => (showCreateProject = true)}
            >
              + New Project
            </button>
          {/if}
        </div>
      </div>
    {:else}
      <div class="viewport-container">
        <Viewport bind:manager={sceneManager} />
        {#if loadingGeometry}
          <div
            class="viewport-loading-overlay"
            aria-live="polite"
            aria-busy="true"
          >
            <div class="viewport-loading-card">
              <Spinner size="3rem" />
              <p class="viewport-loading-message">
                {loadingGeometryTotal === 0
                  ? "Loading model…"
                  : `Rendering ${loadingGeometryCurrent}/${loadingGeometryTotal} objects`}
              </p>
              {#if loadingGeometryTotal > 0}
                <div class="viewport-loading-bar">
                  <div
                    class="viewport-loading-fill"
                    style="width: {Math.round(
                      (loadingGeometryCurrent / loadingGeometryTotal) * 100,
                    )}%"
                  ></div>
                </div>
              {/if}
            </div>
          </div>
        {/if}
      </div>
      <div class="viewport-overlay">
        <Sidebar>
          <!-- Import IFC -->
          <button
            class="toolbar-btn import-btn"
            onclick={() => (showImportModal = true)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
              <path
                d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <polyline
                points="17 8 12 3 7 8"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <line
                x1="12"
                y1="3"
                x2="12"
                y2="15"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            Import IFC
          </button>
          <!-- Fit view -->
          <button
            class="toolbar-btn"
            onclick={() => sceneManager?.fitToContent()}
          >
            Fit View
          </button>
          <!-- Revision filters (when branch is active) -->
          {#if projectState.activeBranchId}
            <section
              class="sidebar-section revision-search-section"
              aria-labelledby="revision-search-heading"
            >
              <h2 id="revision-search-heading" class="sidebar-section-heading">
                Revision
              </h2>

              <!-- Filter revisions (collapsible) -->
              <div class="revision-filter-group">
                <button
                  type="button"
                  class="revision-filter-group-header"
                  aria-expanded={!revisionFilterCollapsed}
                  aria-controls="revision-filter-content"
                  onclick={() =>
                    (revisionFilterCollapsed = !revisionFilterCollapsed)}
                >
                  <span>Filter revisions</span>
                  <span
                    class="revision-filter-group-chevron"
                    class:collapsed={revisionFilterCollapsed}
                    aria-hidden="true">▼</span
                  >
                </button>
                <div
                  id="revision-filter-content"
                  class="revision-filter-group-content"
                  class:collapsed={revisionFilterCollapsed}
                >
                  <!-- Author -->
                  <div class="filter-row revision-filter-row">
                    <label class="revision-filter-checkbox filter-row-label">
                      <input
                        type="checkbox"
                        bind:checked={revisionFilterAuthor.enabled}
                      />
                      <span>Author</span>
                    </label>
                    <div class="filter-fields">
                      <input
                        type="text"
                        class="filter-select revision-filter-input"
                        placeholder="Author…"
                        aria-label="Filter by author"
                        bind:value={revisionFilterAuthor.text}
                      />
                    </div>
                  </div>

                  <!-- IFC Filename -->
                  <div class="filter-row revision-filter-row">
                    <label class="revision-filter-checkbox filter-row-label">
                      <input
                        type="checkbox"
                        bind:checked={revisionFilterFilename.enabled}
                      />
                      <span>IFC Filename</span>
                    </label>
                    <div class="filter-fields">
                      <input
                        type="text"
                        class="filter-select revision-filter-input"
                        placeholder="Filename…"
                        aria-label="Filter by IFC filename"
                        bind:value={revisionFilterFilename.text}
                      />
                    </div>
                  </div>

                  <!-- Commit message -->
                  <div class="filter-row revision-filter-row">
                    <label class="revision-filter-checkbox filter-row-label">
                      <input
                        type="checkbox"
                        bind:checked={revisionFilterMessage.enabled}
                      />
                      <span>Commit message</span>
                    </label>
                    <div class="filter-fields">
                      <input
                        type="text"
                        class="filter-select revision-filter-input"
                        placeholder="Message…"
                        aria-label="Filter by commit message"
                        bind:value={revisionFilterMessage.text}
                      />
                    </div>
                  </div>

                  <!-- Created after (date picker) -->
                  <div class="filter-row revision-filter-row">
                    <label class="revision-filter-checkbox filter-row-label">
                      <input
                        type="checkbox"
                        bind:checked={revisionFilterCreatedAfter.enabled}
                      />
                      <span>Created after</span>
                    </label>
                    <div class="filter-fields">
                      <input
                        type="date"
                        class="filter-select revision-date-input"
                        aria-label="Created after date"
                        bind:value={revisionFilterCreatedAfter.text}
                      />
                    </div>
                  </div>

                  <!-- Created before (date picker) -->
                  <div class="filter-row revision-filter-row">
                    <label class="revision-filter-checkbox filter-row-label">
                      <input
                        type="checkbox"
                        bind:checked={revisionFilterCreatedBefore.enabled}
                      />
                      <span>Created before</span>
                    </label>
                    <div class="filter-fields">
                      <input
                        type="date"
                        class="filter-select revision-date-input"
                        aria-label="Created before date"
                        bind:value={revisionFilterCreatedBefore.text}
                      />
                    </div>
                  </div>

                  <!-- Results (matching revisions) -->
                  <div class="revision-list-wrapper">
                    <h3 class="revision-results-heading">Results</h3>
                    {#if loadingRevisions}
                      <span class="revision-loading" aria-live="polite"
                        >Loading…</span
                      >
                    {:else if revisionList.length === 0}
                      <p class="revision-empty">No revisions match.</p>
                    {:else}
                      <ul class="revision-list" role="list">
                        {#each revisionList as r}
                          <li>
                            <button
                              type="button"
                              class="revision-item"
                              onclick={() =>
                                (revisionState.activeRevision = r.revisionSeq)}
                            >
                              <span class="revision-seq">#{r.revisionSeq}</span>
                              {#if r.ifcFilename}
                                <span class="revision-filename"
                                  >{r.ifcFilename}</span
                                >
                              {/if}
                              {#if r.label}
                                <span class="revision-label">{r.label}</span>
                              {/if}
                              {#if r.authorId}
                                <span class="revision-author">{r.authorId}</span
                                >
                              {/if}
                            </button>
                          </li>
                        {/each}
                      </ul>
                    {/if}
                  </div>
                </div>
              </div>

              <!-- Current revision (always the displayed one, not dependent on filters) -->
              {#if revisionState.activeRevision !== null}
                <div
                  class="current-revision-block"
                  aria-label="Current revision"
                >
                  {#if currentRevisionRow}
                    <div class="revision-item revision-item--current">
                      <span class="revision-current-label"
                        >Current Revision</span
                      >
                      <span class="revision-seq"
                        >#{currentRevisionRow.revisionSeq}</span
                      >
                      {#if currentRevisionRow.ifcFilename}
                        <span class="revision-filename"
                          >{currentRevisionRow.ifcFilename}</span
                        >
                      {/if}
                      {#if currentRevisionRow.label}
                        <span class="revision-label"
                          >{currentRevisionRow.label}</span
                        >
                      {/if}
                      {#if currentRevisionRow.authorId}
                        <span class="revision-author"
                          >{currentRevisionRow.authorId}</span
                        >
                      {/if}
                    </div>
                  {:else}
                    <div
                      class="revision-item revision-item--current revision-item--current-minimal"
                    >
                      <span class="revision-current-label"
                        >Current Revision</span
                      >
                      <span class="revision-seq"
                        >#{revisionState.activeRevision}</span
                      >
                      <span class="revision-current-not-in-filter"
                        >(not in filtered list)</span
                      >
                    </div>
                  {/if}
                </div>
              {/if}
            </section>
          {/if}
          <!-- View Options section -->
          <section
            class="sidebar-section"
            aria-labelledby="view-options-heading"
          >
            <h2 id="view-options-heading" class="sidebar-section-heading">
              View Options
            </h2>
            <DepthWidget bind:value={selection.subgraphDepth} />
          </section>
        </Sidebar>
        <div class="search-actions">
          <!-- Search button -->
          <button
            class="search-btn"
            onclick={openSearchPopup}
            aria-label="Search and filter"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <circle
                cx="11"
                cy="11"
                r="7"
                stroke="currentColor"
                stroke-width="2"
              />
              <path
                d="M16.5 16.5L21 21"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
              />
            </svg>
            Search
          </button>
          <!-- Open Graph popup button -->
          <button
            class="graph-btn"
            onclick={openGraphPopup}
            aria-label="Open graph in new tab"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <!-- Edges: center to outer nodes -->
              <line
                x1="12"
                y1="12"
                x2="12"
                y2="6"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
              <line
                x1="12"
                y1="12"
                x2="18"
                y2="14"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
              <line
                x1="12"
                y1="12"
                x2="7"
                y2="15"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
              <line
                x1="12"
                y1="12"
                x2="8"
                y2="9"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
              <!-- Nodes -->
              <circle
                cx="12"
                cy="12"
                r="2.5"
                stroke="currentColor"
                stroke-width="1.5"
                fill="none"
              />
              <circle
                cx="12"
                cy="6"
                r="2"
                stroke="currentColor"
                stroke-width="1.5"
                fill="none"
              />
              <circle
                cx="18"
                cy="14"
                r="2"
                stroke="currentColor"
                stroke-width="1.5"
                fill="none"
              />
              <circle
                cx="7"
                cy="15"
                r="2"
                stroke="currentColor"
                stroke-width="1.5"
                fill="none"
              />
              <circle
                cx="8"
                cy="9"
                r="2"
                stroke="currentColor"
                stroke-width="1.5"
                fill="none"
              />
            </svg>
            Graph
          </button>
          <!-- Table popup button -->
          <button
            class="table-btn"
            onclick={openTablePopup}
            aria-label="Open table view"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path
                d="M3 6h18M3 12h18M3 18h18"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
              />
              <path
                d="M3 6v12h18V6H3z"
                stroke="currentColor"
                stroke-width="2"
                fill="none"
              />
            </svg>
            Table
          </button>
          <!-- Attribute panel pop-out button -->
          <button
            class="attributes-btn"
            onclick={openAttributesPopup}
            aria-label="Open attribute panel"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <rect
                x="4"
                y="4"
                width="10"
                height="10"
                rx="1.5"
                stroke="currentColor"
                stroke-width="2"
              />
              <path
                d="M14 10H20V20H10V14"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            Attributes
          </button>
          <!-- Agent popup button -->
          <button
            class="agent-btn"
            onclick={openAgentPopup}
            aria-label="Open AI agent"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 2C6.48 2 2 6.02 2 11c0 2.62 1.2 4.98 3.09 6.61L4 22l4.54-2.27A10.9 10.9 0 0012 20c5.52 0 10-3.58 10-8s-4.48-9-10-9z"
                stroke="currentColor"
                stroke-width="2"
                fill="none"
              />
              <circle cx="8" cy="11" r="1" fill="currentColor" />
              <circle cx="12" cy="11" r="1" fill="currentColor" />
              <circle cx="16" cy="11" r="1" fill="currentColor" />
            </svg>
            Agent
          </button>
        </div>
        <!-- Element count -->
        <span class="element-count"
          >{sceneManager?.elementCount ?? 0} elements</span
        >
      </div>
    {/if}

    <!-- Import modal -->
    <ImportModal
      open={showImportModal}
      onclose={() => (showImportModal = false)}
      onsubmit={handleImportSubmit}
    />

    <!-- Delete project confirmation modal -->
    {#if showDeleteProject && projectToDelete}
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <div
        class="backdrop"
        role="dialog"
        aria-modal="true"
        aria-label="Delete project"
        tabindex="-1"
        onclick={(e) => {
          if (e.target === e.currentTarget) {
            showDeleteProject = false;
            projectToDelete = null;
          }
        }}
        onkeydown={(e) => {
          if (e.key === "Escape") {
            showDeleteProject = false;
            projectToDelete = null;
          }
        }}
      >
        <div class="modal">
          <header class="modal-header">
            <h2>Delete project</h2>
            <button
              class="close-btn"
              onclick={() => {
                showDeleteProject = false;
                projectToDelete = null;
              }}
              aria-label="Close"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path
                  d="M4 4L12 12M12 4L4 12"
                  stroke="currentColor"
                  stroke-width="1.5"
                  stroke-linecap="round"
                />
              </svg>
            </button>
          </header>
          <p class="modal-subtitle">
            Delete project <strong>{projectToDelete.name}</strong>? This will
            permanently delete all branches, revisions, and model data.
          </p>
          <footer class="modal-footer">
            <button
              class="btn btn-secondary"
              onclick={() => {
                showDeleteProject = false;
                projectToDelete = null;
              }}
            >
              Cancel
            </button>
            <button
              class="btn btn-danger"
              disabled={deletingProject}
              onclick={handleDeleteProject}
            >
              {deletingProject ? "Deleting..." : "Delete project"}
            </button>
          </footer>
        </div>
      </div>
    {/if}

    <!-- Delete branch confirmation modal -->
    {#if showDeleteBranch && branchToDelete}
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <div
        class="backdrop"
        role="dialog"
        aria-modal="true"
        aria-label="Delete branch"
        tabindex="-1"
        onclick={(e) => {
          if (e.target === e.currentTarget) {
            showDeleteBranch = false;
            branchToDelete = null;
          }
        }}
        onkeydown={(e) => {
          if (e.key === "Escape") {
            showDeleteBranch = false;
            branchToDelete = null;
          }
        }}
      >
        <div class="modal">
          <header class="modal-header">
            <h2>Delete branch</h2>
            <button
              class="close-btn"
              onclick={() => {
                showDeleteBranch = false;
                branchToDelete = null;
              }}
              aria-label="Close"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path
                  d="M4 4L12 12M12 4L4 12"
                  stroke="currentColor"
                  stroke-width="1.5"
                  stroke-linecap="round"
                />
              </svg>
            </button>
          </header>
          <p class="modal-subtitle">
            Delete branch <strong>{branchToDelete.name}</strong>? This will
            permanently delete all revisions and model data on this branch.
          </p>
          <footer class="modal-footer">
            <button
              class="btn btn-secondary"
              onclick={() => {
                showDeleteBranch = false;
                branchToDelete = null;
              }}
            >
              Cancel
            </button>
            <button
              class="btn btn-danger"
              disabled={deletingBranch}
              onclick={handleDeleteBranch}
            >
              {deletingBranch ? "Deleting..." : "Delete branch"}
            </button>
          </footer>
        </div>
      </div>
    {/if}

    <!-- Create branch modal -->
    {#if showCreateBranch}
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <div
        class="backdrop"
        role="dialog"
        aria-modal="true"
        aria-label="Create branch"
        tabindex="-1"
        onclick={(e) => {
          if (e.target === e.currentTarget) showCreateBranch = false;
        }}
        onkeydown={(e) => {
          if (e.key === "Escape") showCreateBranch = false;
        }}
      >
        <div class="modal">
          <header class="modal-header">
            <h2>New Branch</h2>
            <button
              class="close-btn"
              onclick={() => (showCreateBranch = false)}
              aria-label="Close"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path
                  d="M4 4L12 12M12 4L4 12"
                  stroke="currentColor"
                  stroke-width="1.5"
                  stroke-linecap="round"
                />
              </svg>
            </button>
          </header>
          <p class="modal-subtitle">
            Create a new branch in <strong>{activeProject?.name}</strong>.
            Branches start empty until you upload an IFC file.
          </p>
          <input
            class="input modal-input"
            type="text"
            placeholder="Branch name (e.g. structural-update)"
            bind:value={newBranchName}
            onkeydown={(e) => e.key === "Enter" && handleCreateBranch()}
          />
          <footer class="modal-footer">
            <button
              class="btn btn-secondary"
              onclick={() => (showCreateBranch = false)}>Cancel</button
            >
            <button
              class="btn btn-primary"
              disabled={!newBranchName.trim() || creatingBranch}
              onclick={handleCreateBranch}
            >
              {creatingBranch ? "Creating..." : "Create Branch"}
            </button>
          </footer>
        </div>
      </div>
    {/if}

    <!-- Full-screen loading overlay while importing -->
    {#if importing}
      <div class="loading-overlay">
        <Spinner size="3.5rem" message="Parsing and importing IFC model..." />
      </div>
    {/if}

    <!-- Import error toast -->
    {#if importError}
      <div class="error-toast">
        <span>{importError}</span>
        <button
          class="toast-close"
          onclick={() => (importError = null)}
          aria-label="Dismiss"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path
              d="M4 4L12 12M12 4L4 12"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
            />
          </svg>
        </button>
      </div>
    {/if}
  </div>
</main>

<style>
  main {
    display: flex;
    flex-direction: column;
    height: 100vh;
    margin: 0;
    padding: 0;
    color: #e0e0e0;
    font-family:
      system-ui,
      -apple-system,
      sans-serif;
  }

  /* ---- Header ---- */

  .app-header {
    display: flex;
    align-items: center;
    padding: 0 1rem;
    height: 48px;
    min-height: 48px;
    background: #1a1a2e;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    gap: 1rem;
  }

  .brand-title {
    margin: 0;
    padding: 0;
    border: none;
    background: none;
    font-family: inherit;
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    background: linear-gradient(135deg, #ff6644, #ff9966);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    cursor: pointer;
  }

  .brand-title:hover {
    opacity: 0.9;
  }

  .header-spacer {
    flex: 1;
  }

  /* ---- Context selector (project / branch) ---- */

  .context-selector {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex: 0 0 50%;
    max-width: 50%;
    min-width: 0;
  }

  .selector-group {
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }

  .selector-label {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #666;
  }

  .selector {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.3rem;
    color: #ddd;
    padding: 0.25rem 0.5rem;
    font-size: 0.8rem;
    cursor: pointer;
    outline: none;
    max-width: 180px;
  }

  .selector--readonly {
    cursor: default;
  }

  /* Allow the branch selector to grow and occupy half of the header context area */
  .selector-group--branch {
    flex: 1;
    min-width: 0;
  }

  #branch-select.selector {
    flex: 1 1 auto;
    max-width: none;
  }

  .selector:focus {
    border-color: rgba(255, 136, 102, 0.4);
  }

  .selector option {
    background: #1e1e30;
    color: #ddd;
  }

  .separator {
    color: #555;
    font-size: 1rem;
  }

  .revision-search-section {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  /* CSS grid so all revision filter rows share the same column alignment */
  .revision-search-section .filter-row.revision-filter-row {
    display: grid;
    grid-template-columns: 7.5rem 1fr;
    gap: 0.5rem 0.75rem;
    align-items: start;
    padding: 0.4rem 0;
    min-width: 0;
  }

  .revision-search-section .filter-row-label,
  .revision-search-section .revision-filter-checkbox {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.7rem;
    color: #888;
    cursor: pointer;
    min-width: 0;
    line-height: 1.3;
  }

  .revision-search-section .revision-filter-checkbox input {
    accent-color: #ff8866;
    flex-shrink: 0;
  }

  .revision-search-section .revision-filter-checkbox span {
    word-break: break-word;
    line-height: 1.3;
  }

  .revision-search-section .filter-fields {
    display: flex;
    align-items: stretch;
    gap: 0.35rem;
    min-width: 0;
  }

  .revision-search-section .revision-filter-input {
    width: 100%;
    box-sizing: border-box;
    min-height: 2.25rem;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.3rem;
    color: #ddd;
    padding: 0.3rem 0.45rem;
    font-size: 0.78rem;
    outline: none;
    font-family: inherit;
    cursor: text;
  }

  .revision-search-section .revision-filter-input:focus {
    border-color: rgba(255, 136, 102, 0.4);
  }

  .revision-search-section .revision-filter-input::placeholder {
    color: #555;
  }

  .revision-search-section .revision-date-input {
    width: 100%;
    box-sizing: border-box;
    min-height: 2.25rem;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.3rem;
    color: #ddd;
    padding: 0.3rem 0.45rem;
    font-size: 0.78rem;
    outline: none;
    font-family: inherit;
    cursor: pointer;
  }

  .revision-search-section .revision-date-input:focus {
    border-color: rgba(255, 136, 102, 0.4);
  }

  .revision-search-section
    .revision-date-input::-webkit-calendar-picker-indicator {
    filter: invert(0.8);
    cursor: pointer;
    opacity: 0.8;
  }

  .revision-loading,
  .revision-empty {
    font-size: 0.8rem;
    color: #888;
    margin: 0;
  }

  .revision-list-wrapper {
    margin-top: 0.5rem;
  }

  .revision-results-heading {
    margin: 0 0 0.35rem;
    font-size: 0.8rem;
    font-weight: 600;
    color: #aaa;
    text-transform: none;
    letter-spacing: 0;
  }

  .revision-list {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 160px;
    overflow-y: auto;
  }

  .revision-item {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.35rem;
    width: 100%;
    max-width: 100%;
    box-sizing: border-box;
    padding: 0.35rem 0.5rem;
    font-size: 0.78rem;
    text-align: left;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid transparent;
    border-radius: 0.25rem;
    color: #bbb;
    cursor: pointer;
    margin-bottom: 0.2rem;
  }

  .revision-item:hover {
    background: rgba(255, 136, 102, 0.12);
    color: #ddd;
  }

  .revision-item--current {
    cursor: default;
    background: rgba(255, 136, 102, 0.2);
    border-color: rgba(255, 136, 102, 0.4);
    color: #ff8866;
  }

  .revision-item--current:hover {
    background: rgba(255, 136, 102, 0.2);
    color: #ff8866;
  }

  .revision-item--current,
  .revision-item--current * {
    cursor: default;
  }

  .revision-current-label {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: rgba(255, 136, 102, 0.9);
    width: 100%;
    flex-basis: 100%;
    margin-bottom: 0.15rem;
  }

  .current-revision-block {
    margin-top: 0.75rem;
  }

  .revision-current-not-in-filter {
    font-size: 0.7rem;
    color: #888;
    font-style: italic;
  }

  .revision-seq {
    font-weight: 600;
    color: #999;
  }

  .revision-item--current .revision-seq {
    color: #ff8866;
  }

  /* Collapsible "Filter revisions" group */
  .revision-filter-group {
    margin-top: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .revision-filter-group-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 0.35rem 0;
    font-size: 0.8rem;
    font-weight: 600;
    color: #aaa;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
  }

  .revision-filter-group-header:hover {
    color: #ddd;
  }

  .revision-filter-group-chevron {
    font-size: 0.6rem;
    transition: transform 0.2s ease;
  }

  .revision-filter-group-chevron.collapsed {
    transform: rotate(90deg);
  }

  .revision-filter-group-content.collapsed {
    display: none;
  }

  .revision-filter-group-content:not(.collapsed) {
    display: block;
    margin-top: 0.35rem;
  }

  .revision-filename,
  .revision-label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 140px;
  }

  .revision-item--current .revision-filename,
  .revision-item--current .revision-label {
    overflow: visible;
    text-overflow: unset;
    white-space: normal;
    max-width: none;
    word-break: break-word;
  }

  .revision-author {
    font-size: 0.7rem;
    color: #777;
  }

  .icon-btn {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.3rem;
    color: #aaa;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    font-size: 0.85rem;
    transition:
      background 0.15s,
      color 0.15s;
    padding: 0;
  }

  .icon-btn.no-background {
    background: none;
    border: none;
  }

  .icon-btn.no-background:hover:not(:disabled) {
    background: none;
  }

  .icon-btn--danger.no-background:hover:not(:disabled) {
    background: none;
    color: #ee8888;
  }

  .icon-btn:hover {
    background: rgba(255, 136, 102, 0.2);
    color: #ff8866;
  }

  .icon-btn--danger {
    color: #cc6666;
  }

  .icon-btn--danger:hover:not(:disabled) {
    background: rgba(204, 68, 68, 0.2);
    color: #ee8888;
  }

  .icon-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  /* ---- Content area ---- */

  .content {
    flex: 1;
    display: flex;
    min-height: 0;
    position: relative;
  }

  .center-message {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .viewport-container {
    flex: 1;
    position: relative;
    min-height: 0;
  }

  .viewport-loading-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(26, 26, 46, 0.75);
    z-index: 100;
    pointer-events: none;
  }

  .viewport-loading-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    padding: 1.5rem 2rem;
    background: rgba(30, 30, 48, 0.95);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.5rem;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  }

  .viewport-loading-message {
    margin: 0;
    font-size: 0.9rem;
    color: #aaa;
    white-space: nowrap;
  }

  .viewport-loading-bar {
    width: 200px;
    height: 6px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 3px;
    overflow: hidden;
  }

  .viewport-loading-fill {
    height: 100%;
    background: #ff8866;
    border-radius: 3px;
    transition: width 0.1s ease-out;
  }

  .viewport-overlay {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: 1000;
    display: flex;
    flex-direction: row;
    justify-content: space-between;
    pointer-events: none;
  }

  /* ---- Project picker ---- */

  .project-picker {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
  }

  .picker-card {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    background: #1e1e30;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.75rem;
    padding: 2rem;
    max-width: 520px;
    width: 100%;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  }

  .picker-card h2 {
    font-size: 1.2rem;
    font-weight: 600;
    color: #e0e0e0;
  }

  .picker-subtitle {
    color: #888;
    font-size: 0.85rem;
  }

  .project-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .project-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
    transition:
      background 0.15s,
      border-color 0.15s;
  }

  .project-item:hover {
    background: rgba(255, 136, 102, 0.08);
    border-color: rgba(255, 136, 102, 0.2);
  }

  .project-item-main {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: none;
    border: none;
    padding: 0;
    margin: 0;
    cursor: pointer;
    text-align: left;
    width: 100%;
    color: inherit;
    font: inherit;
    border-radius: 0.3rem;
  }

  .project-item-info {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }

  .project-item-name {
    font-size: 0.9rem;
    font-weight: 500;
    color: #e0e0e0;
  }

  .project-item-desc {
    font-size: 0.75rem;
    color: #888;
  }

  .project-item-branches {
    font-size: 0.72rem;
    color: #666;
    white-space: nowrap;
  }

  .empty-msg {
    color: #666;
    font-size: 0.85rem;
    text-align: center;
  }

  .create-form {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
  }

  .input {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 0.4rem;
    color: #e0e0e0;
    padding: 0.5rem 0.75rem;
    font-size: 0.85rem;
    outline: none;
    transition: border-color 0.15s;
  }

  .input:focus {
    border-color: rgba(255, 136, 102, 0.4);
  }

  .input::placeholder {
    color: #555;
  }

  .create-project-btn {
    width: 100%;
  }

  /* ---- Buttons ---- */

  .btn {
    padding: 0.5rem 1.1rem;
    font-size: 0.82rem;
    border: none;
    border-radius: 0.4rem;
    cursor: pointer;
    font-weight: 500;
    transition:
      background 0.15s,
      opacity 0.15s;
  }

  .btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .btn-secondary {
    background: rgba(255, 255, 255, 0.06);
    color: #aaa;
  }

  .btn-secondary:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.1);
    color: #ccc;
  }

  .btn-primary {
    background: rgba(255, 136, 102, 0.2);
    color: #ff8866;
  }

  .btn-primary:hover:not(:disabled) {
    background: rgba(255, 136, 102, 0.35);
    color: #ffaa88;
  }

  .btn-danger {
    background: rgba(204, 68, 68, 0.2);
    color: #cc6666;
  }

  .btn-danger:hover:not(:disabled) {
    background: rgba(204, 68, 68, 0.35);
    color: #ee8888;
  }

  /* ---- Viewport toolbar overlay ---- */

  .toolbar-btn {
    background: rgba(26, 26, 46, 0.85);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #ccc;
    padding: 0.4rem 0.8rem;
    border-radius: 0.35rem;
    cursor: pointer;
    font-size: 0.78rem;
    backdrop-filter: blur(8px);
    transition:
      background 0.15s,
      color 0.15s;
  }

  .toolbar-btn:hover {
    background: rgba(255, 102, 68, 0.2);
    color: #fff;
  }

  .sidebar-section {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .sidebar-section-heading {
    margin: 0;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #666;
  }

  .element-count {
    position: absolute;
    bottom: 1rem;
    right: 1rem;
    font-size: 0.72rem;
    color: #666;
  }

  .import-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.35rem;
  }

  .search-actions {
    position: absolute;
    bottom: 1rem;
    left: 50%;
    transform: translateX(-50%);
    pointer-events: auto;
    display: inline-flex;
    gap: 0.5rem;
  }

  .search-btn,
  .graph-btn,
  .table-btn,
  .attributes-btn,
  .agent-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: rgba(26, 26, 46, 0.9);
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: #ccc;
    padding: 0.45rem 1rem;
    border-radius: 0.4rem;
    cursor: pointer;
    font-size: 0.82rem;
    backdrop-filter: blur(8px);
    transition:
      background 0.15s,
      color 0.15s,
      border-color 0.15s;
  }

  .search-btn:hover,
  .graph-btn:hover,
  .table-btn:hover,
  .attributes-btn:hover,
  .agent-btn:hover {
    background: rgba(255, 102, 68, 0.2);
    border-color: rgba(255, 136, 102, 0.3);
    color: #fff;
  }

  /* ---- Modal (shared) ---- */

  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(4px);
  }

  .modal {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    background: #1e1e30;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.75rem;
    width: 90%;
    max-width: 420px;
    padding: 1.5rem;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .modal-header h2 {
    font-size: 1.05rem;
    font-weight: 600;
    color: #e0e0e0;
  }

  .close-btn {
    background: none;
    border: none;
    color: #666;
    cursor: pointer;
    padding: 0.25rem;
    border-radius: 0.25rem;
    display: flex;
    align-items: center;
    transition: color 0.15s;
  }

  .close-btn:hover {
    color: #ccc;
  }

  .modal-subtitle {
    font-size: 0.82rem;
    color: #888;
    line-height: 1.4;
  }

  .modal-subtitle strong {
    color: #ccc;
  }

  .modal-input {
    width: 100%;
    box-sizing: border-box;
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.6rem;
  }

  /* ---- Loading overlay ---- */

  .loading-overlay {
    position: fixed;
    inset: 0;
    z-index: 1100;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(18, 18, 30, 0.85);
    backdrop-filter: blur(6px);
  }

  /* ---- Error toast ---- */

  .error-toast {
    position: fixed;
    bottom: 1.5rem;
    left: 50%;
    transform: translateX(-50%);
    z-index: 300;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.65rem 1rem;
    background: rgba(255, 107, 107, 0.12);
    border: 1px solid rgba(255, 107, 107, 0.25);
    border-radius: 0.5rem;
    color: #ff8888;
    font-size: 0.82rem;
    backdrop-filter: blur(8px);
    max-width: 90%;
  }

  .toast-close {
    background: none;
    border: none;
    color: inherit;
    cursor: pointer;
    padding: 0.15rem;
    display: flex;
    opacity: 0.6;
    transition: opacity 0.15s;
  }

  .toast-close:hover {
    opacity: 1;
  }
</style>
