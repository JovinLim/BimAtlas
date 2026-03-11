<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { page } from "$app/stores";
  import SearchFilterRow from "$lib/ui/SearchFilter.svelte";
  import ColorPicker from "$lib/ui/ColorPicker.svelte";
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
    IFC_PRODUCT_TREE_QUERY,
  } from "$lib/api/client";
  import { setProductTreeFromApi } from "$lib/ifc/schema";

  // ---- Branch context (received from main window) ----
  let branchId = $state<string | null>(null);
  let projectId = $state<string | null>(null);

  // ---- Filter editor state ----
  let filterSetEditorOpen = $state(false);
  let filters = $state<SearchFilter[]>([]);
  let editorName = $state("");
  let editorLogic = $state<"AND" | "OR">("AND");

  let resultCount = $state(0);
  let totalCount = $state(0);
  let filterGuideOpen = $state(false);
  let filterSetColorsEnabled = $state(false);
  let filterSetsSectionCollapsed = $state(false);
  let editorColor = $state('#334155');
  let scopeDropdownOpen = $state(false);
  let scopeSelectorEl: HTMLDivElement | undefined = $state(undefined);

  const SCOPE_OPTIONS: { value: SearchScope; label: string }[] = [
    { value: "branch", label: "This Branch" },
    { value: "project", label: "This Project" },
    { value: "all", label: "All" },
  ];

  $effect(() => {
    if (!scopeDropdownOpen) return;
    function handleClick(e: MouseEvent) {
      const target = e.target as Node;
      if (scopeSelectorEl?.contains(target)) return;
      scopeDropdownOpen = false;
    }
    document.addEventListener("click", handleClick, true);
    return () => document.removeEventListener("click", handleClick, true);
  });

  $effect(() => {
    if (filterSetsSectionCollapsed) scopeDropdownOpen = false;
  });

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
      relation: f.relation,
      operator: f.operator,
      valueType: f.valueType,
    }));
  }

  function filterSetsToPlain(list: FilterSet[]): FilterSet[] {
    return list.map((fs) => ({
      id: fs.id,
      branchId: fs.branchId,
      name: fs.name,
      logic: fs.logic,
      filters: filtersToPlain(fs.filters),
      color: fs.color,
      createdAt: fs.createdAt,
      updatedAt: fs.updatedAt,
    }));
  }

  // ---- Filter set browser state ----
  let searchQuery = $state("");
  let searchScope = $state<SearchScope>("project");
  let browserFilterSets = $state<FilterSet[]>([]);
  let selectedSetIds = $state<Set<string>>(new Set());
  let combinationLogic = $state<"AND" | "OR">("OR");
  let appliedFilterSets = $state<FilterSet[]>([]);
  let collapsedAppliedIds = $state<Set<string>>(new Set());
  let appliedNameDrafts = $state<Record<string, string>>({});
  const appliedNameInputs: Record<string, HTMLInputElement | null> = {};
  let editingAppliedFilterKey = $state<string | null>(null);
  let editingAppliedFilterDraft = $state<SearchFilter | null>(null);

  function toggleAppliedItem(id: string) {
    const next = new Set(collapsedAppliedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    collapsedAppliedIds = next;
  }

  let lastAppliedSetIds = new Set<string>();
  $effect(() => {
    const sets = appliedFilterSets;
    if (sets.length === 0) {
      lastAppliedSetIds = new Set<string>();
      return;
    }
    const newIds = new Set(sets.map((fs) => fs.id));
    const idsChanged =
      lastAppliedSetIds.size !== newIds.size ||
      [...newIds].some((id) => !lastAppliedSetIds.has(id));
    if (idsChanged) {
      collapsedAppliedIds = new Set(newIds);
      lastAppliedSetIds = new Set(newIds);
    }
  });

  let loadingBrowser = $state(false);
  let savingFilterSet = $state(false);

  // ---- BroadcastChannel ----
  let channel: BroadcastChannel | null = null;
  let initialLoadDone = $state(false);
  let branchContextRetryTimeout: ReturnType<typeof setTimeout> | null = null;
  let branchContextRetryInterval: ReturnType<typeof setInterval> | null = null;
  let productTreeKey = $state<string | null>(null);

  $effect(() => {
    if (!initialLoadDone) return;
    saveSearchFilters(filtersToPlain(filters));
  });

  async function loadFilterSets(forceNetwork = false) {
    if (!branchId) return;
    loadingBrowser = true;
    const context = forceNetwork ? { requestPolicy: "network-only" as const } : undefined;
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
          .query(SEARCH_FILTER_SETS_QUERY, vars, context)
          .toPromise();
        browserFilterSets = result.data?.searchFilterSets ?? [];
      } else {
        const result = await client
          .query(FILTER_SETS_QUERY, { branchId }, context)
          .toPromise();
        browserFilterSets = result.data?.filterSets ?? [];
      }
    } catch (err) {
      console.error("Failed to load filter sets:", err);
    } finally {
      loadingBrowser = false;
    }
  }

  async function ensureProductTreeForBranch(branchId: string) {
    const key = branchId;
    if (productTreeKey === key) return;
    try {
      const result = await client
        .query(IFC_PRODUCT_TREE_QUERY, { branchId, revision: null })
        .toPromise();
      setProductTreeFromApi(result.data?.ifcProductTree ?? null);
      productTreeKey = key;
    } catch (err) {
      console.warn("Failed to load IFC product tree in search popup:", err);
      setProductTreeFromApi(null);
      productTreeKey = key;
    }
  }

  async function loadApplied(forceNetwork = false) {
    if (!branchId) return;
    const context = forceNetwork ? { requestPolicy: "network-only" as const } : undefined;
    try {
      const result = await client
        .query(APPLIED_FILTER_SETS_QUERY, { branchId }, context)
        .toPromise();
      const data = result.data?.appliedFilterSets;
      if (data) {
        const sets = data.filterSets ?? [];
        appliedFilterSets = sets;
        combinationLogic = "OR";
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

  function toggleSetSelection(id: string) {
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
      relation: f.relation ?? null,
      operator: f.operator ?? null,
      valueType: f.valueType ?? null,
    }));
  }

  async function updateFilterSet(
    id: string,
    name: string,
    logic: "AND" | "OR",
    nextFilters: SearchFilter[],
    color?: string,
  ) {
    const vars: Record<string, unknown> = {
      id,
      name,
      logic,
      filters: toFilterInputs(nextFilters),
    };
    if (color !== undefined) vars.color = color;
    await client
      .mutation(UPDATE_FILTER_SET_MUTATION, vars)
      .toPromise();
    setAppliedName(id, name);
    appliedFilterSets = appliedFilterSets.map((fs) =>
      fs.id === id
        ? { ...fs, name, logic, filters: nextFilters, ...(color !== undefined ? { color } : {}) }
        : fs,
    );
    await loadFilterSets();
    channel?.postMessage({
      type: "apply-filter-sets",
      filterSets: filterSetsToPlain(appliedFilterSets),
      combinationLogic,
    } satisfies SearchMessage);
  }

  async function handleColorChange(fs: FilterSet, newColor: string) {
    await client
      .mutation(UPDATE_FILTER_SET_MUTATION, { id: fs.id, color: newColor })
      .toPromise();
    appliedFilterSets = appliedFilterSets.map((s) =>
      s.id === fs.id ? { ...s, color: newColor } : s,
    );
    browserFilterSets = browserFilterSets.map((s) =>
      s.id === fs.id ? { ...s, color: newColor } : s,
    );
    channel?.postMessage({
      type: "apply-filter-sets",
      filterSets: filterSetsToPlain(appliedFilterSets),
      combinationLogic,
    } satisfies SearchMessage);
  }

  function toggleFilterSetColors() {
    filterSetColorsEnabled = !filterSetColorsEnabled;
    channel?.postMessage({
      type: "set-filter-set-colors",
      enabled: filterSetColorsEnabled,
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
          color: editorColor,
        })
        .toPromise();
      await loadFilterSets(true);
      editorName = "";
      editorLogic = "AND";
      editorColor = "#4A90D9";
      filters = [];
      filterSetEditorOpen = false;
    } catch (err) {
      console.error("Failed to save filter set:", err);
    } finally {
      savingFilterSet = false;
    }
  }

  async function handleDeleteFilterSet(id: string) {
    try {
      await client.mutation(DELETE_FILTER_SET_MUTATION, { id }).toPromise();
      const next = new Set(selectedSetIds);
      next.delete(id);
      selectedSetIds = next;
      await loadFilterSets(true);
      await loadApplied(true);
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

  function setAppliedName(id: string, value: string) {
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
      relation: f.relation ?? undefined,
      operator: f.operator ?? undefined,
      valueType: f.valueType ?? undefined,
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

  async function handleLogicChange(fs: FilterSet, newLogic: "AND" | "OR") {
    if (fs.logic === newLogic) return;
    try {
      await updateFilterSet(fs.id, getAppliedName(fs) || fs.name, newLogic, fs.filters);
    } catch (err) {
      console.error("Failed to update filter set logic:", err);
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

  async function addFilterToAppliedSet(fs: FilterSet) {
    const newFilter: SearchFilter = { id: genId(), mode: "class" };
    const nextFilters = [...fs.filters, newFilter];
    try {
      await persistFilterSet(fs, nextFilters);
      const updatedFs = appliedFilterSets.find((s) => s.id === fs.id);
      if (updatedFs?.filters.length) {
        const idx = updatedFs.filters.length - 1;
        beginEditAppliedFilter(updatedFs, updatedFs.filters[idx], idx);
      }
    } catch (err) {
      console.error("Failed to add filter to set:", err);
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
    searchScope = "project";
  }

  async function handleApplySelected() {
    if (!branchId) return;
    const mergedIds = new Set<string>([
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

  async function handleUnapplyFilterSet(filterSetId: string) {
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
    if (urlBranch != null && urlBranch !== "") branchId = urlBranch;
    if (urlProject != null && urlProject !== "") projectId = urlProject;
    // Fallback: recover branch/project from persisted app settings
    if (branchId == null) {
      const settings = loadSettings();
      if (settings?.activeBranchId != null) branchId = settings.activeBranchId;
      if (settings?.activeProjectId != null)
        projectId = settings.activeProjectId;
    }
    if (branchId != null) {
      void ensureProductTreeForBranch(branchId);
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
        void ensureProductTreeForBranch(branchId);
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

  $effect(() => {
    if (!filterGuideOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") filterGuideOpen = false;
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
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
    <div class="page-header-title-row">
      <h2>Search &amp; Filter</h2>
      <button
        type="button"
        class="btn btn-guide"
        onclick={() => (filterGuideOpen = true)}
      >
        Filter Guide
      </button>
    </div>
    <span class="result-count">{resultCount} / {totalCount} elements</span>
  </header>

  <!-- Color mode toggle -->
  <div class="color-toggle-bar">
    <label class="color-toggle-label">
      <input
        type="checkbox"
        checked={filterSetColorsEnabled}
        onchange={toggleFilterSetColors}
      />
      <span>Use filter set colors</span>
    </label>
  </div>

  <!-- Filter Guide modal -->
  {#if filterGuideOpen}
    <!-- svelte-ignore a11y_no_static_element_interactions a11y_click_events_have_key_events -->
    <div class="guide-backdrop" onclick={() => (filterGuideOpen = false)}>
      <!-- svelte-ignore a11y_no_static_element_interactions a11y_click_events_have_key_events -->
      <div
        class="guide-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="guide-title"
        tabindex="-1"
        onclick={(e) => e.stopPropagation()}
      >
        <div class="guide-header">
          <h3 id="guide-title">Filter Guide</h3>
          <button
            type="button"
            class="btn-close"
            aria-label="Close"
            onclick={() => (filterGuideOpen = false)}
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
          </button>
        </div>
        <div class="guide-body">
          <h4>Filter sets</h4>
          <p>A filter set is a named collection of filters you can save and reuse. Each set has AND/OR logic: filters inside a set are combined with that logic. When multiple sets are applied, they are combined with the combination logic shown above the applied list.</p>

          <h4>Adding filters</h4>
          <p>Create a new filter set with <strong>New Filter Set</strong>, add filters with <strong>Add Filter</strong>, then save. Or select existing sets and click <strong>Apply</strong>. You can also add filters to applied sets and click <strong>Update</strong>.</p>

          <h4>Class filters</h4>
          <p>Match IFC entity classes (e.g. <code>IfcWall</code>, <code>IfcDoor</code>). Use <strong>is</strong> for exact match, <strong>is not</strong> to exclude, or <strong>inherits from</strong> to include the class and all its descendants (e.g. walls and subtypes).</p>

          <h4>Attribute filters</h4>
          <p>Match entity attributes at any depth in the JSONB data. Enter the attribute key (e.g. <code>Name</code>, <code>PropertySets</code>) and value. Choose the operator (is, contains, starts with, etc.) and data type (String, Numeric, or Object). For nested keys like <code>PropertySets</code>, use <strong>Object</strong> type to match object key names (e.g. <code>Pset_WallCommon</code>).</p>

          <h4>Relation filters</h4>
          <p>Match entities by IFC relationships (e.g. <code>ContainedIn</code>, <code>FillsVoid</code>). The filter finds entities that have the specified relation type in the graph.</p>
        </div>
      </div>
    </div>
  {/if}

  <!-- ═══════ Filter Set Browser ═══════ -->
  <section class="section">
    <div class="section-header section-header--collapsible-wrap">
      <button
        type="button"
        class="section-header--collapsible"
        onclick={() => (filterSetsSectionCollapsed = !filterSetsSectionCollapsed)}
        aria-expanded={!filterSetsSectionCollapsed}
        aria-label={filterSetsSectionCollapsed ? 'Expand Filter Sets' : 'Collapse Filter Sets'}
      >
        <span class="section-header-title">
          <span class="section-chevron" class:open={!filterSetsSectionCollapsed}>▸</span>
          <h3>Filter Sets</h3>
        </span>
      </button>
      {#if branchId}
        <div
          class="scope-selector"
          bind:this={scopeSelectorEl}
        >
          <button
            type="button"
            class="scope-trigger"
            aria-haspopup="listbox"
            aria-expanded={scopeDropdownOpen}
            aria-label="Search scope"
            onclick={() => (scopeDropdownOpen = !scopeDropdownOpen)}
          >
            {SCOPE_OPTIONS.find((o) => o.value === searchScope)?.label ?? searchScope}
            <span class="scope-chevron" class:open={scopeDropdownOpen}>▾</span>
          </button>
          {#if scopeDropdownOpen}
            <ul
              class="scope-dropdown"
              role="listbox"
              aria-label="Search scope"
            >
              {#each SCOPE_OPTIONS as opt}
                <li
                  role="option"
                  aria-selected={searchScope === opt.value}
                  tabindex="-1"
                  class="scope-option"
                  class:selected={searchScope === opt.value}
                  onclick={() => {
                    searchScope = opt.value;
                    scopeDropdownOpen = false;
                  }}
                  onkeydown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      searchScope = opt.value;
                      scopeDropdownOpen = false;
                    }
                  }}
                >
                  {opt.label}
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      {/if}
    </div>

    {#if !filterSetsSectionCollapsed}
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
            <ColorPicker
              color={fs.color}
              onchange={(c) => handleColorChange(fs, c)}
            />
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
                class="btn-icon btn-danger"
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
        <button class="btn btn-primary" onclick={handleApplySelected}>
          Apply {selectedSetIds.size} Set{selectedSetIds.size === 1 ? "" : "s"}
        </button>
      </div>
    {/if}
    {/if}
  </section>

  <!-- ═══════ Filter Set Editor ═══════ -->
  {#if !filterSetEditorOpen}
    <div class="filter-set-editor-trigger">
      <button
        type="button"
        class="btn btn-primary"
        onclick={() => (filterSetEditorOpen = true)}
      >
        New Filter Set
      </button>
    </div>
  {:else}
    <section class="section" id="filter-set-editor">
      <div class="section-header section-header--with-close">
        <h3>New Filter Set</h3>
        <button
          type="button"
          class="btn-close"
          aria-label="Close filter set editor"
          onclick={() => (filterSetEditorOpen = false)}
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

      {#if !branchId}
        <p class="empty-hint">
          Open a project from the main view to save filter sets.
        </p>
      {/if}

      <div class="editor-row">
        <ColorPicker
          color={editorColor}
          onchange={(c) => (editorColor = c)}
        />
        <input
          class="editor-name"
          type="text"
          placeholder="Filter set name…"
          bind:value={editorName}
        />
        <div class="logic-toggle">
          <button
            class="btn-mode"
            class:active={editorLogic === "AND"}
            onclick={() => (editorLogic = "AND")}>AND</button
          >
          <button
            class="btn-mode"
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
        <button class="btn-add" aria-label="Add filter" onclick={addFilter}>
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
          <button class="btn btn-secondary" onclick={clearAll}>Clear All</button
          >
          <button
            class="btn btn-primary"
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
  {/if}

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
          {@const isCollapsed = collapsedAppliedIds.has(fs.id)}
          <div class="applied-item" class:collapsed={isCollapsed}>
            <div class="applied-item-header">
              <div class="editor-row applied-editor-row">
                <ColorPicker
                  color={fs.color}
                  onchange={(c) => handleColorChange(fs, c)}
                />
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
                    class="btn-mode"
                    class:active={fs.logic === "AND"}
                    onclick={() => handleLogicChange(fs, "AND")}
                    >AND</button
                  >
                  <button
                    class="btn-mode"
                    class:active={fs.logic === "OR"}
                    onclick={() => handleLogicChange(fs, "OR")}
                    >OR</button
                  >
                </div>
              </div>
              <button
                type="button"
                class="applied-item-toggle"
                aria-label={isCollapsed ? "Expand" : "Collapse"}
                aria-expanded={!isCollapsed}
                onclick={() => toggleAppliedItem(fs.id)}
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 16 16"
                  fill="none"
                  class="chevron"
                  class:rotated={isCollapsed}
                >
                  <path
                    d="M4 6l4 4 4-4"
                    stroke="currentColor"
                    stroke-width="1.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </button>
            </div>
            {#if !isCollapsed}
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
                            >{f.operator === "inherits_from"
                              ? "inherits from "
                              : f.operator === "is_not"
                                ? "is not "
                                : ""}{f.ifcClass ?? "—"}</span
                          >
                        {:else if f.mode === "relation"}
                          <span class="applied-filter-mode">Relation</span>
                          <span class="applied-filter-value"
                            >{f.relation ?? "—"}</span
                          >
                        {:else}
                          <span class="applied-filter-mode">Attr</span>
                          <span class="applied-filter-value"
                            >{f.attribute ?? "—"} {f.operator === "is_empty"
                              ? "is empty"
                              : f.operator === "is_not_empty"
                                ? "is not empty"
                                : `${f.operator ?? "contains"} ${f.value ?? "—"}`}</span
                          >
                        {/if}
                        <div class="applied-filter-actions">
                          <button
                            type="button"
                            class="btn-icon"
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
                            class="btn-icon btn-danger"
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
                  class="btn-add"
                  onclick={() => addFilterToAppliedSet(fs)}
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
                    class="btn btn-primary"
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
            {/if}
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
    gap: 1rem;
    min-height: 100vh;
    max-height: 100vh;
    overflow: hidden;
    padding: 1rem;
    background: var(--color-bg-canvas);
    color: var(--color-text-primary);
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
    gap: 0.75rem;
  }

  .page-header-title-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .guide-backdrop {
    position: fixed;
    inset: 0;
    background: color-mix(in srgb, var(--color-bg-canvas) 20%, black);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .guide-modal {
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 12px;
    width: 75%;
    height: 75%;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  }

  .guide-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .guide-header h3 {
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--color-text-primary);
    margin: 0;
  }

  .guide-body {
    padding: 1rem;
    overflow-y: auto;
    font-size: 0.8rem;
    line-height: 1.5;
    color: var(--color-text-secondary);
  }

  .guide-body h4 {
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--color-text-secondary);
    margin: 1rem 0 0.4rem;
  }

  .guide-body h4:first-child {
    margin-top: 0;
  }

  .guide-body p {
    margin: 0 0 0.5rem;
  }

  .guide-body code {
    background: var(--color-bg-elevated);
    padding: 0.1rem 0.35rem;
    border-radius: 0.25rem;
    font-size: 0.75rem;
  }

  .page-header h2 {
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--color-text-primary);
  }

  .result-count {
    font-size: 0.78rem;
    color: var(--color-action-primary);
    font-variant-numeric: tabular-nums;
  }

  /* ---- Sections ---- */

  .section {
    border: 1px solid var(--color-border-subtle);
    border-radius: 12px;
    padding: 0.75rem;
    background: var(--color-bg-elevated);
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .section-header--collapsible-wrap {
    width: 100%;
  }

  .section-header--collapsible {
    flex: 1;
    min-width: 0;
    background: none;
    border: none;
    padding: 0;
    margin: 0;
    cursor: pointer;
    font-family: inherit;
    text-align: left;
  }

  .section-header--collapsible:hover {
    opacity: 0.9;
  }

  .section-header-title {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }


  .section-header--with-close .btn-close {
    margin-left: auto;
  }

  .section-header h3 {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--color-text-secondary);
  }

  /* ---- Search input ---- */

  .search-input {
    width: 100%;
    box-sizing: border-box;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    border-radius: 0.35rem;
    color: var(--color-text-secondary);
    padding: 0.4rem 0.55rem;
    font-size: 0.78rem;
    outline: none;
  }

  .search-input:focus {
    border-color: var(--color-border-strong);
  }

  .search-input::placeholder {
    color: var(--color-text-muted);
  }

  /* ---- Scope selector ---- */

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
    border-radius: 0.5rem;
    border: 1px solid transparent;
    transition: background 0.12s, border-color 0.12s;
  }

  .set-row:hover {
    background: color-mix(in srgb, var(--color-text-primary) 4%, transparent);
  }

  .set-row.selected {
    background: color-mix(in srgb, var(--color-action-primary) 12%, transparent);
    border-color: color-mix(in srgb, var(--color-action-primary) 25%, transparent);
  }

  .set-checkbox input {
    accent-color: var(--color-action-primary);
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
    color: var(--color-text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .set-meta {
    font-size: 0.68rem;
    color: var(--color-text-muted);
  }

  .set-actions {
    display: flex;
    gap: 0.2rem;
    flex-shrink: 0;
  }

  /* ---- Apply bar ---- */

  .apply-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-top: 1px solid var(--color-border-subtle);
  }

  /* ---- Applied filter sets panel ---- */

  .section--applied {
    border: none;
    background: transparent;
    padding: 0;
    flex: 1 1 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .section--applied .section-header {
    flex-shrink: 0;
  }

  .applied-logic {
    font-size: 0.7rem;
    color: var(--color-text-muted);
    font-weight: 500;
  }

  .applied-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    flex: 1;
    min-height: 0;
    overflow-y: auto;
  }

  .applied-item {
    border-radius: 12px;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-subtle);
    font-size: 0.78rem;
    outline: none;
    transition:
      border-color 0.15s,
      background 0.15s;
    padding: 0.55rem 0.65rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .applied-item-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .applied-item-header .applied-editor-row {
    flex: 1;
    min-width: 0;
  }

  .applied-item-toggle {
    flex-shrink: 0;
    background: none;
    border: none;
    color: var(--color-text-muted);
    cursor: pointer;
    padding: 0.2rem;
    border-radius: 0.25rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: color 0.15s;
  }

  .applied-item-toggle:hover {
    color: var(--color-text-secondary);
  }

  .applied-item-toggle .chevron {
    transition: transform 0.2s ease;
  }

  .applied-item-toggle .chevron.rotated {
    transform: rotate(90deg);
  }

  .applied-item:hover {
    border-color: color-mix(in srgb, var(--color-action-primary) 25%, transparent);
    background: color-mix(in srgb, var(--color-action-primary) 8%, transparent);
  }

  .applied-name {
    color: var(--color-text-secondary);
    cursor: text;
  }

  .applied-name:focus {
    border-color: var(--color-border-default);
  }

  .applied-filter-line {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.75rem;
    padding: 0.28rem 0.35rem;
    border-radius: 0.28rem;
    color: var(--color-text-secondary);
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-subtle);
  }

  .applied-filter-mode {
    flex-shrink: 0;
    color: var(--color-text-muted);
    font-size: 0.7rem;
    text-transform: uppercase;
    width: 4rem;
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

  .applied-filter-edit {
    border: 1px solid var(--color-border-default);
    border-radius: 0.35rem;
    background: var(--color-bg-elevated);
    padding: 0.15rem 0.45rem 0.45rem;
  }

  .applied-filter-edit-actions {
    justify-content: flex-end;
  }

  .applied-toolbar {
    padding-top: 0.45rem;
    border-top: 1px solid var(--color-border-subtle);
  }

  /* ---- Logic toggle (shared) ---- */

  .logic-toggle {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }

  /* ---- Editor ---- */

  .editor-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  .editor-name {
    flex: 1;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    border-radius: 0.35rem;
    color: var(--color-text-secondary);
    padding: 0.4rem 0.55rem;
    font-size: 0.78rem;
    outline: none;
  }

  .editor-name:focus {
    border-color: var(--color-border-strong);
  }

  .editor-name::placeholder {
    color: var(--color-text-muted);
  }

  .filter-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .editor-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .editor-actions {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    justify-content: flex-end;
    flex-wrap: wrap;
  }

  .empty-hint {
    padding: 0.75rem 0;
    text-align: center;
    font-size: 0.78rem;
    color: var(--color-text-muted);
  }

  /* ---- Color toggle bar ---- */

  .color-toggle-bar {
    display: flex;
    align-items: center;
    padding: 0.4rem 0.55rem;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.35rem;
  }

  .color-toggle-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.78rem;
    color: var(--color-text-secondary);
    cursor: pointer;
  }

  .color-toggle-label input {
    accent-color: var(--color-action-primary);
    cursor: pointer;
  }

  /* ---- Filter set editor trigger ---- */

  .filter-set-editor-trigger {
    display: flex;
    justify-content: flex-start;
  }
</style>
