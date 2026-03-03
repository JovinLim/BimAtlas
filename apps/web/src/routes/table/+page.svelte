<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { page } from "$app/stores";
  import {
    TABLE_CHANNEL,
    TABLE_PROTOCOL_VERSION,
    type TableMessage,
  } from "$lib/table/protocol";
  import type { ProductMeta } from "$lib/search/protocol";
  import { TABLE_FIXTURE_PRODUCTS } from "$lib/table/fixtures";
  import { loadSettings } from "$lib/state/persistence";
  import { client, PROJECTS_QUERY } from "$lib/api/client";
  import EntityGrid from "$lib/table/EntityGrid.svelte";
  import BottomSheet, {
    type SheetEntry,
  } from "$lib/table/BottomSheet.svelte";

  let branchId = $state<string | null>(null);
  let projectId = $state<string | null>(null);
  let branchName = $state<string | null>(null);
  let projectName = $state<string | null>(null);
  let revision = $state<number | null>(null);
  /** Products from main window context, or fixture when ?fixture=1 */
  let products = $state<ProductMeta[]>([]);
  let useFixture = $state(false);
  /** Row lock state: locked rows are read-only for editable cells. */
  let lockedIds = $state<Set<string>>(new Set());
  /** Bottom sheet entries (notes / quantity surveying). Session-only for v1. */
  let sheetEntries = $state<SheetEntry[]>([]);

  let channel: BroadcastChannel | null = null;
  let contextRetryTimeout: ReturnType<typeof setTimeout> | null = null;
  let contextRetryInterval: ReturnType<typeof setInterval> | null = null;
  let hasChannelContext = $state(false);

  function applyContextFromUrl() {
    const url = $page.url;
    const b = url.searchParams.get("branchId");
    const p = url.searchParams.get("projectId");
    const r = url.searchParams.get("revision");
    const fixtureParam = url.searchParams.get("fixture");
    if (b != null && b !== "") branchId = b;
    if (p != null && p !== "") projectId = p;
    if (r != null && r !== "") {
      const parsed = Number(r);
      revision = Number.isNaN(parsed) ? null : parsed;
    }
    useFixture = fixtureParam === "1" || fixtureParam === "true";
    if (useFixture) {
      products = [...TABLE_FIXTURE_PRODUCTS];
    }
  }

  function applyContextFallbackFromSettings() {
    if (useFixture) return;
    const settings = loadSettings();
    if (!settings) return;
    if (branchId == null && settings.activeBranchId != null) {
      branchId = settings.activeBranchId;
    }
    if (projectId == null && settings.activeProjectId != null) {
      projectId = settings.activeProjectId;
    }
    if (revision == null && settings.activeRevision != null) {
      revision = settings.activeRevision;
    }
  }

  function handleIncomingMessage(e: MessageEvent<TableMessage>) {
    const msg = e.data;
    if (msg.type === "context" && msg.version === TABLE_PROTOCOL_VERSION) {
      if (useFixture) return;
      hasChannelContext = true;
      branchId = msg.branchId;
      projectId = msg.projectId;
      branchName = msg.branchName ?? null;
      projectName = msg.projectName ?? null;
      revision = msg.revision;
      products = msg.products ?? [];

      const params = new URLSearchParams($page.url.searchParams);
      if (branchId != null) params.set("branchId", String(branchId));
      else params.delete("branchId");
      if (projectId != null) params.set("projectId", String(projectId));
      else params.delete("projectId");
      if (revision != null) params.set("revision", String(revision));
      else params.delete("revision");
      window.history.replaceState(
        null,
        "",
        `${$page.url.pathname}?${params.toString()}`,
      );

      if (contextRetryInterval != null) {
        clearInterval(contextRetryInterval);
        contextRetryInterval = null;
      }
    }
  }

  function requestContext() {
    channel?.postMessage({ type: "request-context" } satisfies TableMessage);
  }

  async function resolveNamesFromProjects() {
    if (!projectId || !branchId) return;
    if (projectName && branchName) return;
    try {
      const result = await client.query(PROJECTS_QUERY, {}).toPromise();
      const project = result.data?.projects?.find(
        (p: { id: string; name: string; branches: { id: string; name: string }[] }) =>
          p.id === projectId,
      );
      if (project) {
        projectName = project.name ?? projectName;
        const branch = project.branches?.find(
          (b: { id: string; name: string }) => b.id === branchId,
        );
        if (branch) branchName = branch.name ?? branchName;
      }
    } catch {
      // Non-blocking fallback; keep IDs if name lookup fails.
    }
  }

  function toggleLock(globalId: string) {
    const next = new Set(lockedIds);
    if (next.has(globalId)) {
      next.delete(globalId);
    } else {
      next.add(globalId);
    }
    lockedIds = next;
  }

  onMount(() => {
    applyContextFromUrl();
    applyContextFallbackFromSettings();
    void resolveNamesFromProjects();

    channel = new BroadcastChannel(TABLE_CHANNEL);
    channel.onmessage = handleIncomingMessage;

    if (!useFixture) {
      requestContext();
      contextRetryTimeout = setTimeout(() => {
        if (!hasChannelContext && !useFixture) {
          requestContext();
        }
        contextRetryTimeout = null;
      }, 1500);

      if (!hasChannelContext && !useFixture) {
        let attempts = 0;
        contextRetryInterval = setInterval(() => {
          if (
            hasChannelContext ||
            useFixture ||
            attempts >= 8
          ) {
            if (contextRetryInterval != null) {
              clearInterval(contextRetryInterval);
              contextRetryInterval = null;
            }
            return;
          }
          requestContext();
          attempts += 1;
        }, 1000);
      }
    }
  });

  onDestroy(() => {
    channel?.close();
    if (contextRetryTimeout != null) clearTimeout(contextRetryTimeout);
    if (contextRetryInterval != null) clearInterval(contextRetryInterval);
  });
