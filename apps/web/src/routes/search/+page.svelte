<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import SearchFilterRow from "$lib/ui/SearchFilter.svelte";
  import {
    SEARCH_CHANNEL,
    type SearchFilter,
    type SearchMessage,
  } from "$lib/search/protocol";

  let filters = $state<SearchFilter[]>([]);
  let resultCount = $state<number | null>(null);
  let totalCount = $state<number | null>(null);

  let nextId = 0;
  function genId(): string {
    return `f-${nextId++}`;
  }

  function addFilter() {
    filters = [...filters, { id: genId(), mode: "class" }];
  }

  function removeFilter(id: string) {
    filters = filters.filter((f) => f.id !== id);
    if (filters.length === 0) {
      resultCount = null;
      totalCount = null;
    }
  }

  function updateFilter(id: string, patch: Partial<SearchFilter>) {
    filters = filters.map((f) => (f.id === id ? { ...f, ...patch } : f));
  }

  /** Serialize filters to plain objects so BroadcastChannel can clone them. */
  function filtersToPlain(list: SearchFilter[]): SearchFilter[] {
    return list.map((f) => ({
      id: f.id,
      mode: f.mode,
      ifcClass: f.ifcClass,
      attribute: f.attribute,
      value: f.value,
    }));
  }

  function clearFilters() {
    filters = [];
    resultCount = null;
    totalCount = null;
    channel?.postMessage({
      type: "apply-filters",
      filters: [],
    } satisfies SearchMessage);
  }

  function handleApply() {
    channel?.postMessage({
      type: "apply-filters",
      filters: filtersToPlain(filters),
    } satisfies SearchMessage);
  }

  let channel: BroadcastChannel | null = null;

  onMount(() => {
    channel = new BroadcastChannel(SEARCH_CHANNEL);
    channel.onmessage = (e: MessageEvent<SearchMessage>) => {
      if (e.data.type === "filter-result-count") {
        resultCount = e.data.count;
        totalCount = e.data.total;
      }
    };
  });

  onDestroy(() => {
    channel?.close();
  });
</script>

<div class="search-page">
  <header class="page-header">
    <h2>Search &amp; Filter</h2>
    {#if resultCount !== null && totalCount !== null}
      <span class="result-count">{resultCount} / {totalCount} elements</span>
    {/if}
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

  .result-count {
    font-size: 0.78rem;
    color: #ff8866;
    font-variant-numeric: tabular-nums;
  }

  .search-toolbar {
    margin-bottom: 0.75rem;
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
