<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import SearchFilterRow from "$lib/ui/SearchFilter.svelte";
  import { getDescendantClasses } from "$lib/ifc/schema";
  import {
    SEARCH_CHANNEL,
    FILTERABLE_ATTRIBUTES,
    type ProductMeta,
    type SearchFilter,
    type FilterableAttribute,
    type SearchMessage,
  } from "$lib/search/protocol";

  let products = $state<Map<string, ProductMeta>>(new Map());
  let filters = $state<SearchFilter[]>([]);
  let applied = $state(false);

  let nextId = 0;
  function genId(): string {
    return `f-${nextId++}`;
  }

  function addFilter() {
    filters = [...filters, { id: genId(), mode: "class" }];
  }

  function removeFilter(id: string) {
    filters = filters.filter((f) => f.id !== id);
    if (filters.length === 0) applied = false;
  }

  function updateFilter(id: string, patch: Partial<SearchFilter>) {
    filters = filters.map((f) => (f.id === id ? { ...f, ...patch } : f));
  }

  function clearFilters() {
    filters = [];
    applied = false;
    channel?.postMessage({
      type: "search-results",
      matchingIds: null,
    } satisfies SearchMessage);
  }

  function computeMatchingIds(): Set<string> | null {
    if (!applied || filters.length === 0) return null;
    const activeFilters = filters.filter((f) => {
      if (f.mode === "class") return !!f.ifcClass;
      return !!f.attribute && !!f.value;
    });
    if (activeFilters.length === 0) return null;

    const matching = new Set<string>();

    for (const [globalId, meta] of products) {
      let passes = true;

      for (const filter of activeFilters) {
        if (filter.mode === "class" && filter.ifcClass) {
          const allowed = getDescendantClasses(filter.ifcClass);
          if (!allowed.has(meta.ifcClass)) {
            passes = false;
            break;
          }
        } else if (
          filter.mode === "attribute" &&
          filter.attribute &&
          filter.value
        ) {
          const key = filter.attribute as FilterableAttribute;
          const fieldValue = meta[key];
          if (
            !fieldValue ||
            !fieldValue.toLowerCase().includes(filter.value.toLowerCase())
          ) {
            passes = false;
            break;
          }
        }
      }

      if (passes) matching.add(globalId);
    }

    return matching;
  }

  function handleApply() {
    applied = true;
    const ids = computeMatchingIds();
    const payload: SearchMessage = {
      type: "search-results",
      matchingIds: ids ? [...ids] : null,
    };
    channel?.postMessage(payload);
  }

  let matchCount = $derived.by(() => {
    if (!applied) return null;
    const ids = computeMatchingIds();
    if (ids === null) return null;
    return ids.size;
  });

  let channel: BroadcastChannel | null = null;
  let syncRetryTimer: ReturnType<typeof setInterval> | null = null;

  onMount(() => {
    channel = new BroadcastChannel(SEARCH_CHANNEL);
    channel.onmessage = (e: MessageEvent<SearchMessage>) => {
      if (e.data.type === "products-sync") {
        const map = new Map<string, ProductMeta>();
        for (const p of e.data.products) map.set(p.globalId, p);
        products = map;
        console.log("products synced", products);
        if (syncRetryTimer) {
          clearInterval(syncRetryTimer);
          syncRetryTimer = null;
        }
      }
    };
    channel.postMessage({
      type: "products-sync-request",
    } satisfies SearchMessage);

    syncRetryTimer = setInterval(() => {
      if (products.size > 0) {
        clearInterval(syncRetryTimer!);
        syncRetryTimer = null;
        return;
      }
      channel?.postMessage({
        type: "products-sync-request",
      } satisfies SearchMessage);
    }, 500);
  });

  onDestroy(() => {
    if (syncRetryTimer) clearInterval(syncRetryTimer);
    channel?.close();
  });
</script>

<div class="search-page">
  <header class="page-header">
    <h2>Search &amp; Filter</h2>
    <span class="product-count">{products.size} products loaded</span>
  </header>

  <div class="search-toolbar">
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

  <div class="filter-list">
    {#if filters.length === 0}
      <p class="empty-hint">No filters yet. Add one to start searching.</p>
    {/if}

    {#each filters as filter (filter.id)}
      <SearchFilterRow
        {filter}
        onupdate={(patch) => updateFilter(filter.id, patch)}
        onremove={() => removeFilter(filter.id)}
      />
    {/each}
  </div>

  {#if matchCount !== null}
    <p class="match-count">
      {matchCount} / {products.size} elements match
    </p>
  {/if}

  <footer class="page-footer">
    <button
      class="btn btn-secondary"
      disabled={filters.length === 0}
      onclick={clearFilters}
    >
      Clear All
    </button>
    <button
      class="btn btn-primary"
      disabled={filters.length === 0}
      onclick={handleApply}
    >
      Apply
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

  .search-toolbar {
    margin-bottom: 0.75rem;
  }

  .product-count {
    font-size: 0.72rem;
    color: #666;
    font-variant-numeric: tabular-nums;
  }

  .filter-list {
    overflow-y: auto;
    flex: 1;
    min-height: 48px;
  }

  .empty-hint {
    margin: 0;
    padding: 1rem 0;
    text-align: center;
    font-size: 0.8rem;
    color: #666;
  }

  .add-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    align-self: flex-start;
    background: rgba(255, 255, 255, 0.04);
    border: 1px dashed rgba(255, 255, 255, 0.15);
    border-radius: 0.35rem;
    color: #888;
    padding: 0.35rem 0.7rem;
    font-size: 0.78rem;
    cursor: pointer;
    margin-top: 0.5rem;
    transition:
      background 0.15s,
      color 0.15s;
  }

  .add-btn:hover {
    background: rgba(255, 136, 102, 0.1);
    color: #ff8866;
    border-color: rgba(255, 136, 102, 0.3);
  }

  .match-count {
    margin: 0.75rem 0 0;
    font-size: 0.78rem;
    color: #ff8866;
    font-variant-numeric: tabular-nums;
  }

  .page-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.6rem;
    margin-top: 1rem;
  }

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
</style>
