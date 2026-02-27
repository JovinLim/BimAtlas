<script lang="ts">
  /**
   * Overlay panel that shows details of the currently selected IFC element.
   * Now delegates rendering and data-fetch to AttributePanelContent so the
   * same content can be used in a pop-out tab.
   */
  import {
    getSelection,
    getRevisionState,
    getProjectState,
  } from "$lib/state/selection.svelte";
  import AttributePanelContent from "$lib/ui/AttributePanelContent.svelte";

  const selection = getSelection();
  const revisionState = getRevisionState();
  const projectState = getProjectState();
</script>

{#if selection.activeGlobalId}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions a11y_click_events_have_key_events -->
  <aside class="selection-panel">
    <header class="panel-header">
      <h3>Attribute Panel</h3>
      <button class="close-btn" onclick={() => (selection.activeGlobalId = null)}>
        &times;
      </button>
    </header>

    <AttributePanelContent
      branchId={projectState.activeBranchId}
      revision={revisionState.activeRevision}
      globalId={selection.activeGlobalId}
      onSelectGlobalId={(id: string | null) => (selection.activeGlobalId = id)}
    />
  </aside>
{/if}

<style>
	.selection-panel {
		position: absolute;
		top: 1rem;
		right: 1rem;
		bottom: 1rem;
		background: rgba(26, 26, 46, 0.92);
		color: #e0e0e0;
		padding: 1rem;
		border-radius: 0.5rem;
		min-width: 260px;
		max-width: 360px;
		max-height: calc(100% - 2rem);
		display: flex;
		flex-direction: column;
		min-height: 0;
		font-family: system-ui, -apple-system, sans-serif;
		font-size: 0.85rem;
		box-shadow: 0 4px 24px rgba(0, 0, 0, 0.4);
		backdrop-filter: blur(8px);
		z-index: 10;
		user-select: text;
		-webkit-user-select: text;
		pointer-events: auto;
	}

	.panel-header {
		flex-shrink: 0;
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.75rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
		padding-bottom: 0.5rem;
	}

	.panel-body {
		flex: 1 1 0;
		min-height: 0;
		display: flex;
		flex-direction: column;
		overflow-y: auto;
		overflow-x: hidden;
	}

	h3 {
		margin: 0;
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #ff6644;
	}

	.close-btn {
		background: none;
		border: none;
		color: #888;
		font-size: 1.2rem;
		cursor: pointer;
		padding: 0 0.25rem;
		line-height: 1;
	}
	.close-btn:hover {
		color: #fff;
	}

	.panel-body .detail {
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		margin-bottom: 0.6rem;
	}

	.value-row {
		display: flex;
		align-items: flex-start;
		gap: 0.35rem;
		min-width: 0;
	}

	.value-row .value {
		flex: 1;
		min-width: 0;
	}

	.copy-btn {
		flex-shrink: 0;
		background: none;
		border: none;
		color: #888;
		cursor: pointer;
		padding: 0.2rem;
		line-height: 0;
		border-radius: 0.25rem;
	}
	.copy-btn:hover {
		color: #ff6644;
		background: rgba(255, 102, 68, 0.1);
	}

	.label {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: #888;
	}

	.value {
		color: #ddd;
		word-break: break-all;
	}

	.mono {
		font-family: 'SF Mono', 'Fira Code', monospace;
		font-size: 0.78rem;
	}

	.badge {
		display: inline-block;
		background: rgba(255, 102, 68, 0.15);
		color: #ff8866;
		padding: 0.1rem 0.4rem;
		border-radius: 0.25rem;
		font-size: 0.78rem;
		width: fit-content;
	}

	.badge.secondary {
		background: rgba(100, 181, 246, 0.18);
		color: #64b5f6;
	}

	.link-btn {
		background: none;
		border: none;
		color: #5dade2;
		cursor: pointer;
		padding: 0;
		font-size: 0.82rem;
		text-align: left;
	}
	.link-btn:hover {
		text-decoration: underline;
		color: #85c1e9;
	}

	.relations-section {
		margin-top: 0.5rem;
		padding-top: 0.5rem;
		border-top: 1px solid rgba(255, 255, 255, 0.08);
	}

	.relation-list {
		list-style: none;
		padding: 0;
		margin: 0.3rem 0 0;
	}

	.relation-list li {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 0.5rem;
		padding: 0.2rem 0;
		min-height: 1.5em;
	}

	.relation-list li .link-btn {
		flex: 1;
		min-width: 0;
		word-break: break-word;
	}

	.rel-type {
		font-size: 0.65rem;
		color: #666;
		text-align: right;
		white-space: normal;
		word-break: break-word;
		flex-shrink: 0;
		max-width: 55%;
	}

	.pset-list {
		margin-top: 0.4rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.pset-list details {
		background: rgba(255, 255, 255, 0.02);
		border-radius: 0.25rem;
		padding: 0.25rem 0.4rem;
	}

	.pset-list summary {
		cursor: pointer;
		color: #ccc;
	}

	.pset-props {
		list-style: none;
		padding: 0.25rem 0 0.35rem 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}

	.pset-key {
		font-size: 0.75rem;
		color: #aaa;
		margin-right: 0.4rem;
	}

	.pset-value {
		font-size: 0.8rem;
		color: #ddd;
		word-break: break-all;
	}

	.panel-body .status-msg {
		flex-shrink: 0;
		color: #888;
		margin: 0.5rem 0;
		font-size: 0.82rem;
	}

	.error {
		color: #e57373;
	}
</style>
