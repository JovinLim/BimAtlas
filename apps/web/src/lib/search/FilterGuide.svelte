<script lang="ts">
  let { open, onclose }: { open: boolean; onclose: () => void } = $props();

  $effect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onclose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
</script>

{#if open}
  <!-- svelte-ignore a11y_no_static_element_interactions a11y_click_events_have_key_events -->
  <div class="guide-backdrop" onclick={onclose} role="presentation">
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
          onclick={onclose}
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
      <div class="guide-body">
        <h4>Filter sets</h4>
        <p>
          A filter set is a named collection of filters you can save and reuse.
          Each set uses Match ALL or Match ANY: filters inside a set are combined
          with that logic. When multiple sets are applied, they are combined
          with the combination logic shown above the applied list.
        </p>

        <h4>Adding filters</h4>
        <p>
          Create a new filter set with <strong>New Filter Set</strong>, add
          filters with <strong>Add Filter</strong>, then save. Or select
          existing sets and click <strong>Apply</strong>. You can also add
          filters to applied sets and click <strong>Update</strong>.
        </p>

        <h4>Class filters</h4>
        <p>
          Match IFC entity classes (e.g. <code>IfcWall</code>, <code>IfcDoor</code
          >). Use <strong>is</strong> for exact match, <strong>is not</strong> to
          exclude, or <strong>inherits from</strong> to include the class and
          all its descendants (e.g. walls and subtypes).
        </p>

        <h4>Attribute filters</h4>
        <p>
          Match entity attributes at any depth in the JSONB data. Enter the
          attribute key (e.g. <code>Name</code>, <code>PropertySets</code>) and
          value. Choose the operator (is, contains, starts with, etc.) and data
          type (String, Numeric, or Object). For nested keys like
          <code>PropertySets</code>, use <strong>Object</strong> type to match
          object key names (e.g. <code>Pset_WallCommon</code>).
        </p>

        <h4>Relation filters</h4>
        <p>
          Match entities by IFC relationships (e.g.
          <code>IfcRelContainedInSpatialStructure</code>,
          <code>IfcRelVoidsElement</code>). Choose the relation type, then
          optionally specify the related entity: its IFC class (e.g.
          <code>IFCBuildingStorey</code>) and attributes (e.g. Name, string,
          &quot;Ground Floor&quot;). The filter finds entities that have the
          relation to entities matching that class and attribute criteria.
        </p>
      </div>
    </div>
  </div>
{/if}

<style>
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
    max-width: 600px;
    max-height: 85%;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.15);
  }

  .guide-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.25rem;
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .guide-header h3 {
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-text-primary);
    margin: 0;
  }

  .guide-body {
    padding: 1.25rem;
    overflow-y: auto;
    font-size: 0.85rem;
    line-height: 1.6;
    color: var(--color-text-secondary);
  }

  .guide-body h4 {
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--color-text-primary);
    margin: 1.25rem 0 0.5rem;
  }

  .guide-body h4:first-child {
    margin-top: 0;
  }

  .guide-body p {
    margin: 0 0 0.75rem;
  }

  .guide-body code {
    background: var(--color-bg-elevated);
    padding: 0.1rem 0.35rem;
    border-radius: 0.25rem;
    font-size: 0.8rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  }
</style>
