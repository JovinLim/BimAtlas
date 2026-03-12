<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { page } from "$app/stores";
  import SearchFilterRow from "$lib/ui/SearchFilter.svelte";
  import ColorPicker from "$lib/ui/ColorPicker.svelte";
  import FilterGuide from "$lib/search/FilterGuide.svelte";
  import AppliedFilterSet from "$lib/search/AppliedFilterSet.svelte";
  import AppliedDisplayOrderPanel from "$lib/search/AppliedDisplayOrderPanel.svelte";
  import {
    APPLY_FILTER_SETS_MESSAGE_TYPE,
    APPLY_FILTER_SETS_STORAGE_KEY,
    SEARCH_CHANNEL,
    countLeaves,
    expressionToFlatFilters,
    flatFiltersToExpression,
    getLogicLabel,
    type FilterGroup,
    type FilterLeaf,
    type FilterSet,
    type SearchFilter,
    type SearchMessage,
    type SearchScope,
  } from "$lib/search/protocol";
  import type { AgentBusEvent } from "$lib/agent/protocol";
  import FilterTreeEditor from "$lib/search/FilterTreeEditor.svelte";
  import {
    loadFilterSetEditorDraft,
    loadSearchFilters,
    loadSettings,
    saveFilterSetEditorDraft,
    saveSearchFilters,
    clearFilterSetEditorDraft,
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
  let editorRoot = $state<FilterGroup>({
    kind: "group",
    op: "ALL",
    children: [],
  });
  let editorName = $state("");
  let editorLogic = $state<"AND" | "OR">("AND");

  let resultCount = $state(0);
  let totalCount = $state(0);
  let filterGuideOpen = $state(false);
  let filterSetColorsEnabled = $state(false);
  let filterSetsSectionCollapsed = $state(false);
  let editorColor = $state("#334155");
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

  let hasAutoOpenedFromDraft = false;
  $effect(() => {
    if (hasAutoOpenedFromDraft) return;
    const draft = loadFilterSetEditorDraft(branchId);
    if (!draft) return;
    hasAutoOpenedFromDraft = true;
    editorRoot = draft.root;
    editorName = draft.name;
    editorLogic = draft.logic;
    editorColor = draft.color;
    filterSetEditorOpen = true;
  });

  $effect(() => {
    if (!filterSetEditorOpen || !branchId) return;
    const root = editorRoot;
    const name = editorName;
    const logic = editorLogic;
    const color = editorColor;
    const id = setTimeout(() => {
      saveFilterSetEditorDraft(branchId, { root, name, logic, color });
    }, 500);
    return () => clearTimeout(id);
  });

  let openMenuPath = $state<string | null>(null);

  function getGroupAt(root: FilterGroup, path: string): FilterGroup | null {
    if (!path) return root;
    const parts = path.split(".");
    let node: FilterGroup | FilterLeaf | null = root;
    for (const p of parts) {
      if (!node || node.kind !== "group") return null;
      const idx = parseInt(p, 10);
      if (Number.isNaN(idx) || idx < 0 || idx >= node.children.length)
        return null;
      const child: FilterGroup | FilterLeaf = node.children[idx] as
        | FilterGroup
        | FilterLeaf;
      node = child.kind === "group" ? child : null;
    }
    return node && node.kind === "group" ? node : null;
  }

  function addFilterAt(parentPath: string) {
    openMenuPath = null;
    const parent = getGroupAt(editorRoot, parentPath);
    if (!parent) return;
    const newLeaf: FilterLeaf = { kind: "leaf", mode: "class" };
    const next = JSON.parse(JSON.stringify(editorRoot)) as FilterGroup;
    const p = getGroupAt(next, parentPath);
    if (p) p.children.push(newLeaf);
    editorRoot = next;
  }

  function addSubgroupAt(parentPath: string) {
    openMenuPath = null;
    const parent = getGroupAt(editorRoot, parentPath);
    if (!parent) return;
    const newGroup: FilterGroup = { kind: "group", op: "ALL", children: [] };
    const next = JSON.parse(JSON.stringify(editorRoot)) as FilterGroup;
    const p = getGroupAt(next, parentPath);
    if (p) p.children.push(newGroup);
    editorRoot = next;
  }

  function updateLeafAt(path: string, patch: Partial<SearchFilter>) {
    const parts = path.split(".");
    const next = JSON.parse(JSON.stringify(editorRoot)) as FilterGroup;
    let node: FilterGroup = next;
    for (let i = 0; i < parts.length - 1; i++) {
      const idx = parseInt(parts[i], 10);
      const child = node.children[idx];
      if (!child || child.kind !== "group") return;
      node = child;
    }
    const lastIdx = parseInt(parts[parts.length - 1], 10);
    const leaf = node.children[lastIdx];
    if (leaf?.kind === "leaf") {
      Object.assign(leaf, patch);
      node.children = [...node.children];
      editorRoot = next;
    }
  }

  function removeLeafAt(path: string) {
    const parts = path.split(".");
    const next = JSON.parse(JSON.stringify(editorRoot)) as FilterGroup;
    let node: FilterGroup = next;
    for (let i = 0; i < parts.length - 1; i++) {
      const idx = parseInt(parts[i], 10);
      const child = node.children[idx];
      if (!child || child.kind !== "group") return;
      node = child;
    }
    const lastIdx = parseInt(parts[parts.length - 1], 10);
    node.children = node.children.filter((_, i) => i !== lastIdx);
    editorRoot = next;
  }

  function updateSubgroupAt(path: string, op: "ALL" | "ANY") {
    const group = getGroupAt(editorRoot, path);
    if (!group) return;
    const next = JSON.parse(JSON.stringify(editorRoot)) as FilterGroup;
    const target = getGroupAt(next, path);
    if (target) target.op = op;
    editorRoot = next;
  }

  function removeSubgroupAt(path: string) {
    const parts = path.split(".");
    if (parts.length === 1) {
      const idx = parseInt(path, 10);
      if (Number.isNaN(idx) || idx < 0 || idx >= editorRoot.children.length)
        return;
      const child = editorRoot.children[idx];
      if (child?.kind !== "group") return;
      const next = JSON.parse(JSON.stringify(editorRoot)) as FilterGroup;
      next.children = next.children.filter((_, i) => i !== idx);
      editorRoot = next;
      return;
    }
    const parentPath = parts.slice(0, -1).join(".");
    const lastIdx = parseInt(parts[parts.length - 1], 10);
    const parent = getGroupAt(editorRoot, parentPath);
    if (!parent) return;
    if (lastIdx < 0 || lastIdx >= parent.children.length) return;
    const toRemove = parent.children[lastIdx];
    if (toRemove?.kind !== "group") return;
    const next = JSON.parse(JSON.stringify(editorRoot)) as FilterGroup;
    const p = getGroupAt(next, parentPath);
    if (!p) return;
    p.children = p.children.filter((_, i) => i !== lastIdx);
    editorRoot = next;
  }

  function addFilter() {
    addFilterAt("");
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
      relationTargetClass: f.relationTargetClass,
      relationTargetAttribute: f.relationTargetAttribute,
      relationTargetOperator: f.relationTargetOperator,
      relationTargetValue: f.relationTargetValue,
      relationTargetValueType: f.relationTargetValueType,
    }));
  }

  function filterSetsToPlain(list: FilterSet[]): FilterSet[] {
    return list.map((fs) => ({
      id: fs.id,
      branchId: fs.branchId,
      name: fs.name,
      logic: fs.logic,
      filters: filtersToPlain(fs.filters),
      filtersTree: fs.filtersTree ?? undefined,
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
    const flat = expressionToFlatFilters({ root: editorRoot });
    saveSearchFilters(filtersToPlain(flat));
  });

  async function loadFilterSets(forceNetwork = false) {
    if (!branchId) return;
    loadingBrowser = true;
    const context = forceNetwork
      ? { requestPolicy: "network-only" as const }
      : undefined;
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
    const context = forceNetwork
      ? { requestPolicy: "network-only" as const }
      : undefined;
    try {
      const result = await client
        .query(APPLIED_FILTER_SETS_QUERY, { branchId }, context)
        .toPromise();
      const data = result.data?.appliedFilterSets;
      if (data) {
        const sets = data.filterSets ?? [];
        appliedFilterSets = sets;
        combinationLogic = (data.combinationLogic === "AND" ? "AND" : "OR") as
          | "AND"
          | "OR";
      } else {
        appliedFilterSets = [];
      }
    } catch (err) {
      console.error("Failed to load applied filter sets:", err);
      appliedFilterSets = [];
    }
  }

  function postApplyFilterSetsToMain() {
    const filterSets = filterSetsToPlain(appliedFilterSets);
    const message = {
      type: "apply-filter-sets",
      filterSets,
      combinationLogic,
    } satisfies SearchMessage;
    const clone = JSON.parse(JSON.stringify(message));
    if (channel) {
      channel.postMessage(clone);
    } else {
      const fallbackChannel = new BroadcastChannel(SEARCH_CHANNEL);
      fallbackChannel.postMessage(clone);
      fallbackChannel.close();
    }
    try {
      localStorage.setItem(
        APPLY_FILTER_SETS_STORAGE_KEY,
        JSON.stringify({ filterSets, combinationLogic, timestamp: Date.now() }),
      );
    } catch {
      // Ignore quota/private mode
    }
    if (typeof window !== "undefined" && window.opener) {
      try {
        window.opener.postMessage(
          { type: APPLY_FILTER_SETS_MESSAGE_TYPE, filterSets: clone.filterSets, combinationLogic: clone.combinationLogic },
          window.location.origin,
        );
      } catch {}
    }
  }

  async function syncAppliedFilterSetsToMain(forceNetwork = true) {
    // Trigger viewer refresh immediately, then refresh again with network-truth state.
    postApplyFilterSetsToMain();
    await loadApplied(forceNetwork);
    postApplyFilterSetsToMain();
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
      relationTargetClass: f.relationTargetClass ?? null,
      relationTargetAttribute: f.relationTargetAttribute ?? null,
      relationTargetOperator: f.relationTargetOperator ?? null,
      relationTargetValue: f.relationTargetValue ?? null,
      relationTargetValueType: f.relationTargetValueType ?? null,
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
    await client.mutation(UPDATE_FILTER_SET_MUTATION, vars).toPromise();
    appliedFilterSets = appliedFilterSets.map((fs) =>
      fs.id === id
        ? {
            ...fs,
            name,
            logic,
            filters: nextFilters,
            ...(color !== undefined ? { color } : {}),
          }
        : fs,
    );
    if (branchId) {
      await client
        .mutation(APPLY_FILTER_SETS_MUTATION, {
          branchId,
          filterSetIds: appliedFilterSets.map((fs) => fs.id),
          combinationLogic,
        })
        .toPromise();
    }
    await syncAppliedFilterSetsToMain(true);
    await loadFilterSets(true);
  }

  async function updateFilterSetWithTree(
    id: string,
    name: string,
    logic: "AND" | "OR",
    filtersTree: FilterGroup,
    color?: string,
  ) {
    const flat = expressionToFlatFilters({ root: filtersTree });
    const vars: Record<string, unknown> = {
      id,
      name,
      logic,
      filtersTree,
    };
    if (color !== undefined) vars.color = color;
    await client.mutation(UPDATE_FILTER_SET_MUTATION, vars).toPromise();
    appliedFilterSets = appliedFilterSets.map((fs) =>
      fs.id === id
        ? {
            ...fs,
            name,
            logic,
            filters: flat,
            filtersTree,
            ...(color !== undefined ? { color } : {}),
          }
        : fs,
    );
    if (branchId) {
      await client
        .mutation(APPLY_FILTER_SETS_MUTATION, {
          branchId,
          filterSetIds: appliedFilterSets.map((fs) => fs.id),
          combinationLogic,
        })
        .toPromise();
    }
    await syncAppliedFilterSetsToMain(true);
    await loadFilterSets(true);
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
    await syncAppliedFilterSetsToMain(true);
  }

  function toggleFilterSetColors() {
    filterSetColorsEnabled = !filterSetColorsEnabled;
    channel?.postMessage({
      type: "set-filter-set-colors",
      enabled: filterSetColorsEnabled,
    } satisfies SearchMessage);
  }

  async function handleSaveFilterSet() {
    if (!branchId || !editorName.trim() || countLeaves(editorRoot) === 0)
      return;
    savingFilterSet = true;
    const trimmedName = editorName.trim();
    try {
      await client
        .mutation(CREATE_FILTER_SET_MUTATION, {
          branchId,
          name: trimmedName,
          logic: editorLogic,
          filtersTree: editorRoot,
          color: editorColor,
        })
        .toPromise();
      await loadFilterSets(true);
      clearFilterSetEditorDraft(branchId);
      editorName = "";
      editorLogic = "AND";
      editorColor = "#4A90D9";
      editorRoot = { kind: "group", op: "ALL", children: [] };
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
      postApplyFilterSetsToMain();
    } catch (err) {
      console.error("Failed to delete filter set:", err);
    }
  }

  async function persistFilterSet(fs: FilterSet, nextFilters: SearchFilter[]) {
    const name = fs.name;
    await updateFilterSet(fs.id, name, fs.logic, nextFilters);
  }

  function loadFilterSetIntoEditor(fs: FilterSet) {
    editorName = fs.name;
    if (
      fs.filtersTree &&
      typeof fs.filtersTree === "object" &&
      fs.filtersTree.kind === "group"
    ) {
      editorRoot = fs.filtersTree as FilterGroup;
    } else {
      const expr = flatFiltersToExpression(fs.filters, fs.logic);
      editorRoot = expr.root;
    }
    editorLogic = editorRoot.op === "ANY" ? "OR" : "AND";
  }

  function clearEditor() {
    editorName = "";
    editorLogic = "AND";
    editorColor = "#334155";
    editorRoot = { kind: "group", op: "ALL", children: [] };
    resultCount = 0;
    totalCount = 0;
    clearFilterSetEditorDraft(branchId);
  }

  function resetFilterSetBrowserSection() {
    selectedSetIds = new Set();
    searchQuery = "";
    searchScope = "project";
    collapsedAppliedIds = new Set();
    openMenuPath = null;
    scopeDropdownOpen = false;
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
      resetFilterSetBrowserSection();
      await syncAppliedFilterSetsToMain(true);
    } catch (err) {
      console.error("Failed to apply filter sets:", err);
    }
  }

  async function handleReorderAppliedSets(newOrder: FilterSet[]) {
    if (!branchId || newOrder.length === 0) return;
    const ids = newOrder.map((fs) => fs.id);
    try {
      await client
        .mutation(APPLY_FILTER_SETS_MUTATION, {
          branchId,
          filterSetIds: ids,
          combinationLogic,
        })
        .toPromise();
      await syncAppliedFilterSetsToMain(true);
    } catch (err) {
      console.error("Failed to reorder applied filter sets:", err);
    }
  }

  async function handleUnapplyFilterSet(filterSetId: string) {
    if (!branchId) return;
    const remaining = appliedFilterSets.filter((fs) => fs.id !== filterSetId);
    const remainingIds = remaining.map((fs) => fs.id);
    try {
      await client
        .mutation(APPLY_FILTER_SETS_MUTATION, {
          branchId,
          filterSetIds: remainingIds,
          combinationLogic,
        })
        .toPromise();
      appliedFilterSets = remaining;
      await syncAppliedFilterSetsToMain(true);
    } catch (err) {
      console.error("Failed to unapply filter set:", err);
    }
  }

  function handleApplyAdHoc() {
    const flat = expressionToFlatFilters({ root: editorRoot });
    channel?.postMessage({
      type: "apply-filters",
      filters: filtersToPlain(flat),
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

  // ---- Agent events: refresh filter sets when agent creates/modifies/applies via MCP tools ----
  const API_BASE = import.meta.env.VITE_API_URL
    ? (import.meta.env.VITE_API_URL as string).replace("/graphql", "")
    : "/api";
  let agentEventSource: EventSource | null = null;
  $effect(() => {
    const bid = branchId;
    if (agentEventSource) {
      agentEventSource.close();
      agentEventSource = null;
    }
    if (!bid || typeof window === "undefined") return;
    const url = `${API_BASE}/stream/agent-events?branch_id=${encodeURIComponent(bid)}`;
    const es = new EventSource(url);
    agentEventSource = es;
    es.onmessage = (e) => {
      try {
        const event: AgentBusEvent = JSON.parse(e.data);
        if (
          event.type === "filter-applied" ||
          event.type === "filter-set-changed"
        ) {
          loadFilterSets(true);
          loadApplied(true);
        }
      } catch {}
    };
    return () => {
      es.close();
    };
  });

  onMount(() => {
    const saved = loadSearchFilters();
    if (saved.length > 0) {
      const expr = flatFiltersToExpression(saved, "AND");
      editorRoot = expr.root;
      editorLogic = "AND";
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
      } else if (e.data.type === "request-applied-filter-sets") {
        void syncAppliedFilterSetsToMain(true);
      } else if (e.data.type === "branch-context") {
        branchId = e.data.branchId;
        projectId = e.data.projectId;
        if (e.data.filterSetColorsEnabled !== undefined) {
          filterSetColorsEnabled = e.data.filterSetColorsEnabled;
        }
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
    agentEventSource?.close();
    agentEventSource = null;
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
      <h2>Search & Filter</h2>
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

  <main class="main-content">
    <!-- Color mode toggle -->
    <div class="color-toggle-bar">
      <label class="color-toggle-label">
        <input
          type="checkbox"
          checked={filterSetColorsEnabled}
          onchange={toggleFilterSetColors}
        />
        <span>Use filter set colors in view</span>
      </label>
    </div>

    <!-- ═══════ Filter Set Browser ═══════ -->
    <section class="section">
      <div class="section-header">
        <button
          type="button"
          class="btn-icon"
          onclick={() =>
            (filterSetsSectionCollapsed = !filterSetsSectionCollapsed)}
          aria-expanded={!filterSetsSectionCollapsed}
          aria-label={filterSetsSectionCollapsed
            ? "Expand filter sets"
            : "Collapse filter sets"}
        >
          <span class="section-chevron" class:open={!filterSetsSectionCollapsed}
            >▸</span
          >
          <h3>Filter Sets</h3>
        </button>

        {#if branchId && !filterSetsSectionCollapsed}
          <div class="scope-selector" bind:this={scopeSelectorEl}>
            <button
              type="button"
              class="scope-trigger"
              onclick={() => (scopeDropdownOpen = !scopeDropdownOpen)}
            >
              {SCOPE_OPTIONS.find((o) => o.value === searchScope)?.label ??
                searchScope}
              <span class="section-chevron" class:open={scopeDropdownOpen}
                >▾</span
              >
            </button>
            {#if scopeDropdownOpen}
              <ul class="scope-dropdown">
                {#each SCOPE_OPTIONS as opt}
                  <li
                    class="scope-option"
                    class:selected={searchScope === opt.value}
                    onclick={() => {
                      searchScope = opt.value;
                      scopeDropdownOpen = false;
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
          placeholder="Search saved filter sets…"
          bind:value={searchQuery}
        />

        <div class="set-list">
          {#if !branchId}
            <p class="empty-hint">Open a project to browse filter sets.</p>
          {:else if loadingBrowser}
            <p class="empty-hint">Loading filter sets…</p>
          {:else if browserFilterSets.length === 0}
            <p class="empty-hint">No filter sets found.</p>
          {:else}
            {#each browserFilterSets as fs (fs.id)}
              <div class="set-row" class:selected={selectedSetIds.has(fs.id)}>
                <input
                  type="checkbox"
                  checked={selectedSetIds.has(fs.id)}
                  onchange={() => toggleSetSelection(fs.id)}
                />
                <ColorPicker
                  color={fs.color}
                  onchange={(c) => handleColorChange(fs, c)}
                />
                <div class="set-info">
                  <span class="set-name">{fs.name}</span>
                  <span class="set-meta">
                    {fs.logic} · {fs.filters.length} filter{fs.filters
                      .length === 1
                      ? ""
                      : "s"}
                  </span>
                </div>
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
            {/each}
          {/if}
        </div>

        {#if selectedSetIds.size > 0}
          <div class="apply-bar" style="padding-top: 0.6rem;">
            <div style="flex: 1"></div>
            <button class="btn btn-primary" onclick={handleApplySelected}>
              Apply {selectedSetIds.size} Selected
            </button>
          </div>
        {/if}
      {/if}
    </section>

    <!-- ═══════ Filter Set Editor ═══════ -->
    {#if !filterSetEditorOpen}
      <div style="display: flex; justify-content: center;">
        <button
          type="button"
          class="btn btn-secondary"
          style="width: 100%; max-width: 400px; border-style: dashed;"
          onclick={() => {
            const draft = loadFilterSetEditorDraft(branchId);
            if (draft) {
              editorRoot = draft.root;
              editorName = draft.name;
              editorLogic = draft.logic;
              editorColor = draft.color;
            }
            filterSetEditorOpen = true;
          }}
        >
          + New Filter Set
        </button>
      </div>
    {:else}
      <section class="section" id="filter-set-editor">
        <div class="section-header">
          <h3>New Filter Set</h3>
          <button
            type="button"
            class="btn-close"
            onclick={() => {
              filterSetEditorOpen = false;
              clearEditor();
              clearFilterSetEditorDraft(branchId);
              openMenuPath = null;
            }}
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
          <p class="empty-hint">Open a project to save filter sets.</p>
        {:else}
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
          </div>

          <div class="filter-list">
            <FilterTreeEditor
              root={editorRoot}
              onUpdateRootOp={(op) => {
                editorLogic = op === "ALL" ? "AND" : "OR";
                editorRoot = { ...editorRoot, op };
              }}
              onAddFilter={addFilterAt}
              onAddSubgroup={addSubgroupAt}
              onUpdateLeaf={updateLeafAt}
              onUpdateSubgroup={updateSubgroupAt}
              onRemoveSubgroup={removeSubgroupAt}
              onRemoveLeaf={removeLeafAt}
              {openMenuPath}
              onToggleMenu={(p: string | null) => (openMenuPath = p)}
            />
          </div>

          <div class="editor-toolbar">
            <div class="editor-actions">
              <button class="btn btn-secondary btn-sm" onclick={clearAll}
                >Clear All</button
              >
              <button
                class="btn btn-primary btn-sm"
                disabled={countLeaves(editorRoot) === 0}
                onclick={handleApplyAdHoc}
              >
                Apply Ad-hoc
              </button>
              <button
                class="btn btn-primary btn-sm"
                disabled={!branchId ||
                  !editorName.trim() ||
                  countLeaves(editorRoot) === 0 ||
                  savingFilterSet}
                onclick={handleSaveFilterSet}
              >
                {savingFilterSet ? "Saving..." : "Save Filter Set"}
              </button>
            </div>
          </div>
        {/if}
      </section>
    {/if}

    <!-- ═══════ Applied Panel ═══════ -->
    <section class="section section--applied">
      <div class="section-header" style="padding-bottom: 0.25rem;">
        <h3>Applied to view</h3>
        {#if appliedFilterSets.length > 1}
          <span class="applied-logic"
            >Combined with {getLogicLabel(combinationLogic)}</span
          >
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
            <AppliedFilterSet
              {fs}
              isCollapsed={collapsedAppliedIds.has(fs.id)}
              onToggle={() => toggleAppliedItem(fs.id)}
              onColorChange={(c) => handleColorChange(fs, c)}
              onUpdate={(name, root) =>
                updateFilterSetWithTree(
                  fs.id,
                  name,
                  root.op === "ANY" ? "OR" : "AND",
                  root,
                )}
              onUnapply={() => handleUnapplyFilterSet(fs.id)}
              onDelete={() => handleDeleteFilterSet(fs.id)}
            />
          {/each}
          {#if appliedFilterSets.length > 1}
            <AppliedDisplayOrderPanel
              appliedSets={appliedFilterSets}
              onReorder={handleReorderAppliedSets}
            />
          {/if}
        {/if}
      </div>
    </section>
  </main>
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
    height: 100vh;
    background: var(--color-bg-canvas);
    color: var(--color-text-primary);
    font-family:
      system-ui,
      -apple-system,
      sans-serif;
  }

  .page-header {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--color-border-subtle);
    background: var(--color-bg-surface);
  }

  .page-header-title-row {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
  }

  .page-header h2 {
    font-size: 1.15rem;
    font-weight: 700;
    color: var(--color-text-primary);
    letter-spacing: -0.01em;
  }

  .result-count {
    font-size: 0.8rem;
    color: var(--color-text-secondary);
    font-variant-numeric: tabular-nums;
    font-weight: 500;
  }

  .main-content {
    flex: 1;
    min-width: 0;
    overflow-y: auto;
    padding: 0.5rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    max-width: 1400px;
    margin: 0 auto;
    width: 100%;
    box-sizing: border-box;
  }

  .section {
    min-width: 0;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 12px;
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  }

  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }

  .section-header h3 {
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--color-text-primary);
  }

  /* ---- Filter Browser Specifics ---- */
  .set-list {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    max-height: 250px;
    overflow-y: auto;
    padding-right: 0.25rem;
  }

  .set-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.45rem 0.6rem;
    border-radius: 10px;
    background: var(--color-bg-elevated);
    border: 1px solid transparent;
    transition: all 0.15s ease;
  }

  .set-row:hover {
    background: var(--color-bg-surface);
    border-color: var(--color-border-default);
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
  }

  .set-row.selected {
    background: color-mix(
      in srgb,
      var(--color-action-primary) 8%,
      var(--color-bg-surface)
    );
    border-color: var(--color-action-primary);
  }

  .set-info {
    flex: 1;
    min-width: 0;
  }

  .set-name {
    display: block;
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--color-text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .set-meta {
    font-size: 0.7rem;
    color: var(--color-text-muted);
  }

  /* ---- Editor Specifics ---- */
  .editor-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  .editor-name {
    flex: 1;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    border-radius: 8px;
    padding: 0.5rem 0.75rem;
    font-size: 0.85rem;
    color: var(--color-text-primary);
    outline: none;
    transition: all 0.15s ease;
  }

  .editor-name:focus {
    background: var(--color-bg-surface);
    border-color: var(--color-border-strong);
    box-shadow: 0 0 0 2px
      color-mix(in srgb, var(--color-border-strong) 10%, transparent);
  }

  .filter-list {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .editor-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.6rem;
    padding-top: 0.6rem;
    border-top: 1px solid var(--color-border-subtle);
  }

  .menu-wrap {
    position: relative;
  }

  .btn-menu {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-subtle);
    border-radius: 8px;
    padding: 0.35rem 0.5rem;
    color: var(--color-text-muted);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .btn-menu:hover {
    background: var(--color-bg-surface);
    color: var(--color-text-secondary);
  }

  .menu-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    margin-top: 0.25rem;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    z-index: 50;
    min-width: 140px;
  }

  .menu-item {
    display: block;
    width: 100%;
    padding: 0.5rem 0.75rem;
    text-align: left;
    font-size: 0.8rem;
    color: var(--color-text-secondary);
    background: none;
    border: none;
    cursor: pointer;
  }

  .menu-item:hover {
    background: var(--color-bg-elevated);
    color: var(--color-text-primary);
  }

  .editor-actions {
    display: flex;
    gap: 0.4rem;
  }

  /* ---- Applied Panel Specifics ---- */
  .section--applied {
    background: transparent;
    border: none;
    box-shadow: none;
    padding: 0;
    flex: 1;
    min-height: 0;
  }

  .applied-list {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    padding: 0;
  }

  .color-toggle-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.45rem 0.75rem;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 10px;
  }

  .color-toggle-label {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: 0.8rem;
    color: var(--color-text-secondary);
    cursor: pointer;
    font-weight: 500;
  }

  .btn-guide {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-subtle);
    color: var(--color-text-secondary);
    padding: 0.4rem 0.75rem;
    font-size: 0.75rem;
    border-radius: 8px;
    font-weight: 600;
  }

  .btn-guide:hover {
    background: var(--color-bg-surface);
    color: var(--color-text-primary);
    border-color: var(--color-border-default);
  }

  .empty-hint {
    padding: 1rem 0.75rem;
    text-align: center;
    color: var(--color-text-muted);
    font-size: 0.85rem;
    background: var(--color-bg-elevated);
    border-radius: 12px;
    border: 1px dashed var(--color-border-default);
  }

  .section-chevron {
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-text-muted);
    transition: transform 0.2s ease;
    display: inline-block;
  }

  .section-chevron.open {
    transform: rotate(90deg);
  }

  .scope-selector {
    position: relative;
  }

  .scope-trigger {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.4rem 0.75rem;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-subtle);
    border-radius: 8px;
    font-size: 0.8rem;
    font-weight: 500;
    color: var(--color-text-secondary);
    cursor: pointer;
  }

  .scope-trigger:hover {
    background: var(--color-bg-surface);
    color: var(--color-text-primary);
  }

  .scope-dropdown {
    position: absolute;
    top: 100%;
    right: 0;
    margin-top: 0.4rem;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-default);
    border-radius: 10px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
    z-index: 50;
    list-style: none;
    padding: 0.4rem;
    min-width: 140px;
  }

  .scope-option {
    padding: 0.5rem 0.75rem;
    font-size: 0.8rem;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .scope-option:hover {
    background: var(--color-bg-elevated);
  }

  .scope-option.selected {
    background: var(--color-action-primary);
    color: white;
  }

  .search-input {
    width: 100%;
    min-width: 0;
    box-sizing: border-box;
    padding: 0.45rem 0.6rem;
    font-size: 0.85rem;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    border-radius: 8px;
    color: var(--color-text-primary);
    outline: none;
    transition: all 0.15s ease;
  }

  .search-input:focus {
    background: var(--color-bg-surface);
    border-color: var(--color-border-strong);
  }
</style>
