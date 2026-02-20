<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { page } from "$app/stores";
  import SearchFilterRow from "$lib/ui/SearchFilter.svelte";
  import {
    SEARCH_CHANNEL,
    type FilterSet,
    type SearchFilter,
    type SearchMessage,
    type SearchScope,
  } from "$lib/search/protocol";
  import {
    loadSearchFilters,
    loadSettings,
    saveSearchFilters,
  } from "$lib/state/persistence";
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

  let resultCount = $state(0);
  let totalCount = $state(0);

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

  function filterSetsToPlain(list: FilterSet[]): FilterSet[] {
    return list.map((fs) => ({
      id: fs.id,
      branchId: fs.branchId,
      name: fs.name,
      logic: fs.logic,
      filters: filtersToPlain(fs.filters),
      createdAt: fs.createdAt,
      updatedAt: fs.updatedAt,
    }));
  }

  // ---- Filter set browser state ----
  let searchQuery = $state("");
  let searchScope = $state<SearchScope>("branch");
  let browserFilterSets = $state<FilterSet[]>([]);
  let selectedSetIds = $state<Set<number>>(new Set());
  let combinationLogic = $state<"AND" | "OR">("AND");
  let appliedFilterSets = $state<FilterSet[]>([]);
  let appliedNameDrafts = $state<Record<number, string>>({});
  const appliedNameInputs: Record<number, HTMLInputElement | null> = {};
  let editingAppliedFilterKey = $state<string | null>(null);
  let editingAppliedFilterDraft = $state<SearchFilter | null>(null);
  let loadingBrowser = $state(false);
  let savingFilterSet = $state(false);

  // ---- BroadcastChannel ----
  let channel: BroadcastChannel | null = null;
  let initialLoadDone = $state(false);
  let branchContextRetryTimeout: ReturnType<typeof setTimeout> | null = null;
  let branchContextRetryInterval: ReturnType<typeof setInterval> | null = null;

  $effect(() => {
    if (!initialLoadDone) return;
    saveSearchFilters(filtersToPlain(filters));
  });

  async function loadFilterSets() {
    if (!branchId) return;
    loadingBrowser = true;
    try {
      const query = searchQuery.trim();
      if (query || searchScope !== "branch") {
        const vars: Record<string, unknown> = { query };
        if (searchScope === "branch") vars.branchId = branchId;
        else if (searchScope === "project") {
          if (projectId) vars.projectId = projectId;
          else vars.branchId = branchId;
        }
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
        const sets = data.filterSets ?? [];
        appliedFilterSets = sets;
        appliedNameDrafts = Object.fromEntries(
          sets.map((fs: FilterSet) => [fs.id, fs.name]),
        );
      } else {
        appliedFilterSets = [];
        appliedNameDrafts = {};
      }
    } catch (err) {
      console.error("Failed to load applied filter sets:", err);
      appliedFilterSets = [];
      appliedNameDrafts = {};
    }
  }

  function toggleSetSelection(id: number) {
    const next = new Set(selectedSetIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    selectedSetIds = next;
  }

  function toFilterInputs(list: SearchFilter[]) {
    return list.map((f) => ({
      mode: f.mode,
      ifcClass: f.ifcClass ?? null,
      attribute: f.attribute ?? null,
      value: f.value ?? null,
    }));
  }

  async function updateFilterSet(
    id: number,
    name: string,
    logic: "AND" | "OR",
    nextFilters: SearchFilter[],
  ) {
    await client
      .mutation(UPDATE_FILTER_SET_MUTATION, {
        id,
        name,
        logic,
        filters: toFilterInputs(nextFilters),
      })
      .toPromise();
    setAppliedName(id, name);
    await loadFilterSets();
    await loadApplied();
    channel?.postMessage({
      type: "apply-filter-sets",
      filterSets: filterSetsToPlain(appliedFilterSets),
      combinationLogic,
    } satisfies SearchMessage);
  }

  async function handleSaveFilterSet() {
    if (!branchId || !editorName.trim() || filters.length === 0) return;
    savingFilterSet = true;
    const trimmedName = editorName.trim();
    try {
      await client
        .mutation(CREATE_FILTER_SET_MUTATION, {
          branchId,
          name: trimmedName,
          logic: editorLogic,
          filters: toFilterInputs(filters),
        })
        .toPromise();
      await loadFilterSets();
      editorName = "";
      editorLogic = "AND";
      filters = [];
    } catch (err) {
      console.error("Failed to save filter set:", err);
    } finally {
      savingFilterSet = false;
    }
  }

  async function handleDeleteFilterSet(id: number) {
    try {
      await client.mutation(DELETE_FILTER_SET_MUTATION, { id }).toPromise();
      const next = new Set(selectedSetIds);
      next.delete(id);
      selectedSetIds = next;
      await loadFilterSets();
      await loadApplied();
      channel?.postMessage({
        type: "apply-filter-sets",
        filterSets: filterSetsToPlain(appliedFilterSets),
        combinationLogic,
      } satisfies SearchMessage);
    } catch (err) {
      console.error("Failed to delete filter set:", err);
    }
  }

  async function persistFilterSet(fs: FilterSet, nextFilters: SearchFilter[]) {
    const name = appliedNameDrafts[fs.id]?.trim() || fs.name;
    await updateFilterSet(fs.id, name, fs.logic, nextFilters);
  }

  function getAppliedName(fs: FilterSet): string {
    return appliedNameDrafts[fs.id] ?? fs.name;
  }

  function setAppliedName(id: number, value: string) {
    appliedNameDrafts = { ...appliedNameDrafts, [id]: value };
  }

  function loadFilterSetIntoEditor(fs: FilterSet) {
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

  async function handleUpdateAppliedFilterSet(fs: FilterSet) {
    const liveName = appliedNameInputs[fs.id]?.value ?? getAppliedName(fs);
    const name = liveName.trim();
    if (!name) {
      setAppliedName(fs.id, fs.name);
      return;
    }
    setAppliedName(fs.id, liveName);
    try {
      await updateFilterSet(fs.id, name, fs.logic, fs.filters);
    } catch (err) {
      console.error("Failed to update applied filter set:", err);
    }
  }

  function appliedFilterKey(
    fs: FilterSet,
    filter: SearchFilter,
    index: number,
  ): string {
    return `${fs.id}:${filter.id || index}`;
  }

  function beginEditAppliedFilter(
    fs: FilterSet,
    filter: SearchFilter,
    index: number,
  ) {
    editingAppliedFilterKey = appliedFilterKey(fs, filter, index);
    editingAppliedFilterDraft = { ...filter };
  }

  function cancelEditAppliedFilter() {
    console.log("cancelEditAppliedFilter");
    editingAppliedFilterKey = null;
    editingAppliedFilterDraft = null;
  }

  async function saveAppliedFilterEdit(fs: FilterSet, index: number) {
    const draft = editingAppliedFilterDraft;
    if (!draft) return;
    const nextFilters: SearchFilter[] = fs.filters.map((f, i) =>
      i === index ? { ...draft } : f,
    );
    try {
      await persistFilterSet(fs, nextFilters);
      cancelEditAppliedFilter();
    } catch (err) {
      console.error("Failed to update applied filter:", err);
    }
  }

  async function deleteAppliedFilter(fs: FilterSet, index: number) {
    const nextFilters = fs.filters.filter((_, i) => i !== index);
    if (nextFilters.length === 0) return;
    try {
      await persistFilterSet(fs, nextFilters);
      cancelEditAppliedFilter();
    } catch (err) {
      console.error("Failed to delete filter from set:", err);
    }
  }

  function focusEditorToAddFilter(fs: FilterSet) {
    loadFilterSetIntoEditor(fs);
    addFilter();
    requestAnimationFrame(() => {
      document
        .getElementById("filter-set-editor")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function clearEditor() {
    editorName = "";
    editorLogic = "AND";
    filters = [];
    resultCount = 0;
    totalCount = 0;
  }

  function resetFilterSetBrowserSection() {
    selectedSetIds = new Set();
    searchQuery = "";
    searchScope = "branch";
  }

  async function handleApplySelected() {
    if (!branchId) return;
    const mergedIds = new Set<number>([
      ...appliedFilterSets.map((fs) => fs.id),
      ...selectedSetIds,
    ]);
    const ids = [...mergedIds];
    try {
      await client
        .mutation(APPLY_FILTER_SETS_MUTATION, {
          branchId,
          filterSetIds: ids,
          combinationLogic,
        })
        .toPromise();
      await loadApplied();
      const applied = appliedFilterSets.length
        ? appliedFilterSets
        : browserFilterSets.filter((fs) => selectedSetIds.has(fs.id));
      channel?.postMessage({
        type: "apply-filter-sets",
        filterSets: filterSetsToPlain(applied),
        combinationLogic,
      } satisfies SearchMessage);
      resetFilterSetBrowserSection();
    } catch (err) {
      console.error("Failed to apply filter sets:", err);
    }
  }

  async function handleUnapplyFilterSet(filterSetId: number) {
    if (!branchId) return;
    const remainingIds = appliedFilterSets
      .filter((fs) => fs.id !== filterSetId)
      .map((fs) => fs.id);
    try {
      await client
        .mutation(APPLY_FILTER_SETS_MUTATION, {
          branchId,
          filterSetIds: remainingIds,
          combinationLogic,
        })
        .toPromise();
      await loadApplied();
      channel?.postMessage({
        type: "apply-filter-sets",
        filterSets: filterSetsToPlain(appliedFilterSets),
        combinationLogic,
      } satisfies SearchMessage);
    } catch (err) {
      console.error("Failed to unapply filter set:", err);
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
    // Restore branch/project from URL so filter sets load after refresh
    const urlBranch = $page.url.searchParams.get("branchId");
    const urlProject = $page.url.searchParams.get("projectId");
    if (urlBranch != null) {
      const bid = parseInt(urlBranch, 10);
      if (!Number.isNaN(bid)) branchId = bid;
    }
    if (urlProject != null) {
      const pid = parseInt(urlProject, 10);
      if (!Number.isNaN(pid)) projectId = pid;
    }
    // Fallback: recover branch/project from persisted app settings
    if (branchId == null) {
      const settings = loadSettings();
      if (settings?.activeBranchId != null) branchId = settings.activeBranchId;
      if (settings?.activeProjectId != null)
        projectId = settings.activeProjectId;
    }
    if (branchId != null) {
      loadFilterSets();
      loadApplied();
    }
    channel = new BroadcastChannel(SEARCH_CHANNEL);
    channel.onmessage = (e: MessageEvent<SearchMessage>) => {
      if (e.data.type === "filter-result-count") {
        resultCount = e.data.count;
        totalCount = e.data.total;
      } else if (e.data.type === "branch-context") {
        branchId = e.data.branchId;
        projectId = e.data.projectId;
        if (branchContextRetryInterval != null) {
          clearInterval(branchContextRetryInterval);
          branchContextRetryInterval = null;
        }
        if (branchId != null || projectId != null) {
          const params = new URLSearchParams($page.url.searchParams);
          if (branchId != null) params.set("branchId", String(branchId));
          if (projectId != null) params.set("projectId", String(projectId));
          window.history.replaceState(
            null,
            "",
            `${$page.url.pathname}?${params.toString()}`,
          );
        }
        loadFilterSets();
        loadApplied();
      }
    };
    channel.postMessage({
      type: "request-branch-context",
    } satisfies SearchMessage);
    // Re-request context after a short delay in case main page wasn't ready (e.g. after refresh)
    branchContextRetryTimeout = setTimeout(() => {
      if (branchId == null)
        channel?.postMessage({
          type: "request-branch-context",
        } satisfies SearchMessage);
      branchContextRetryTimeout = null;
    }, 1500);
    if (branchId == null) {
      let attempts = 0;
      branchContextRetryInterval = setInterval(() => {
        if (branchId != null || attempts >= 8) {
          if (branchContextRetryInterval != null) {
            clearInterval(branchContextRetryInterval);
            branchContextRetryInterval = null;
          }
          return;
        }
        channel?.postMessage({
          type: "request-branch-context",
        } satisfies SearchMessage);
        attempts += 1;
      }, 1000);
    }
  });

  onDestroy(() => {
    channel?.close();
    clearTimeout(searchTimeout);
    if (branchContextRetryTimeout != null)
      clearTimeout(branchContextRetryTimeout);
    if (branchContextRetryInterval != null)
      clearInterval(branchContextRetryInterval);
  });
</script>

<div class="search-page">
  <header class="page-header">
    <h2>Search &amp; Filter</h2>
    <span class="result-count">{resultCount} / {totalCount} elements</span>
  </header>

  <!-- ═══════ Filter Set Browser ═══════ -->
  <section class="section">
    <div class="section-header">
      <h3>Filter Sets</h3>
      {#if branchId}
        <div class="scope-selector">
          <select class="scope-select" bind:value={searchScope}>
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
  <section class="section" id="filter-set-editor">
    <div class="section-header">
      <h3>New Filter Set</h3>
    </div>

    {#if !branchId}
      <p class="empty-hint">
        Open a project from the main view to save filter sets.
      </p>
    {/if}

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
      <div class="editor-actions">
        <button class="btn btn-secondary" onclick={clearAll}>Clear All</button>
        <button
          class="btn btn-secondary"
          disabled={filters.length === 0}
          onclick={handleApplyAdHoc}
        >
          Apply Ad-hoc
        </button>
        <button
          class="btn btn-primary"
          disabled={!branchId ||
            !editorName.trim() ||
            filters.length === 0 ||
            savingFilterSet}
          onclick={handleSaveFilterSet}
        >
          Save Filter Set
        </button>
      </div>
    </div>
  </section>

  <!-- ═══════ Applied to view (below editor) ═══════ -->
  <section class="section section--applied" id="applied-panel">
    <div class="section-header">
      <h3>Applied to view</h3>
      {#if appliedFilterSets.length > 1}
        <span class="applied-logic">{combinationLogic}</span>
      {/if}
    </div>
    <div class="applied-list">
      {#if !branchId}
        <p class="empty-hint">Open a project to see applied filter sets.</p>
      {:else if appliedFilterSets.length === 0}
        <p class="empty-hint">
          No filter sets applied. Select sets above and click Apply.
        </p>
      {:else}
        {#each appliedFilterSets as fs (fs.id)}
          <div class="applied-item">
            <div class="editor-row applied-editor-row">
              <input
                class="editor-name applied-name"
                type="text"
                value={getAppliedName(fs)}
                bind:this={appliedNameInputs[fs.id]}
                oninput={(e) => setAppliedName(fs.id, e.currentTarget.value)}
                onkeydown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void handleUpdateAppliedFilterSet(fs);
                  }
                }}
              />
              <div class="logic-toggle">
                <button
                  class="mode-btn"
                  class:active={fs.logic === "AND"}
                  disabled>AND</button
                >
                <button
                  class="mode-btn"
                  class:active={fs.logic === "OR"}
                  disabled>OR</button
                >
              </div>
            </div>
            <div class="filter-list applied-filter-list">
              {#if fs.filters.length === 0}
                <p class="empty-hint">No filters in this set.</p>
              {:else}
                {#each fs.filters as f, idx}
                  {@const lineKey = appliedFilterKey(fs, f, idx)}
                  {#if editingAppliedFilterKey === lineKey && editingAppliedFilterDraft}
                    <div class="applied-filter-edit">
                      <SearchFilterRow
                        filter={editingAppliedFilterDraft}
                        onupdate={(patch) =>
                          (editingAppliedFilterDraft = {
                            ...editingAppliedFilterDraft!,
                            ...patch,
                          })}
                        onremove={() => deleteAppliedFilter(fs, idx)}
                      />
                      <div class="editor-actions applied-filter-edit-actions">
                        <button
                          type="button"
                          class="btn btn-secondary"
                          onclick={cancelEditAppliedFilter}
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          class="btn btn-primary"
                          onclick={() => saveAppliedFilterEdit(fs, idx)}
                        >
                          Save
                        </button>
                      </div>
                    </div>
                  {:else}
                    <div class="applied-filter-line">
                      {#if f.mode === "class"}
                        <span class="applied-filter-mode">Class</span>
                        <span class="applied-filter-value"
                          >{f.ifcClass ?? "—"}</span
                        >
                      {:else}
                        <span class="applied-filter-mode">Attr</span>
                        <span class="applied-filter-value"
                          >{f.attribute ?? "—"} = {f.value ?? "—"}</span
                        >
                      {/if}
                      <div class="applied-filter-actions">
                        <button
                          type="button"
                          class="icon-btn"
                          aria-label="Edit filter"
                          onclick={() => beginEditAppliedFilter(fs, f, idx)}
                        >
                          <svg
                            width="14"
                            height="14"
                            viewBox="0 0 16 16"
                            fill="none"
                          >
                            <path
                              d="M3 11.75V13h1.25L11.5 5.75l-1.25-1.25L3 11.75ZM12.2 5.05l.75-.75a.884.884 0 0 0 0-1.25l-.5-.5a.884.884 0 0 0-1.25 0l-.75.75 1.75 1.75Z"
                              fill="currentColor"
                            />
                          </svg>
                        </button>
                        <button
                          type="button"
                          class="icon-btn icon-btn-danger"
                          aria-label="Delete filter"
                          disabled={fs.filters.length <= 1}
                          onclick={() => deleteAppliedFilter(fs, idx)}
                        >
                          <svg
                            width="14"
                            height="14"
                            viewBox="0 0 16 16"
                            fill="none"
                          >
                            <path
                              d="M4 4L12 12M12 4L4 12"
                              stroke="currentColor"
                              stroke-width="1.5"
                              stroke-linecap="round"
                            />
                          </svg>
                        </button>
                      </div>
                    </div>
                  {/if}
                {/each}
              {/if}
            </div>
            <div class="editor-toolbar applied-toolbar">
              <button
                type="button"
                class="add-btn"
                onclick={() => focusEditorToAddFilter(fs)}
              >
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
              <div class="editor-actions">
                <button
                  type="button"
                  class="btn btn-secondary"
                  onclick={() => handleUpdateAppliedFilterSet(fs)}
                >
                  Update
                </button>
                <button
                  type="button"
                  class="btn btn-secondary"
                  onclick={() => handleUnapplyFilterSet(fs.id)}
                >
                  Unapply
                </button>
                <button
                  type="button"
                  class="btn btn-danger"
                  onclick={() => handleDeleteFilterSet(fs.id)}
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        {/each}
      {/if}
    </div>
  </section>
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

  /* ---- Applied filter sets panel ---- */

  .section--applied {
    border: none;
    background: transparent;
    padding: 0;
  }

  .section--applied .section-header {
    margin-bottom: 0.4rem;
  }

  .applied-logic {
    font-size: 0.7rem;
    color: #888;
    font-weight: 500;
  }

  .applied-list {
    height: fit-content;
  }

  .applied-item {
    border-radius: 0.45rem;
    background: rgba(255, 255, 255, 0.015);
    border: 1px solid rgba(255, 255, 255, 0.06);
    margin-bottom: 0.55rem;
    font-size: 0.78rem;
    outline: none;
    transition:
      border-color 0.15s,
      background 0.15s;
    padding: 0.55rem 0.65rem;
  }

  .applied-item:hover {
    border-color: rgba(255, 136, 102, 0.24);
    background: rgba(255, 136, 102, 0.03);
  }

  .applied-item:last-child {
    margin-bottom: 0;
  }

  .applied-editor-row {
    margin-bottom: 0.45rem;
  }

  .applied-name {
    color: #ddd;
    cursor: text;
  }

  .applied-name:focus {
    border-color: rgba(255, 255, 255, 0.1);
  }

  .applied-filter-list {
    margin-bottom: 0.5rem;
  }

  .applied-filter-line {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.75rem;
    padding: 0.28rem 0.35rem;
    border-radius: 0.28rem;
    color: #bbb;
    background: rgba(255, 255, 255, 0.015);
    border: 1px solid rgba(255, 255, 255, 0.05);
    margin-bottom: 0.3rem;
  }

  .applied-filter-mode {
    flex-shrink: 0;
    color: #888;
    font-size: 0.7rem;
    text-transform: uppercase;
    width: 2.5rem;
  }

  .applied-filter-value {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
    flex: 1;
  }

  .applied-filter-actions {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 0.2rem;
    flex-shrink: 0;
  }

  .icon-btn {
    width: 1.5rem;
    height: 1.5rem;
    border-radius: 0.28rem;
    border: 1px solid rgba(255, 255, 255, 0.12);
    background: rgba(255, 255, 255, 0.03);
    color: #999;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition:
      color 0.15s,
      border-color 0.15s,
      background 0.15s;
  }

  .icon-btn:hover:not(:disabled) {
    color: #ddd;
    border-color: rgba(255, 255, 255, 0.22);
    background: rgba(255, 255, 255, 0.07);
  }

  .icon-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .icon-btn-danger:hover:not(:disabled) {
    color: #ff6b6b;
    border-color: rgba(255, 107, 107, 0.4);
    background: rgba(255, 107, 107, 0.09);
  }

  .applied-filter-edit {
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.35rem;
    background: rgba(255, 255, 255, 0.02);
    padding: 0.15rem 0.45rem 0.45rem;
    margin-bottom: 0.3rem;
  }

  .applied-filter-edit-actions {
    justify-content: flex-end;
  }

  .applied-toolbar {
    margin-top: 0;
    padding-top: 0.45rem;
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
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-top: 0.25rem;
  }

  .editor-actions {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    justify-content: flex-end;
    flex-wrap: wrap;
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

  .btn-danger {
    background: rgba(255, 107, 107, 0.16);
    color: #ff8f8f;
  }

  .btn-danger:hover:not(:disabled) {
    background: rgba(255, 107, 107, 0.3);
    color: #ffb1b1;
  }
</style>
