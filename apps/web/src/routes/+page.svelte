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
  } from "$lib/state/selection.svelte";
  import { getGraphStore } from "$lib/graph/graphStore.svelte";
  import { computeSubgraph } from "$lib/graph/subgraph";
  import type { SceneManager } from "$lib/engine/SceneManager";
  import {
    client,
    IFC_PRODUCTS_QUERY,
    PROJECTS_QUERY,
    CREATE_PROJECT_MUTATION,
    CREATE_BRANCH_MUTATION,
    REVISIONS_QUERY,
  } from "$lib/api/client";
  import {
    createBufferGeometry,
    type RawMeshData,
  } from "$lib/engine/BufferGeometryLoader";
  import { untrack } from "svelte";

  const selection = getSelection();
  const revisionState = getRevisionState();
  const projectState = getProjectState();
  const graphStore = getGraphStore();

  let sceneManager: SceneManager | undefined = $state(undefined);
  let activeView: "viewport" | "graph" = $state("viewport");

  const API_BASE = import.meta.env.VITE_API_URL
    ? (import.meta.env.VITE_API_URL as string).replace("/graphql", "")
    : "/api";

  let showImportModal = $state(false);
  let importing = $state(false);
  let importError = $state<string | null>(null);
  let loadingGeometry = $state(false);

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

  // ---- API helpers ----

  async function loadProjects() {
    loadingProjects = true;
    try {
      const result = await client.query(PROJECTS_QUERY, {}).toPromise();
      if (result.data?.projects) {
        projects = result.data.projects;
      }
    } catch (err) {
      console.error("Failed to load projects:", err);
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
    // Auto-select the main branch
    const proj = projects.find((p) => p.id === projectId);
    const mainBranch = proj?.branches.find((b) => b.name === "main");
    if (mainBranch) {
      projectState.activeBranchId = mainBranch.id;
    }
    // Clear the scene
    sceneManager?.clearAll();
  }

  function selectBranch(branchId: number) {
    projectState.activeBranchId = branchId;
    // Clear the scene for the new branch
    sceneManager?.clearAll();
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

  async function loadGeometry(
    mgr: SceneManager,
    revision: number,
    branchId: number,
  ) {
    if (loadingGeometry) return;
    loadingGeometry = true;

    try {
      const result = await client.query(IFC_PRODUCTS_QUERY, {
        branchId,
        revision,
      });
      if (result.error) {
        console.error("Failed to fetch geometry:", result.error);
        return;
      }

      const products = result.data?.ifcProducts || [];
      mgr.clearAll();

      for (const product of products) {
        if (product.mesh && product.mesh.vertices && product.mesh.faces) {
          try {
            const geometry = createBufferGeometry(product.mesh as RawMeshData);
            mgr.addElement(product.globalId, geometry);
          } catch (err) {
            console.warn(
              `Failed to load geometry for ${product.globalId}:`,
              err,
            );
          }
        }
      }

      if (mgr.elementCount > 0) {
        mgr.fitToContent();
      }
    } catch (err) {
      console.error("Failed to load geometry:", err);
    } finally {
      loadingGeometry = false;
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

  .viewport-overlay {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: 1000;
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
