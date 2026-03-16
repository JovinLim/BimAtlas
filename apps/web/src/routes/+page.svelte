<script lang="ts">
  /**
   * Main BimAtlas page -- project/branch selector, 3D viewport, force graph, and selection panel.
   * Users first select (or create) a project, then pick a branch. All IFC data is scoped to the branch.
   */
  import Viewport from "$lib/ui/Viewport.svelte";
  import ImportModal from "$lib/ui/ImportModal.svelte";
  import SaveAsViewModal from "$lib/ui/SaveAsViewModal.svelte";
  import Spinner from "$lib/ui/Spinner.svelte";
  import Sidebar from "$lib/ui/Sidebar.svelte";
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
    APPLY_FILTER_SETS_MESSAGE_TYPE,
    APPLY_FILTER_SETS_STORAGE_KEY,
    SEARCH_CHANNEL,
    type FilterSet,
    type ProductMeta,
    type SearchFilter,
    type SearchMessage,
  } from "$lib/search/protocol";
  import {
    ATTRIBUTES_CHANNEL,
    type AttributesContextPayload,
    type AttributesMessage,
  } from "$lib/attributes/protocol";
  import { getDescendantClasses } from "$lib/ifc/schema";
  import { getGraphStore } from "$lib/graph/graphStore.svelte";
  import { computeSubgraph } from "$lib/graph/subgraph";
  import {
    GRAPH_CHANNEL,
    type GraphContextPayload,
    type GraphMessage,
  } from "$lib/graph/protocol";
  import {
    TABLE_CHANNEL,
    TABLE_PROTOCOL_VERSION,
    type TableMessage,
  } from "$lib/table/protocol";
  import { SCHEMA_CHANNEL, type SchemaMessage } from "$lib/schema/protocol";
  import {
    VALIDATION_CHANNEL,
    type ValidationContextPayload,
    type ValidationMessage,
  } from "$lib/validation/protocol";
  import {
    VIEWS_CHANNEL,
    type ViewsMessage,
    type SavedViewPayload,
  } from "$lib/views/protocol";
  import type { SceneManager } from "$lib/engine/SceneManager";
  import {
    client,
    APPLIED_FILTER_SETS_QUERY,
    APPLY_FILTER_SETS_MUTATION,
    FILTER_SET_MATCHES_QUERY,
    PROJECTS_QUERY,
    CREATE_PROJECT_MUTATION,
    CREATE_BRANCH_MUTATION,
    DELETE_PROJECT_MUTATION,
    DELETE_BRANCH_MUTATION,
    REVISIONS_QUERY,
    IFC_PRODUCT_TREE_QUERY,
    CREATE_SAVED_VIEW_MUTATION,
    ATTACH_FILTER_SETS_TO_SAVED_VIEW_MUTATION,
  } from "$lib/api/client";
  import {
    createBufferGeometry,
    type RawMeshData,
  } from "$lib/engine/BufferGeometryLoader";
  import { untrack, onMount, onDestroy, tick } from "svelte";
  import { loadSettings, saveSettings } from "$lib/state/persistence";
  import { setProductTreeFromApi } from "$lib/ifc/schema";

  /** Maps vertical wheel scroll to horizontal scroll on the element. */
  function wheelToHorizontalScroll(node: HTMLElement) {
    function handleWheel(e: WheelEvent) {
      if (node.scrollWidth <= node.clientWidth) return;
      node.scrollLeft += e.deltaY;
      e.preventDefault();
    }
    node.addEventListener("wheel", handleWheel, { passive: false });
    return {
      destroy() {
        node.removeEventListener("wheel", handleWheel);
      },
    };
  }

  const selection = getSelection();
  const revisionState = getRevisionState();
  const projectState = getProjectState();
  const graphStore = getGraphStore();
  const searchState = getSearchState();

  let sceneManager: SceneManager | undefined = $state(undefined);
  let elementCount = $state(0);
  let filterSetColorsEnabled = $state(false);
  let searchPopup: Window | null = null;
  let searchChannel: BroadcastChannel | null = null;
  let attributePopup: Window | null = null;
  let attributesChannel: BroadcastChannel | null = null;
  let graphPopup: Window | null = null;
  let graphChannel: BroadcastChannel | null = null;
  let tablePopup: Window | null = null;
  let tableChannel: BroadcastChannel | null = null;
  let schemaPopup: Window | null = null;
  let schemaChannel: BroadcastChannel | null = null;
  let validationPopup: Window | null = null;
  let validationChannel: BroadcastChannel | null = null;
  let viewsPopup: Window | null = null;
  let viewsChannel: BroadcastChannel | null = null;
  const APPLIED_FILTER_SETS_COMBINATION_LOGIC: "OR" = "OR";
  let lastSentAttributesContextKey: string | null = null;
  let lastSentGraphContextKey: string | null = null;
  let lastSentTableContextKey: string | null = null;
  let lastSentValidationContextKey: string | null = null;
  /** Set by table popup via sync-mode message; when true, selection syncs both ways. */
  let tableSyncEnabled = $state(false);

  type MessageWithType = { type: string };
  type ChannelHandlers<T extends MessageWithType> = {
    [K in T["type"]]?: (message: Extract<T, { type: K }>) => void;
  };

  function setupChannel<T extends MessageWithType>(
    channelName: string,
    handlers: ChannelHandlers<T>,
  ): BroadcastChannel {
    const nextChannel = new BroadcastChannel(channelName);
    nextChannel.onmessage = (e: MessageEvent<T>) => {
      const message = e.data;
      if (!message || typeof message.type !== "string") return;
      const handler = handlers[message.type as T["type"]] as
        | ((msg: T) => void)
        | undefined;
      handler?.(message);
    };
    return nextChannel;
  }

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
        if (
          event.type === "filter-applied" ||
          event.type === "filter-set-changed"
        ) {
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
  let showSaveAsViewModal = $state(false);
  let saveAsViewError = $state<string | null>(null);
  let importing = $state(false);
  let importError = $state<string | null>(null);
  let importProgressPercent = $state(0);
  let importProgressMessage = $state("Preparing import...");
  let loadingGeometry = $state(false);
  let loadingGeometryCurrent = $state(0);
  let loadingGeometryTotal = $state(0);
  let totalCountKey = $state<string | null>(null);
  let productTreeKey = $state<string | null>(null);
  let geometryAbort: AbortController | null = null;

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

  function resolveContextNames(
    projectId: string | null,
    branchId: string | null,
  ): { projectName: string | null; branchName: string | null } {
    let projectName: string | null = null;
    let branchName: string | null = null;
    let project: ProjectData | null = null;

    if (projectId != null) {
      project = projects.find((p) => p.id === projectId) ?? null;
      projectName = project?.name ?? null;
    }

    if (branchId == null) {
      return { projectName, branchName };
    }

    const branchInProject = project?.branches.find((b) => b.id === branchId);
    if (branchInProject) {
      return { projectName, branchName: branchInProject.name };
    }

    for (const p of projects) {
      const branch = p.branches.find((b) => b.id === branchId);
      if (!branch) continue;
      if (projectName == null) projectName = p.name;
      branchName = branch.name;
      break;
    }

    return { projectName, branchName };
  }

  function openPopupWithContext(
    popup: Window | null,
    options: {
      route: string;
      name: string;
      features: string;
      params: Record<string, string | number | null>;
      sendContext: () => void;
    },
  ): Window | null {
    if (!popup || popup.closed) {
      const query = new URLSearchParams();
      for (const [key, value] of Object.entries(options.params)) {
        if (value != null) query.set(key, String(value));
      }
      const queryString = query.toString();
      const url = queryString
        ? `${options.route}?${queryString}`
        : options.route;
      const nextPopup = window.open(url, options.name, options.features);
      setTimeout(options.sendContext, 500);
      return nextPopup;
    }

    popup.focus();
    options.sendContext();
    return popup;
  }

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
    const filterColors = filterSetColorsEnabled;
    const branchId = projectState.activeBranchId;
    const rev = revisionState.activeRevision;

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
      if (filterColors && branchId && rev !== null) {
        applyFilterSetColorsToScene(mgr, branchId, rev);
      } else {
        mgr.applySubgraphFilter(null, null);
      }
    }
  });

  // Keep Attribute pop-out in sync when selection or context changes
  $effect(() => {
    sendAttributesContext();
  });

  // Keep Graph popup in sync when selection or context changes
  $effect(() => {
    sendGraphContext();
  });

  // Keep Schema popup in sync when project/branch/revision changes
  $effect(() => {
    const branchId = projectState.activeBranchId;
    const projectId = projectState.activeProjectId;
    const revision = revisionState.activeRevision;
    const { projectName, branchName } = resolveContextNames(projectId, branchId);
    if (!schemaChannel) return;
    schemaChannel.postMessage({
      type: "context",
      branchId,
      projectId,
      revision,
      projectName,
      branchName,
    } satisfies SchemaMessage);
  });

  // Keep Validation popup in sync when project/branch/revision changes
  $effect(() => {
    sendValidationContext();
  });

  // Keep Views popup in sync when project/branch changes
  $effect(() => {
    sendViewsContext();
  });

  let visibilityCleanup: (() => void) | null = null;

  // BroadcastChannels for cross-window communication
  onMount(() => {
    searchChannel = new BroadcastChannel(SEARCH_CHANNEL);
    searchChannel.onmessage = (e: MessageEvent<SearchMessage>) => {
      if (e.data.type === "apply-filters") {
        handleApplyFilters(e.data.filters);
      } else if (e.data.type === "apply-filter-sets") {
        // Apply payload immediately, then refresh from API as source of truth.
        void handleApplyFilterSets(e.data.filterSets);
        void reloadGeometryFromAppliedFilterSets(e.data.filterSets);
      } else if (e.data.type === "request-branch-context") {
        sendBranchContext();
      } else if (e.data.type === "set-filter-set-colors") {
        filterSetColorsEnabled = e.data.enabled;
        handleFilterSetColorToggle();
      }
    };
    // Request current applied filter sets from search popup (if open) so viewer syncs after mount/refresh
    searchChannel.postMessage({
      type: "request-applied-filter-sets",
    } satisfies SearchMessage);

    function applyFromStorage(payload: {
      filterSets: FilterSet[];
    }) {
      void handleApplyFilterSets(payload.filterSets);
      void reloadGeometryFromAppliedFilterSets(payload.filterSets);
    }

    const onStorage = (e: StorageEvent) => {
      if (e.key !== APPLY_FILTER_SETS_STORAGE_KEY || !e.newValue) return;
      try {
        const { filterSets } = JSON.parse(e.newValue) as {
          filterSets: FilterSet[];
          combinationLogic: "AND" | "OR";
          timestamp?: number;
        };
        if (filterSets) applyFromStorage({ filterSets });
      } catch {}
    };
    window.addEventListener("storage", onStorage);

    const onMessage = (e: MessageEvent) => {
      if (e.origin !== window.location.origin) return;
      if (e.data?.type !== APPLY_FILTER_SETS_MESSAGE_TYPE) return;
      const { filterSets } = e.data;
      if (filterSets) applyFromStorage({ filterSets });
    };
    window.addEventListener("message", onMessage);

    visibilityCleanup = () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("message", onMessage);
    };

    try {
      const stored = localStorage.getItem(APPLY_FILTER_SETS_STORAGE_KEY);
      if (stored) {
        const { filterSets, timestamp } = JSON.parse(
          stored,
        ) as {
          filterSets: FilterSet[];
          combinationLogic: "AND" | "OR";
          timestamp?: number;
        };
        if (filterSets && timestamp && Date.now() - timestamp < 60000) {
          applyFromStorage({ filterSets });
        }
      }
    } catch {}

    const onVisibilityChange = () => {
      if (
        document.visibilityState === "visible" &&
        projectState.activeBranchId
      ) {
        searchChannel?.postMessage({
          type: "request-applied-filter-sets",
        } satisfies SearchMessage);
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    attributesChannel = setupChannel<AttributesMessage>(ATTRIBUTES_CHANNEL, {
      "request-context": () => {
        sendAttributesContext(true);
      },
      "selection-changed": (message) => {
        selection.activeGlobalId = message.globalId;
      },
    });

    graphChannel = setupChannel<GraphMessage>(GRAPH_CHANNEL, {
      "request-context": () => {
        sendGraphContext(true);
      },
      "selection-changed": (message) => {
        selection.activeGlobalId = message.globalId;
      },
    });

    tableChannel = setupChannel<TableMessage>(TABLE_CHANNEL, {
      "request-context": () => {
        sendTableContext(true);
      },
      "sync-mode": (message) => {
        tableSyncEnabled = message.enabled;
      },
      "selection-changed": (message) => {
        if (!tableSyncEnabled) return;
        selection.activeGlobalId = message.globalId;
      },
    });

    agentChannel = setupChannel<AgentChannelMessage>(AGENT_CHANNEL, {
      "request-context": () => {
        sendAgentContext();
      },
    });

    schemaChannel = setupChannel<SchemaMessage>(SCHEMA_CHANNEL, {
      "request-context": () => {
        sendSchemaContext();
      },
    });

    validationChannel = setupChannel<ValidationMessage>(VALIDATION_CHANNEL, {
      "request-context": () => {
        sendValidationContext(true);
      },
    });

    viewsChannel = setupChannel<ViewsMessage>(VIEWS_CHANNEL, {
      "request-context": () => {
        sendViewsContext(true);
      },
      "request-camera": () => {
        const mgr = sceneManager;
        if (!mgr || !viewsChannel) return;
        const bcfCameraState = mgr.getBcfCameraState();
        viewsChannel.postMessage(
          JSON.parse(
            JSON.stringify({
              type: "camera",
              bcfCameraState,
            } satisfies ViewsMessage),
          ),
        );
      },
      "LOAD_VIEW": (message) => {
        if (message.type !== "LOAD_VIEW" || !message.view) return;
        void handleLoadView(message.view);
      },
      "TOGGLE_GHOST_MODE": (message) => {
        if (message.type !== "TOGGLE_GHOST_MODE") return;
        void handleToggleGhostMode(message.filterSetId, message.enabled);
      },
    });
  });

  onDestroy(() => {
    visibilityCleanup?.();
    searchChannel?.close();
    attributesChannel?.close();
    graphChannel?.close();
    tableChannel?.close();
    agentChannel?.close();
    schemaChannel?.close();
    validationChannel?.close();
    viewsChannel?.close();
  });

  // Sync viewer selection to table popup when table has sync enabled.
  $effect(() => {
    if (!tableSyncEnabled) return;
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
        filterSetColorsEnabled,
      } satisfies SearchMessage);
      searchChannel?.postMessage({
        type: "filter-result-count",
        count: elementCount || searchState.products.length,
        total: searchState.totalProductCount,
      } satisfies SearchMessage);
    }
  }

  // Keep a reactive element count in sync with the SceneManager.
  $effect(() => {
    const mgr = sceneManager;
    if (!mgr) {
      elementCount = 0;
      return;
    }
    mgr.setElementCountListener((count) => {
      elementCount = count;
    });
    // Ensure we start from the current value.
    elementCount = mgr.elementCount;
    return () => {
      mgr.setElementCountListener(null);
    };
  });

  function buildAttributesContextPayload(): AttributesContextPayload {
    const branchId = projectState.activeBranchId;
    const projectId = projectState.activeProjectId;
    const revision = revisionState.activeRevision;
    const globalId = selection.activeGlobalId;
    const { projectName, branchName } = resolveContextNames(projectId, branchId);
    return {
      branchId,
      projectId,
      branchName,
      projectName,
      revision,
      globalId,
    };
  }

  function sendAttributesContext(force = false) {
    const payload = buildAttributesContextPayload();
    if (!attributesChannel) return;
    const key = JSON.stringify(payload);
    if (!force && key === lastSentAttributesContextKey) return;
    lastSentAttributesContextKey = key;
    attributesChannel.postMessage({
      type: "context",
      ...payload,
    } satisfies AttributesMessage);
  }

  function buildGraphContextPayload(): GraphContextPayload {
    const branchId = projectState.activeBranchId;
    const projectId = projectState.activeProjectId;
    const revision = revisionState.activeRevision;
    const globalId = selection.activeGlobalId;
    const subgraphDepth = selection.subgraphDepth;
    const { projectName, branchName } = resolveContextNames(projectId, branchId);
    return {
      branchId,
      projectId,
      branchName,
      projectName,
      revision,
      globalId,
      subgraphDepth,
    };
  }

  function sendGraphContext(force = false) {
    const payload = buildGraphContextPayload();
    if (!graphChannel) return;
    const key = JSON.stringify(payload);
    if (!force && key === lastSentGraphContextKey) return;
    lastSentGraphContextKey = key;
    graphChannel.postMessage({
      type: "context",
      ...payload,
    } satisfies GraphMessage);
  }

  function sendTableContext(force = false) {
    const branchId = projectState.activeBranchId;
    const projectId = projectState.activeProjectId;
    const revision = revisionState.activeRevision;
    const products = searchState.products;

    // Resolve human-readable names from loaded project list
    const { projectName, branchName } = resolveContextNames(projectId, branchId);

    const contextBase = {
      type: "context" as const,
      branchId,
      projectId,
      branchName,
      projectName,
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
    const contextKey = JSON.stringify({
      branchId,
      projectId,
      revision,
      branchName,
      projectName,
      activeGlobalId: selection.activeGlobalId,
      version: TABLE_PROTOCOL_VERSION,
      products: leanProducts.map((p) => p.globalId),
    });
    if (!force && contextKey === lastSentTableContextKey) return;
    lastSentTableContextKey = contextKey;

    tableChannel?.postMessage({
      ...contextBase,
      products: leanProducts,
    } satisfies TableMessage);
    // Do not send attribute chunks here; table will request them after receiving context
    // so it is guaranteed to be listening when chunks arrive (fixes chunks not reaching table).
    if (tableSyncEnabled) {
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
    const { projectName, branchName } = resolveContextNames(projectId, branchId);
    agentChannel?.postMessage({
      type: "context",
      branchId,
      projectId,
      revision,
      projectName,
      branchName,
    } satisfies AgentChannelMessage);
  }

  function sendSchemaContext() {
    const branchId = projectState.activeBranchId;
    const projectId = projectState.activeProjectId;
    const revision = revisionState.activeRevision;
    const { projectName, branchName } = resolveContextNames(projectId, branchId);
    schemaChannel?.postMessage({
      type: "context",
      branchId,
      projectId,
      revision,
      projectName,
      branchName,
    } satisfies SchemaMessage);
  }

  function buildValidationContextPayload(): ValidationContextPayload {
    const branchId = projectState.activeBranchId;
    const projectId = projectState.activeProjectId;
    const revision = revisionState.activeRevision;
    const { projectName, branchName } = resolveContextNames(projectId, branchId);
    return {
      branchId,
      projectId,
      revision,
      projectName,
      branchName,
    };
  }

  function sendValidationContext(force = false) {
    if (!validationChannel) return;
    const payload = buildValidationContextPayload();
    const key = JSON.stringify(payload);
    if (!force && key === lastSentValidationContextKey) return;
    lastSentValidationContextKey = key;
    validationChannel.postMessage({
      type: "context",
      ...payload,
    } satisfies ValidationMessage);
  }

  function sendViewsContext(force = false) {
    if (!viewsChannel) return;
    const branchId = projectState.activeBranchId;
    const projectId = projectState.activeProjectId;
    const revision = revisionState.activeRevision;
    const key = JSON.stringify({ branchId, projectId, revision });
    if (!force && key === lastSentViewsContextKey) return;
    lastSentViewsContextKey = key;
    const { projectName, branchName } = resolveContextNames(projectId, branchId);
    viewsChannel.postMessage(
      JSON.parse(
        JSON.stringify({
          type: "context",
          branchId,
          projectId,
          branchName,
          projectName,
          revision,
        } satisfies ViewsMessage),
      ),
    );
  }

  let lastSentViewsContextKey: string | null = null;

  let ghostedFilterSetIds = $state<Set<string>>(new Set());

  async function handleLoadView(view: SavedViewPayload) {
    const branchId = projectState.activeBranchId;
    if (!branchId || view.branchId !== branchId) return;
    const mgr = sceneManager;
    if (!mgr) return;

    ghostedFilterSetIds = new Set();
    mgr.setGhostedGlobalIds(new Set());

    const filterSets = view.filterSets ?? [];
    const filterSetIds = filterSets.map((fs) => fs.id ?? fs.filterSetId ?? "").filter(Boolean);
    try {
      await client.mutation(
        APPLY_FILTER_SETS_MUTATION,
        {
          branchId,
          filterSetIds,
          combinationLogic: "AND",
        },
        { requestPolicy: "network-only" },
      ).toPromise();
    } catch (err) {
      console.error("Failed to apply filter sets for view:", err);
    }

    await reloadGeometryFromAppliedFilterSets();

    selection.activeGlobalId = null;

    const bcf = view.bcfCameraState;
    if (bcf && (bcf.perspective_camera || bcf.orthogonal_camera)) {
      mgr.setProjectionMode(!!bcf.orthogonal_camera);
      mgr.applyBcfCamera(bcf);
    }
  }

  async function handleSaveAsViewSubmit(name: string) {
    const branchId = projectState.activeBranchId;
    const mgr = sceneManager;
    if (!branchId || !mgr) return;
    saveAsViewError = null;
    try {
      const bcf = mgr.getBcfCameraState();
      const uiFilters = { projectionMode: mgr.projectionIsometric ? "orthographic" : "perspective" };
      const result = await client
        .mutation(
          CREATE_SAVED_VIEW_MUTATION,
          {
            branchId,
            name: name.trim(),
            bcfCameraState: bcf,
            uiFilters,
          },
          { requestPolicy: "network-only" },
        )
        .toPromise();
      const created = (result.data as { createSavedView?: { id: string } })?.createSavedView;
      if (created) {
        const filterSetIds = searchState.appliedFilterSets.map((fs) => fs.id).filter(Boolean);
        if (filterSetIds.length > 0) {
          await client
            .mutation(
              ATTACH_FILTER_SETS_TO_SAVED_VIEW_MUTATION,
              { viewId: created.id, filterSetIds },
              { requestPolicy: "network-only" },
            )
            .toPromise();
        }
      }
      showSaveAsViewModal = false;
    } catch (e) {
      saveAsViewError = e instanceof Error ? e.message : String(e);
    }
  }

  async function handleToggleGhostMode(filterSetId: string, enabled: boolean) {
    const mgr = sceneManager;
    const branchId = projectState.activeBranchId;
    const rev = revisionState.activeRevision;
    if (!mgr || !branchId || rev === null) return;

    const next = new Set(ghostedFilterSetIds);
    if (enabled) next.add(filterSetId);
    else next.delete(filterSetId);
    ghostedFilterSetIds = next;

    try {
      const result = await client
        .query(FILTER_SET_MATCHES_QUERY, { branchId, revision: rev }, { requestPolicy: "network-only" })
        .toPromise();
      const matches = (result.data?.filterSetMatches ?? []) as Array<{ filterSetId: string; globalIds: string[] }>;
      const ghostedIds = new Set<string>();
      for (const m of matches) {
        if (ghostedFilterSetIds.has(m.filterSetId)) {
          for (const gid of m.globalIds) ghostedIds.add(gid);
        }
      }
      mgr.setGhostedGlobalIds(ghostedIds);
      if (filterSetColorsEnabled) {
        await applyFilterSetColorsToScene(mgr, branchId, rev);
      } else {
        mgr.applyFilterSetColors(null);
      }
    } catch (err) {
      console.error("Failed to apply ghost mode:", err);
    }
  }

  function openAgentPopup() {
    agentPopup = openPopupWithContext(agentPopup, {
      route: "/agent",
      name: "bimatlas-agent",
      features: "width=460,height=700",
      params: {
        branchId: projectState.activeBranchId,
        projectId: projectState.activeProjectId,
        revision: revisionState.activeRevision,
      },
      sendContext: sendAgentContext,
    });
  }

  function openGraphPopup() {
    graphPopup = openPopupWithContext(graphPopup, {
      route: "/graph",
      name: "bimatlas-graph",
      features: "width=800,height=700",
      params: {
        branchId: projectState.activeBranchId,
        projectId: projectState.activeProjectId,
        revision: revisionState.activeRevision,
        globalId: selection.activeGlobalId,
        subgraphDepth: selection.subgraphDepth,
      },
      sendContext: () => sendGraphContext(true),
    });
  }

  function openSearchPopup() {
    searchPopup = openPopupWithContext(searchPopup, {
      route: "/search",
      name: "bimatlas-search",
      features: "width=520,height=700",
      params: {
        branchId: projectState.activeBranchId,
        projectId: projectState.activeProjectId,
      },
      sendContext: sendBranchContext,
    });
  }

  function openAttributesPopup() {
    attributePopup = openPopupWithContext(attributePopup, {
      route: "/attributes",
      name: "bimatlas-attributes",
      features: "width=420,height=700",
      params: {
        branchId: projectState.activeBranchId,
        projectId: projectState.activeProjectId,
        revision: revisionState.activeRevision,
        globalId: selection.activeGlobalId,
      },
      sendContext: () => sendAttributesContext(true),
    });
  }

  function openTablePopup() {
    tablePopup = openPopupWithContext(tablePopup, {
      route: "/table",
      name: "bimatlas-table",
      features: "width=900,height=700",
      params: {
        branchId: projectState.activeBranchId,
        projectId: projectState.activeProjectId,
        revision: revisionState.activeRevision,
      },
      sendContext: () => sendTableContext(true),
    });
  }

  function openSchemaPopup() {
    schemaPopup = openPopupWithContext(schemaPopup, {
      route: "/schema",
      name: "bimatlas-schema",
      features: "width=900,height=700",
      params: {
        branchId: projectState.activeBranchId,
        projectId: projectState.activeProjectId,
        revision: revisionState.activeRevision,
      },
      sendContext: sendSchemaContext,
    });
  }

  function openValidationPopup() {
    validationPopup = openPopupWithContext(validationPopup, {
      route: "/validation",
      name: "bimatlas-validation",
      features: "width=900,height=700",
      params: {
        branchId: projectState.activeBranchId,
        projectId: projectState.activeProjectId,
        revision: revisionState.activeRevision,
      },
      sendContext: () => sendValidationContext(true),
    });
  }

  function openViewsPopup() {
    viewsPopup = openPopupWithContext(viewsPopup, {
      route: "/views",
      name: "bimatlas-views",
      features: "width=480,height=600",
      params: {
        branchId: projectState.activeBranchId,
        projectId: projectState.activeProjectId,
        revision: revisionState.activeRevision,
      },
      sendContext: () => sendViewsContext(true),
    });
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
    if (projectState.activeBranchId !== branchId) return;

    await ensureTotalProductCount(branchId, rev);

    searchChannel?.postMessage({
      type: "filter-result-count",
      count: mgr.elementCount,
      total: searchState.totalProductCount,
    } satisfies SearchMessage);
  }

  function filterSetsToQueryVars(
    filterSets: FilterSet[],
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

  async function reloadGeometryFromAppliedFilterSets(
    fallbackFilterSets?: FilterSet[],
  ) {
    const branchId = projectState.activeBranchId;
    if (!branchId) return;
    try {
      const result = await client
        .query(
          APPLIED_FILTER_SETS_QUERY,
          { branchId },
          { requestPolicy: "network-only" },
        )
        .toPromise();
      const data = result.data?.appliedFilterSets;
      const filterSets = data?.filterSets ?? [];
      await handleApplyFilterSets(filterSets);
    } catch (err) {
      console.error("Failed to reload geometry from applied filter sets:", err);
      if (fallbackFilterSets) {
        await handleApplyFilterSets(fallbackFilterSets);
      }
    }
  }

  async function handleApplyFilterSets(filterSets: FilterSet[]) {
    searchState.appliedFilterSets = filterSets;
    searchState.combinationLogic = APPLIED_FILTER_SETS_COMBINATION_LOGIC;
    searchState.activeFilters = [];
    const mgr = sceneManager;
    const rev = revisionState.activeRevision;
    const branchId = projectState.activeBranchId;
    if (!mgr || rev === null || !branchId) return;

    const extraVars =
      filterSets.length > 0
        ? filterSetsToQueryVars(filterSets)
        : {};
    await loadGeometry(mgr, rev, branchId, extraVars);
    if (projectState.activeBranchId !== branchId) return;

    await ensureTotalProductCount(branchId, rev);
    if (projectState.activeBranchId !== branchId) return;

    if (filterSetColorsEnabled) {
      if (filterSets.length > 0) {
        await applyFilterSetColorsToScene(mgr, branchId, rev);
      } else {
        mgr.applyFilterSetColors(null);
      }
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
        .query(
          APPLIED_FILTER_SETS_QUERY,
          { branchId },
          { requestPolicy: "network-only" },
        )
        .toPromise();
      const data = result.data?.appliedFilterSets;
      if (data && data.filterSets && data.filterSets.length > 0) {
        await handleApplyFilterSets(data.filterSets);
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
    if (projectState.activeBranchId !== branchId) return;

    const hasAppliedSets = await autoLoadAppliedFilterSets(branchId);
    if (projectState.activeBranchId !== branchId) return;

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
      const signal = geometryAbort?.signal;
      const res = await fetch(url, signal ? { signal } : undefined);
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
    } catch (err: any) {
      if (err?.name === "AbortError") return;
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

  function cancelGeometryLoad() {
    if (geometryAbort) {
      geometryAbort.abort();
      geometryAbort = null;
    }
    loadingGeometry = false;
    loadingGeometryCurrent = 0;
    loadingGeometryTotal = 0;
  }

  async function loadGeometry(
    mgr: SceneManager,
    revision: number,
    branchId: string,
    filterVars: Record<string, unknown> = {},
  ) {
    cancelGeometryLoad();
    const abort = new AbortController();
    geometryAbort = abort;

    loadingGeometry = true;
    loadingGeometryCurrent = 0;
    loadingGeometryTotal = 0;

    try {
      const params = streamQueryParams(branchId, revision, filterVars);
      const url = `${API_BASE}/stream/ifc-products?${params.toString()}`;
      const res = await fetch(url, { signal: abort.signal });

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
        if (abort.signal.aborted) break;
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
              if (abort.signal.aborted) break;
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
        if (done || streamEnded || abort.signal.aborted) break;
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

      if (abort.signal.aborted) return;

      searchState.setProducts(metaList);

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
    } catch (err: any) {
      if (err?.name === "AbortError") return;
      console.error("Failed to load geometry:", err);
    } finally {
      if (geometryAbort === abort) {
        loadingGeometry = false;
        loadingGeometryCurrent = 0;
        loadingGeometryTotal = 0;
        geometryAbort = null;
      }
    }
  }

  function hexToThreeColor(hex: string): number {
    return parseInt(hex.replace("#", ""), 16);
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
        .query(
          FILTER_SET_MATCHES_QUERY,
          { branchId, revision },
          { requestPolicy: "network-only" },
        )
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
    importProgressPercent = 0;
    importProgressMessage = "Uploading IFC file...";

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("branch_id", String(branchId));

      const res = await fetch(`${API_BASE}/upload-ifc/stream`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Upload failed (${res.status})`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("Upload stream was not available");

      const decoder = new TextDecoder();
      let buffer = "";
      let finalResult: { revision_seq: number } | null = null;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const rawLine of lines) {
          const line = rawLine.trim();
          if (!line) continue;
          const event = JSON.parse(line) as
            | {
                progress: number;
                message: string;
                stage: string;
                filename: string;
              }
            | { type: "result"; result: { revision_seq: number } }
            | { type: "error"; message: string };
          if ("progress" in event) {
            importProgressPercent = event.progress;
            importProgressMessage = event.message;
          } else if (event.type === "result") {
            finalResult = event.result;
          } else if (event.type === "error") {
            throw new Error(event.message);
          }
        }
      }

      if (!finalResult) {
        throw new Error("Upload completed without a final result");
      }

      importProgressPercent = 100;
      importProgressMessage = "Import complete";
      revisionState.activeRevision = finalResult.revision_seq;
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
          cancelGeometryLoad();
          sceneManager?.clearAll();
          lastFetchedRev = null;
          lastFetchedBranchId = null;
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
            type="button"
            class="branch-add-btn btn-icon-primary"
            onclick={() => (showCreateBranch = true)}
            title="New branch"
            aria-label="New branch"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 16 16"
              aria-hidden="true"
              focusable="false"
            >
              <path
                d="M8 3v10M3 8h10"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </button>
          <button
            type="button"
            class="branch-delete-btn"
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
            <svg
              width="14"
              height="14"
              viewBox="0 0 16 16"
              aria-hidden="true"
              focusable="false"
            >
              <path
                d="M4 4L12 12M12 4L4 12"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
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
                    class="project-delete-btn"
                    title="Delete project"
                    aria-label="Delete project {p.name}"
                    onclick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      projectToDelete = p;
                      showDeleteProject = true;
                    }}
                  >
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 16 16"
                      aria-hidden="true"
                      focusable="false"
                    >
                      <path
                        d="M4 4L12 12M12 4L4 12"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="1.8"
                        stroke-linecap="round"
                        stroke-linejoin="round"
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
              type="button"
              class="project-add-btn btn-icon-primary"
              title="New project"
              aria-label="New project"
              onclick={() => (showCreateProject = true)}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 16 16"
                aria-hidden="true"
                focusable="false"
              >
                <path
                  d="M8 3v10M3 8h10"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
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
            class="toolbar-btn btn-primary"
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
          <!-- Save as view -->
          {#if projectState.activeBranchId}
            <button
              class="toolbar-btn"
              onclick={() => (showSaveAsViewModal = true)}
              title="Save current view (filter sets and camera)"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <path
                  d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
                <polyline
                  points="17 21 17 13 7 13 7 21"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
                <polyline
                  points="7 3 7 8 15 8"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
              Save as view
            </button>
          {/if}
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
        </Sidebar>
        <div class="search-actions" use:wheelToHorizontalScroll>
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
          <!-- Validation popup button -->
          <button
            class="table-btn"
            onclick={openValidationPopup}
            aria-label="Open validation results"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <rect
                x="4"
                y="4"
                width="16"
                height="16"
                rx="2"
                stroke="currentColor"
                stroke-width="2"
                fill="none"
              />
              <path
                d="M8 13l3 3 5-6"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            Validation
          </button>
          <!-- Views popup button -->
          <button
            class="table-btn"
            onclick={openViewsPopup}
            aria-label="Open saved views"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"
                stroke="currentColor"
                stroke-width="1.5"
                fill="none"
              />
            </svg>
            Views
          </button>
          <!-- Schema Browser popup button -->
          <button
            class="schema-btn"
            onclick={openSchemaPopup}
            aria-label="Open schema browser"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
              />
              <path
                d="M9 5a2 2 0 012-2h2a2 2 0 012 2v0a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                stroke="currentColor"
                stroke-width="2"
              />
              <path
                d="M9 12l2 2 4-4"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            Schema
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
        <span class="element-count">{elementCount} elements</span>
      </div>
    {/if}

    <!-- Import modal -->
    <ImportModal
      open={showImportModal}
      onclose={() => (showImportModal = false)}
      onsubmit={handleImportSubmit}
    />

    <SaveAsViewModal
      open={showSaveAsViewModal}
      appliedFilterSetCount={searchState.appliedFilterSets.length}
      projectionMode={sceneManager?.projectionIsometric ? "orthographic" : "perspective"}
      error={saveAsViewError}
      onclose={() => {
        showSaveAsViewModal = false;
        saveAsViewError = null;
      }}
      onsubmit={handleSaveAsViewSubmit}
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
              class="btn-close"
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
              class="btn-close"
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
              class="btn-close"
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
        <div class="import-loading-card">
          <Spinner size="3.5rem" />
          <p class="import-loading-message">{importProgressMessage}</p>
          <p class="import-loading-percent">{importProgressPercent}%</p>
          <div class="viewport-loading-bar import-loading-bar">
            <div
              class="viewport-loading-fill"
              style="width: {importProgressPercent}%"
            ></div>
          </div>
        </div>
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
    color: var(--color-text-primary);
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
    background: var(--color-bg-surface);
    border-bottom: 1px solid var(--color-border-subtle);
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
    background: linear-gradient(
      135deg,
      var(--color-brand-gradient-start),
      var(--color-brand-gradient-end)
    );
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
    color: var(--color-text-muted);
  }

  .selector {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    border-radius: 0.5rem;
    color: var(--color-text-secondary);
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
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  .branch-add-btn {
    width: 1.75rem;
    height: 1.75rem;
    border-radius: 999px;
    border: none;
    background: var(--color-action-primary);
    color: var(--color-bg-surface);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    cursor: pointer;
  }

  .branch-add-btn:hover {
    background: var(--color-action-primary);
    color: var(--color-bg-surface);
  }

  .branch-delete-btn {
    width: 1.75rem;
    height: 1.75rem;
    border-radius: 999px;
    border: 1px solid var(--color-border-subtle);
    background: var(--color-bg-surface);
    color: var(--color-text-secondary);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    cursor: pointer;
  }

  .branch-delete-btn:disabled {
    cursor: default;
    color: var(--color-border-subtle);
    border-color: var(--color-border-subtle);
  }

  .branch-delete-btn:hover:not(:disabled) {
    background: color-mix(in srgb, var(--color-danger) 15%, transparent);
    color: var(--color-danger);
    border-color: var(--color-danger);
  }

  #branch-select.selector {
    flex: 1 1 auto;
    max-width: none;
  }

  .selector:focus {
    border-color: var(--color-border-strong);
  }

  .selector option {
    background: var(--color-bg-surface);
    color: var(--color-text-secondary);
  }

  .separator {
    color: var(--color-text-muted);
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
    color: var(--color-text-muted);
    cursor: pointer;
    min-width: 0;
    line-height: 1.3;
  }

  .revision-search-section .revision-filter-checkbox input {
    accent-color: var(--color-brand-500);
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
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    border-radius: 0.5rem;
    color: var(--color-text-secondary);
    padding: 0.3rem 0.45rem;
    font-size: 0.78rem;
    outline: none;
    font-family: inherit;
    cursor: text;
  }

  .revision-search-section .revision-filter-input:focus {
    border-color: var(--color-border-strong);
  }

  .revision-search-section .revision-filter-input::placeholder {
    color: var(--color-text-muted);
  }

  .revision-search-section .revision-date-input {
    width: 100%;
    box-sizing: border-box;
    min-height: 2.25rem;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    border-radius: 0.5rem;
    color: var(--color-text-secondary);
    padding: 0.3rem 0.45rem;
    font-size: 0.78rem;
    outline: none;
    font-family: inherit;
    cursor: pointer;
  }

  .revision-search-section .revision-date-input:focus {
    border-color: var(--color-border-strong);
  }

  .revision-search-section
    .revision-date-input::-webkit-calendar-picker-indicator {
    filter: none;
    cursor: pointer;
    opacity: 0.7;
  }

  .revision-loading,
  .revision-empty {
    font-size: 0.8rem;
    color: var(--color-text-muted);
    margin: 0;
  }

  .revision-list-wrapper {
    margin-top: 0.5rem;
  }

  .revision-results-heading {
    margin: 0 0 0.35rem;
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--color-text-muted);
    text-transform: none;
    letter-spacing: 0;
  }

  .revision-list {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 160px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
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
    background: var(--color-bg-elevated);
    border: 1px solid transparent;
    border-radius: 0.5rem;
    color: var(--color-text-secondary);
    cursor: pointer;
  }

  .revision-item:hover {
    background: color-mix(in srgb, var(--color-brand-500) 8%, transparent);
    color: var(--color-text-primary);
  }

  .revision-item--current {
    cursor: default;
    background: color-mix(in srgb, var(--color-brand-500) 15%, transparent);
    border-color: color-mix(in srgb, var(--color-brand-500) 40%, transparent);
    color: var(--color-brand-500);
  }

  .revision-item--current:hover {
    background: color-mix(in srgb, var(--color-brand-500) 15%, transparent);
    color: var(--color-brand-500);
  }

  .revision-item--current,
  .revision-item--current * {
    cursor: default;
  }

  .revision-current-label {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--color-brand-500);
    width: 100%;
    flex-basis: 100%;
    margin-bottom: 0.15rem;
  }

  .current-revision-block {
    margin-top: 0.75rem;
  }

  .revision-current-not-in-filter {
    font-size: 0.7rem;
    color: var(--color-text-muted);
    font-style: italic;
  }

  .revision-seq {
    font-weight: 600;
    color: var(--color-text-muted);
  }

  .revision-item--current .revision-seq {
    color: var(--color-brand-500);
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
    color: var(--color-text-muted);
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
  }

  .revision-filter-group-header:hover {
    color: var(--color-text-secondary);
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
    color: var(--color-text-muted);
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
    background: color-mix(in srgb, var(--color-bg-canvas) 80%, transparent);
    z-index: 100;
    pointer-events: none;
  }

  .viewport-loading-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    padding: 1.5rem 2rem;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
  }

  .viewport-loading-message {
    margin: 0;
    font-size: 0.9rem;
    color: var(--color-text-muted);
    white-space: nowrap;
  }

  .viewport-loading-bar {
    width: 200px;
    height: 6px;
    background: var(--color-bg-elevated);
    border-radius: 3px;
    overflow: hidden;
  }

  .viewport-loading-fill {
    height: 100%;
    background: var(--color-brand-500);
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
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 16px;
    padding: 2rem;
    max-width: 520px;
    width: 100%;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.08);
  }

  .picker-card h2 {
    font-size: 1.2rem;
    font-weight: 600;
    color: var(--color-text-primary);
  }

  .picker-subtitle {
    color: var(--color-text-muted);
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
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-subtle);
    border-radius: 12px;
    padding: 0.75rem 1rem;
    transition:
      background 0.15s,
      border-color 0.15s;
  }

  .project-item:hover {
    background: color-mix(in srgb, var(--color-brand-500) 8%, transparent);
    border-color: color-mix(in srgb, var(--color-brand-500) 25%, transparent);
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
    color: var(--color-text-primary);
  }

  .project-item-desc {
    font-size: 0.75rem;
    color: var(--color-text-muted);
  }

  .project-item-branches {
    font-size: 0.72rem;
    color: var(--color-text-muted);
    white-space: nowrap;
  }

  .project-add-btn {
    width: 1.75rem;
    height: 1.75rem;
    border-radius: 999px;
    border: none;
    background: var(--color-action-primary);
    color: var(--color-bg-surface);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    cursor: pointer;
  }

  .project-add-btn:hover {
    background: var(--color-action-primary);
    color: var(--color-bg-surface);
  }

  .project-delete-btn {
    width: 1.75rem;
    height: 1.75rem;
    border-radius: 999px;
    border: 1px solid var(--color-border-subtle);
    background: var(--color-bg-surface);
    color: var(--color-text-secondary);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    cursor: pointer;
  }

  .project-delete-btn:hover {
    color: var(--color-danger);
    border-color: var(--color-danger);
  }

  .empty-msg {
    color: var(--color-text-muted);
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
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    border-radius: 12px;
    color: var(--color-text-primary);
    padding: 0.5rem 0.75rem;
    font-size: 0.85rem;
    outline: none;
    transition: border-color 0.15s;
  }

  .input:focus {
    border-color: var(--color-border-strong);
  }

  .input::placeholder {
    color: var(--color-text-muted);
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
    color: var(--color-text-muted);
  }

  .element-count {
    position: absolute;
    top: 1rem;
    left: 1rem;
    font-size: 0.72rem;
    color: var(--color-text-muted);
    z-index: 1;
  }

  .search-actions {
    position: absolute;
    bottom: 1rem;
    left: 50%;
    transform: translateX(-50%);
    pointer-events: auto;
    display: inline-flex;
    gap: 0.5rem;
    max-width: calc(100vw - 2rem);
    overflow-x: auto;
    overflow-y: hidden;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: thin;
  }

  .search-btn,
  .graph-btn,
  .table-btn,
  .schema-btn,
  .attributes-btn,
  .agent-btn {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: color-mix(
      in srgb,
      var(--color-action-primary) 15%,
      transparent
    );
    border: 1px solid
      color-mix(in srgb, var(--color-action-primary) 35%, transparent);
    color: var(--color-action-primary);
    padding: 0.45rem 1rem;
    border-radius: 12px;
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
  .schema-btn:hover,
  .attributes-btn:hover,
  .agent-btn:hover {
    background: var(--color-action-primary);
    border-color: var(--color-action-primary);
    color: var(--color-bg-surface);
  }

  /* ---- Modal (shared) ---- */

  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 1200;
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
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 16px;
    width: 90%;
    max-width: 420px;
    padding: 1.5rem;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.12);
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .modal-header h2 {
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--color-text-primary);
  }

  .modal-subtitle {
    font-size: 0.82rem;
    color: var(--color-text-muted);
    line-height: 1.4;
  }

  .modal-subtitle strong {
    color: var(--color-text-secondary);
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
    background: color-mix(in srgb, var(--color-bg-canvas) 90%, transparent);
    backdrop-filter: blur(6px);
  }

  .import-loading-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    min-width: 260px;
    padding: 1.5rem 1.75rem;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 14px;
    box-shadow: 0 12px 36px rgba(0, 0, 0, 0.12);
  }

  .import-loading-message,
  .import-loading-percent {
    margin: 0;
  }

  .import-loading-message {
    color: var(--color-text-secondary);
    font-size: 0.92rem;
    text-align: center;
  }

  .import-loading-percent {
    color: var(--color-text-primary);
    font-size: 1.05rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }

  .import-loading-bar {
    width: 100%;
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
    background: var(--color-danger-soft);
    border: 1px solid color-mix(in srgb, var(--color-danger) 40%, transparent);
    border-radius: 12px;
    color: var(--color-danger);
    font-size: 0.82rem;
    backdrop-filter: blur(8px);
    max-width: 90%;
  }
</style>
