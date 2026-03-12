<script lang="ts">
  import ColorPicker from "$lib/ui/ColorPicker.svelte";
  import FilterTreeEditor from "$lib/search/FilterTreeEditor.svelte";
  import type {
    FilterGroup,
    FilterLeaf,
    FilterSet,
    FilterTreeNode,
    SearchFilter,
  } from "$lib/search/protocol";
  import { flatFiltersToExpression } from "$lib/search/protocol";

  let {
    fs,
    isCollapsed,
    onToggle,
    onColorChange,
    onUpdate,
    onUnapply,
    onDelete,
  }: {
    fs: FilterSet;
    isCollapsed: boolean;
    onToggle: () => void;
    onColorChange: (color: string) => void;
    onUpdate: (name: string, root: FilterGroup) => Promise<void>;
    onUnapply: () => void;
    onDelete: () => void;
  } = $props();

  let nameInput: HTMLInputElement | undefined = $state(undefined);
  let nameDraft = $state(fs.name);
  let localRoot = $state<FilterGroup>({
    kind: "group",
    op: "ALL",
    children: [],
  });
  let saving = $state(false);

  $effect(() => {
    nameDraft = fs.name;
  });

  $effect(() => {
    const next =
      fs.filtersTree &&
      typeof fs.filtersTree === "object" &&
      fs.filtersTree.kind === "group"
        ? (fs.filtersTree as FilterGroup)
        : flatFiltersToExpression(fs.filters, fs.logic).root;
    localRoot = next;
  });

  function handleNameKeyDown(e: KeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault();
      handleUpdate();
      nameInput?.blur();
    } else if (e.key === "Escape") {
      nameDraft = fs.name;
      nameInput?.blur();
    }
  }

  function getGroupAt(root: FilterGroup, path: string): FilterGroup | null {
    if (!path) return root;
    const parts = path.split(".");
    let node: FilterGroup | FilterLeaf | null = root;
    for (const p of parts) {
      if (!node || node.kind !== "group") return null;
      const idx = parseInt(p, 10);
      if (Number.isNaN(idx) || idx < 0 || idx >= node.children.length)
        return null;
      const child: FilterTreeNode | undefined = node.children[idx];
      node = child?.kind === "group" ? child : null;
    }
    return node && node.kind === "group" ? node : null;
  }

  function addFilterAt(parentPath: string) {
    const parent = getGroupAt(localRoot, parentPath);
    if (!parent) return;
    const newLeaf: FilterLeaf = { kind: "leaf", mode: "class" };
    const next = JSON.parse(JSON.stringify(localRoot)) as FilterGroup;
    const p = getGroupAt(next, parentPath);
    if (p) p.children.push(newLeaf);
    localRoot = next;
  }

  function addSubgroupAt(parentPath: string) {
    const parent = getGroupAt(localRoot, parentPath);
    if (!parent) return;
    const newGroup: FilterGroup = { kind: "group", op: "ALL", children: [] };
    const next = JSON.parse(JSON.stringify(localRoot)) as FilterGroup;
    const p = getGroupAt(next, parentPath);
    if (p) p.children.push(newGroup);
    localRoot = next;
  }

  function updateLeafAt(path: string, patch: Partial<SearchFilter>) {
    const parts = path.split(".");
    const next = JSON.parse(JSON.stringify(localRoot)) as FilterGroup;
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
      localRoot = next;
    }
  }

  function removeLeafAt(path: string) {
    const parts = path.split(".");
    const next = JSON.parse(JSON.stringify(localRoot)) as FilterGroup;
    let node: FilterGroup = next;
    for (let i = 0; i < parts.length - 1; i++) {
      const idx = parseInt(parts[i], 10);
      const child = node.children[idx];
      if (!child || child.kind !== "group") return;
      node = child;
    }
    const lastIdx = parseInt(parts[parts.length - 1], 10);
    node.children = node.children.filter((_, i) => i !== lastIdx);
    localRoot = next;
  }

  function updateSubgroupAt(path: string, op: "ALL" | "ANY") {
    const next = JSON.parse(JSON.stringify(localRoot)) as FilterGroup;
    const target = getGroupAt(next, path);
    if (target) target.op = op;
    localRoot = next;
  }

  function removeSubgroupAt(path: string) {
    const parts = path.split(".");
    if (parts.length === 1) {
      const idx = parseInt(path, 10);
      if (Number.isNaN(idx) || idx < 0 || idx >= localRoot.children.length)
        return;
      const child = localRoot.children[idx];
      if (child?.kind !== "group") return;
      const next = JSON.parse(JSON.stringify(localRoot)) as FilterGroup;
      next.children = next.children.filter((_, i) => i !== idx);
      localRoot = next;
      return;
    }
    const parentPath = parts.slice(0, -1).join(".");
    const lastIdx = parseInt(parts[parts.length - 1], 10);
    const parent = getGroupAt(localRoot, parentPath);
    if (!parent) return;
    const next = JSON.parse(JSON.stringify(localRoot)) as FilterGroup;
    const p = getGroupAt(next, parentPath);
    if (!p) return;
    p.children = p.children.filter((_, i) => i !== lastIdx);
    localRoot = next;
  }

  async function handleUpdate() {
    saving = true;
    console.log("handleUpdate", nameDraft, localRoot);
    try {
      await onUpdate(nameDraft, localRoot);
    } finally {
      saving = false;
    }
  }
