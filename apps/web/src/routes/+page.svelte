<script lang="ts">
  /**
   * Main BimAtlas page -- project/branch selector, 3D viewport, force graph, and selection panel.
   * Users first select (or create) a project, then pick a branch. All IFC data is scoped to the branch.
   */
  import Viewport from "$lib/ui/Viewport.svelte";
  import SelectionPanel from "$lib/ui/SelectionPanel.svelte";
  import ForceGraph from "$lib/graph/ForceGraph.svelte";
  import ImportModal from "$lib/ui/ImportModal.svelte";
  import Spinner from "$lib/ui/Spinner.svelte";
  import Sidebar from "$lib/ui/Sidebar.svelte";
  import DepthWidget from "$lib/ui/DepthWidget.svelte";
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
  import { getDescendantClasses } from "$lib/ifc/schema";
  import { getGraphStore } from "$lib/graph/graphStore.svelte";
  import { computeSubgraph } from "$lib/graph/subgraph";
  import type { SceneManager } from "$lib/engine/SceneManager";
  import {
    client,
    APPLIED_FILTER_SETS_QUERY,
    PROJECTS_QUERY,
    CREATE_PROJECT_MUTATION,
    CREATE_BRANCH_MUTATION,
    REVISIONS_QUERY,
  } from "$lib/api/client";
  import {
    createBufferGeometry,
    type RawMeshData,
  } from "$lib/engine/BufferGeometryLoader";
  import { untrack, onMount, onDestroy } from "svelte";
  import { loadSettings, saveSettings } from "$lib/state/persistence";

  const selection = getSelection();
  const revisionState = getRevisionState();
  const projectState = getProjectState();
  const graphStore = getGraphStore();
  const searchState = getSearchState();

  let sceneManager: SceneManager | undefined = $state(undefined);
  let activeView: "viewport" | "graph" = $state("viewport");
  let searchPopup: Window | null = null;
  let searchChannel: BroadcastChannel | null = null;
  
  // Load saved settings and initialize state (only in browser)
  let settingsLoaded = $state(false);
  $effect(() => {
    if (typeof window === 'undefined' || settingsLoaded) return;
    const savedSettings = loadSettings();
    if (savedSettings) {
      activeView = savedSettings.activeView;
      initializeFromSettings(savedSettings);
    }
    settingsLoaded = true;
  });

  const API_BASE = import.meta.env.VITE_API_URL
    ? (import.meta.env.VITE_API_URL as string).replace("/graphql", "")
    : "/api";

  let showImportModal = $state(false);
  let importing = $state(false);
  let importError = $state<string | null>(null);
  let loadingGeometry = $state(false);
  let loadingGeometryCurrent = $state(0);
  let loadingGeometryTotal = $state(0);

  // ---- Project / Branch state ----
  interface ProjectData {
    id: number;
    name: string;
    description: string | null;
    createdAt: string;
    branches: BranchData[];
  }
  interface BranchData {
    id: number;
    projectId: number;
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

  // Derived: currently selected project and its branches
  let activeProject = $derived(
    projects.find((p) => p.id === projectState.activeProjectId) ?? null,
  );
  let activeBranch = $derived(
    activeProject?.branches.find((b) => b.id === projectState.activeBranchId) ??
      null,
  );

  // ---- Lifecycle ----

  // Persist settings to localStorage whenever they change (only after initial load)
  $effect(() => {
    if (typeof window === 'undefined' || !settingsLoaded) return;
    saveSettings({
      activeProjectId: projectState.activeProjectId,
      activeBranchId: projectState.activeBranchId,
      activeRevision: revisionState.activeRevision,
      activeGlobalId: selection.activeGlobalId,
      subgraphDepth: selection.subgraphDepth,
      activeView: activeView,
    });
  });

  // Load projects on mount
  $effect(() => {
    loadProjects();
  });

  // Load graph data when switching to graph view (if branch is selected)
  $effect(() => {
    const branchId = projectState.activeBranchId;
    if (
      activeView === "graph" &&
      branchId &&
      graphStore.data.nodes.length === 0 &&
      !graphStore.loading
    ) {
      graphStore.fetchGraph(branchId, revisionState.activeRevision);
    }
  });

  // Load latest revision when branch changes
  $effect(() => {
    const branchId = projectState.activeBranchId;
    if (branchId && revisionState.activeRevision === null && !importing) {
      fetchLatestRevision(branchId);
    }
  });

  // Load 3D geometry when revision changes and sceneManager is ready
  let lastFetchedRev: number | null = $state(null);
  let lastFetchedBranchId: number | null = $state(null);
  $effect(() => {
    const rev = revisionState.activeRevision;
    const branchId = projectState.activeBranchId;
    const mgr = sceneManager;
    if (!mgr || rev === null || !branchId) return;

    // Only fetch if revision or branchId changed
    if (rev === lastFetchedRev && branchId === lastFetchedBranchId) return;

    // Check loading state without tracking it
    if (untrack(() => graphStore.loading)) return;

    lastFetchedRev = rev;
    lastFetchedBranchId = branchId;

    untrack(() => {
      loadGeometry(mgr, rev, branchId);
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
      const subgraphIds = computeSubgraph(graphStore.data, selectedId, depth);
      mgr.applySubgraphFilter(selectedId, subgraphIds);
    } else {
      mgr.applySubgraphFilter(null, null);
    }
  });

  // BroadcastChannel for cross-window search communication
  onMount(() => {
    searchChannel = new BroadcastChannel(SEARCH_CHANNEL);
    searchChannel.onmessage = (e: MessageEvent<SearchMessage>) => {
      if (e.data.type === "apply-filters") {
        handleApplyFilters(e.data.filters);
      } else if (e.data.type === "apply-filter-sets") {
        handleApplyFilterSets(e.data.filterSets, e.data.combinationLogic);
      }
    };
  });

  onDestroy(() => {
    searchChannel?.close();
  });

  function sendBranchContext() {
    const branchId = projectState.activeBranchId;
    const projectId = projectState.activeProjectId;
    if (branchId && projectId) {
      searchChannel?.postMessage({
        type: "branch-context",
        branchId,
        projectId,
      } satisfies SearchMessage);
    }
  }

  function openSearchPopup() {
    if (!searchPopup || searchPopup.closed) {
      searchPopup = window.open(
        "/search",
        "bimatlas-search",
        "width=520,height=700",
      );
      setTimeout(sendBranchContext, 500);
    } else {
      searchPopup.focus();
      sendBranchContext();
    }
  }

  function filtersToQueryVars(filters: SearchFilter[]): Record<string, unknown> {
    const vars: Record<string, unknown> = {};
    const allClasses: string[] = [];

    for (const f of filters) {
      if (f.mode === "class" && f.ifcClass) {
        const descendants = getDescendantClasses(f.ifcClass);
        for (const cls of descendants) allClasses.push(cls);
      } else if (f.mode === "attribute" && f.attribute && f.value) {
        const key = f.attribute === "objectType" ? "objectType" : f.attribute;
        vars[key] = f.value;
      }
    }

    if (allClasses.length > 0) {
      vars.ifcClasses = [...new Set(allClasses)];
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

    searchChannel?.postMessage({
      type: "filter-result-count",
      count: mgr.elementCount,
      total: searchState.totalProductCount,
    } satisfies SearchMessage);
  }

  async function autoLoadAppliedFilterSets(branchId: number) {
    try {
      const result = await client
        .query(APPLIED_FILTER_SETS_QUERY, { branchId })
        .toPromise();
      const data = result.data?.appliedFilterSets;
      if (data && data.filterSets && data.filterSets.length > 0) {
        await handleApplyFilterSets(data.filterSets, data.combinationLogic ?? "AND");
      }
    } catch (err) {
      console.error("Failed to auto-load applied filter sets:", err);
    }
  }

  // ---- API helpers ----

  async function loadProjects() {
    loadingProjects = true;
    try {
      const result = await client.query(PROJECTS_QUERY, {}).toPromise();
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
      }
    } catch (err) {
      console.error("Failed to create branch:", err);
    } finally {
      creatingBranch = false;
    }
  }

  function selectProject(projectId: number) {
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

  function selectBranch(branchId: number) {
    projectState.activeBranchId = branchId;
    sceneManager?.clearAll();
    sendBranchContext();
    autoLoadAppliedFilterSets(branchId);
  }

  async function fetchLatestRevision(branchId: number) {
    try {
      const result = await client
        .query(REVISIONS_QUERY, { branchId })
        .toPromise();

      const revisions = result.data?.revisions || [];
      if (revisions.length > 0) {
        const latest = Math.max(...revisions.map((r: any) => r.id));
        revisionState.activeRevision = latest;
      }
    } catch (err) {
      console.error("Failed to fetch latest revision:", err);
    }
  }

  /** Map GraphQL-style filter vars (camelCase) to stream query params (snake_case). */
  function streamQueryParams(
    branchId: number,
    revision: number,
    filterVars: Record<string, unknown>,
  ): URLSearchParams {
    const params = new URLSearchParams();
    params.set("branch_id", String(branchId));
    params.set("revision", String(revision));
    if (filterVars.ifcClass != null) params.set("ifc_class", String(filterVars.ifcClass));
    if (filterVars.ifcClasses != null) {
      for (const c of filterVars.ifcClasses as string[]) params.append("ifc_classes", c);
    }
    if (filterVars.containedIn != null) params.set("contained_in", String(filterVars.containedIn));
    if (filterVars.name != null) params.set("name", String(filterVars.name));
    if (filterVars.objectType != null) params.set("object_type", String(filterVars.objectType));
    if (filterVars.tag != null) params.set("tag", String(filterVars.tag));
    if (filterVars.description != null) params.set("description", String(filterVars.description));
    if (filterVars.globalId != null) params.set("global_id", String(filterVars.globalId));
    return params;
  }

  async function loadGeometry(
    mgr: SceneManager,
    revision: number,
    branchId: number,
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

      if (!reader) {
        throw new Error("No response body");
      }

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() ?? "";

        for (const chunk of lines) {
          const dataMatch = chunk.match(/^data:\s*(.+)$/m);
          if (!dataMatch) continue;
          try {
            const data = JSON.parse(dataMatch[1]);
            if (data.type === "error") {
              console.error("Stream error:", data.message);
              return;
            }
            if (data.type === "start") {
              loadingGeometryTotal = data.total ?? 0;
              continue;
            }
            if (data.type === "product") {
              const product = data.product;
              loadingGeometryCurrent = data.current ?? metaList.length + 1;
              metaList.push({
                globalId: product.globalId,
                ifcClass: product.ifcClass,
                name: product.name ?? null,
                description: product.description ?? null,
                objectType: product.objectType ?? null,
                tag: product.tag ?? null,
              });
              if (product.mesh?.vertices && product.mesh?.faces) {
                try {
                  const geometry = createBufferGeometry(product.mesh as RawMeshData);
                  mgr.addElement(product.globalId, geometry);
                } catch (err) {
                  console.warn(`Failed to load geometry for ${product.globalId}:`, err);
                }
              }
              await new Promise((r) => requestAnimationFrame(r));
              continue;
            }
            if (data.type === "end") {
              break;
            }
          } catch (e) {
            console.warn("Parse stream chunk:", e);
          }
        }
      }

      if (buffer.trim()) {
        const dataMatch = buffer.match(/^data:\s*(.+)$/m);
        if (dataMatch) {
          try {
            const data = JSON.parse(dataMatch[1]);
            if (data.type === "product") {
              const product = data.product;
              metaList.push({
                globalId: product.globalId,
                ifcClass: product.ifcClass,
                name: product.name ?? null,
                description: product.description ?? null,
                objectType: product.objectType ?? null,
                tag: product.tag ?? null,
              });
              if (product.mesh?.vertices && product.mesh?.faces) {
                try {
                  const geometry = createBufferGeometry(product.mesh as RawMeshData);
                  mgr.addElement(product.globalId, geometry);
                } catch (_) {}
              }
            }
          } catch (_) {}
        }
      }

      searchState.setProducts(metaList);

      if (Object.keys(filterVars).length === 0) {
        searchState.totalProductCount = metaList.length;
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
      revisionState.activeRevision = result.revision_id;
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
      <h1>BimAtlas</h1>
    </div>

    <!-- Project selector -->
    {#if projectState.activeProjectId && activeProject}
      <div class="context-selector">
        <div class="selector-group">
          <label class="selector-label" for="project-select">Project</label>
          <select
            id="project-select"
            class="selector"
            value={projectState.activeProjectId}
            onchange={(e) =>
              selectProject(Number((e.target as HTMLSelectElement).value))}
          >
            {#each projects as p}
              <option value={p.id}>{p.name}</option>
            {/each}
          </select>
        </div>

        <span class="separator">/</span>

        <!-- Branch selector -->
        <div class="selector-group">
          <label class="selector-label" for="branch-select">Branch</label>
          <select
            id="branch-select"
            class="selector"
            value={projectState.activeBranchId}
            onchange={(e) =>
              selectBranch(Number((e.target as HTMLSelectElement).value))}
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
        </div>
      </div>

      <div class="view-toggle" role="tablist">
        <button
          class="tab-btn"
          class:active={activeView === "viewport"}
          role="tab"
          aria-selected={activeView === "viewport"}
          onclick={() => (activeView = "viewport")}
        >
          3D View
        </button>
        <button
          class="tab-btn"
          class:active={activeView === "graph"}
          role="tab"
          aria-selected={activeView === "graph"}
          onclick={() => (activeView = "graph")}
        >
          Graph
        </button>
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
                <button
                  class="project-item"
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
    {:else if activeView === "viewport"}
      <div class="viewport-container">
        <Viewport bind:manager={sceneManager} />
        {#if loadingGeometry}
          <div class="viewport-loading-overlay" aria-live="polite" aria-busy="true">
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
                      (loadingGeometryCurrent / loadingGeometryTotal) * 100
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
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              style="margin-right:0.35rem"
            >
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
          <!-- Depth widget -->
          <DepthWidget bind:value={selection.subgraphDepth} />
        </Sidebar>
        <!-- Search button -->
        <button
          class="search-btn"
          onclick={openSearchPopup}
          aria-label="Search and filter"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="2" />
            <path d="M16.5 16.5L21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
          </svg>
          Search
        </button>
        <!-- Element count -->
        <span class="element-count"
          >{sceneManager?.elementCount ?? 0} elements</span
        >
        <SelectionPanel />
      </div>
    {:else}
      <div class="graph-wrapper">
        <ForceGraph />
        {#if selection.activeGlobalId}
          <SelectionPanel />
        {/if}
      </div>
    {/if}

    <!-- Import modal -->
    <ImportModal
      open={showImportModal}
      onclose={() => (showImportModal = false)}
      onsubmit={handleImportSubmit}
    />

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
  :global(html, body) {
    margin: 0;
    padding: 0;
    height: 100%;
    overflow: hidden;
    background: #12121e;
  }

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

  .brand h1 {
    margin: 0;
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    background: linear-gradient(135deg, #ff6644, #ff9966);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .header-spacer {
    flex: 1;
  }

  /* ---- Context selector (project / branch) ---- */

  .context-selector {
    display: flex;
    align-items: center;
    gap: 0.5rem;
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
    margin-right: 0.15rem;
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
    margin: 0 0.1rem;
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

  .icon-btn:hover {
    background: rgba(255, 136, 102, 0.2);
    color: #ff8866;
  }

  /* ---- View toggle tabs ---- */

  .view-toggle {
    display: flex;
    gap: 0;
    background: rgba(255, 255, 255, 0.04);
    border-radius: 0.4rem;
    padding: 0.2rem;
  }

  .tab-btn {
    background: none;
    border: none;
    color: #888;
    padding: 0.35rem 0.9rem;
    font-size: 0.8rem;
    cursor: pointer;
    border-radius: 0.3rem;
    transition:
      background 0.15s,
      color 0.15s;
  }

  .tab-btn:hover {
    color: #ccc;
  }

  .tab-btn.active {
    background: rgba(255, 102, 68, 0.15);
    color: #ff8866;
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

  .graph-wrapper {
    flex: 1;
    position: relative;
    min-height: 0;
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
    background: #1e1e30;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.75rem;
    padding: 2rem;
    max-width: 520px;
    width: 100%;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  }

  .picker-card h2 {
    margin: 0 0 0.5rem;
    font-size: 1.2rem;
    font-weight: 600;
    color: #e0e0e0;
  }

  .picker-subtitle {
    margin: 0 0 1.5rem;
    color: #888;
    font-size: 0.85rem;
  }

  .project-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 1.25rem;
  }

  .project-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
    cursor: pointer;
    transition:
      background 0.15s,
      border-color 0.15s;
    text-align: left;
    width: 100%;
    color: inherit;
  }

  .project-item:hover {
    background: rgba(255, 136, 102, 0.08);
    border-color: rgba(255, 136, 102, 0.2);
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
    margin: 1.5rem 0;
  }

  .create-form {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    margin-top: 1rem;
  }

  .form-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: 0.25rem;
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
    margin-top: 0.5rem;
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
  }

  .search-btn {
    position: absolute;
    bottom: 1rem;
    left: 50%;
    transform: translateX(-50%);
    pointer-events: auto;
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

  .search-btn:hover {
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
    margin-bottom: 0.75rem;
  }

  .modal-header h2 {
    margin: 0;
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
    margin: 0 0 1rem;
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
    margin-bottom: 0.5rem;
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.6rem;
    margin-top: 1rem;
  }

  /* ---- Loading overlay ---- */

  .loading-overlay {
    position: fixed;
    inset: 0;
    z-index: 200;
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
