<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { page } from "$app/stores";
  import { loadSettings } from "$lib/state/persistence";
  import { client, VALIDATION_RESULTS_QUERY, PROJECTS_QUERY } from "$lib/api/client";
  import { SCHEMA_CHANNEL, type SchemaMessage } from "$lib/schema/protocol";
  import { ATTRIBUTES_CHANNEL, type AttributesMessage } from "$lib/attributes/protocol";

  type Violation = {
    globalId: string;
    ifcClass: string;
    message: string;
  };

  type RuleResult = {
    ruleGlobalId: string;
    ruleName: string;
    severity: string;
    passed: boolean;
    violations: Violation[];
  };

  type RunResult = {
    schemaGlobalId: string;
    schemaName: string;
    branchId: string;
    revisionSeq: number;
    errorCount: number;
    warningCount: number;
    infoCount: number;
    passedCount: number;
    results: RuleResult[];
  };

  let branchId = $state<string | null>(null);
  let projectId = $state<string | null>(null);
  let projectName = $state<string | null>(null);
  let branchName = $state<string | null>(null);
  let revision = $state<number | null>(null);

  let loading = $state(false);
  let error = $state<string | null>(null);
  let runResults = $state<RunResult[]>([]);
  /** Expanded rule rows: "runIndex:ruleGlobalId" */
  let expandedRules = $state<Set<string>>(new Set());
  /** Expanded run cards (show rules table): run index */
  let expandedRunCards = $state<Set<number>>(new Set());

  let channel: BroadcastChannel | null = null;
  let attributesChannel: BroadcastChannel | null = null;
  let contextRetryTimeout: ReturnType<typeof setTimeout> | null = null;
  let contextRetryInterval: ReturnType<typeof setInterval> | null = null;

  function selectInViewer(globalId: string) {
    attributesChannel?.postMessage({
      type: "selection-changed",
      globalId,
    } satisfies AttributesMessage);
  }

  const hasAnyResults = $derived(runResults.length > 0);

  const overallSummary = $derived.by(() => {
    const summary = {
      errors: 0,
      warnings: 0,
      info: 0,
      passed: 0,
    };
    for (const r of runResults) {
      summary.errors += r.errorCount ?? 0;
      summary.warnings += r.warningCount ?? 0;
      summary.info += r.infoCount ?? 0;
      summary.passed += r.passedCount ?? 0;
    }
    return summary;
  });

  function applyContextFromUrl() {
    const url = $page.url;
    const b = url.searchParams.get("branchId");
    const p = url.searchParams.get("projectId");
    const r = url.searchParams.get("revision");
    if (b) branchId = b;
    if (p) projectId = p;
    if (r) {
      const parsed = Number(r);
      revision = Number.isNaN(parsed) ? null : parsed;
    }
  }

  function applyContextFallbackFromSettings() {
    const settings = loadSettings();
    if (!settings) return;
    if (!branchId && settings.activeBranchId)
      branchId = settings.activeBranchId;
    if (!projectId && settings.activeProjectId)
      projectId = settings.activeProjectId;
    if (revision == null && settings.activeRevision != null)
      revision = settings.activeRevision;
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

  function handleIncomingMessage(e: MessageEvent<SchemaMessage>) {
    const msg = e.data;
    if (msg.type === "context") {
      branchId = msg.branchId;
      projectId = msg.projectId;
      projectName = msg.projectName ?? null;
      branchName = msg.branchName ?? null;
      revision = msg.revision;

      // Keep URL in sync so refresh preserves the latest context.
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

      // Reload results for the newly active revision.
      if (branchId) {
        void loadResults();
      }
    }
  }

  function requestContext() {
    channel?.postMessage({ type: "request-context" } satisfies SchemaMessage);
  }

  async function loadResults() {
    if (!branchId) return;
    loading = true;
    error = null;
    try {
      const variables: { branchId: string; revision: number | null } = {
        branchId,
        revision,
      };
      const result = await client
        .query(
          VALIDATION_RESULTS_QUERY,
          variables,
          { requestPolicy: "network-only" },
        )
        .toPromise();
      if (result.error) {
        error = result.error.message;
        runResults = [];
        return;
      }
      runResults = (result.data?.validationResults ?? []) as RunResult[];
    } catch (e: any) {
      error = e?.message ?? "Failed to load validation results.";
      runResults = [];
    } finally {
      loading = false;
    }
  }

  function formatRevisionLabel(): string {
    if (revision == null) return "Latest revision";
    return `Revision #${revision}`;
  }

  function formatRunRevisionLabel(run: RunResult): string {
    return `rev ${run.revisionSeq}`;
  }

  function hasRunCounts(run: RunResult): boolean {
    return (
      (run.errorCount ?? 0) > 0 ||
      (run.warningCount ?? 0) > 0 ||
      (run.infoCount ?? 0) > 0 ||
      (run.passedCount ?? 0) > 0
    );
  }

  function ruleRowKey(runIndex: number, rule: RuleResult): string {
    return `${runIndex}:${rule.ruleGlobalId}`;
  }

  function toggleRuleExpanded(runIndex: number, rule: RuleResult) {
    const key = ruleRowKey(runIndex, rule);
    const next = new Set(expandedRules);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    expandedRules = next;
  }

  function isRuleExpanded(runIndex: number, rule: RuleResult): boolean {
    return expandedRules.has(ruleRowKey(runIndex, rule));
  }

  function toggleRunCardExpanded(runIndex: number) {
    const next = new Set(expandedRunCards);
    if (next.has(runIndex)) next.delete(runIndex);
    else next.add(runIndex);
    expandedRunCards = next;
  }

  function isRunCardExpanded(runIndex: number): boolean {
    return expandedRunCards.has(runIndex);
  }

  onMount(() => {
    applyContextFromUrl();
    applyContextFallbackFromSettings();

    channel = new BroadcastChannel(SCHEMA_CHANNEL);
    channel.onmessage = handleIncomingMessage;
    attributesChannel = new BroadcastChannel(ATTRIBUTES_CHANNEL);

    // Initial request for context from the main window.
    requestContext();

    // One-time delayed retry in case the main page wasn't ready yet.
    contextRetryTimeout = setTimeout(() => {
      if (branchId == null && projectId == null) {
        requestContext();
      }
      contextRetryTimeout = null;
    }, 1500);

    // Additional retries while we still have no context.
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

    // If we already had context from URL/settings, load immediately.
    if (branchId) {
      void loadResults();
      void resolveNamesFromProjects();
    }
  });

  onDestroy(() => {
    channel?.close();
    attributesChannel?.close();
    if (contextRetryTimeout != null) clearTimeout(contextRetryTimeout);
    if (contextRetryInterval != null) clearInterval(contextRetryInterval);
  });
</script>

<svelte:head>
  <title>Validation • BimAtlas</title>
</svelte:head>

<div class="validation-page">
  <header class="page-header">
    <div class="header-main">
      <h2>Validation</h2>
      <p class="header-subtitle">
        Validation results for the current revision. Each schema is evaluated at most once per revision.
      </p>
    </div>
    {#if branchId}
      <div class="context-pills">
        <span class="context-pill mono">
          {projectName ?? projectId ?? "—"}, {branchName ?? branchId ?? "—"}
        </span>
        <span class="context-pill">
          {formatRevisionLabel()}
        </span>
      </div>
    {:else}
      <span class="context-pill empty">Open a project in the main view to see validation results.</span>
    {/if}
  </header>

  {#if error}
    <div class="error-bar">
      <span>{error}</span>
      <button type="button" class="btn-icon" onclick={() => (error = null)} aria-label="Dismiss error">
        ✕
      </button>
    </div>
  {/if}

  <main class="content">
    {#if !branchId}
      <div class="empty-state">
        <p>Select a project and branch in the main window, then reopen this Validation tab.</p>
      </div>
    {:else if loading}
      <div class="empty-state">
        <p>Loading validation results…</p>
      </div>
    {:else if !hasAnyResults}
      <div class="empty-state">
        <p>No validation results for this revision yet.</p>
        <p class="empty-hint">
          Run validation from the Schema Browser or validation tools, then refresh this tab.
        </p>
      </div>
    {:else}
      <!-- Overall summary -->
      <section class="overall-section">
        <div class="overall-header">
          <h3>Overall</h3>
          <span class="overall-caption">{runResults.length} schema run{runResults.length === 1 ? "" : "s"}</span>
        </div>
        <div class="stats-row">
          <div class="stat-card">
            <span class="stat-label">Errors</span>
            <div class="stat-value">
              <span class="severity-dot severity-error"></span>
              <span>{overallSummary.errors}</span>
            </div>
          </div>
          <div class="stat-card">
            <span class="stat-label">Warnings</span>
            <div class="stat-value">
              <span class="severity-dot severity-warning"></span>
              <span>{overallSummary.warnings}</span>
            </div>
          </div>
          <div class="stat-card">
            <span class="stat-label">Info</span>
            <div class="stat-value">
              <span class="severity-dot severity-info"></span>
              <span>{overallSummary.info}</span>
            </div>
          </div>
          <div class="stat-card">
            <span class="stat-label">Passed</span>
            <div class="stat-value">
              <span class="severity-dot severity-passed"></span>
              <span>{overallSummary.passed}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- Per-schema runs -->
      <section class="runs-section">
        <h3 class="section-title">Per schema</h3>
        <div class="runs-list">
          {#each runResults as run, i (`${run.schemaGlobalId}-${i}`)}
            <article class="run-card">
              <header class="run-header">
                <div class="run-title-block">
                  <h4>{run.schemaName}</h4>
                  <p class="run-meta">
                    {formatRunRevisionLabel(run)} · {run.results.length} rule{run.results.length === 1 ? "" : "s"}
                  </p>
                </div>
                <code class="run-id mono">{run.schemaGlobalId}</code>
              </header>

              {#if hasRunCounts(run)}
                <div class="run-stats-row">
                  <div class="stat-card">
                    <span class="stat-label">Errors</span>
                    <div class="stat-value">
                      <span class="severity-dot severity-error"></span>
                      <span>{run.errorCount}</span>
                    </div>
                  </div>
                  <div class="stat-card">
                    <span class="stat-label">Warnings</span>
                    <div class="stat-value">
                      <span class="severity-dot severity-warning"></span>
                      <span>{run.warningCount}</span>
                    </div>
                  </div>
                  <div class="stat-card">
                    <span class="stat-label">Info</span>
                    <div class="stat-value">
                      <span class="severity-dot severity-info"></span>
                      <span>{run.infoCount}</span>
                    </div>
                  </div>
                  <div class="stat-card">
                    <span class="stat-label">Passed</span>
                    <div class="stat-value">
                      <span class="severity-dot severity-passed"></span>
                      <span>{run.passedCount}</span>
                    </div>
                  </div>
                </div>
              {/if}

              <div class="rules-collapsible">
                <button
                  type="button"
                  class="rules-toggle"
                  onclick={() => toggleRunCardExpanded(i)}
                  aria-expanded={isRunCardExpanded(i)}
                >
                  <span class="rules-toggle-chevron">{isRunCardExpanded(i) ? "▾" : "▸"}</span>
                  <span>{isRunCardExpanded(i) ? "Collapse Results" : "Expand Results"}</span>
                </button>
                {#if isRunCardExpanded(i)}
                <div class="rules-table-wrap">
                <table class="rules-table">
                  <thead>
                    <tr>
                      <th class="rules-th-expand"></th>
                      <th class="rules-th-name">Rule</th>
                      <th class="rules-th-severity">Severity</th>
                      <th class="rules-th-status">Status</th>
                      <th class="rules-th-fail">Fail count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {#each run.results as rule, ruleIdx}
                      {@const key = ruleRowKey(i, rule)}
                      {@const expanded = isRuleExpanded(i, rule)}
                      {@const failCount = rule.violations?.length ?? 0}
                      <tr class="rule-row" class:has-failures={failCount > 0}>
                        <td class="rules-td-expand">
                          {#if failCount > 0}
                            <button
                              type="button"
                              class="expand-btn"
                              onclick={() => toggleRuleExpanded(i, rule)}
                              aria-expanded={expanded}
                              aria-label={expanded ? "Collapse violations" : "Expand violations"}
                            >
                              {expanded ? "▾" : "▸"}
                            </button>
                          {:else}
                            <span class="expand-placeholder"></span>
                          {/if}
                        </td>
                        <td class="rules-td-name">{rule.ruleName || rule.ruleGlobalId}</td>
                        <td class="rules-td-severity">
                          <span class="severity-dot severity-{rule.severity?.toLowerCase() ?? "error"}"></span>
                          {rule.severity ?? "Error"}
                        </td>
                        <td class="rules-td-status">
                          <span class="status-badge" class:passed={rule.passed} class:failed={!rule.passed}>
                            {rule.passed ? "Pass" : "Fail"}
                          </span>
                        </td>
                        <td class="rules-td-fail">{failCount}</td>
                      </tr>
                      {#if expanded && failCount > 0}
                        <tr class="violations-row">
                          <td colspan="5">
                            <div class="violations-panel">
                              <span class="violations-label">Violating entities:</span>
                              <ul class="violations-list">
                                {#each rule.violations ?? [] as v}
                                  <li class="violation-item">
                                    <button
                                      type="button"
                                      class="violation-select-btn"
                                      onclick={() => selectInViewer(v.globalId)}
                                      title="Select in viewer"
                                    >
                                      <code class="violation-id mono">{v.globalId}</code>
                                      <span class="violation-class">{v.ifcClass}</span>
                                      {#if v.message}
                                        <span class="violation-msg">— {v.message}</span>
                                      {/if}
                                    </button>
                                  </li>
                                {/each}
                              </ul>
                            </div>
                          </td>
                        </tr>
                      {/if}
                    {/each}
                  </tbody>
                </table>
              </div>
              {/if}
              </div>
            </article>
          {/each}
        </div>
      </section>
    {/if}
  </main>
</div>

<style>
  .validation-page {
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: var(--color-bg-canvas);
    color: var(--color-text-primary);
    font-family:
      system-ui,
      -apple-system,
      sans-serif;
    overflow: hidden;
  }

  .page-header {
    flex-shrink: 0;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .header-main h2 {
    margin: 0;
    font-size: 0.95rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--color-brand-500);
  }

  .header-subtitle {
    margin: 0.15rem 0 0;
    font-size: 0.78rem;
    color: var(--color-text-secondary);
  }

  .context-pills {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    align-items: flex-end;
  }

  .context-pill {
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    font-size: 0.72rem;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    color: var(--color-text-secondary);
    max-width: 260px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .context-pill.empty {
    opacity: 0.75;
    font-style: italic;
  }

  .mono {
    font-family: "SF Mono", "Fira Code", monospace;
  }

  .error-bar {
    padding: 0.5rem 1rem;
    background: color-mix(in srgb, var(--color-danger) 12%, transparent);
    color: var(--color-danger);
    font-size: 0.8rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .content {
    flex: 1;
    padding: 0.75rem 1rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    overflow-y: auto;
  }

  .empty-state {
    margin-top: 2rem;
    text-align: center;
    color: var(--color-text-secondary);
    font-size: 0.85rem;
  }

  .empty-hint {
    margin-top: 0.35rem;
    font-size: 0.78rem;
    color: var(--color-text-muted);
  }

  .overall-section {
    border-radius: 0.75rem;
    border: 1px solid var(--color-border-subtle);
    background: var(--color-bg-elevated);
    padding: 0.75rem 0.9rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .overall-header {
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
  }

  .overall-header h3 {
    margin: 0;
    font-size: 0.9rem;
    color: var(--color-text-primary);
  }

  .overall-caption {
    font-size: 0.78rem;
    color: var(--color-text-muted);
  }

  .stats-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .stat-card {
    flex: 0 1 140px;
    min-width: 0;
    border-radius: 0.6rem;
    border: 1px solid var(--color-border-default);
    background: var(--color-bg-surface);
    padding: 0.45rem 0.6rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .stat-label {
    font-size: 0.72rem;
    color: var(--color-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .stat-value {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--color-text-primary);
  }

  .severity-dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 999px;
    display: inline-block;
  }

  .severity-dot.severity-error {
    background: var(--color-danger);
  }

  .severity-dot.severity-warning {
    /* Default warning yellow */
    background: #eab308;
  }

  .severity-dot.severity-info {
    background: var(--color-info);
  }

  .severity-dot.severity-passed {
    /* Use a clear default green for passed */
    background: #16a34a;
  }

  .runs-section {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .section-title {
    margin: 0;
    font-size: 0.85rem;
    color: var(--color-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .runs-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .run-card {
    border-radius: 0.75rem;
    border: 1px solid var(--color-border-subtle);
    background: var(--color-bg-surface);
    padding: 0.7rem 0.9rem;
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
  }

  .run-header {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
  }

  .run-title-block h4 {
    margin: 0;
    font-size: 0.9rem;
    color: var(--color-text-primary);
  }

  .run-meta {
    margin: 0.15rem 0 0;
    font-size: 0.78rem;
    color: var(--color-text-muted);
  }

  .run-id {
    margin-left: auto;
    font-size: 0.7rem;
    color: var(--color-text-muted);
    padding: 0.15rem 0.4rem;
    border-radius: 0.35rem;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-subtle);
  }

  .run-stats-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .rules-collapsible {
    margin-top: 0.5rem;
  }

  .rules-toggle {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.35rem 0;
    font-size: 0.82rem;
    font-weight: 500;
    color: var(--color-text-secondary);
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
  }

  .rules-toggle:hover {
    color: var(--color-brand-500);
  }

  .rules-toggle-chevron {
    font-size: 0.75rem;
    color: var(--color-text-muted);
  }

  .rules-table-wrap {
    margin-top: 0.35rem;
    overflow-x: auto;
    border-radius: 0.35rem;
    border: 1px solid var(--color-border-subtle);
  }

  .rules-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8rem;
  }

  .rules-table th,
  .rules-table td {
    padding: 0.35rem 0.5rem;
    text-align: left;
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .rules-table th {
    font-weight: 600;
    color: var(--color-text-muted);
    text-transform: uppercase;
    font-size: 0.7rem;
    letter-spacing: 0.04em;
  }

  .rules-table tbody tr:last-child td {
    border-bottom: none;
  }

  .rules-th-expand,
  .rules-td-expand {
    width: 2rem;
    padding-right: 0;
  }

  .rules-td-name {
    font-weight: 500;
    color: var(--color-text-primary);
  }

  .rules-td-fail {
    text-align: right;
  }

  .rule-row.has-failures {
    background: color-mix(in srgb, var(--color-danger) 4%, transparent);
  }

  .expand-btn {
    width: 1.5rem;
    height: 1.5rem;
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: 0.2rem;
    background: transparent;
    color: var(--color-text-muted);
    cursor: pointer;
    font-size: 0.75rem;
  }

  .expand-btn:hover {
    background: var(--color-bg-elevated);
    color: var(--color-brand-500);
  }

  .expand-placeholder {
    display: inline-block;
    width: 1.5rem;
    height: 1.5rem;
  }

  .status-badge {
    display: inline-block;
    padding: 0.1rem 0.35rem;
    border-radius: 0.2rem;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
  }

  .status-badge.passed {
    background: color-mix(in srgb, #16a34a 15%, transparent);
    color: #16a34a;
  }

  .status-badge.failed {
    background: color-mix(in srgb, var(--color-danger) 15%, transparent);
    color: var(--color-danger);
  }

  .violations-row td {
    padding: 0;
    border-bottom: 1px solid var(--color-border-subtle);
    vertical-align: top;
  }

  .violations-panel {
    padding: 0.5rem 0.75rem;
    background: var(--color-bg-elevated);
    border-left: 3px solid var(--color-danger);
  }

  .violations-label {
    font-size: 0.72rem;
    color: var(--color-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    display: block;
    margin-bottom: 0.35rem;
  }

  .violations-list {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .violation-item {
    font-size: 0.78rem;
    padding: 0;
  }

  .violation-select-btn {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    flex-wrap: wrap;
    width: 100%;
    padding: 0.2rem 0;
    text-align: left;
    background: none;
    border: none;
    cursor: pointer;
    color: inherit;
    font: inherit;
  }

  .violation-select-btn:hover {
    background: color-mix(in srgb, var(--color-brand-500) 12%, transparent);
    border-radius: 0.2rem;
  }

  .violation-select-btn .violation-id {
    color: var(--color-brand-500);
  }

  .violation-select-btn:hover .violation-id {
    text-decoration: underline;
  }

  .violation-id {
    font-size: 0.75rem;
    color: var(--color-brand-500);
  }

  .violation-class {
    color: var(--color-text-secondary);
  }

  .violation-msg {
    color: var(--color-text-muted);
    flex: 1;
    min-width: 0;
  }
</style>