</script>

<div class="table-page">
  <header class="table-header">
    <h2>Table</h2>
    {#if useFixture}
      <span class="context-pill fixture">Fixture data</span>
    {:else if branchName || projectName || branchId || projectId}
      <span class="context-pill mono">
        {projectName ?? projectId ?? "—"} / {branchName ?? branchId ?? "—"}
        {#if revision != null}(rev {revision}){/if}
      </span>
    {:else}
      <span class="context-pill empty">Waiting for context…</span>
    {/if}
  </header>

  <div class="table-split">
    <section class="table-segment table-segment-top" aria-label="IFC entities">
      <p class="segment-label">Entities ({products.length})</p>
      <EntityGrid
        products={products}
        lockedIds={lockedIds}
        onToggleLock={toggleLock}
      />
    </section>
    <section class="table-segment table-segment-bottom" aria-label="Sheet interactions">
      <BottomSheet bind:entries={sheetEntries} rowStart={products.length + 2} />
    </section>
  </div>
</div>

<style>
  .table-page {
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: #1a1a2e;
    color: #e0e0e0;
    font-family: system-ui, -apple-system, sans-serif;
    overflow: hidden;
  }

  .table-header {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .table-header h2 {
    margin: 0;
    font-size: 0.95rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #ff8866;
  }

  .context-pill {
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    font-size: 0.72rem;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: #ccc;
    max-width: 60%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .context-pill.empty {
    opacity: 0.7;
    font-style: italic;
  }

  .context-pill.fixture {
    color: #8f8;
  }

  .mono {
    font-family: "SF Mono", "Fira Code", monospace;
  }

  .table-split {
    flex: 1 1 0;
    min-height: 0;
    display: grid;
    grid-template-rows: minmax(0, 1fr) minmax(190px, 38%);
  }

  .table-segment {
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
  }

  .table-segment-top {
    min-height: 0;
    overflow: auto;
  }

  .table-segment-bottom {
    min-height: 0;
    overflow: auto;
  }

</style>