</script>

<div class="applied-item" class:collapsed={isCollapsed}>
  <div class="applied-item-header">
    <div class="header-main">
      <ColorPicker color={fs.color} onchange={onColorChange} />
      <input
        bind:this={nameInput}
        class="applied-name-input"
        type="text"
        bind:value={nameDraft}
        onblur={() => handleUpdate()}
        onkeydown={handleNameKeyDown}
      />
    </div>
    <button
      type="button"
      class="applied-item-toggle"
      aria-label={isCollapsed ? "Expand" : "Collapse"}
      aria-expanded={!isCollapsed}
      onclick={onToggle}
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
    <div class="filter-list">
      <FilterTreeEditor
        root={localRoot}
        onUpdateRootOp={(op) => {
          const next = JSON.parse(JSON.stringify(localRoot)) as FilterGroup;
          next.op = op;
          localRoot = next;
        }}
        onAddFilter={addFilterAt}
        onAddSubgroup={addSubgroupAt}
        onUpdateLeaf={updateLeafAt}
        onUpdateSubgroup={updateSubgroupAt}
        onRemoveSubgroup={removeSubgroupAt}
        onRemoveLeaf={removeLeafAt}
        openMenuPath={null}
        onToggleMenu={() => {}}
      />
    </div>

    <div class="item-footer">
      <div class="footer-actions">
        <button
          type="button"
          class="btn btn-primary btn-sm"
          disabled={saving}
          onclick={handleUpdate}
        >
          {saving ? "Updating…" : "Update"}
        </button>
        <button
          type="button"
          class="btn btn-secondary btn-sm"
          onclick={onUnapply}
        >
          Unapply
        </button>
        <button type="button" class="btn btn-danger btn-sm" onclick={onDelete}>
          Delete
        </button>
      </div>
    </div>
  {/if}
</div>

<style>
  .applied-item {
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 12px;
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    transition: all 0.2s ease;
    min-width: 0;
    overflow: hidden;
  }

  .applied-item:hover {
    border-color: var(--color-border-default);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  }

  .applied-item.collapsed {
    padding-bottom: 0.75rem;
  }

  .applied-item-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }

  .header-main {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex: 1;
    min-width: 0;
  }

  .applied-name-input {
    flex: 1;
    min-width: 0;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 0.25rem 0.5rem;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--color-text-primary);
    outline: none;
    transition: all 0.15s ease;
  }

  .applied-name-input:hover {
    background: var(--color-bg-elevated);
    border-color: var(--color-border-subtle);
  }

  .applied-name-input:focus {
    background: var(--color-bg-surface);
    border-color: var(--color-border-strong);
    box-shadow: 0 0 0 2px
      color-mix(in srgb, var(--color-border-strong) 10%, transparent);
  }

  .applied-item-toggle {
    background: none;
    border: none;
    padding: 0.25rem;
    border-radius: 6px;
    color: var(--color-text-muted);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .applied-item-toggle:hover {
    background: var(--color-bg-elevated);
    color: var(--color-text-secondary);
  }

  .chevron {
    transition: transform 0.2s ease;
  }

  .chevron.rotated {
    transform: rotate(-90deg);
  }

  .filter-list {
    padding-left: 0;
    min-width: 0;
    overflow-x: auto;
    overflow-y: visible;
  }

  .item-footer {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 0.5rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--color-border-subtle);
  }

  .footer-actions {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
</style>
