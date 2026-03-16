<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { page } from "$app/stores";
  import {
    VIEWS_CHANNEL,
    cloneForPost,
    type ViewsMessage,
    type SavedViewPayload,
  } from "$lib/views/protocol";
  import { loadSettings } from "$lib/state/persistence";
  import {
    client,
    PROJECTS_QUERY,
    SAVED_VIEWS_QUERY,
    SAVED_VIEW_QUERY,
    CREATE_SAVED_VIEW_MUTATION,
    UPDATE_SAVED_VIEW_MUTATION,
    DELETE_SAVED_VIEW_MUTATION,
    ATTACH_FILTER_SETS_TO_SAVED_VIEW_MUTATION,
    FILTER_SETS_QUERY,
  } from "$lib/api/client";

  let branchId = $state<string | null>(null);
  let projectId = $state<string | null>(null);
  let branchName = $state<string | null>(null);
  let projectName = $state<string | null>(null);
  let revision = $state<number | null>(null);

  let channel: BroadcastChannel | null = null;
  let contextRetryTimeout: ReturnType<typeof setTimeout> | null = null;
  let contextRetryInterval: ReturnType<typeof setInterval> | null = null;
  let lastContextKey: string | null = null;

  let views = $state<SavedViewPayload[]>([]);
  let selectedViewId = $state<string | null>(null);
  let activeView = $state<SavedViewPayload | null>(null);
  let ghostedFilterSetIds = $state<Set<string>>(new Set());
  let editorOpen = $state(false);
  let editorName = $state("");
  let editorBcf = $state<Record<string, unknown>>({});
  let editorUiFilters = $state<Record<string, unknown>>({});
  let editorFilterSetIds = $state<string[]>([]);
  let filterSets = $state<Array<{ id: string; name: string }>>([]);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let searchQuery = $state("");

  function applyContextFromUrl() {
    const url = $page.url;
    const b = url.searchParams.get("branchId");
    const p = url.searchParams.get("projectId");
    const r = url.searchParams.get("revision");
    const bn = url.searchParams.get("branchName");
    const pn = url.searchParams.get("projectName");
    if (b != null && b !== "") branchId = b;
    if (p != null && p !== "") projectId = p;
    if (r != null && r !== "") {
      const parsed = Number(r);
      revision = Number.isNaN(parsed) ? null : parsed;
    }
    if (bn != null && bn !== "") branchName = bn;
    if (pn != null && pn !== "") projectName = pn;
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
  }

  function contextKey(msg: Extract<ViewsMessage, { type: "context" }>): string {
    return JSON.stringify({
      branchId: msg.branchId,
      projectId: msg.projectId,
      revision: msg.revision,
      branchName: msg.branchName,
      projectName: msg.projectName,
    });
  }

  function handleContextMessage(msg: Extract<ViewsMessage, { type: "context" }>) {
    const nextKey = contextKey(msg);
    if (nextKey === lastContextKey) return;
    lastContextKey = nextKey;
    branchId = msg.branchId;
    projectId = msg.projectId;
    branchName = msg.branchName ?? null;
    projectName = msg.projectName ?? null;
    revision = msg.revision ?? null;
  }

  async function resolveNamesFromProjects() {
    if (!projectId || !branchId) return;
    if (projectName && branchName) return;
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
        if (branch) branchName = branch.name ?? branchName;
      }
    } catch {
      // Non-blocking fallback; keep IDs if name lookup fails.
    }
  }

  const messageHandlers: Partial<Record<ViewsMessage["type"], (msg: ViewsMessage) => void>> = {
    context: (msg) => handleContextMessage(msg as Extract<ViewsMessage, { type: "context" }>),
    camera: (msg) => {
      if (msg.type === "camera" && msg.bcfCameraState) {
        editorBcf = msg.bcfCameraState as Record<string, unknown>;
      }
    },
  };

  function handleIncomingMessage(e: MessageEvent<ViewsMessage>) {
    const msg = e.data;
    if (!msg || typeof msg.type !== "string") return;
    const handler = messageHandlers[msg.type as ViewsMessage["type"]];
    if (handler) handler(msg);
  }

  function requestContext() {
    channel?.postMessage(cloneForPost({ type: "request-context" } satisfies ViewsMessage));
  }

  function captureCurrentCamera() {
    channel?.postMessage(cloneForPost({ type: "request-camera" } satisfies ViewsMessage));
  }

  async function loadViews() {
    if (!branchId) return;
    loading = true;
    error = null;
    try {
      const result = await client
        .query(SAVED_VIEWS_QUERY, { branchId }, { requestPolicy: "network-only" })
        .toPromise();
      const data = result.data as { savedViews?: SavedViewPayload[] };
      views = data?.savedViews ?? [];
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      views = [];
    } finally {
      loading = false;
    }
  }

  async function loadFilterSets() {
    if (!branchId) return;
    try {
      const result = await client
        .query(FILTER_SETS_QUERY, { branchId }, { requestPolicy: "network-only" })
        .toPromise();
      const data = result.data as { filterSets?: Array<{ id: string; name: string }> };
      filterSets = (data?.filterSets ?? []).map((fs) => ({ id: fs.id, name: fs.name }));
    } catch {
      filterSets = [];
    }
  }

  async function openEditor(view?: SavedViewPayload) {
    error = null;
    if (branchId) await loadFilterSets();
    if (view) {
      selectedViewId = view.id;
      editorName = view.name;
      editorBcf = (view.bcfCameraState ?? {}) as Record<string, unknown>;
      editorUiFilters = (view.uiFilters ?? {}) as Record<string, unknown>;
      editorFilterSetIds = view.filterSets?.map((fs) => fs.id ?? fs.filterSetId ?? "").filter(Boolean) ?? [];
    } else {
      selectedViewId = null;
      editorName = "";
      editorBcf = {};
      editorUiFilters = {};
      editorFilterSetIds = [];
    }
    editorOpen = true;
  }

  function closeEditor() {
    editorOpen = false;
    selectedViewId = null;
  }

  function checkMutationError<T>(result: { data?: T; error?: { message: string } }): asserts result is { data: T } {
    if (result.error) throw new Error(result.error.message);
  }

  async function saveView() {
    if (!branchId) return;
    error = null;
    const bcf = Object.keys(editorBcf).length > 0 ? editorBcf : { perspective_camera: { position: [0, 0, 10], direction: [0, 0, -1], up_vector: [0, 1, 0] } };
    try {
      const idsToAttach = [...new Set(editorFilterSetIds)].filter(Boolean);
      if (selectedViewId) {
        const updateResult = await client.mutation(
          UPDATE_SAVED_VIEW_MUTATION,
          {
            id: selectedViewId,
            name: editorName,
            bcfCameraState: bcf,
            uiFilters: editorUiFilters,
          },
          { requestPolicy: "network-only" }
        ).toPromise();
        checkMutationError(updateResult);
        const attachResult = await client.mutation(
          ATTACH_FILTER_SETS_TO_SAVED_VIEW_MUTATION,
          { viewId: selectedViewId, filterSetIds: idsToAttach },
          { requestPolicy: "network-only" }
        ).toPromise();
        checkMutationError(attachResult);
      } else {
        const createResult = await client.mutation(
          CREATE_SAVED_VIEW_MUTATION,
          {
            branchId,
            name: editorName,
            bcfCameraState: bcf,
            uiFilters: editorUiFilters,
          },
          { requestPolicy: "network-only" }
        ).toPromise();
        checkMutationError(createResult);
        const created = await client
          .query(SAVED_VIEWS_QUERY, { branchId }, { requestPolicy: "network-only" })
          .toPromise();
        const list = (created.data as { savedViews?: SavedViewPayload[] })?.savedViews ?? [];
        const newView = list.find((v) => v.name === editorName);
        if (newView && idsToAttach.length > 0) {
          const attachResult = await client.mutation(
            ATTACH_FILTER_SETS_TO_SAVED_VIEW_MUTATION,
            { viewId: newView.id, filterSetIds: idsToAttach },
            { requestPolicy: "network-only" }
          ).toPromise();
          checkMutationError(attachResult);
        }
      }
      closeEditor();
      await loadViews();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  }

  async function deleteView(view: SavedViewPayload) {
    if (!confirm(`Delete view "${view.name}"?`)) return;
    error = null;
    try {
      await client.mutation(
        DELETE_SAVED_VIEW_MUTATION,
        { id: view.id },
        { requestPolicy: "network-only" }
      ).toPromise();
      if (selectedViewId === view.id) closeEditor();
      await loadViews();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  }

  async function loadView(view: SavedViewPayload) {
    if (!view) return;
    const full = await client
      .query(SAVED_VIEW_QUERY, { id: view.id }, { requestPolicy: "network-only" })
      .toPromise();
    const data = full.data as { savedView?: SavedViewPayload };
    const payload = data?.savedView ?? view;
    if (!payload) return;
    activeView = payload;
    ghostedFilterSetIds = new Set();
    const msg = {
      type: "LOAD_VIEW" as const,
      view: cloneForPost(payload),
    };
    channel?.postMessage(msg);
  }

  function toggleGhostMode(filterSetId: string) {
    const next = new Set(ghostedFilterSetIds);
    const enabled = !next.has(filterSetId);
    if (enabled) next.add(filterSetId);
    else next.delete(filterSetId);
    ghostedFilterSetIds = next;
    const msg = {
      type: "TOGGLE_GHOST_MODE" as const,
      filterSetId,
      enabled,
    };
    channel?.postMessage(cloneForPost(msg));
  }

  onMount(() => {
    applyContextFromUrl();
    applyContextFallbackFromSettings();
    void resolveNamesFromProjects();

    channel = new BroadcastChannel(VIEWS_CHANNEL);
    channel.onmessage = handleIncomingMessage;
    requestContext();

    contextRetryTimeout = setTimeout(() => {
      if (branchId == null && projectId == null) requestContext();
      contextRetryTimeout = null;
    }, 1500);

    if (branchId == null && projectId == null) {
      let attempts = 0;
      contextRetryInterval = setInterval(() => {
        if (branchId != null || projectId != null || attempts >= 8) {
          if (contextRetryInterval) {
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
    if (contextRetryTimeout) clearTimeout(contextRetryTimeout);
    if (contextRetryInterval) clearInterval(contextRetryInterval);
  });

  $effect(() => {
    if (branchId) {
      loadViews();
      loadFilterSets();
    } else {
      views = [];
      filterSets = [];
    }
  });

  $effect(() => {
    if (branchId && projectId && (!projectName || !branchName)) {
      void resolveNamesFromProjects();
    }
  });

  function formatBcf(bcf: Record<string, unknown> | null | undefined): string {
    if (!bcf || typeof bcf !== "object") return "—";
    const fmt = (n: unknown) =>
      typeof n === "number" ? (Math.abs(n) < 0.0001 || Math.abs(n) > 9999 ? n.toExponential(2) : n.toFixed(3)) : String(n);
    const vec = (v: unknown) =>
      Array.isArray(v) && v.length >= 3 ? `[${fmt(v[0])}, ${fmt(v[1])}, ${fmt(v[2])}]` : "";
    const lines: string[] = [];
    const pc = bcf.perspective_camera as Record<string, unknown> | undefined;
    const oc = bcf.orthogonal_camera as Record<string, unknown> | undefined;
    const cam = pc ?? oc;
    if (cam) {
      lines.push(pc ? "Perspective" : "Orthogonal");
      if (cam.position) lines.push(`  position: ${vec(cam.position)}`);
      if (cam.direction) lines.push(`  direction: ${vec(cam.direction)}`);
      if (cam.up_vector) lines.push(`  up_vector: ${vec(cam.up_vector)}`);
      if (pc?.field_of_view != null) lines.push(`  field_of_view: ${fmt(pc.field_of_view)}°`);
      if (oc?.view_to_world_scale != null) lines.push(`  view_to_world_scale: ${fmt(oc.view_to_world_scale)}`);
    }
    const cp = bcf.clipping_planes as unknown[] | undefined;
    if (cp?.length) lines.push(`clipping_planes: ${cp.length} plane(s)`);
    return lines.length ? lines.join("\n") : "—";
  }

  const filteredViews = $derived(
    searchQuery.trim()
      ? views.filter(
          (v) =>
            v.name.toLowerCase().includes(searchQuery.toLowerCase().trim()) ||
            v.filterSets?.some(
              (fs) =>
                (fs.name ?? "")
                  .toLowerCase()
                  .includes(searchQuery.toLowerCase().trim()),
            ),
        )
      : views,
  );
</script>

<div class="views-page">
  <header class="page-header">
    <h2>Saved Views</h2>
    {#if branchName || projectName || branchId || projectId}
      <span class="context-pill mono">
        {projectName ?? projectId ?? "—"} / {branchName ?? branchId ?? "—"}
        {#if revision != null}(rev {revision}){/if}
      </span>
    {:else}
      <span class="context-pill empty">Waiting for context…</span>
    {/if}
  </header>

  {#if error}
    <div class="error-banner">{error}</div>
  {/if}

  <section class="actions toolbar">
    <input
      type="search"
      class="search-input"
      placeholder="Search views…"
      aria-label="Search saved views"
      bind:value={searchQuery}
    />
    <button type="button" class="btn btn-primary" onclick={() => openEditor()}>New View</button>
  </section>

  {#if activeView && activeView.filterSets && activeView.filterSets.length > 0}
    <section class="active-view-section">
      <h3>Active: {activeView.name}</h3>
      <p class="muted">Toggle filter sets to ghost (dim) them in the viewer:</p>
      <ul class="filter-set-toggles">
        {#each activeView.filterSets as fs (fs.id ?? fs.filterSetId)}
          {@const fsId = fs.id ?? fs.filterSetId ?? ""}
          <li>
            <label class="checkbox-row">
              <input
                type="checkbox"
                checked={!ghostedFilterSetIds.has(fsId)}
                onchange={() => toggleGhostMode(fsId)}
              />
              <span>{fs.name ?? fsId.slice(0, 8)}</span>
            </label>
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  <section class="view-list">
    {#if loading}
      <p class="muted">Loading…</p>
    {:else if views.length === 0}
      <p class="muted">No saved views. Create one to save camera, clipping, and filter state.</p>
    {:else if filteredViews.length === 0}
      <p class="muted">No views match "{searchQuery}".</p>
    {:else}
      <ul class="view-cards">
        {#each filteredViews as view (view.id)}
          <li class="view-card-item">
            <details class="view-card">
              <summary class="view-card-summary">
                <span class="view-card-name">{view.name}</span>
                <div class="view-card-actions" role="group" aria-label="View actions">
                  <button
                    type="button"
                    class="btn btn-primary btn-sm"
                    onclick={(e) => { e.stopPropagation(); loadView(view); }}
                    title="Load this view in the main viewer"
                  >
                    Load
                  </button>
                  <button
                    type="button"
                    class="btn btn-secondary btn-sm"
                    onclick={(e) => { e.stopPropagation(); openEditor(view); }}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    class="btn btn-danger btn-sm"
                    onclick={(e) => { e.stopPropagation(); deleteView(view); }}
                  >
                    Delete
                  </button>
                </div>
              </summary>
              <div class="view-card-details">
                <div class="detail-row">
                  <span class="detail-row-label">Filter sets</span>
                  <span class="detail-row-value">
                    {#if view.filterSets && view.filterSets.length > 0}
                      {view.filterSets.map((fs) => fs.name ?? fs.id ?? fs.filterSetId ?? "—").join(", ")}
                    {:else}
                      <span class="muted">None</span>
                    {/if}
                  </span>
                </div>
                <div class="detail-row">
                  <span class="detail-row-label">BCF camera</span>
                  <pre class="detail-row-value bcf-json mono">{formatBcf(view.bcfCameraState as Record<string, unknown>)}</pre>
                </div>
              </div>
            </details>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  {#if editorOpen}
    <div class="editor-overlay">
      <div class="editor-modal">
        <h3>{selectedViewId ? "Edit View" : "New View"}</h3>
        {#if error}
          <div class="editor-error">{error}</div>
        {/if}
        <div class="form-row">
          <label for="view-name">Name</label>
          <input id="view-name" type="text" bind:value={editorName} placeholder="View name" />
        </div>
        <fieldset class="form-row">
          <legend>Filter sets</legend>
          <div class="filter-set-list">
            {#each filterSets as fs}
              <label class="checkbox-row">
                <input
                  type="checkbox"
                  checked={editorFilterSetIds.includes(fs.id)}
                  onchange={(e) => {
                    const checked = (e.currentTarget as HTMLInputElement).checked;
                    editorFilterSetIds = checked
                      ? [...editorFilterSetIds, fs.id]
                      : editorFilterSetIds.filter((id) => id !== fs.id);
                  }}
                />
                <span>{fs.name}</span>
              </label>
            {/each}
          </div>
        </fieldset>
        <div class="form-row camera-section">
          <span class="detail-row-label">Camera</span>
          <pre class="detail-row-value bcf-json mono">{formatBcf(editorBcf)}</pre>
          <button type="button" class="btn btn-secondary btn-sm camera-capture-btn" onclick={captureCurrentCamera} title="Capture current camera from main viewer">
            Save current camera
          </button>
        </div>
        <div class="editor-actions">
          <button type="button" class="btn btn-primary" onclick={saveView}>Save</button>
          <button type="button" class="btn btn-secondary" onclick={closeEditor}>Cancel</button>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .views-page {
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: var(--color-bg-canvas, #1e293b);
    color: var(--color-text-primary, #f1f5f9);
    font-family: system-ui, -apple-system, sans-serif;
    font-size: 0.8rem;
    overflow: hidden;
  }

  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.25rem;
    border-bottom: 1px solid var(--color-border-default, #334155);
    gap: 1rem;
  }

  .page-header h2 {
    margin: 0;
    font-size: 1.1rem;
  }

  .context-pill {
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    font-size: 0.75rem;
    background: var(--color-bg-elevated, #334155);
    border: 1px solid var(--color-border-default, #475569);
    max-width: 50%;
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

  .error-banner {
    padding: 0.5rem 1rem;
    background: #7f1d1d;
    color: #fecaca;
    font-size: 0.8rem;
  }

  .actions.toolbar {
    padding: 0.75rem 1.25rem;
    border-bottom: 1px solid var(--color-border-default, #334155);
    display: flex;
    gap: 0.5rem;
    align-items: center;
    flex-wrap: wrap;
  }

  .search-input {
    flex: 1;
    min-width: 140px;
    padding: 0.55rem 1.15rem;
    border: 1px solid var(--color-border-default, #475569);
    border-radius: 0.5rem;
    background: var(--color-bg-canvas, #1e293b);
    color: var(--color-text-primary, #f1f5f9);
    font-size: 0.82rem;
    box-sizing: border-box;
  }

  .search-input::placeholder {
    color: var(--color-text-muted, #94a3b8);
  }

  .search-input:focus {
    outline: none;
    border-color: var(--color-brand-500, #3b82f6);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-brand-500, #3b82f6) 25%, transparent);
  }

  .active-view-section {
    padding: 0.75rem 1.25rem;
    border-bottom: 1px solid var(--color-border-default, #334155);
  }

  .active-view-section h3 {
    margin: 0 0 0.5rem 0;
    font-size: 0.95rem;
  }

  .filter-set-toggles {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .filter-set-toggles li {
    padding: 0.25rem 0;
  }

  .view-list {
    flex: 1 1 0;
    overflow-y: auto;
    padding: 1rem 1.25rem;
  }

  .view-list ul.view-cards {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .view-card-item {
    list-style: none;
  }

  .view-card {
    border-radius: 0.75rem;
    border: 1px solid var(--color-border-subtle, #334155);
    background: var(--color-bg-elevated, #334155);
    overflow: hidden;
  }

  .view-card-summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.6rem 0.9rem;
    cursor: pointer;
    list-style: none;
    gap: 0.5rem;
  }

  .view-card-summary::-webkit-details-marker {
    display: none;
  }

  .view-card-summary::before {
    content: "▸";
    font-size: 0.65rem;
    color: var(--color-text-muted, #94a3b8);
    transition: transform 0.2s;
  }

  .view-card[open] .view-card-summary::before {
    transform: rotate(90deg);
  }

  .view-card-name {
    flex: 1;
    font-weight: 500;
    font-size: 0.9rem;
    color: var(--color-text-primary, #f1f5f9);
  }

  .view-card-actions {
    display: flex;
    gap: 0.25rem;
  }

  .view-card-details {
    padding: 0.6rem 0.9rem 0.9rem;
    border-top: 1px solid var(--color-border-default, #475569);
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }

  .detail-row {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    width: 100%;
  }

  .detail-row-label {
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-text-muted, #94a3b8);
  }

  .detail-row-value {
    font-size: 0.8rem;
    color: var(--color-text-secondary, #cbd5e1);
    word-break: break-word;
  }

  .detail-row-value.bcf-json {
    margin: 0;
    padding: 0.5rem 0.6rem;
    background: color-mix(in srgb, var(--color-bg-canvas, #1e293b) 60%, transparent);
    border-radius: 4px;
    border: 1px solid var(--color-border-subtle, #475569);
    font-size: 0.75rem;
    line-height: 1.4;
    overflow-x: auto;
    max-height: 10rem;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .muted {
    color: var(--color-text-muted, #94a3b8);
    font-style: italic;
  }

  .editor-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .editor-modal {
    background: var(--color-bg-elevated, #334155);
    border: 1px solid var(--color-border-default, #475569);
    border-radius: 8px;
    padding: 1.5rem;
    min-width: 320px;
    max-width: 90vw;
  }

  .editor-modal h3 {
    margin: 0 0 1rem 0;
    font-size: 1rem;
  }

  .editor-error {
    padding: 0.5rem 0.75rem;
    margin-bottom: 1rem;
    font-size: 0.8rem;
    color: #fecaca;
    background: #7f1d1d;
    border-radius: 4px;
  }

  .form-row {
    margin-bottom: 1rem;
  }

  fieldset.form-row {
    border: none;
    padding: 0;
    margin: 0;
  }

  .form-row legend {
    display: block;
    margin-bottom: 0.25rem;
    font-size: 0.8rem;
    color: var(--color-text-muted, #94a3b8);
  }

  .form-row label {
    display: block;
    margin-bottom: 0.25rem;
    font-size: 0.8rem;
    color: var(--color-text-muted, #94a3b8);
  }

  .form-row input[type="text"] {
    width: 100%;
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--color-border-default, #475569);
    border-radius: 4px;
    background: var(--color-bg-canvas, #1e293b);
    color: var(--color-text-primary, #f1f5f9);
    box-sizing: border-box;
  }

  .filter-set-list {
    max-height: 120px;
    overflow-y: auto;
    border: 1px solid var(--color-border-default, #475569);
    border-radius: 4px;
    padding: 0.5rem;
    background: var(--color-bg-canvas, #1e293b);
  }

  .camera-section {
    margin-bottom: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .camera-section .bcf-json {
    margin: 0;
  }

  .camera-capture-btn {
    margin-top: 0.25rem;
    align-self: flex-start;
  }

  .checkbox-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.25rem 0;
    cursor: pointer;
  }

  .checkbox-row input {
    cursor: pointer;
  }

  .editor-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
  }
</style>
