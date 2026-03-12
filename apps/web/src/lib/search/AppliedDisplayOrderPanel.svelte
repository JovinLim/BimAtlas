<script lang="ts">
  import type { FilterSet } from "$lib/search/protocol";

  let {
    appliedSets,
    onReorder,
  }: {
    appliedSets: FilterSet[];
    onReorder: (newOrder: FilterSet[]) => void;
  } = $props();

  function moveUp(index: number) {
    if (index <= 0) return;
    const next = [...appliedSets];
    [next[index - 1], next[index]] = [next[index], next[index - 1]];
    onReorder(next);
  }

  function moveDown(index: number) {
    if (index >= appliedSets.length - 1) return;
    const next = [...appliedSets];
    [next[index], next[index + 1]] = [next[index + 1], next[index]];
    onReorder(next);
  }
</script>

<div class="display-order-panel">
  <p class="order-hint">
    When elements match multiple sets, the topmost set's color wins.
  </p>
  <div class="order-list">
    {#each appliedSets as fs, idx (fs.id)}
      <div class="order-row">
        <div class="order-controls">
          <button
            type="button"
            class="btn-order"
            aria-label="Move up"
            disabled={idx === 0}
            onclick={() => moveUp(idx)}
          >
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
              <path d="M8 12V4M4 8l4-4 4 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
          <button
            type="button"
            class="btn-order"
            aria-label="Move down"
            disabled={idx === appliedSets.length - 1}
            onclick={() => moveDown(idx)}
          >
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
              <path d="M8 4v8M4 8l4 4 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
        </div>
        <span
          class="order-color"
          style="background: {fs.color};"
          title={fs.color}
        />
        <span class="order-name">{fs.name}</span>
      </div>
    {/each}
  </div>
</div>

<style>
  .display-order-panel {
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--color-border-subtle);
  }

  .order-hint {
    font-size: 0.75rem;
    color: var(--color-text-muted);
    margin: 0 0 0.5rem;
  }

  .order-list {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .order-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.5rem;
    background: var(--color-bg-elevated);
    border-radius: 6px;
    font-size: 0.8rem;
    color: var(--color-text-secondary);
  }

  .order-controls {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .btn-order {
    background: none;
    border: none;
    padding: 0.15rem;
    color: var(--color-text-muted);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
  }

  .btn-order:hover:not(:disabled) {
    background: var(--color-bg-canvas);
    color: var(--color-text-secondary);
  }

  .btn-order:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .order-color {
    width: 12px;
    height: 12px;
    border-radius: 3px;
    flex-shrink: 0;
  }

  .order-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
