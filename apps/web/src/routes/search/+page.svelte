<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import SearchFilterRow from "$lib/ui/SearchFilter.svelte";
  import {
    SEARCH_CHANNEL,
    type FilterSet,
    type SearchFilter,
    type SearchMessage,
    type SearchScope,
  } from "$lib/search/protocol";
  import { loadSearchFilters, saveSearchFilters } from "$lib/state/persistence";
  import {
    client,
    FILTER_SETS_QUERY,
    SEARCH_FILTER_SETS_QUERY,
    APPLIED_FILTER_SETS_QUERY,
    CREATE_FILTER_SET_MUTATION,
    UPDATE_FILTER_SET_MUTATION,
    DELETE_FILTER_SET_MUTATION,
    APPLY_FILTER_SETS_MUTATION,
  } from "$lib/api/client";

  // ---- Branch context (received from main window) ----
  let branchId = $state<number | null>(null);
  let projectId = $state<number | null>(null);

  // ---- Filter editor state ----
  let filters = $state<SearchFilter[]>([]);
  let editorName = $state("");
  let editorLogic = $state<"AND" | "OR">("AND");
  let editingFilterSetId = $state<number | null>(null);

  let resultCount = $state<number | null>(null);
  let totalCount = $state<number | null>(null);

  let nextId = 0;
  function genId(): string {
    return `f-${nextId++}`;
  }

  function initNextIdFromFilters(list: SearchFilter[]) {
    const max = list.reduce((acc, f) => {
      const n = parseInt(f.id.replace(/^f-/, ""), 10);
      return Number.isNaN(n) ? acc : Math.max(acc, n + 1);
    }, 0);
    nextId = max;
  }

  function addFilter() {
    filters = [...filters, { id: genId(), mode: "class" }];
  }

  function removeFilter(id: string) {
    filters = filters.filter((f) => f.id !== id);
  }

  function updateFilter(id: string, patch: Partial<SearchFilter>) {
    filters = filters.map((f) => (f.id === id ? { ...f, ...patch } : f));
  }

  function filtersToPlain(list: SearchFilter[]): SearchFilter[] {
    return list.map((f) => ({
      id: f.id,
      mode: f.mode,
      ifcClass: f.ifcClass,
      attribute: f.attribute,
      value: f.value,
    }));
  }

  // ---- Filter set browser state ----
  let searchQuery = $state("");
  let searchScope = $state<SearchScope>("branch");
  let browserFilterSets = $state<FilterSet[]>([]);
  let selectedSetIds = $state<Set<number>>(new Set());
  let combinationLogic = $state<"AND" | "OR">("AND");
  let loadingBrowser = $state(false);
  let savingFilterSet = $state(false);

  // ---- BroadcastChannel ----
  let channel: BroadcastChannel | null = null;
  let initialLoadDone = $state(false);

  $effect(() => {
    if (!initialLoadDone) return;
    saveSearchFilters(filtersToPlain(filters));
  });

  async function loadFilterSets() {
    if (!branchId) return;
    loadingBrowser = true;
    try {
      if (searchQuery.trim()) {
        const vars: Record<string, unknown> = { query: searchQuery };
        if (searchScope === "branch") vars.branchId = branchId;
        else if (searchScope === "project" && projectId)
          vars.projectId = projectId;
        const result = await client
          .query(SEARCH_FILTER_SETS_QUERY, vars)
          .toPromise();
        browserFilterSets = result.data?.searchFilterSets ?? [];
      } else {
        const result = await client
          .query(FILTER_SETS_QUERY, { branchId })
          .toPromise();
        browserFilterSets = result.data?.filterSets ?? [];
      }
    } catch (err) {
      console.error("Failed to load filter sets:", err);
    } finally {
      loadingBrowser = false;
    }
  }

  async function loadApplied() {
    if (!branchId) return;
    try {
      const result = await client
        .query(APPLIED_FILTER_SETS_QUERY, { branchId })
        .toPromise();
      const data = result.data?.appliedFilterSets;
      if (data) {
        combinationLogic = data.combinationLogic ?? "AND";
        selectedSetIds = new Set(
          (data.filterSets ?? []).map((fs: FilterSet) => fs.id),
        );
      }
    } catch (err) {
      console.error("Failed to load applied filter sets:", err);
    }
  }

  function toggleSetSelection(id: number) {
    const next = new Set(selectedSetIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    selectedSetIds = next;
  }

  async function handleSaveFilterSet() {
    if (!branchId || !editorName.trim() || filters.length === 0) return;
    savingFilterSet = true;
    try {
      const filterInputs = filters.map((f) => ({
        mode: f.mode,
        ifcClass: f.ifcClass ?? null,
        attribute: f.attribute ?? null,
        value: f.value ?? null,
      }));
      if (editingFilterSetId) {
        await client
          .mutation(UPDATE_FILTER_SET_MUTATION, {
            id: editingFilterSetId,
            name: editorName,
            logic: editorLogic,
            filters: filterInputs,
          })
          .toPromise();
      } else {
        await client
          .mutation(CREATE_FILTER_SET_MUTATION, {
            branchId,
            name: editorName,
            logic: editorLogic,
            filters: filterInputs,
          })
          .toPromise();
      }
      editingFilterSetId = null;
      editorName = "";
      editorLogic = "AND";
      filters = [];
      await loadFilterSets();
    } catch (err) {
      console.error("Failed to save filter set:", err);
    } finally {
      savingFilterSet = false;
    }
  }

  async function handleDeleteFilterSet(id: number) {
    try {
      await client
        .mutation(DELETE_FILTER_SET_MUTATION, { id })
        .toPromise();
      const next = new Set(selectedSetIds);
      next.delete(id);
      selectedSetIds = next;
      await loadFilterSets();
    } catch (err) {
      console.error("Failed to delete filter set:", err);
    }
  }

  function editFilterSet(fs: FilterSet) {
    editingFilterSetId = fs.id;
    editorName = fs.name;
    editorLogic = fs.logic;
    filters = fs.filters.map((f, i) => ({
      id: `f-${i}`,
      mode: f.mode,
      ifcClass: f.ifcClass ?? undefined,
      attribute: f.attribute ?? undefined,
      value: f.value ?? undefined,
    }));
    initNextIdFromFilters(filters);
  }

  function clearEditor() {
    editingFilterSetId = null;
    editorName = "";
    editorLogic = "AND";
    filters = [];
    resultCount = null;
    totalCount = null;
  }

  async function handleApplySelected() {
    if (!branchId) return;
    const ids = [...selectedSetIds];
    try {
      await client
        .mutation(APPLY_FILTER_SETS_MUTATION, {
          branchId,
          filterSetIds: ids,
          combinationLogic,
        })
        .toPromise();
      const applied = browserFilterSets.filter((fs) =>
        selectedSetIds.has(fs.id),
      );
      channel?.postMessage({
        type: "apply-filter-sets",
        filterSets: applied,
        combinationLogic,
      } satisfies SearchMessage);
    } catch (err) {
      console.error("Failed to apply filter sets:", err);
    }
  }

  function handleApplyAdHoc() {
    channel?.postMessage({
      type: "apply-filters",
      filters: filtersToPlain(filters),
    } satisfies SearchMessage);
  }

  function clearAll() {
    clearEditor();
    selectedSetIds = new Set();
    channel?.postMessage({
      type: "apply-filters",
      filters: [],
    } satisfies SearchMessage);
  }

  // ---- Debounced search ----
  let searchTimeout: ReturnType<typeof setTimeout>;
  $effect(() => {
    // Re-run search when query or scope changes
    void searchQuery;
    void searchScope;
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      if (branchId) loadFilterSets();
    }, 250);
  });

  onMount(() => {
    const saved = loadSearchFilters();
    if (saved.length > 0) {
      filters = saved;
      initNextIdFromFilters(saved);
    }
    initialLoadDone = true;
    channel = new BroadcastChannel(SEARCH_CHANNEL);
    channel.onmessage = (e: MessageEvent<SearchMessage>) => {
      if (e.data.type === "filter-result-count") {
        resultCount = e.data.count;
        totalCount = e.data.total;
      } else if (e.data.type === "branch-context") {
        branchId = e.data.branchId;
        projectId = e.data.projectId;
        loadFilterSets();
        loadApplied();
      }
    };
  });

  onDestroy(() => {
    channel?.close();
    clearTimeout(searchTimeout);
  });
