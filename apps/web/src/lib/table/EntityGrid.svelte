<script lang="ts">
  import type { ProductMeta } from "$lib/search/protocol";

  type EditableKey = "name" | "description" | "objectType" | "tag";
  const EDITABLE_KEYS: EditableKey[] = ["name", "description", "objectType", "tag"];

  type Props = {
    products: ProductMeta[];
    lockedIds: Set<string>;
    onToggleLock: (globalId: string) => void;
  };

  let { products, lockedIds, onToggleLock }: Props = $props();

  let edits = $state<Record<string, Partial<Record<EditableKey, string | null>>>>({});

  function getValue(product: ProductMeta, key: EditableKey): string {
    const local = edits[product.globalId]?.[key];
    if (local !== undefined) return local ?? "";
    return product[key] ?? "";
  }

  function setValue(globalId: string, key: EditableKey, value: string) {
    edits = {
      ...edits,
      [globalId]: {
        ...edits[globalId],
        [key]: value.trim() === "" ? null : value,
      },
    };
  }

  function isLocked(globalId: string): boolean {
    return lockedIds.has(globalId);
  }
</script>

<div class="entity-grid-wrap">
  <table class="entity-grid" role="grid" aria-label="IFC entities">
    <colgroup>
      <col class="col-rownum" />
      <col class="col-lock" />
      <col class="col-globalId" />
      <col class="col-ifcClass" />
      <col class="col-name" />
      <col class="col-description" />
      <col class="col-objectType" />
      <col class="col-tag" />
    </colgroup>
    <thead>
      <tr class="letters-row">
        <th class="corner" scope="col"></th>
        <th scope="col">A</th>
        <th scope="col">B</th>
        <th scope="col">C</th>
        <th scope="col">D</th>
        <th scope="col">E</th>
        <th scope="col">F</th>
        <th scope="col">G</th>
      </tr>
      <tr class="labels-row">
        <th class="row-index" scope="row">1</th>
        <th scope="col">Lock</th>
        <th scope="col">Global ID</th>
        <th scope="col">IFC CLASS</th>
        <th scope="col">Name</th>
        <th scope="col">Description</th>
        <th scope="col">Object Type</th>
        <th scope="col">Tag</th>
      </tr>
    </thead>
    <tbody>
      {#each products as product, idx (product.globalId)}
        {@const locked = isLocked(product.globalId)}
        <tr class="entity-row" data-global-id={product.globalId} data-locked={locked}>
          <th class="row-index" scope="row">{idx + 2}</th>
          <td class="col-lock">
            <button
              type="button"
              class="lock-btn"
              aria-label={locked ? "Unlock row" : "Lock row"}
              title={locked ? "Unlock row" : "Lock row"}
              onclick={() => onToggleLock(product.globalId)}
            >
              {#if locked}
                <svg class="lock-icon" width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                  <rect x="6.5" y="10" width="11" height="9" rx="2" ry="2" stroke="currentColor" stroke-width="1.8" fill="none" />
                  <path d="M9 10V8.5C9 6.6 10.6 5 12.5 5C14.4 5 16 6.6 16 8.5V10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none" />
                </svg>
              {:else}
                <svg class="lock-icon" width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                  <rect x="6.5" y="10" width="11" height="9" rx="2" ry="2" stroke="currentColor" stroke-width="1.8" fill="none" />
                  <path d="M9 10V8.5C9 6.6 10.6 5 12.5 5C13.6 5 14.6 5.5 15.3 6.3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none" />
                </svg>
              {/if}
            </button>
          </td>
          <td class="col-globalId">
            <input class="cell-input readonly-cell" type="text" value={product.globalId} readonly />
          </td>
          <td class="col-ifcClass">
            <input class="cell-input readonly-cell" type="text" value={product.ifcClass} readonly />
          </td>
          {#each EDITABLE_KEYS as key}
            <td class={"col-" + key}>
              <input
                class="cell-input"
                type="text"
                value={getValue(product, key)}
                readonly={locked}
                oninput={(e) => setValue(product.globalId, key, e.currentTarget.value)}
              />
            </td>
          {/each}
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .entity-grid-wrap { flex: 1; min-height: 0; width: 100%; max-width: 100%; overflow: auto; }
  .entity-grid { width: max-content; min-width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 0.78rem; }
  .entity-grid col.col-rownum { width: 2.8rem; }
  .entity-grid col.col-lock { width: 3rem; }
  .entity-grid col.col-globalId { width: 16rem; }
  .entity-grid col.col-ifcClass { width: 10rem; }
  .entity-grid col.col-name { width: 10rem; }
  .entity-grid col.col-description { width: 14rem; }
  .entity-grid col.col-objectType { width: 10rem; }
  .entity-grid col.col-tag { width: 8rem; }

  .entity-grid th, .entity-grid td { border-right: 1px solid rgba(255,255,255,0.06); border-bottom: 1px solid rgba(255,255,255,0.06); padding: 0; height: 34px; }
  .letters-row th {
    position: sticky;
    top: 0;
    z-index: 4;
    height: 28px;
    background: #1a1a2e;
    color: #c0c0d0;
    font-weight: 600;
    text-align: center;
  }
  .labels-row th {
    position: sticky;
    top: 28px;
    z-index: 3;
    background: #1a1a2e;
    color: #ccccd8;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    padding: 0 0.5rem;
    text-align: left;
    height: 34px;
  }
  .row-index {
    background: #1a1a2e;
    color: #c0c0d0;
    text-align: center !important;
    font-weight: 500;
    padding: 0;
  }
  .corner { background: #1a1a2e; }
  .entity-row:hover td { background: rgba(255,255,255,0.02); }

  .cell-input { box-sizing: border-box; width: 100%; height: 100%; border: none; background: transparent; color: #e0e0e0; font-size: 0.78rem; padding: 0 0.5rem; font-family: inherit; }
  .cell-input:focus { outline: none; background: rgba(255,136,102,0.08); box-shadow: inset 0 0 0 1px rgba(255,136,102,0.45); }
  .cell-input[readonly] { color: #b9b9c5; }
  .readonly-cell { background: rgba(255,255,255,0.02); }

  .lock-btn { width: 100%; height: 100%; border: none; background: transparent; color: #c8c8d3; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; }
  .lock-btn:hover { background: rgba(255,255,255,0.08); color: #ff8866; }
  .lock-icon { display: block; }
</style>
