<script lang="ts">
/**
 * Dedicated viewer popup/tab.
 * Matches layout/style of other popup pages (graph, table, etc.).
 * Loads currently filtered products with geometry.
 */
import { onDestroy, onMount } from "svelte";
import { page } from "$app/stores";
import { loadSettings } from "$lib/state/persistence";
import { getWorkspaceState } from "$lib/state/workspace.svelte";
import ViewerRuntime from "$lib/ui/ViewerRuntime.svelte";

const workspace = getWorkspaceState();

let branchId = $state<string | null>(null);
let projectId = $state<string | null>(null);
let revision = $state<number | null>(null);
let projectName = $state<string | null>(null);
let branchName = $state<string | null>(null);
let reloadNonce = $state(0);

let channel: BroadcastChannel | null = null;
let lastPublishedSelection = $state<string | null>(null);

onMount(() => {
	const url = $page.url;
	const p = url.searchParams.get("projectId");
	const b = url.searchParams.get("branchId");
	const r = url.searchParams.get("revision");
	if (p) projectId = p;
	if (b) branchId = b;
	if (r) revision = Number(r);

	// Sync from workspace/settings if available
	if (workspace.activeProjectId) projectId = workspace.activeProjectId;
	if (workspace.activeBranchId) branchId = workspace.activeBranchId;
	if (workspace.activeRevision !== undefined)
		revision = workspace.activeRevision;
	const settings = loadSettings();
	if (projectId == null && settings?.activeProjectId)
		projectId = settings.activeProjectId;
	if (branchId == null && settings?.activeBranchId)
		branchId = settings.activeBranchId;
	if (revision == null && settings?.activeRevision != null)
		revision = settings.activeRevision;

	// Hydrate shared workspace state used by ViewerRuntime
	workspace.activeProjectId = projectId;
	workspace.activeBranchId = branchId;
	workspace.activeRevision = revision;

	// Listen for context from main page (includes names + revision)
	channel = new BroadcastChannel("viewer");
	channel.onmessage = handleContextMessage;
	channel.postMessage({ type: "request-context" });
});

function handleContextMessage(e: MessageEvent) {
	const msg = e.data;
	if (msg.type === "context" || msg.type === "workspace-context") {
		projectId = msg.projectId ?? projectId;
		branchId = msg.branchId ?? branchId;
		revision = msg.revision ?? revision;
		projectName = msg.projectName ?? projectName ?? null;
		branchName = msg.branchName ?? branchName ?? null;
		workspace.activeProjectId = projectId;
		workspace.activeBranchId = branchId;
		workspace.activeRevision = revision;
		reloadNonce += 1;
	} else if (msg.type === "reload") {
		reloadNonce += 1;
	}
}

// Publish selection changes back to workspace shell (main window).
// This lets other pop-outs (like Attributes) react to viewer picks.
$effect(() => {
	if (!channel) return;
	const globalId = workspace.activeGlobalId ?? null;
	if (globalId === lastPublishedSelection) return;
	lastPublishedSelection = globalId;
	channel.postMessage({
		type: "selection-changed",
		globalId,
	});
});

// Keep synced with workspace and main page context messages
$effect(() => {
	projectId = workspace.activeProjectId ?? projectId;
	branchId = workspace.activeBranchId ?? branchId;
	if (workspace.activeRevision != null) revision = workspace.activeRevision;
});

onDestroy(() => {
	channel?.close();
});
</script>

<svelte:head>
  <title>Viewer • BimAtlas</title>
</svelte:head>

<div class="viewer-page">
  <header class="page-header">
    <div class="page-header-title-row">
      <h2>Viewer</h2>
    </div>
    {#if branchId || projectId}
      <span class="context-pill">
        {projectName ?? projectId ?? '—'} / {branchName ?? branchId ?? '—'}
        {#if revision != null}<span class="mono">(rev {revision})</span>{/if}
      </span>
    {:else}
      <span class="context-pill empty">Waiting for context…</span>
    {/if}
  </header>

  <div class="viewer-runtime-host">
    <ViewerRuntime {workspace} {branchId} {revision} reloadKey={reloadNonce} />
  </div>
</div>

<style>
  .viewer-page {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }

  .viewer-runtime-host {
    flex: 1 1 0;
    min-height: 0;
  }
</style>