</script>

<div class="search-page">
  <header class="page-header">
    <h2>Search &amp; Filter</h2>
    {#if resultCount !== null && totalCount !== null}
      <span class="result-count">{resultCount} / {totalCount} elements</span>
    {/if}
  </header>

  <!-- ═══════ Filter Set Browser ═══════ -->
  <section class="section">
    <div class="section-header">
      <h3>Filter Sets</h3>
      {#if branchId}
        <div class="scope-selector">
          <select
            class="scope-select"
            bind:value={searchScope}
          >
            <option value="branch">This Branch</option>
            <option value="project">This Project</option>
            <option value="all">All</option>
          </select>
        </div>
      {/if}
    </div>

    <input
      class="search-input"
      type="text"
      placeholder="Search filter sets…"
      bind:value={searchQuery}
    />

    <div class="set-list">
      {#if !branchId}
        <p class="empty-hint">Open a project to browse filter sets.</p>
      {:else if loadingBrowser}
        <p class="empty-hint">Loading…</p>
      {:else if browserFilterSets.length === 0}
        <p class="empty-hint">No filter sets found.</p>
      {:else}
        {#each browserFilterSets as fs (fs.id)}
          <div class="set-row" class:selected={selectedSetIds.has(fs.id)}>
            <label class="set-checkbox">
              <input
                type="checkbox"
                checked={selectedSetIds.has(fs.id)}
                onchange={() => toggleSetSelection(fs.id)}
              />
            </label>
            <div class="set-info">
              <span class="set-name">{fs.name}</span>
              <span class="set-meta"
                >{fs.logic} · {fs.filters.length} filter{fs.filters.length === 1
                  ? ""
                  : "s"}</span
              >
            </div>
            <div class="set-actions">
              <button
                class="icon-btn"
                title="Edit"
                onclick={() => editFilterSet(fs)}
              >
                <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M11.5 1.5l3 3L5 14H2v-3L11.5 1.5z"
                    stroke="currentColor"
                    stroke-width="1.3"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </button>
              <button
                class="icon-btn icon-btn--danger"
                title="Delete"
                onclick={() => handleDeleteFilterSet(fs.id)}
              >
                <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M4 4L12 12M12 4L4 12"
                    stroke="currentColor"
                    stroke-width="1.3"
                    stroke-linecap="round"
                  />
                </svg>
              </button>
            </div>
          </div>
        {/each}
      {/if}
    </div>

    {#if selectedSetIds.size > 0}
      <div class="apply-bar">
        <div class="logic-toggle">
          <span class="logic-label">Combine:</span>
          <button
            class="mode-btn"
            class:active={combinationLogic === "AND"}
            onclick={() => (combinationLogic = "AND")}>AND</button
          >
          <button
            class="mode-btn"
            class:active={combinationLogic === "OR"}
            onclick={() => (combinationLogic = "OR")}>OR</button
          >
        </div>
        <button class="btn btn-primary" onclick={handleApplySelected}>
          Apply {selectedSetIds.size} Set{selectedSetIds.size === 1 ? "" : "s"}
        </button>
      </div>
    {/if}
  </section>

  <!-- ═══════ Filter Set Editor ═══════ -->
  <section class="section">
    <div class="section-header">
      <h3>
        {editingFilterSetId ? "Edit Filter Set" : "New Filter Set"}
      </h3>
    </div>

    <div class="editor-row">
      <input
        class="editor-name"
        type="text"
        placeholder="Filter set name…"
        bind:value={editorName}
      />
      <div class="logic-toggle">
        <button
          class="mode-btn"
          class:active={editorLogic === "AND"}
          onclick={() => (editorLogic = "AND")}>AND</button
        >
        <button
          class="mode-btn"
          class:active={editorLogic === "OR"}
          onclick={() => (editorLogic = "OR")}>OR</button
        >
      </div>
    </div>

    <div class="filter-list">
      {#if filters.length === 0}
        <p class="empty-hint">No filters yet. Add one to start.</p>
      {/if}

      {#each filters as filter (filter.id)}
        <SearchFilterRow
          {filter}
          onupdate={(patch) => updateFilter(filter.id, patch)}
          onremove={() => removeFilter(filter.id)}
        />
      {/each}
    </div>

    <div class="editor-toolbar">
      <button class="add-btn" onclick={addFilter}>
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
          <path
            d="M8 3v10M3 8h10"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
          />
        </svg>
        Add Filter
      </button>
    </div>
  </section>

  <!-- ═══════ Footer ═══════ -->
  <footer class="page-footer">
    <button class="btn btn-secondary" onclick={clearAll}> Clear All </button>
    <button
      class="btn btn-secondary"
      disabled={filters.length === 0}
      onclick={handleApplyAdHoc}
    >
      Apply Ad-hoc
    </button>
    <button
      class="btn btn-primary"
      disabled={!editorName.trim() || filters.length === 0 || savingFilterSet}
      onclick={handleSaveFilterSet}
    >
      {editingFilterSetId ? "Update" : "Save"} Filter Set
    </button>
  </footer>
</div>

<style>
  :global(html, body) {
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
  }

  .search-page {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    padding: 1rem;
    background: #12121e;
    color: #e0e0e0;
    font-family:
      system-ui,
      -apple-system,
      sans-serif;
    box-sizing: border-box;
  }

  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.75rem;
  }

  .page-header h2 {
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
    color: #e0e0e0;
  }

  .result-count {
    font-size: 0.78rem;
    color: #ff8866;
    font-variant-numeric: tabular-nums;
  }

  /* ---- Sections ---- */

  .section {
    margin-bottom: 1rem;
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 0.5rem;
    padding: 0.75rem;
    background: rgba(255, 255, 255, 0.02);
  }

  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.5rem;
  }

  .section-header h3 {
    margin: 0;
    font-size: 0.85rem;
    font-weight: 600;
    color: #ccc;
  }

  /* ---- Search input ---- */

  .search-input {
    width: 100%;
    box-sizing: border-box;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.35rem;
    color: #ddd;
    padding: 0.4rem 0.55rem;
    font-size: 0.78rem;
    outline: none;
    margin-bottom: 0.5rem;
  }

  .search-input:focus {
    border-color: rgba(255, 136, 102, 0.4);
  }

  .search-input::placeholder {
    color: #555;
  }

  /* ---- Scope selector ---- */

  .scope-selector {
    flex-shrink: 0;
  }

  .scope-select {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.3rem;
    color: #aaa;
    padding: 0.2rem 0.4rem;
    font-size: 0.7rem;
    cursor: pointer;
    outline: none;
  }

  .scope-select option {
    background: #1e1e30;
    color: #ddd;
  }

  /* ---- Filter set list ---- */

  .set-list {
    max-height: 180px;
    overflow-y: auto;
  }

  .set-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.4rem;
    border-radius: 0.3rem;
    transition: background 0.12s;
  }

  .set-row:hover {
    background: rgba(255, 255, 255, 0.04);
  }

  .set-row.selected {
    background: rgba(255, 136, 102, 0.08);
  }

  .set-checkbox input {
    accent-color: #ff8866;
    cursor: pointer;
  }

  .set-info {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 0;
  }

  .set-name {
    font-size: 0.8rem;
    color: #ddd;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .set-meta {
    font-size: 0.68rem;
    color: #666;
  }

  .set-actions {
    display: flex;
    gap: 0.2rem;
    flex-shrink: 0;
  }

  .icon-btn {
    background: none;
    border: none;
    color: #666;
    cursor: pointer;
    padding: 0.2rem;
    border-radius: 0.2rem;
    display: flex;
    align-items: center;
    transition: color 0.12s;
  }

  .icon-btn:hover {
    color: #ff8866;
  }

  .icon-btn--danger:hover {
    color: #ff6b6b;
  }

  /* ---- Apply bar ---- */

  .apply-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }

  /* ---- Logic toggle (shared) ---- */

  .logic-toggle {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }

  .logic-label {
    font-size: 0.7rem;
    color: #888;
    margin-right: 0.15rem;
  }

  .mode-btn {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.25rem;
    color: #888;
    padding: 0.2rem 0.5rem;
    font-size: 0.68rem;
    cursor: pointer;
    transition:
      background 0.15s,
      color 0.15s;
  }

  .mode-btn:hover {
    color: #ccc;
  }

  .mode-btn.active {
    background: rgba(255, 136, 102, 0.18);
    color: #ff8866;
    border-color: rgba(255, 136, 102, 0.3);
  }

  /* ---- Editor ---- */

  .editor-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin-bottom: 0.5rem;
  }

  .editor-name {
    flex: 1;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.35rem;
    color: #ddd;
    padding: 0.4rem 0.55rem;
    font-size: 0.78rem;
    outline: none;
  }

  .editor-name:focus {
    border-color: rgba(255, 136, 102, 0.4);
  }

  .editor-name::placeholder {
    color: #555;
  }

  .filter-list {
    overflow-y: auto;
    max-height: 220px;
    min-height: 36px;
  }

  .editor-toolbar {
    margin-top: 0.25rem;
  }

  .add-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    background: rgba(255, 255, 255, 0.04);
    border: 1px dashed rgba(255, 255, 255, 0.15);
    border-radius: 0.35rem;
    color: #888;
    padding: 0.35rem 0.7rem;
    font-size: 0.78rem;
    cursor: pointer;
    transition:
      background 0.15s,
      color 0.15s;
  }

  .add-btn:hover {
    background: rgba(255, 136, 102, 0.1);
    color: #ff8866;
    border-color: rgba(255, 136, 102, 0.3);
  }

  .empty-hint {
    margin: 0;
    padding: 0.75rem 0;
    text-align: center;
    font-size: 0.78rem;
    color: #555;
  }

  /* ---- Footer ---- */

  .page-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: auto;
    padding-top: 0.75rem;
  }

  .btn {
    padding: 0.45rem 1rem;
    font-size: 0.78rem;
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
</style>
