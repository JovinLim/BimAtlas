<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { page } from "$app/stores";
  import AttributePanelContent from "$lib/ui/AttributePanelContent.svelte";
  import {
    ATTRIBUTES_CHANNEL,
    type AttributesMessage,
  } from "$lib/attributes/protocol";
  import { loadSettings } from "$lib/state/persistence";

  let branchId = $state<string | null>(null);
  let projectId = $state<string | null>(null);
  let branchName = $state<string | null>(null);
  let projectName = $state<string | null>(null);
  let revision = $state<number | null>(null);
  let globalId = $state<string | null>(null);

  let channel: BroadcastChannel | null = null;
  let contextRetryTimeout: ReturnType<typeof setTimeout> | null = null;
  let contextRetryInterval: ReturnType<typeof setInterval> | null = null;
  let lastContextKey: string | null = null;
  let lastSelectionSent: string | null = null;

  function applyContextFromUrl() {
    const url = $page.url;
    const b = url.searchParams.get("branchId");
    const p = url.searchParams.get("projectId");
    const r = url.searchParams.get("revision");
    const g = url.searchParams.get("globalId");
    if (b != null && b !== "") branchId = b;
    if (p != null && p !== "") projectId = p;
    if (r != null && r !== "") {
      const parsed = Number(r);
      revision = Number.isNaN(parsed) ? null : parsed;
    }
    if (g != null && g !== "") globalId = g;
  }

  function applyContextFallbackFromSettings() {
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
    if (globalId == null && settings.activeGlobalId != null) {
      globalId = settings.activeGlobalId;
    }
  }

  function syncUrlWithContext() {
    const params = new URLSearchParams($page.url.searchParams);
    if (branchId != null) params.set("branchId", String(branchId));
    else params.delete("branchId");
    if (projectId != null) params.set("projectId", String(projectId));
    else params.delete("projectId");
    if (revision != null) params.set("revision", String(revision));
    else params.delete("revision");
    if (globalId != null) params.set("globalId", String(globalId));
    else params.delete("globalId");
    const nextQuery = params.toString();
    const currentQuery = $page.url.searchParams.toString();
    if (nextQuery === currentQuery) return;
    window.history.replaceState(null, "", `${$page.url.pathname}?${nextQuery}`);
  }

  function contextKey(msg: Extract<AttributesMessage, { type: "context" }>): string {
    return JSON.stringify({
      branchId: msg.branchId,
      projectId: msg.projectId,
      branchName: msg.branchName ?? null,
      projectName: msg.projectName ?? null,
      revision: msg.revision,
      globalId: msg.globalId,
    });
  }

  function handleContextMessage(msg: Extract<AttributesMessage, { type: "context" }>) {
    const nextContextKey = contextKey(msg);
    if (nextContextKey === lastContextKey) return;
    lastContextKey = nextContextKey;

    branchId = msg.branchId;
    projectId = msg.projectId;
    branchName = msg.branchName ?? null;
    projectName = msg.projectName ?? null;
    revision = msg.revision;
    globalId = msg.globalId;
    syncUrlWithContext();

    if (contextRetryInterval != null) {
      clearInterval(contextRetryInterval);
      contextRetryInterval = null;
    }
  }

  type AttributesMessageHandlers = {
    [K in AttributesMessage["type"]]?: (
      message: Extract<AttributesMessage, { type: K }>,
    ) => void;
  };

  const attributesMessageHandlers: AttributesMessageHandlers = {
    context: handleContextMessage,
    "selection-changed": (message) => {
      if (globalId === message.globalId) return;
      globalId = message.globalId;
    },
    "close-panel": () => {
      window.close();
    },
  };

  function handleIncomingMessage(e: MessageEvent<AttributesMessage>) {
    const msg = e.data;
    if (!msg || typeof msg.type !== "string") return;
    const handler = attributesMessageHandlers[
      msg.type as AttributesMessage["type"]
    ] as ((message: AttributesMessage) => void) | undefined;
    handler?.(msg);
  }

  function requestContext() {
    channel?.postMessage({ type: "request-context" } satisfies AttributesMessage);
  }

  function handleSelectGlobalId(id: string | null) {
    globalId = id;
    if (lastSelectionSent === id) return;
    lastSelectionSent = id;
    channel?.postMessage({
      type: "selection-changed",
      globalId: id,
    } satisfies AttributesMessage);
  }

  onMount(() => {
    applyContextFromUrl();
    applyContextFallbackFromSettings();

    channel = new BroadcastChannel(ATTRIBUTES_CHANNEL);
    channel.onmessage = handleIncomingMessage;

    // Initial request for context from main window
    requestContext();

    // One-time delayed retry
    contextRetryTimeout = setTimeout(() => {
      if (branchId == null && projectId == null) {
        requestContext();
      }
      contextRetryTimeout = null;
    }, 1500);

    // Additional retries while we still have no context
    if (branchId == null && projectId == null) {
      let attempts = 0;
      contextRetryInterval = setInterval(() => {
        if (branchId != null || projectId != null || attempts >= 8) {
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
  });

  onDestroy(() => {
    channel?.close();
    if (contextRetryTimeout != null) clearTimeout(contextRetryTimeout);
    if (contextRetryInterval != null) clearInterval(contextRetryInterval);
  });
</script>

<svelte:head>
  <title>Attributes • BimAtlas</title>
</svelte:head>

<div class="attributes-page">
  <header class="page-header">
    <div class="page-header-title-row">
      <h2>Attributes</h2>
    </div>
    {#if branchName || projectName || branchId || projectId}
      <span class="context-pill mono">
        {projectName ?? projectId ?? "—"} / {branchName ?? branchId ?? "—"}
        {#if revision != null}(rev {revision}){/if}
      </span>
    {:else}
      <span class="context-pill empty">Waiting for context…</span>
    {/if}
  </header>

  <section class="panel-wrapper">
    <AttributePanelContent
      branchId={branchId}
      revision={revision}
      globalId={globalId}
      onSelectGlobalId={handleSelectGlobalId}
    />
  </section>
</div>

<style>
  .attributes-page {
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: var(--color-bg-canvas);
    color: var(--color-text-primary);
    font-family: system-ui, -apple-system, sans-serif;
    font-size: 0.8rem;
    overflow: hidden;
  }

  .context-pill {
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    font-size: 0.8rem;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    color: var(--color-text-primary);
    max-width: 60%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-align: right;
  }

  .context-pill.empty {
    opacity: 0.7;
    font-style: italic;
  }

  .mono {
    font-family: "SF Mono", "Fira Code", monospace;
  }

  .panel-wrapper {
    flex: 1 1 0;
    min-height: 0;
    padding: 1rem 1.25rem;
    overflow-y: auto;
    box-sizing: border-box;
  }
</style>

