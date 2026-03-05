<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { page } from "$app/stores";
  import { client } from "$lib/api/client";
  import {
    VALIDATION_SCHEMAS_QUERY,
    VALIDATION_RULES_QUERY,
    CREATE_VALIDATION_SCHEMA_MUTATION,
    DELETE_VALIDATION_SCHEMA_MUTATION,
    CREATE_VALIDATION_RULE_MUTATION,
    DELETE_VALIDATION_RULE_MUTATION,
    LINK_RULE_TO_SCHEMA_MUTATION,
    RUN_VALIDATION_MUTATION,
  } from "$lib/api/client";
  import {
    SCHEMA_CHANNEL,
    type SchemaMessage,
  } from "$lib/schema/protocol";
  import { loadSettings } from "$lib/state/persistence";

  let branchId = $state<string | null>(null);
  let projectId = $state<string | null>(null);
  let revision = $state<number | null>(null);

  type ValidationCondition = { path: string; operator: string; value: string | null };
  type SpatialContext = { traversal: string; scopeClass: string | null; scopeName: string | null; scopeGlobalId: string | null };
  type ValidationRule = {
    globalId: string; name: string; description: string | null;
    ruleType: string | null; targetClass: string | null; severity: string;
    conditions: ValidationCondition[]; spatialContext: SpatialContext | null;
    includeSubtypes: boolean;
  };
  type ValidationSchema = {
    globalId: string; name: string; description: string | null;
    version: string | null; isActive: boolean; rules: ValidationRule[];
  };
  type Violation = { globalId: string; ifcClass: string; message: string };
  type RuleResult = {
    ruleGlobalId: string; ruleName: string; severity: string;
    passed: boolean; violations: Violation[];
  };
  type RunResult = {
    schemaGlobalId: string; schemaName: string;
    errorCount: number; warningCount: number; infoCount: number; passedCount: number;
    results: RuleResult[];
  };

  let schemas = $state<ValidationSchema[]>([]);
  let activeSchema = $state<ValidationSchema | null>(null);
  let loading = $state(false);
  let error = $state<string | null>(null);

  // Rule editor state
  let showRuleEditor = $state(false);
  let ruleName = $state("");
  let ruleTargetClass = $state("");
  let ruleSeverity = $state("Error");
  let ruleIncludeSubtypes = $state(false);
  let ruleConditions = $state<{ path: string; operator: string; value: string }[]>([
    { path: "", operator: "exists", value: "" },
  ]);

  // Schema creator state
  let showSchemaCreator = $state(false);
  let newSchemaName = $state("");
  let newSchemaDescription = $state("");

  // Validation results
  let validationResult = $state<RunResult | null>(null);
  let runningValidation = $state(false);

  let channel: BroadcastChannel | null = null;

  function applyContextFromUrl() {
    const url = $page.url;
    const b = url.searchParams.get("branchId");
    const p = url.searchParams.get("projectId");
    const r = url.searchParams.get("revision");
    if (b) branchId = b;
    if (p) projectId = p;
    if (r) { const parsed = Number(r); revision = Number.isNaN(parsed) ? null : parsed; }
  }

  function applyContextFallbackFromSettings() {
    const settings = loadSettings();
    if (!settings) return;
    if (!branchId && settings.activeBranchId) branchId = settings.activeBranchId;
    if (!projectId && settings.activeProjectId) projectId = settings.activeProjectId;
    if (revision == null && settings.activeRevision != null) revision = settings.activeRevision;
  }

  function handleIncomingMessage(e: MessageEvent<SchemaMessage>) {
    const msg = e.data;
    if (msg.type === "context") {
      branchId = msg.branchId;
      projectId = msg.projectId;
      revision = msg.revision;
    }
  }

  async function loadSchemas() {
    if (!branchId) return;
    loading = true;
    error = null;
    try {
      const result = await client.query(VALIDATION_SCHEMAS_QUERY, {
        branchId, revision,
      }).toPromise();
      if (result.error) { error = result.error.message; return; }
      schemas = result.data?.validationSchemas ?? [];
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  async function selectSchema(schema: ValidationSchema) {
    activeSchema = schema;
    validationResult = null;
  }

  async function createSchema() {
    if (!branchId || !newSchemaName.trim()) return;
    try {
      const result = await client.mutation(CREATE_VALIDATION_SCHEMA_MUTATION, {
        branchId, name: newSchemaName.trim(), description: newSchemaDescription.trim() || null,
      }).toPromise();
      if (result.data?.createValidationSchema) {
        schemas = [...schemas, result.data.createValidationSchema];
        showSchemaCreator = false;
        newSchemaName = "";
        newSchemaDescription = "";
      }
    } catch (e: any) {
      error = e.message;
    }
  }

  async function deleteSchema(globalId: string) {
    if (!branchId) return;
    try {
      await client.mutation(DELETE_VALIDATION_SCHEMA_MUTATION, { branchId, globalId }).toPromise();
      schemas = schemas.filter((s) => s.globalId !== globalId);
      if (activeSchema?.globalId === globalId) activeSchema = null;
    } catch (e: any) {
      error = e.message;
    }
  }

  async function createRule() {
    if (!branchId || !ruleName.trim() || !ruleTargetClass.trim()) return;
    if (!activeSchema) return;
    try {
      const conditions = ruleConditions
        .filter((c) => c.path.trim())
        .map((c) => ({ path: c.path, operator: c.operator, value: c.value || null }));
      const result = await client.mutation(CREATE_VALIDATION_RULE_MUTATION, {
        branchId,
        name: ruleName.trim(),
        targetClass: ruleTargetClass.trim(),
        severity: ruleSeverity,
        includeSubtypes: ruleIncludeSubtypes,
        conditions,
      }).toPromise();
      if (result.data?.createValidationRule) {
        const newRule = result.data.createValidationRule;
        // Link to active schema
        await client.mutation(LINK_RULE_TO_SCHEMA_MUTATION, {
          branchId,
          ruleGlobalId: newRule.globalId,
          schemaGlobalId: activeSchema.globalId,
        }).toPromise();
        activeSchema = {
          ...activeSchema,
          rules: [...activeSchema.rules, newRule],
        };
        showRuleEditor = false;
        ruleName = "";
        ruleTargetClass = "";
        ruleConditions = [{ path: "", operator: "exists", value: "" }];
      }
    } catch (e: any) {
      error = e.message;
    }
  }

  async function deleteRule(ruleGlobalId: string) {
    if (!branchId) return;
    try {
      await client.mutation(DELETE_VALIDATION_RULE_MUTATION, { branchId, globalId: ruleGlobalId }).toPromise();
      if (activeSchema) {
        activeSchema = {
          ...activeSchema,
          rules: activeSchema.rules.filter((r) => r.globalId !== ruleGlobalId),
        };
      }
    } catch (e: any) {
      error = e.message;
    }
  }

  async function runValidation() {
    if (!branchId || !activeSchema) return;
    runningValidation = true;
    validationResult = null;
    try {
      const result = await client.mutation(RUN_VALIDATION_MUTATION, {
        branchId,
        schemaGlobalId: activeSchema.globalId,
        revision,
      }).toPromise();
      if (result.data?.runValidation) {
        validationResult = result.data.runValidation;
      }
      if (result.error) error = result.error.message;
    } catch (e: any) {
      error = e.message;
    } finally {
      runningValidation = false;
    }
  }

  function addCondition() {
    ruleConditions = [...ruleConditions, { path: "", operator: "exists", value: "" }];
  }

  function removeCondition(index: number) {
    ruleConditions = ruleConditions.filter((_, i) => i !== index);
  }

  function severityColor(severity: string): string {
    if (severity === "Error") return "#ef4444";
    if (severity === "Warning") return "#f59e0b";
    return "#3b82f6";
  }

  $effect(() => {
    if (branchId) loadSchemas();
  });

  onMount(() => {
    applyContextFromUrl();
    applyContextFallbackFromSettings();
    channel = new BroadcastChannel(SCHEMA_CHANNEL);
    channel.onmessage = handleIncomingMessage;
    channel.postMessage({ type: "request-context" } satisfies SchemaMessage);
  });

  onDestroy(() => {
    channel?.close();
  });
</script>

<div class="schema-page">
  <header class="page-header">
    <h2>Schema Browser</h2>
    {#if branchId}
      <span class="context-pill mono">{branchId.slice(0, 8)}…</span>
    {:else}
      <span class="context-pill empty">No branch selected</span>
    {/if}
  </header>

  {#if error}
    <div class="error-bar">{error}
      <button onclick={() => (error = null)}>✕</button>
    </div>
  {/if}

  <div class="content">
    <!-- Left panel: schema list -->
    <aside class="schema-list">
      <div class="panel-header">
        <h3>Schemas</h3>
        <button class="btn-sm btn-primary" onclick={() => (showSchemaCreator = true)}>+ New</button>
      </div>

      {#if showSchemaCreator}
        <div class="creator-form">
          <input bind:value={newSchemaName} placeholder="Schema name" class="input-sm" />
          <input bind:value={newSchemaDescription} placeholder="Description (optional)" class="input-sm" />
          <div class="form-actions">
            <button class="btn-sm btn-primary" onclick={createSchema}>Create</button>
            <button class="btn-sm" onclick={() => (showSchemaCreator = false)}>Cancel</button>
          </div>
        </div>
      {/if}

      {#if loading}
        <div class="empty-state">Loading…</div>
      {:else if schemas.length === 0}
        <div class="empty-state">No schemas found. Create one to get started.</div>
      {:else}
        <ul class="schema-items">
          {#each schemas as schema (schema.globalId)}
            <li class:active={activeSchema?.globalId === schema.globalId}>
              <button class="schema-item" onclick={() => selectSchema(schema)}>
                <span class="schema-name">{schema.name}</span>
                <span class="rule-count">{schema.rules.length} rules</span>
              </button>
              <button class="btn-icon btn-danger" onclick={() => deleteSchema(schema.globalId)} aria-label="Delete schema">✕</button>
            </li>
          {/each}
        </ul>
      {/if}
    </aside>

    <!-- Right panel: schema detail -->
    <main class="schema-detail">
      {#if activeSchema}
        <div class="detail-header">
          <div>
            <h3>{activeSchema.name}</h3>
            {#if activeSchema.description}
              <p class="detail-description">{activeSchema.description}</p>
            {/if}
            {#if activeSchema.version}
              <span class="version-badge">v{activeSchema.version}</span>
            {/if}
          </div>
          <div class="detail-actions">
            <button class="btn-sm btn-primary" onclick={() => (showRuleEditor = true)}>+ Add Rule</button>
            <button
              class="btn-sm btn-success"
              onclick={runValidation}
              disabled={runningValidation}
            >
              {runningValidation ? "Running…" : "▶ Run Validation"}
            </button>
          </div>
        </div>

        <!-- Rule editor inline form -->
        {#if showRuleEditor}
          <div class="rule-editor">
            <h4>New Rule</h4>
            <div class="form-grid">
              <label>
                Name
                <input bind:value={ruleName} placeholder="Rule name" class="input-sm" />
              </label>
              <label>
                Target Class
                <input bind:value={ruleTargetClass} placeholder="e.g. IfcWall" class="input-sm" />
              </label>
              <label>
                Severity
                <select bind:value={ruleSeverity} class="input-sm">
                  <option value="Error">Error</option>
                  <option value="Warning">Warning</option>
                  <option value="Info">Info</option>
                </select>
              </label>
              <label class="checkbox-label">
                <input type="checkbox" bind:checked={ruleIncludeSubtypes} />
                Include subtypes
              </label>
            </div>

            <h5>Conditions</h5>
            {#each ruleConditions as cond, i}
              <div class="condition-row">
                <input bind:value={cond.path} placeholder="Attribute path" class="input-sm" />
                <select bind:value={cond.operator} class="input-sm">
                  <option value="exists">exists</option>
                  <option value="not_exists">not exists</option>
                  <option value="equals">equals</option>
                  <option value="not_equals">not equals</option>
                  <option value="contains">contains</option>
                  <option value="greater_than">greater than</option>
                  <option value="less_than">less than</option>
                  <option value="matches">matches (regex)</option>
                </select>
                <input bind:value={cond.value} placeholder="Value" class="input-sm" />
                <button class="btn-icon" onclick={() => removeCondition(i)}>✕</button>
              </div>
            {/each}
            <button class="btn-sm" onclick={addCondition}>+ Condition</button>

            <div class="form-actions">
              <button class="btn-sm btn-primary" onclick={createRule}>Save Rule</button>
              <button class="btn-sm" onclick={() => (showRuleEditor = false)}>Cancel</button>
            </div>
          </div>
        {/if}

        <!-- Rules list -->
        <div class="rules-section">
          <h4>Rules ({activeSchema.rules.length})</h4>
          {#if activeSchema.rules.length === 0}
            <div class="empty-state">No rules yet. Add one above.</div>
          {:else}
            <div class="rules-list">
              {#each activeSchema.rules as rule (rule.globalId)}
                <div class="rule-card">
                  <div class="rule-header">
                    <span class="severity-badge" style="background: {severityColor(rule.severity)}">{rule.severity}</span>
                    <span class="rule-name">{rule.name}</span>
                    <span class="rule-target">{rule.targetClass}{rule.includeSubtypes ? '+' : ''}</span>
                    <button class="btn-icon btn-danger" onclick={() => deleteRule(rule.globalId)}>✕</button>
                  </div>
                  {#if rule.conditions.length > 0}
                    <div class="rule-conditions">
                      {#each rule.conditions as cond}
                        <code>{cond.path} {cond.operator} {cond.value ?? ''}</code>
                      {/each}
                    </div>
                  {/if}
                  {#if rule.spatialContext}
                    <div class="spatial-ctx">
                      Scope: {rule.spatialContext.traversal}
                      {#if rule.spatialContext.scopeName}→ {rule.spatialContext.scopeName}{/if}
                    </div>
                  {/if}
                </div>
              {/each}
            </div>
          {/if}
        </div>

        <!-- Validation results -->
        {#if validationResult}
          <div class="results-section">
            <h4>Validation Results</h4>
            <div class="results-summary">
              <span class="result-badge error">{validationResult.errorCount} errors</span>
              <span class="result-badge warning">{validationResult.warningCount} warnings</span>
              <span class="result-badge info">{validationResult.infoCount} info</span>
              <span class="result-badge passed">{validationResult.passedCount} passed</span>
            </div>
            {#each validationResult.results as rr (rr.ruleGlobalId)}
              <div class="result-card" class:failed={!rr.passed}>
                <div class="result-header">
                  <span class="severity-badge" style="background: {severityColor(rr.severity)}">{rr.severity}</span>
                  <span>{rr.ruleName}</span>
                  <span class="result-status">{rr.passed ? "✓ PASS" : "✗ FAIL"}</span>
                </div>
                {#if rr.violations.length > 0}
                  <details>
                    <summary>{rr.violations.length} violation{rr.violations.length === 1 ? '' : 's'}</summary>
                    <ul class="violations-list">
                      {#each rr.violations as v}
                        <li>
                          <code>{v.globalId}</code>
                          <span class="viol-class">{v.ifcClass}</span>
                          <span class="viol-msg">{v.message}</span>
                        </li>
                      {/each}
                    </ul>
                  </details>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      {:else}
        <div class="empty-state-center">
          <p>Select a schema from the list to view its rules and run validation.</p>
        </div>
      {/if}
    </main>
  </div>
</div>

<style>
  .schema-page {
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: #1a1a2e;
    color: #e0e0e0;
    font-family: system-ui, -apple-system, sans-serif;
    overflow: hidden;
  }
  .page-header {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }
  .page-header h2 {
    margin: 0;
    font-size: 0.95rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #a78bfa;
  }
  .context-pill {
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    font-size: 0.72rem;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: #ccc;
  }
  .context-pill.empty { opacity: 0.7; font-style: italic; }
  .mono { font-family: "SF Mono", "Fira Code", monospace; }
  .error-bar {
    padding: 0.5rem 1rem;
    background: rgba(239, 68, 68, 0.15);
    color: #fca5a5;
    font-size: 0.8rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .error-bar button { background: none; border: none; color: #fca5a5; cursor: pointer; }
  .content {
    flex: 1;
    display: flex;
    overflow: hidden;
  }
  .schema-list {
    width: 280px;
    flex-shrink: 0;
    border-right: 1px solid rgba(255, 255, 255, 0.08);
    display: flex;
    flex-direction: column;
    overflow-y: auto;
  }
  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }
  .panel-header h3 { margin: 0; font-size: 0.85rem; color: #ccc; }
  .creator-form {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .schema-items {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .schema-items li {
    display: flex;
    align-items: center;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  }
  .schema-items li.active {
    background: rgba(167, 139, 250, 0.1);
  }
  .schema-item {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    padding: 0.6rem 1rem;
    background: none;
    border: none;
    color: #e0e0e0;
    text-align: left;
    cursor: pointer;
  }
  .schema-item:hover { background: rgba(255, 255, 255, 0.04); }
  .schema-name { font-size: 0.85rem; font-weight: 500; }
  .rule-count { font-size: 0.72rem; color: #888; }
  .schema-detail {
    flex: 1;
    overflow-y: auto;
    padding: 1rem 1.5rem;
  }
  .detail-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 1rem;
  }
  .detail-header h3 { margin: 0 0 0.25rem 0; font-size: 1.1rem; }
  .detail-description { color: #999; font-size: 0.82rem; margin: 0; }
  .version-badge {
    display: inline-block;
    margin-top: 0.3rem;
    padding: 0.1rem 0.5rem;
    border-radius: 999px;
    font-size: 0.7rem;
    background: rgba(167, 139, 250, 0.15);
    color: #a78bfa;
  }
  .detail-actions {
    display: flex;
    gap: 0.5rem;
    flex-shrink: 0;
  }
  .rule-editor {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
  }
  .rule-editor h4 { margin: 0 0 0.75rem 0; font-size: 0.9rem; color: #a78bfa; }
  .rule-editor h5 { margin: 0.75rem 0 0.5rem 0; font-size: 0.82rem; color: #bbb; }
  .form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
  }
  .form-grid label { display: flex; flex-direction: column; gap: 0.2rem; font-size: 0.78rem; color: #aaa; }
  .checkbox-label { flex-direction: row !important; align-items: center; gap: 0.5rem !important; }
  .condition-row {
    display: flex;
    gap: 0.4rem;
    margin-bottom: 0.4rem;
  }
  .condition-row .input-sm { flex: 1; }
  .form-actions { display: flex; gap: 0.5rem; margin-top: 0.75rem; }
  .rules-section { margin-top: 1rem; }
  .rules-section h4 { margin: 0 0 0.5rem 0; font-size: 0.9rem; }
  .rules-list { display: flex; flex-direction: column; gap: 0.5rem; }
  .rule-card {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 6px;
    padding: 0.6rem 0.8rem;
  }
  .rule-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .severity-badge {
    display: inline-block;
    padding: 0.1rem 0.4rem;
    border-radius: 4px;
    font-size: 0.68rem;
    font-weight: 600;
    color: white;
    text-transform: uppercase;
  }
  .rule-name { font-size: 0.85rem; font-weight: 500; flex: 1; }
  .rule-target { font-size: 0.75rem; color: #888; font-family: monospace; }
  .rule-conditions {
    margin-top: 0.3rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
  }
  .rule-conditions code {
    font-size: 0.72rem;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    background: rgba(255, 255, 255, 0.06);
    color: #bbb;
  }
  .spatial-ctx {
    margin-top: 0.25rem;
    font-size: 0.72rem;
    color: #888;
    font-style: italic;
  }
  .results-section {
    margin-top: 1.5rem;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    padding-top: 1rem;
  }
  .results-section h4 { margin: 0 0 0.5rem 0; }
  .results-summary {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }
  .result-badge {
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
  }
  .result-badge.error { background: rgba(239, 68, 68, 0.2); color: #fca5a5; }
  .result-badge.warning { background: rgba(245, 158, 11, 0.2); color: #fcd34d; }
  .result-badge.info { background: rgba(59, 130, 246, 0.2); color: #93c5fd; }
  .result-badge.passed { background: rgba(34, 197, 94, 0.2); color: #86efac; }
  .result-card {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 6px;
    padding: 0.5rem 0.8rem;
    margin-bottom: 0.4rem;
  }
  .result-card.failed { border-color: rgba(239, 68, 68, 0.3); }
  .result-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
  }
  .result-status {
    margin-left: auto;
    font-size: 0.78rem;
    font-weight: 600;
  }
  details { margin-top: 0.3rem; }
  summary { cursor: pointer; font-size: 0.78rem; color: #aaa; }
  .violations-list {
    list-style: none;
    padding: 0;
    margin: 0.3rem 0 0 0;
    font-size: 0.75rem;
  }
  .violations-list li {
    display: flex;
    gap: 0.5rem;
    padding: 0.2rem 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  }
  .violations-list code { color: #a78bfa; font-size: 0.7rem; }
  .viol-class { color: #888; }
  .viol-msg { color: #ccc; flex: 1; }
  .empty-state {
    padding: 1.5rem;
    text-align: center;
    color: #777;
    font-size: 0.82rem;
  }
  .empty-state-center {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #666;
  }
  /* Shared small controls */
  .input-sm {
    padding: 0.35rem 0.5rem;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 4px;
    color: #e0e0e0;
    font-size: 0.8rem;
    outline: none;
  }
  .input-sm:focus { border-color: #a78bfa; }
  .btn-sm {
    padding: 0.3rem 0.7rem;
    border-radius: 4px;
    font-size: 0.78rem;
    border: 1px solid rgba(255, 255, 255, 0.12);
    background: rgba(255, 255, 255, 0.06);
    color: #ccc;
    cursor: pointer;
  }
  .btn-sm:hover { background: rgba(255, 255, 255, 0.1); }
  .btn-primary { background: rgba(167, 139, 250, 0.2); color: #a78bfa; border-color: rgba(167, 139, 250, 0.3); }
  .btn-primary:hover { background: rgba(167, 139, 250, 0.3); }
  .btn-success { background: rgba(34, 197, 94, 0.2); color: #86efac; border-color: rgba(34, 197, 94, 0.3); }
  .btn-success:hover { background: rgba(34, 197, 94, 0.3); }
  .btn-icon {
    background: none;
    border: none;
    color: #888;
    cursor: pointer;
    padding: 0.2rem 0.4rem;
    font-size: 0.75rem;
  }
  .btn-icon:hover { color: #ccc; }
  .btn-danger:hover { color: #ef4444; }
</style>
