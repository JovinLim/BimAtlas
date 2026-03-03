<script lang="ts">
  export interface SheetEntry {
    id: string;
    entityGlobalId: string | null;
    category: string;
    label: string;
    value: string;
    notes: string;
    tag: string;
  }

  type Props = {
    entries?: SheetEntry[];
    rowStart?: number;
    onEntriesChange?: (entries: SheetEntry[]) => void;
  };

  let {
    entries = $bindable([]),
    rowStart = 2,
    onEntriesChange,
  }: Props = $props();

  function addEntry() {
    const id = crypto.randomUUID?.() ?? `sheet-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    entries = [
      ...entries,
      { id, entityGlobalId: null, category: "", label: "", value: "", notes: "", tag: "" },
    ];
    onEntriesChange?.(entries);
  }

  function removeEntry(id: string) {
    entries = entries.filter((e) => e.id !== id);
    onEntriesChange?.(entries);
  }

  function updateEntry(
    id: string,
    field: keyof Omit<SheetEntry, "id">,
    value: string | null,
  ) {
    entries = entries.map((e) =>
      e.id === id ? { ...e, [field]: value ?? "" } : e,
    );
    onEntriesChange?.(entries);
  }
</script>

<div class="bottom-sheet">
  <div class="sheet-toolbar">
    <button type="button" class="sheet-add-btn" onclick={addEntry}>+ Add row</button>
  </div>
  <div class="sheet-table-wrap">
    <table class="sheet-table" role="grid" aria-label="Sheet interactions">
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
      </thead>
      <tbody>
        {#if entries.length > 0}
          {#each entries as entry, idx (entry.id)}
            <tr class="sheet-row">
              <th class="row-index" scope="row">{rowStart + idx}</th>
              <td class="col-lock">
                <button
                  type="button"
                  class="sheet-remove-btn"
                  aria-label="Remove row"
                  onclick={() => removeEntry(entry.id)}
                />
              </td>
              <td class="col-globalId">
                <input
                  type="text"
                  class="sheet-input"
                  value={entry.entityGlobalId ?? ""}
                  oninput={(e) =>
                    updateEntry(
                      entry.id,
                      "entityGlobalId",
                      e.currentTarget.value.trim() || null,
                    )}
                />
              </td>
              <td class="col-ifcClass">
                <input
                  type="text"
                  class="sheet-input"
                  value={entry.category}
                  oninput={(e) => updateEntry(entry.id, "category", e.currentTarget.value)}
                />
              </td>
              <td class="col-name">
                <input
                  type="text"
                  class="sheet-input"
                  value={entry.label}
                  oninput={(e) => updateEntry(entry.id, "label", e.currentTarget.value)}
                />
              </td>
              <td class="col-description">
                <input
                  type="text"
                  class="sheet-input"
                  value={entry.value}
                  oninput={(e) => updateEntry(entry.id, "value", e.currentTarget.value)}
                />
              </td>
              <td class="col-objectType">
                <input
                  type="text"
                  class="sheet-input"
                  value={entry.notes}
                  oninput={(e) => updateEntry(entry.id, "notes", e.currentTarget.value)}
                />
              </td>
              <td class="col-tag">
                <input
                  type="text"
                  class="sheet-input"
                  value={entry.tag}
                  oninput={(e) => updateEntry(entry.id, "tag", e.currentTarget.value)}
                />
              </td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>
  </div>
</div>

<style>
  .bottom-sheet { display: flex; flex-direction: column; flex: 1; min-height: 0; width: 100%; max-width: 100%; overflow: hidden; }
  .sheet-toolbar { flex-shrink: 0; padding: 0.35rem 0.5rem; border-bottom: 1px solid rgba(255,255,255,0.06); background: rgba(255,255,255,0.02); }
  .sheet-add-btn { padding: 0.3rem 0.6rem; font-size: 0.78rem; background: rgba(255,136,102,0.15); border: 1px solid rgba(255,136,102,0.35); border-radius: 0.3rem; color: #ff8866; cursor: pointer; }
  .sheet-add-btn:hover { background: rgba(255,136,102,0.25); }

  .sheet-table-wrap { flex: 1; min-height: 0; width: 100%; max-width: 100%; overflow: auto; }
  .sheet-table { width: max-content; min-width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 0.78rem; }
  .sheet-table col.col-rownum { width: 2.8rem; }
  .sheet-table col.col-lock { width: 3rem; }
  .sheet-table col.col-globalId { width: 16rem; }
  .sheet-table col.col-ifcClass { width: 10rem; }
  .sheet-table col.col-name { width: 10rem; }
  .sheet-table col.col-description { width: 14rem; }
  .sheet-table col.col-objectType { width: 10rem; }
  .sheet-table col.col-tag { width: 8rem; }

  .sheet-table th, .sheet-table td { border-right: 1px solid rgba(255,255,255,0.06); border-bottom: 1px solid rgba(255,255,255,0.06); padding: 0; height: 34px; }
  .letters-row th {
    position: sticky;
    top: 0;
    z-index: 2;
    height: 28px;
    background: #1a1a2e;
    color: #c0c0d0;
    text-align: center;
    font-weight: 600;
  }
  .corner { background: #1a1a2e; }
  .row-index { background: #1a1a2e; color: #c0c0d0; text-align: center; font-weight: 500; }
  .sheet-row:hover td { background: rgba(255,255,255,0.02); }

  .sheet-input { box-sizing: border-box; width: 100%; height: 100%; border: none; background: transparent; color: #e0e0e0; font-size: 0.78rem; padding: 0 0.5rem; }
  .sheet-input:focus { outline: none; background: rgba(255,136,102,0.08); box-shadow: inset 0 0 0 1px rgba(255,136,102,0.45); }

  .sheet-remove-btn {
    width: 100%;
    height: 100%;
    border: none;
    background: transparent;
    cursor: pointer;
  }
  .sheet-remove-btn:hover {
    background: rgba(255,255,255,0.06);
  }

  .empty-cell { color: #777; padding: 0 0.6rem !important; font-style: italic; }
</style>
