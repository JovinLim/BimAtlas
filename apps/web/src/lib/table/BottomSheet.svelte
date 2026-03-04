<script lang="ts">
  import type { SpreadsheetCellState } from "$lib/table/engine";
  import type { SheetEntry } from "$lib/table/types";

  type Props = {
    entries?: SheetEntry[];
    rowStart?: number;
    onEntriesChange?: (entries: SheetEntry[]) => void;
    activeCellRef: string | null;
    getCellDisplayValue: (ref: string, fallback: string) => string;
    onCellFocus: (cell: SpreadsheetCellState) => void;
    onCellInput: (cell: SpreadsheetCellState, value: string) => void;
    onCellCommit: (cell: SpreadsheetCellState, value: string) => void;
    onCellCancel: (cell: SpreadsheetCellState) => void;
    onCellNavigate: (
      cell: SpreadsheetCellState,
      direction: "up" | "down" | "left" | "right" | "enter" | "tab",
      shift: boolean,
    ) => void;
    onFillDown: (cell: SpreadsheetCellState) => void;
    isCellInSelection: (ref: string) => boolean;
    onCellPointerDown: (
      cell: SpreadsheetCellState,
      event: MouseEvent,
    ) => boolean | void;
    onCellPointerEnter: (cell: SpreadsheetCellState, event: MouseEvent) => void;
    onCellPointerUp: (cell: SpreadsheetCellState, event: MouseEvent) => void;
  };

  let {
    entries = $bindable([]),
    rowStart = 2,
    onEntriesChange,
    activeCellRef,
    getCellDisplayValue,
    onCellFocus,
    onCellInput,
    onCellCommit,
    onCellCancel,
    onCellNavigate,
    onFillDown,
    isCellInSelection,
    onCellPointerDown,
    onCellPointerEnter,
    onCellPointerUp,
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

  function buildCell(
    row: number,
    col: string,
    editable: boolean,
    isProtected: boolean,
  ): SpreadsheetCellState {
    return {
      surface: "sheet",
      row,
      col,
      ref: `${col}${row}`,
      editable,
      protected: isProtected,
    };
  }

  function onCellKeydown(
    e: KeyboardEvent,
    cell: SpreadsheetCellState,
    value: string,
  ) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "d") {
      e.preventDefault();
      onFillDown(cell);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      onCellNavigate(cell, "up", e.shiftKey);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      onCellNavigate(cell, "down", e.shiftKey);
      return;
    }
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      onCellNavigate(cell, "left", e.shiftKey);
      return;
    }
    if (e.key === "ArrowRight") {
      e.preventDefault();
      onCellNavigate(cell, "right", e.shiftKey);
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      onCellCommit(cell, value);
      onCellNavigate(cell, "enter", e.shiftKey);
      (e.currentTarget as HTMLInputElement).blur();
      return;
    }
    if (e.key === "Tab") {
      e.preventDefault();
      onCellCommit(cell, value);
      onCellNavigate(cell, "tab", e.shiftKey);
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      onCellCancel(cell);
      (e.currentTarget as HTMLInputElement).blur();
    }
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
            {@const row = rowStart + idx}
            <tr class="sheet-row">
              <th class="row-index" scope="row">{rowStart + idx}</th>
              <td class="col-lock">
                <button
                  type="button"
                  class="sheet-remove-btn"
                  aria-label="Remove row"
                  onclick={() => removeEntry(entry.id)}
                ></button>
              </td>
              <td class="col-globalId">
                <input
                  type="text"
                  class="sheet-input"
                  class:active-cell={activeCellRef === `B${row}`}
                  class:selected-range={isCellInSelection(`B${row}`)}
                  data-cell-ref={`B${row}`}
                  value={getCellDisplayValue(`B${row}`, entry.entityGlobalId ?? "")}
                  onmousedown={(e) => {
                    if (onCellPointerDown(buildCell(row, "B", true, false), e)) return;
                  }}
                  onmouseenter={(e) => onCellPointerEnter(buildCell(row, "B", true, false), e)}
                  onmouseup={(e) => onCellPointerUp(buildCell(row, "B", true, false), e)}
                  onfocus={() => onCellFocus(buildCell(row, "B", true, false))}
                  oninput={(e) => onCellInput(buildCell(row, "B", true, false), e.currentTarget.value)}
                  onblur={(e) => onCellCommit(buildCell(row, "B", true, false), e.currentTarget.value)}
                  onkeydown={(e) =>
                    onCellKeydown(
                      e,
                      buildCell(row, "B", true, false),
                      (e.currentTarget as HTMLInputElement).value,
                    )}
                />
              </td>
              <td class="col-ifcClass">
                <input
                  type="text"
                  class="sheet-input"
                  class:active-cell={activeCellRef === `C${row}`}
                  class:selected-range={isCellInSelection(`C${row}`)}
                  data-cell-ref={`C${row}`}
                  value={getCellDisplayValue(`C${row}`, entry.category)}
                  onmousedown={(e) => {
                    if (onCellPointerDown(buildCell(row, "C", true, false), e)) return;
                  }}
                  onmouseenter={(e) => onCellPointerEnter(buildCell(row, "C", true, false), e)}
                  onmouseup={(e) => onCellPointerUp(buildCell(row, "C", true, false), e)}
                  onfocus={() => onCellFocus(buildCell(row, "C", true, false))}
                  oninput={(e) => onCellInput(buildCell(row, "C", true, false), e.currentTarget.value)}
                  onblur={(e) => onCellCommit(buildCell(row, "C", true, false), e.currentTarget.value)}
                  onkeydown={(e) =>
                    onCellKeydown(
                      e,
                      buildCell(row, "C", true, false),
                      getCellDisplayValue(`C${row}`, entry.category),
                    )}
                />
              </td>
              <td class="col-name">
                <input
                  type="text"
                  class="sheet-input"
                  class:active-cell={activeCellRef === `D${row}`}
                  class:selected-range={isCellInSelection(`D${row}`)}
                  data-cell-ref={`D${row}`}
                  value={getCellDisplayValue(`D${row}`, entry.label)}
                  onmousedown={(e) => {
                    if (onCellPointerDown(buildCell(row, "D", true, false), e)) return;
                  }}
                  onmouseenter={(e) => onCellPointerEnter(buildCell(row, "D", true, false), e)}
                  onmouseup={(e) => onCellPointerUp(buildCell(row, "D", true, false), e)}
                  onfocus={() => onCellFocus(buildCell(row, "D", true, false))}
                  oninput={(e) => onCellInput(buildCell(row, "D", true, false), e.currentTarget.value)}
                  onblur={(e) => onCellCommit(buildCell(row, "D", true, false), e.currentTarget.value)}
                  onkeydown={(e) =>
                    onCellKeydown(
                      e,
                      buildCell(row, "D", true, false),
                      (e.currentTarget as HTMLInputElement).value,
                    )}
                />
              </td>
              <td class="col-description">
                <input
                  type="text"
                  class="sheet-input"
                  class:active-cell={activeCellRef === `E${row}`}
                  class:selected-range={isCellInSelection(`E${row}`)}
                  data-cell-ref={`E${row}`}
                  value={getCellDisplayValue(`E${row}`, entry.value)}
                  onmousedown={(e) => {
                    if (onCellPointerDown(buildCell(row, "E", true, false), e)) return;
                  }}
                  onmouseenter={(e) => onCellPointerEnter(buildCell(row, "E", true, false), e)}
                  onmouseup={(e) => onCellPointerUp(buildCell(row, "E", true, false), e)}
                  onfocus={() => onCellFocus(buildCell(row, "E", true, false))}
                  oninput={(e) => onCellInput(buildCell(row, "E", true, false), e.currentTarget.value)}
                  onblur={(e) => onCellCommit(buildCell(row, "E", true, false), e.currentTarget.value)}
                  onkeydown={(e) =>
                    onCellKeydown(
                      e,
                      buildCell(row, "E", true, false),
                      (e.currentTarget as HTMLInputElement).value,
                    )}
                />
              </td>
              <td class="col-objectType">
                <input
                  type="text"
                  class="sheet-input"
                  class:active-cell={activeCellRef === `F${row}`}
                  class:selected-range={isCellInSelection(`F${row}`)}
                  data-cell-ref={`F${row}`}
                  value={getCellDisplayValue(`F${row}`, entry.notes)}
                  onmousedown={(e) => {
                    if (onCellPointerDown(buildCell(row, "F", true, false), e)) return;
                  }}
                  onmouseenter={(e) => onCellPointerEnter(buildCell(row, "F", true, false), e)}
                  onmouseup={(e) => onCellPointerUp(buildCell(row, "F", true, false), e)}
                  onfocus={() => onCellFocus(buildCell(row, "F", true, false))}
                  oninput={(e) => onCellInput(buildCell(row, "F", true, false), e.currentTarget.value)}
                  onblur={(e) => onCellCommit(buildCell(row, "F", true, false), e.currentTarget.value)}
                  onkeydown={(e) =>
                    onCellKeydown(
                      e,
                      buildCell(row, "F", true, false),
                      (e.currentTarget as HTMLInputElement).value,
                    )}
                />
              </td>
              <td class="col-tag">
                <input
                  type="text"
                  class="sheet-input"
                  class:active-cell={activeCellRef === `G${row}`}
                  class:selected-range={isCellInSelection(`G${row}`)}
                  data-cell-ref={`G${row}`}
                  value={getCellDisplayValue(`G${row}`, entry.tag)}
                  onmousedown={(e) => {
                    if (onCellPointerDown(buildCell(row, "G", true, false), e)) return;
                  }}
                  onmouseenter={(e) => onCellPointerEnter(buildCell(row, "G", true, false), e)}
                  onmouseup={(e) => onCellPointerUp(buildCell(row, "G", true, false), e)}
                  onfocus={() => onCellFocus(buildCell(row, "G", true, false))}
                  oninput={(e) => onCellInput(buildCell(row, "G", true, false), e.currentTarget.value)}
                  onblur={(e) => onCellCommit(buildCell(row, "G", true, false), e.currentTarget.value)}
                  onkeydown={(e) =>
                    onCellKeydown(
                      e,
                      buildCell(row, "G", true, false),
                      (e.currentTarget as HTMLInputElement).value,
                    )}
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
  .sheet-input.active-cell { box-shadow: inset 0 0 0 1px rgba(102, 171, 255, 0.65); background: rgba(102, 171, 255, 0.09); }
  .sheet-input.selected-range { background: rgba(102, 171, 255, 0.12); }

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

</style>
