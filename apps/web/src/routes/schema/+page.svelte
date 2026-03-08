<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { page } from "$app/stores";
  import { client } from "$lib/api/client";
  import {
    VALIDATION_SCHEMAS_QUERY,
    VALIDATION_RULES_QUERY,
    VALIDATION_RULES_FOR_UPLOADED_SCHEMA_QUERY,
    UPDATE_UPLOADED_SCHEMA_RULE_MUTATION,
    CREATE_VALIDATION_SCHEMA_MUTATION,
    DELETE_VALIDATION_SCHEMA_MUTATION,
    CREATE_VALIDATION_RULE_MUTATION,
    DELETE_VALIDATION_RULE_MUTATION,
    LINK_RULE_TO_SCHEMA_MUTATION,
    RUN_VALIDATION_MUTATION,
    RUN_VALIDATION_BY_UPLOADED_SCHEMA_MUTATION,
    UPLOADED_SCHEMAS_QUERY,
    APPLY_SCHEMA_TO_PROJECT_MUTATION,
    UNAPPLY_SCHEMA_FROM_PROJECT_MUTATION,
    PROJECTS_QUERY,
    BRANCH_QUERY,
  } from "$lib/api/client";
  import { SCHEMA_CHANNEL, type SchemaMessage } from "$lib/schema/protocol";
  import { loadSettings } from "$lib/state/persistence";

  let branchId = $state<string | null>(null);
  let projectId = $state<string | null>(null);
  let revision = $state<number | null>(null);

  type ValidationCondition = {
    path: string;
    operator: string;
    value: string | null;
  };
  type SpatialContext = {
    traversal: string;
    scopeClass: string | null;
    scopeName: string | null;
    scopeGlobalId: string | null;
  };
  type ValidationRule = {
    globalId: string;
    name: string;
    description: string | null;
    ruleType: string | null;
    targetClass: string | null;
    severity: string;
    conditions: ValidationCondition[];
    spatialContext: SpatialContext | null;
    includeSubtypes: boolean;
  };
  type ValidationSchema = {
    globalId: string;
    name: string;
    description: string | null;
    version: string | null;
    isActive: boolean;
    rules: ValidationRule[];
  };
  type Violation = { globalId: string; ifcClass: string; message: string };
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
    errorCount: number;
    warningCount: number;
    infoCount: number;
    passedCount: number;
    results: RuleResult[];
  };
  type UploadedSchema = {
    id: string;
    versionName: string;
    ruleCount: number;
    projectIds: string[];
  };
  type EffAttr = {
    name?: string;
    type?: string;
    required?: boolean;
    definedOn?: string;
  };
  type UploadedSchemaRule = {
    ruleId: string;
    name: string;
    description: string | null;
    targetIfcClass: string;
    effectiveRequiredAttributes: string | null;
    displaySeverity: string;
    severity: string;
  };
  type ProjectInfo = { id: string; name: string; description: string | null };

  let ruleViewMode = $state<Record<string, "card" | "json">>({});
  let ruleDraftJson = $state<Record<string, string>>({});
  let ruleEditingAttr = $state<Record<string, number | null>>({});
  let ruleSaving = $state<Record<string, boolean>>({});
  let ruleJsonError = $state<Record<string, string | null>>({});

  let schemas = $state<ValidationSchema[]>([]);
  let uploadedSchemas = $state<UploadedSchema[]>([]);
  let uploadedSchemaSearchQuery = $state("");
  let projects = $state<ProjectInfo[]>([]);
  let uploadedSchemasLoading = $state(false);
  let applyProjectId = $state<string | null>(null);

  const filteredUploadedSchemas = $derived(
    uploadedSchemaSearchQuery.trim()
      ? uploadedSchemas.filter((us) =>
          us.versionName
            .toLowerCase()
            .includes(uploadedSchemaSearchQuery.trim().toLowerCase()),
        )
      : uploadedSchemas,
  );

  const appliedSchemasForProject = $derived.by(() => {
    const pid = applyProjectId;
    return pid
      ? filteredUploadedSchemas.filter((us) => us.projectIds.includes(pid))
      : [];
  });
  let activeSchema = $state<ValidationSchema | null>(null);
  let activeAppliedSchema = $state<UploadedSchema | null>(null);
  let uploadedSchemaRules = $state<UploadedSchemaRule[]>([]);
  let uploadedSchemaRulesLoading = $state(false);

  const rulesBySeverity = $derived.by(() => {
    const groups: Record<string, UploadedSchemaRule[]> = {
      Required: [],
      Warning: [],
      Info: [],
    };
    for (const r of uploadedSchemaRules) {
      const key =
        r.displaySeverity === "Required"
          ? "Required"
          : r.displaySeverity === "Warning"
            ? "Warning"
            : "Info";
      groups[key].push(r);
    }
    return [
      { severity: "Required", rules: groups.Required },
      { severity: "Warning", rules: groups.Warning },
      { severity: "Info", rules: groups.Info },
    ].filter((g) => g.rules.length > 0);
  });
  let loading = $state(false);
  let error = $state<string | null>(null);

  // Rule editor state
  let showRuleEditor = $state(false);
  let ruleName = $state("");
  let ruleTargetClass = $state("");
  let ruleSeverity = $state("Error");
  let ruleIncludeSubtypes = $state(false);
  let ruleConditions = $state<
    { path: string; operator: string; value: string }[]
  >([{ path: "", operator: "exists", value: "" }]);

  // Schema creator state
  let showSchemaCreator = $state(false);
  let newSchemaName = $state("");
  let newSchemaDescription = $state("");

  // Validation results
  let validationResult = $state<RunResult | null>(null);
  let runningValidation = $state(false);
  let runningValidationSchemaId = $state<string | null>(null);
  let runningAllValidations = $state(false);
  let uploadedSchemaValidationResult = $state<RunResult | null>(null);

  let channel: BroadcastChannel | null = null;

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

  function handleIncomingMessage(e: MessageEvent<SchemaMessage>) {
    const msg = e.data;
    if (msg.type === "context") {
      branchId = msg.branchId;
      projectId = msg.projectId;
      revision = msg.revision;
    }
  }

  async function loadUploadedSchemas() {
    uploadedSchemasLoading = true;
    error = null;
    try {
      const result = await client.query(UPLOADED_SCHEMAS_QUERY, {}).toPromise();
      if (result.error) {
        error = result.error.message;
        return;
      }
      uploadedSchemas = result.data?.uploadedSchemas ?? [];
    } catch (e: any) {
      error = e.message;
    } finally {
      uploadedSchemasLoading = false;
    }
  }

  async function loadProjects() {
    try {
      const result = await client.query(PROJECTS_QUERY, {}).toPromise();
      if (result.error) return;
      projects = (result.data?.projects ?? []).map(
        (p: { id: string; name: string; description: string | null }) => ({
          id: p.id,
          name: p.name,
          description: p.description ?? null,
        }),
      );
    } catch {
      projects = [];
    }
  }

  async function resolveProjectIdFromBranch() {
    if (projectId || !branchId) return;
    try {
      const result = await client.query(BRANCH_QUERY, { branchId }).toPromise();
      if (result.data?.branch?.projectId) {
        projectId = result.data.branch.projectId;
        applyProjectId = result.data.branch.projectId;
      }
    } catch {
      // ignore
    }
  }

  async function applySchemaToProject(schemaId: string) {
    const pid = applyProjectId ?? projectId;
    if (!pid) return;
    try {
      await client
        .mutation(APPLY_SCHEMA_TO_PROJECT_MUTATION, {
          projectId: pid,
          schemaId,
        })
        .toPromise();
      await loadUploadedSchemas();
    } catch (e: any) {
      error = e.message;
    }
  }

  async function unapplySchemaFromProject(schemaId: string) {
    const pid = applyProjectId ?? projectId;
    if (!pid) return;
    try {
      await client
        .mutation(UNAPPLY_SCHEMA_FROM_PROJECT_MUTATION, {
          projectId: pid,
          schemaId,
        })
        .toPromise();
      if (activeAppliedSchema?.id === schemaId) activeAppliedSchema = null;
      await loadUploadedSchemas();
    } catch (e: any) {
      error = e.message;
    }
  }

  async function loadSchemas() {
    if (!branchId) return;
    loading = true;
    error = null;
    try {
      const result = await client
        .query(VALIDATION_SCHEMAS_QUERY, {
          branchId,
          revision,
        })
        .toPromise();
      if (result.error) {
        error = result.error.message;
        return;
      }
      schemas = result.data?.validationSchemas ?? [];
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  async function selectSchema(schema: ValidationSchema) {
    activeSchema = schema;
    activeAppliedSchema = null;
    validationResult = null;
  }

  async function selectAppliedSchema(schema: UploadedSchema) {
    activeAppliedSchema = schema;
    activeSchema = null;
    uploadedSchemaValidationResult = null;
    await loadUploadedSchemaRules(schema.id);
  }

  async function loadUploadedSchemaRules(schemaId: string) {
    uploadedSchemaRulesLoading = true;
    try {
      const result = await client
        .query(VALIDATION_RULES_FOR_UPLOADED_SCHEMA_QUERY, {
          schemaId,
        })
        .toPromise();
      uploadedSchemaRules = result.data?.validationRulesForUploadedSchema ?? [];
    } catch {
      uploadedSchemaRules = [];
    } finally {
      uploadedSchemaRulesLoading = false;
    }
  }

  async function createSchema() {
    if (!branchId || !newSchemaName.trim()) return;
    try {
      const result = await client
        .mutation(CREATE_VALIDATION_SCHEMA_MUTATION, {
          branchId,
          name: newSchemaName.trim(),
          description: newSchemaDescription.trim() || null,
        })
        .toPromise();
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
      await client
        .mutation(DELETE_VALIDATION_SCHEMA_MUTATION, { branchId, globalId })
        .toPromise();
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
        .map((c) => ({
          path: c.path,
          operator: c.operator,
          value: c.value || null,
        }));
      const result = await client
        .mutation(CREATE_VALIDATION_RULE_MUTATION, {
          branchId,
          name: ruleName.trim(),
          targetClass: ruleTargetClass.trim(),
          severity: ruleSeverity,
          includeSubtypes: ruleIncludeSubtypes,
          conditions,
        })
        .toPromise();
      if (result.data?.createValidationRule) {
        const newRule = result.data.createValidationRule;
        // Link to active schema
        await client
          .mutation(LINK_RULE_TO_SCHEMA_MUTATION, {
            branchId,
            ruleGlobalId: newRule.globalId,
            schemaGlobalId: activeSchema.globalId,
          })
          .toPromise();
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
      await client
        .mutation(DELETE_VALIDATION_RULE_MUTATION, {
          branchId,
          globalId: ruleGlobalId,
        })
        .toPromise();
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
      const result = await client
        .mutation(RUN_VALIDATION_MUTATION, {
          branchId,
          schemaGlobalId: activeSchema.globalId,
          revision,
        })
        .toPromise();
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

  async function runValidationByUploadedSchema(schemaId: string) {
    if (!branchId) return;
    runningValidationSchemaId = schemaId;
    uploadedSchemaValidationResult = null;
    error = null;
    try {
      const result = await client
        .mutation(RUN_VALIDATION_BY_UPLOADED_SCHEMA_MUTATION, {
          branchId,
          schemaId,
          revision,
        })
        .toPromise();
      if (result.data?.runValidationByUploadedSchema) {
        uploadedSchemaValidationResult =
          result.data.runValidationByUploadedSchema;
      }
      if (result.error) error = result.error.message;
    } catch (e: any) {
      error = e.message;
    } finally {
      runningValidationSchemaId = null;
    }
  }

  async function runAllValidationsForAppliedSchemas() {
    if (!branchId || appliedSchemasForProject.length === 0) return;
    runningAllValidations = true;
    uploadedSchemaValidationResult = null;
    error = null;
    try {
      for (const us of appliedSchemasForProject) {
        const result = await client
          .mutation(RUN_VALIDATION_BY_UPLOADED_SCHEMA_MUTATION, {
            branchId,
            schemaId: us.id,
            revision,
          })
          .toPromise();
        if (result.data?.runValidationByUploadedSchema) {
          uploadedSchemaValidationResult =
            result.data.runValidationByUploadedSchema;
        }
        if (result.error) {
          error = result.error.message;
          break;
        }
      }
    } catch (e: any) {
      error = e.message;
    } finally {
      runningAllValidations = false;
    }
  }

  function addCondition() {
    ruleConditions = [
      ...ruleConditions,
      { path: "", operator: "exists", value: "" },
    ];
  }

  function removeCondition(index: number) {
    ruleConditions = ruleConditions.filter((_, i) => i !== index);
  }

  function severityClass(severity: string): string {
    if (severity === "Error" || severity === "Required")
      return "severity-error";
    if (severity === "Warning") return "severity-warning";
    return "severity-info";
  }

  function getViewMode(ruleId: string): "card" | "json" {
    return ruleViewMode[ruleId] ?? "card";
  }

  function setViewMode(ruleId: string, mode: "card" | "json") {
    ruleViewMode = { ...ruleViewMode, [ruleId]: mode };
  }

  function toggleViewMode(rule: UploadedSchemaRule) {
    const current = getViewMode(rule.ruleId);
    const next = current === "card" ? "json" : "card";
    setViewMode(rule.ruleId, next);
    if (next === "json") {
      const existing = ruleDraftJson[rule.ruleId];
      if (existing === undefined || existing === "") {
        ruleDraftJson = {
          ...ruleDraftJson,
          [rule.ruleId]: rule.effectiveRequiredAttributes ?? "[]",
        };
      }
    }
  }

  function parseEffAttrs(json: string | null): EffAttr[] {
    if (!json?.trim()) return [];
    try {
      const arr = JSON.parse(json);
      return Array.isArray(arr) ? arr : [];
    } catch {
      return [];
    }
  }

  function getDraftJson(rule: UploadedSchemaRule): string {
    if (ruleDraftJson[rule.ruleId] !== undefined)
      return ruleDraftJson[rule.ruleId];
    return rule.effectiveRequiredAttributes ?? "[]";
  }

  function setDraftJson(ruleId: string, value: string) {
    ruleDraftJson = { ...ruleDraftJson, [ruleId]: value };
    ruleJsonError = { ...ruleJsonError, [ruleId]: null };
  }

  function validateEffAttrsJson(json: string): string | null {
    try {
      const arr = JSON.parse(json);
      if (!Array.isArray(arr)) return "Must be a JSON array";
      for (let i = 0; i < arr.length; i++) {
        if (typeof arr[i] !== "object" || arr[i] === null) {
          return `Item ${i} must be an object`;
        }
      }
      return null;
    } catch (e: any) {
      return e.message ?? "Invalid JSON";
    }
  }

  async function saveRuleJson(rule: UploadedSchemaRule) {
    const json = getDraftJson(rule);
    const err = validateEffAttrsJson(json);
    if (err) {
      ruleJsonError = { ...ruleJsonError, [rule.ruleId]: err };
      return;
    }
    ruleSaving = { ...ruleSaving, [rule.ruleId]: true };
    ruleJsonError = { ...ruleJsonError, [rule.ruleId]: null };
    try {
      await client
        .mutation(UPDATE_UPLOADED_SCHEMA_RULE_MUTATION, {
          ruleId: rule.ruleId,
          effectiveRequiredAttributesJson: json,
        })
        .toPromise();
      uploadedSchemaRules = uploadedSchemaRules.map((r) =>
        r.ruleId === rule.ruleId
          ? { ...r, effectiveRequiredAttributes: json }
          : r,
      );
      const { [rule.ruleId]: _, ...rest } = ruleDraftJson;
      ruleDraftJson = rest;
    } catch (e: any) {
      ruleJsonError = {
        ...ruleJsonError,
        [rule.ruleId]: e.message ?? "Save failed",
      };
    } finally {
      ruleSaving = { ...ruleSaving, [rule.ruleId]: false };
    }
  }

  let ruleEditAttrDraft = $state<Record<string, EffAttr>>({});

  function startEditAttr(rule: UploadedSchemaRule, index: number) {
    const attrs = parseEffAttrs(rule.effectiveRequiredAttributes);
    ruleEditingAttr = { ...ruleEditingAttr, [rule.ruleId]: index };
    ruleEditAttrDraft = {
      ...ruleEditAttrDraft,
      [`${rule.ruleId}:${index}`]: { ...attrs[index] },
    };
  }

  function cancelEditAttr(ruleId: string) {
    ruleEditingAttr = { ...ruleEditingAttr, [ruleId]: null };
  }

  async function saveAttrEdit(rule: UploadedSchemaRule, index: number) {
    const key = `${rule.ruleId}:${index}`;
    const draft = ruleEditAttrDraft[key];
    if (!draft) return;
    const attrs = parseEffAttrs(rule.effectiveRequiredAttributes);
    attrs[index] = { ...attrs[index], ...draft };
    const json = JSON.stringify(attrs, null, 2);
    ruleEditingAttr = { ...ruleEditingAttr, [rule.ruleId]: null };
    const { [key]: _, ...rest } = ruleEditAttrDraft;
    ruleEditAttrDraft = rest;
    ruleSaving = { ...ruleSaving, [rule.ruleId]: true };
    ruleJsonError = { ...ruleJsonError, [rule.ruleId]: null };
    try {
      await client
        .mutation(UPDATE_UPLOADED_SCHEMA_RULE_MUTATION, {
          ruleId: rule.ruleId,
          effectiveRequiredAttributesJson: json,
        })
        .toPromise();
      uploadedSchemaRules = uploadedSchemaRules.map((r) =>
        r.ruleId === rule.ruleId
          ? { ...r, effectiveRequiredAttributes: json }
          : r,
      );
    } catch (e: any) {
      ruleJsonError = {
        ...ruleJsonError,
        [rule.ruleId]: e.message ?? "Save failed",
      };
    } finally {
      ruleSaving = { ...ruleSaving, [rule.ruleId]: false };
    }
  }

  $effect(() => {
    if (branchId) loadSchemas();
  });

  onMount(() => {
    applyContextFromUrl();
    applyContextFallbackFromSettings();
    loadUploadedSchemas();
    loadProjects();
    channel = new BroadcastChannel(SCHEMA_CHANNEL);
    channel.onmessage = handleIncomingMessage;
    channel.postMessage({ type: "request-context" } satisfies SchemaMessage);
  });

  $effect(() => {
    if (branchId && !projectId) resolveProjectIdFromBranch();
  });

  $effect(() => {
    if (projectId && !applyProjectId) applyProjectId = projectId;
  });

  $effect(() => {
    if (activeAppliedSchema && applyProjectId) {
      const stillApplied = appliedSchemasForProject.some(
        (us) => us.id === activeAppliedSchema?.id,
      );
      if (!stillApplied) activeAppliedSchema = null;
    }
  });

  onDestroy(() => {
    channel?.close();
  });
</script>

<div class="schema-page">
  <header class="page-header">
    <h2>Schema Browser</h2>
  </header>

  {#if error}
    <div class="error-bar">
      {error}
      <button onclick={() => (error = null)}>✕</button>
    </div>
  {/if}

  <!-- Uploaded IFC Schemas (from POST /ifc-schema) -->
  <section class="uploaded-schemas-section">
    <div class="section-header">
      <h3>Uploaded IFC Schemas</h3>
      <div class="uploaded-schemas-controls">
        <input
          class="uploaded-schema-search-input"
          type="text"
          placeholder="Search schemas…"
          bind:value={uploadedSchemaSearchQuery}
          aria-label="Search uploaded schemas"
        />
        <div class="project-selector">
          <label for="apply-project-select">Apply to project:</label>
          <select
            id="apply-project-select"
            class="input-sm"
            value={applyProjectId ?? ""}
            onchange={(e) => {
              applyProjectId =
                (e.currentTarget as HTMLSelectElement).value || null;
            }}
          >
            <option value="">Select project…</option>
            {#each projects as p}
              <option value={p.id}>{p.name}</option>
            {/each}
          </select>
        </div>
      </div>
    </div>
    {#if uploadedSchemasLoading}
      <div class="empty-state">Loading uploaded schemas…</div>
    {:else if uploadedSchemas.length === 0}
      <div class="empty-state">
        No uploaded schemas. Use POST /ifc-schema to upload IFC schema
        definitions.
      </div>
    {:else if filteredUploadedSchemas.length === 0}
      <div class="empty-state">
        No schemas match "{uploadedSchemaSearchQuery.trim()}".
      </div>
    {:else}
      <ul class="uploaded-schema-list">
        {#each filteredUploadedSchemas as us (us.id)}
          <li class="uploaded-schema-item">
            <div class="uploaded-schema-info">
              <span class="uploaded-schema-name">{us.versionName}</span>
              <span class="uploaded-schema-rules"
                >{us.ruleCount} validation rules</span
              >
              {#if us.projectIds.length > 0}
                <span class="applied-badge"
                  >Applied to {us.projectIds.length} project{us.projectIds
                    .length === 1
                    ? ""
                    : "s"}</span
                >
              {/if}
            </div>
            {#if applyProjectId}
              {#if us.projectIds.includes(applyProjectId)}
                <button
                  class="btn-sm"
                  onclick={() => unapplySchemaFromProject(us.id)}
                  >Unapply</button
                >
              {:else}
                <button
                  class="btn-sm btn-primary"
                  onclick={() => applySchemaToProject(us.id)}>Apply</button
                >
              {/if}
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <div class="content">
    <!-- Left panel: applied schemas -->
    <aside class="schema-list">
      <div class="panel-header">
        <h3>Applied Schemas</h3>
        {#if appliedSchemasForProject.length > 0}
          <button
            class="btn-sm btn-success"
            onclick={runAllValidationsForAppliedSchemas}
            disabled={runningAllValidations || !branchId}
          >
            {runningAllValidations ? "Running…" : "▶ Run all"}
          </button>
        {/if}
      </div>

      {#if !applyProjectId}
        <div class="empty-state">
          Select a project above to see applied schemas.
        </div>
      {:else if uploadedSchemasLoading}
        <div class="empty-state">Loading…</div>
      {:else if appliedSchemasForProject.length === 0}
        <div class="empty-state">
          No schemas applied to this project. Apply schemas above.
        </div>
      {:else}
        <ul class="schema-items">
          {#each appliedSchemasForProject as us (us.id)}
            <li class:active={activeAppliedSchema?.id === us.id}>
              <button
                class="schema-item"
                onclick={() => selectAppliedSchema(us)}
              >
                <span class="schema-name">{us.versionName}</span>
                <span class="rule-count">{us.ruleCount} rules</span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </aside>

    <!-- Right panel: schema detail -->
    <main class="schema-detail">
      {#if activeAppliedSchema}
        {@const sel = activeAppliedSchema}
        <div class="detail-header">
          <div>
            <h3>{sel.versionName}</h3>
            <span class="version-badge">{sel.ruleCount} rules</span>
          </div>
          <div class="detail-actions">
            <button
              class="btn-sm btn-success"
              onclick={() => runValidationByUploadedSchema(sel.id)}
              disabled={runningValidationSchemaId === sel.id ||
                runningAllValidations ||
                !branchId}
            >
              {runningValidationSchemaId === sel.id
                ? "Running…"
                : "▶ Run validation"}
            </button>
          </div>
        </div>

        <!-- Rules list (collapsible by severity) -->
        <div class="rules-section">
          <h4>Rules ({uploadedSchemaRules.length})</h4>
          {#if uploadedSchemaRulesLoading}
            <div class="empty-state">Loading rules…</div>
          {:else if uploadedSchemaRules.length === 0}
            <div class="empty-state">No rules in this schema.</div>
          {:else}
            <div class="rules-by-severity">
              {#each rulesBySeverity as group (group.severity)}
                <details class="severity-group">
                  <summary class="severity-group-summary">
                    <span class="severity-badge {severityClass(group.severity)}"
                      >{group.severity}</span
                    >
                    <span
                      >{group.rules.length} rule{group.rules.length === 1
                        ? ""
                        : "s"}</span
                    >
                  </summary>
                  <div class="rules-list">
                    {#each group.rules as rule (rule.ruleId)}
                      <details class="rule-card rule-card-expandable">
                        <summary class="rule-header">
                          <span
                            class="severity-badge {severityClass(
                              rule.displaySeverity,
                            )}">{rule.displaySeverity}</span
                          >
                          <span class="rule-name">{rule.name}</span>
                          <span class="rule-target">{rule.targetIfcClass}</span>
                        </summary>
                        <div class="rule-details">
                          <div class="rule-detail-row">
                            <strong>Name:</strong>
                            <span>{rule.name}</span>
                          </div>
                          {#if rule.description}
                            <div class="rule-detail-row">
                              <strong>Description:</strong>
                              <span>{rule.description}</span>
                            </div>
                          {/if}
                          {#if rule.effectiveRequiredAttributes}
                            <div class="rule-detail-row eff-attrs-block">
                              <div class="eff-attrs-header">
                                <strong>Effective required attributes</strong>
                                <button
                                  class="btn-sm view-mode-toggle"
                                  class:card-active={getViewMode(
                                    rule.ruleId,
                                  ) === "card"}
                                  class:json-active={getViewMode(
                                    rule.ruleId,
                                  ) === "json"}
                                  onclick={() => toggleViewMode(rule)}
                                >
                                  <span class="toggle-option">Card</span>
                                  <span class="toggle-option">JSON</span>
                                </button>
                              </div>
                              {#if getViewMode(rule.ruleId) === "card"}
                                <div class="eff-attr-cards">
                                  {#each parseEffAttrs(rule.effectiveRequiredAttributes) as attr, i}
                                    {@const editing =
                                      ruleEditingAttr[rule.ruleId] === i}
                                    {@const draftKey = `${rule.ruleId}:${i}`}
                                    {@const draft = ruleEditAttrDraft[draftKey]}
                                    <div class="eff-attr-card">
                                      {#if editing && draft}
                                        <div class="eff-attr-edit-form">
                                          <label
                                            >Name <input
                                              type="text"
                                              bind:value={draft.name}
                                              class="input-sm"
                                            /></label
                                          >
                                          <label
                                            >Type <input
                                              type="text"
                                              bind:value={draft.type}
                                              class="input-sm"
                                            /></label
                                          >
                                          <label class="checkbox-label">
                                            <input
                                              type="checkbox"
                                              bind:checked={draft.required}
                                            />
                                            Required
                                          </label>
                                          <label
                                            >Defined on <input
                                              type="text"
                                              bind:value={draft.definedOn}
                                              class="input-sm"
                                            /></label
                                          >
                                          <div class="eff-attr-edit-actions">
                                            <button
                                              class="btn-sm btn-primary"
                                              onclick={() =>
                                                saveAttrEdit(rule, i)}
                                              disabled={ruleSaving[rule.ruleId]}
                                            >
                                              {ruleSaving[rule.ruleId]
                                                ? "Saving…"
                                                : "Save"}
                                            </button>
                                            <button
                                              class="btn-sm"
                                              onclick={() =>
                                                cancelEditAttr(rule.ruleId)}
                                              >Cancel</button
                                            >
                                          </div>
                                        </div>
                                      {:else}
                                        <div class="eff-attr-card-content">
                                          <span class="eff-attr-name"
                                            >{attr.name ?? "—"}</span
                                          >
                                          <span class="eff-attr-type"
                                            >{attr.type ?? "—"}</span
                                          >
                                          <span class="eff-attr-required"
                                            >{attr.required
                                              ? "Required"
                                              : "Optional"}</span
                                          >
                                          {#if attr.definedOn}
                                            <span class="eff-attr-defined"
                                              >{attr.definedOn}</span
                                            >
                                          {/if}
                                          <button
                                            class="btn-icon eff-attr-edit-btn"
                                            onclick={() =>
                                              startEditAttr(rule, i)}
                                            aria-label="Edit">✎</button
                                          >
                                        </div>
                                      {/if}
                                    </div>
                                  {/each}
                                </div>
                              {:else}
                                <div class="eff-attrs-json-block">
                                  <textarea
                                    class="rule-schema-json-input"
                                    value={getDraftJson(rule)}
                                    oninput={(e) =>
                                      setDraftJson(
                                        rule.ruleId,
                                        (e.currentTarget as HTMLTextAreaElement)
                                          .value,
                                      )}
                                    spellcheck="false"
                                    rows="8"
                                  ></textarea>
                                  {#if ruleJsonError[rule.ruleId]}
                                    <div class="rule-json-error">
                                      {ruleJsonError[rule.ruleId]}
                                    </div>
                                  {/if}
                                  <button
                                    class="btn-sm btn-primary"
                                    onclick={() => saveRuleJson(rule)}
                                    disabled={ruleSaving[rule.ruleId]}
                                  >
                                    {ruleSaving[rule.ruleId]
                                      ? "Saving…"
                                      : "Save"}
                                  </button>
                                </div>
                              {/if}
                            </div>
                          {/if}
                        </div>
                      </details>
                    {/each}
                  </div>
                </details>
              {/each}
            </div>
          {/if}
        </div>

        <!-- Validation results -->
        {#if uploadedSchemaValidationResult && uploadedSchemaValidationResult.schemaGlobalId === sel.id}
          <div class="results-section">
            <h4>Validation Results</h4>
            <div class="results-summary">
              <span class="result-badge error"
                >{uploadedSchemaValidationResult.errorCount} errors</span
              >
              <span class="result-badge warning"
                >{uploadedSchemaValidationResult.warningCount} warnings</span
              >
              <span class="result-badge info"
                >{uploadedSchemaValidationResult.infoCount} info</span
              >
              <span class="result-badge passed"
                >{uploadedSchemaValidationResult.passedCount} passed</span
              >
            </div>
            {#each uploadedSchemaValidationResult.results as rr (rr.ruleGlobalId)}
              <div class="result-card" class:failed={!rr.passed}>
                <div class="result-header">
                  <span class="severity-badge {severityClass(rr.severity)}"
                    >{rr.severity}</span
                  >
                  <span>{rr.ruleName}</span>
                  <span class="result-status"
                    >{rr.passed ? "✓ PASS" : "✗ FAIL"}</span
                  >
                </div>
                {#if rr.violations.length > 0}
                  <details>
                    <summary
                      >{rr.violations.length} violation{rr.violations.length ===
                      1
                        ? ""
                        : "s"}</summary
                    >
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
          <p>
            Select a schema from the list to view its rules and run validation.
          </p>
        </div>
      {/if}
    </main>
  </div>
</div>

<style>
  /* Layout: flex column, gap-based spacing, design tokens */
  .schema-page {
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
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .page-header h2 {
    margin: 0;
    font-size: 0.95rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--color-action-primary);
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

  .error-bar button {
    background: none;
    border: none;
    color: var(--color-danger);
    cursor: pointer;
  }

  .error-bar button:hover {
    opacity: 0.8;
  }

  /* Uploaded schemas section */
  .uploaded-schemas-section {
    flex-shrink: 0;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--color-border-subtle);
    background: var(--color-bg-elevated);
  }

  .uploaded-schemas-section .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.5rem;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .uploaded-schemas-section h3 {
    margin: 0;
    font-size: 0.85rem;
    color: var(--color-action-primary);
  }

  .uploaded-schemas-controls {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  .uploaded-schema-search-input {
    padding: 0.35rem 0.5rem;
    min-width: 11.25rem;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-default);
    border-radius: 0.5rem;
    color: var(--color-text-primary);
    font-size: 0.8rem;
    outline: none;
  }

  .uploaded-schema-search-input::placeholder {
    color: var(--color-text-muted);
  }

  .uploaded-schema-search-input:focus {
    border-color: var(--color-border-strong);
  }

  .uploaded-schema-search-input:focus-visible {
    box-shadow: 0 0 0 2px
      color-mix(in srgb, var(--color-border-strong) 25%, transparent);
  }

  .project-selector {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .project-selector label {
    font-size: 0.78rem;
    color: var(--color-text-secondary);
  }

  .uploaded-schema-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .uploaded-schema-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.4rem 0.75rem;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.75rem;
  }

  .uploaded-schema-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .uploaded-schema-name {
    font-weight: 500;
    font-size: 0.85rem;
    color: var(--color-text-primary);
  }

  .uploaded-schema-rules {
    font-size: 0.72rem;
    color: var(--color-text-muted);
  }

  .applied-badge {
    font-size: 0.7rem;
    padding: 0.1rem 0.4rem;
    border-radius: 0.25rem;
    background: color-mix(in srgb, var(--color-success) 15%, transparent);
    color: var(--color-text-primary);
  }

  /* Main content: aside + main */
  .content {
    flex: 1;
    display: flex;
    overflow: hidden;
  }

  .schema-list {
    width: 17.5rem;
    flex-shrink: 0;
    border-right: 1px solid var(--color-border-subtle);
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    background: var(--color-bg-elevated);
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .panel-header h3 {
    margin: 0;
    font-size: 0.85rem;
    color: var(--color-text-secondary);
  }

  .creator-form {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--color-border-subtle);
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
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .schema-items li.active {
    background: color-mix(in srgb, var(--color-action-primary) 8%, transparent);
  }

  .schema-item {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    padding: 0.6rem 1rem;
    background: none;
    border: none;
    color: var(--color-text-primary);
    text-align: left;
    cursor: pointer;
  }

  .schema-item:hover {
    background: var(--color-bg-elevated);
  }

  .schema-item:focus-visible {
    outline: 2px solid var(--color-border-strong);
    outline-offset: -2px;
  }

  .schema-name {
    font-size: 0.85rem;
    font-weight: 500;
  }

  .rule-count {
    font-size: 0.72rem;
    color: var(--color-text-muted);
  }

  .schema-detail {
    flex: 1;
    overflow-y: auto;
    padding: 1rem 1.5rem;
    background: var(--color-bg-canvas);
  }

  .detail-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 1rem;
    gap: 1rem;
  }

  .detail-header h3 {
    margin: 0 0 0.25rem 0;
    font-size: 1.1rem;
    color: var(--color-text-primary);
  }

  .detail-description {
    color: var(--color-text-secondary);
    font-size: 0.82rem;
    margin: 0;
  }

  .version-badge {
    display: inline-block;
    margin-top: 0.3rem;
    padding: 0.1rem 0.5rem;
    border-radius: 999px;
    font-size: 0.7rem;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    color: var(--color-text-secondary);
  }

  .detail-actions {
    display: flex;
    gap: 0.5rem;
    flex-shrink: 0;
  }

  /* Rule editor card: 12px radius per style guide */
  .rule-editor {
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.75rem;
    padding: 1rem;
    margin-bottom: 1rem;
  }

  .rule-editor h4 {
    margin: 0 0 0.75rem 0;
    font-size: 0.9rem;
    color: var(--color-action-primary);
  }

  .rule-editor h5 {
    margin: 0.75rem 0 0.5rem 0;
    font-size: 0.82rem;
    color: var(--color-text-secondary);
  }

  .form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
  }

  .form-grid label {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    font-size: 0.78rem;
    color: var(--color-text-secondary);
  }

  .checkbox-label {
    flex-direction: row !important;
    align-items: center;
    gap: 0.5rem !important;
  }

  .condition-row {
    display: flex;
    gap: 0.4rem;
    margin-bottom: 0.4rem;
  }

  .condition-row .input-sm {
    flex: 1;
  }

  .form-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.75rem;
  }

  .rules-section {
    margin-top: 1rem;
  }

  .rules-section h4 {
    margin: 0 0 0.5rem 0;
    font-size: 0.9rem;
    color: var(--color-text-primary);
  }

  .rules-by-severity {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .severity-group {
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.75rem;
    overflow: hidden;
  }

  .severity-group-summary {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    cursor: pointer;
    font-size: 0.85rem;
    color: var(--color-text-primary);
    list-style: none;
  }

  .severity-group-summary::-webkit-details-marker {
    display: none;
  }

  .severity-group-summary::before {
    content: "▶";
    font-size: 0.65rem;
    transition: transform 0.2s;
  }

  .severity-group[open] .severity-group-summary::before {
    transform: rotate(90deg);
  }

  .severity-group .rules-list {
    padding: 0 0.75rem 0.75rem;
  }

  .rules-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .rule-card {
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.75rem;
    padding: 0.6rem 0.8rem;
  }

  .rule-card-expandable {
    padding: 0;
    overflow: hidden;
  }

  .rule-card-expandable .rule-header {
    padding: 0.6rem 0.8rem;
    cursor: pointer;
    list-style: none;
  }

  .rule-card-expandable .rule-header::-webkit-details-marker {
    display: none;
  }

  .rule-card-expandable .rule-header::before {
    content: "▶";
    font-size: 0.6rem;
    margin-right: 0.25rem;
    opacity: 0.7;
    transition: transform 0.2s;
  }

  .rule-card-expandable[open] .rule-header::before {
    transform: rotate(90deg);
  }

  .rule-details {
    padding: 0 0.8rem 0.8rem;
    border-top: 1px solid var(--color-border-subtle);
    margin-top: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .rule-detail-row {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    font-size: 0.8rem;
  }

  .rule-detail-row strong {
    color: var(--color-text-secondary);
    font-weight: 500;
  }

  .rule-schema-json {
    margin: 0;
    padding: 0.5rem;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.5rem;
    font-size: 0.72rem;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .eff-attrs-block {
    margin-top: 0.5rem;
  }

  .eff-attrs-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.5rem;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .view-mode-toggle {
    display: inline-flex;
    border-radius: 0.25rem;
    border: 1px solid var(--color-border-subtle);
    background: var(--color-bg-elevated);
  }

  .view-mode-toggle .toggle-option {
    padding: 0.3rem 0.5rem;
    font-size: 0.8rem;
    border-radius: 0.25rem;
    transition:
      background 0.15s,
      color 0.15s;
  }

  .view-mode-toggle.card-active .toggle-option:first-child,
  .view-mode-toggle.json-active .toggle-option:last-child {
    background: var(--color-action-primary);
    color: var(--color-bg-surface);
  }

  .eff-attr-cards {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .eff-attr-card {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.5rem;
    padding: 0.5rem 0.75rem;
  }

  .eff-attr-card-content {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .eff-attr-name {
    font-weight: 500;
    color: var(--color-text-primary);
  }

  .eff-attr-type {
    font-size: 0.8rem;
    color: var(--color-text-secondary);
  }

  .eff-attr-required {
    font-size: 0.75rem;
    padding: 0.1rem 0.35rem;
    border-radius: 0.25rem;
    background: color-mix(
      in srgb,
      var(--color-action-primary) 15%,
      transparent
    );
    color: var(--color-text-secondary);
  }

  .eff-attr-defined {
    font-size: 0.75rem;
    color: var(--color-text-muted);
    font-style: italic;
  }

  .eff-attr-edit-btn {
    margin-left: auto;
  }

  .eff-attr-edit-form {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .eff-attr-edit-form label {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    font-size: 0.8rem;
    color: var(--color-text-secondary);
  }

  .eff-attr-edit-form .checkbox-label {
    flex-direction: row;
    align-items: center;
  }

  .eff-attr-edit-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.25rem;
  }

  .eff-attrs-json-block {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .rule-schema-json-input {
    font-family: ui-monospace, "Cascadia Code", "Fira Code", monospace;
    font-size: 0.78rem;
    padding: 0.5rem;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    border-radius: 0.5rem;
    color: var(--color-text-primary);
    resize: vertical;
    min-height: 6rem;
  }

  .rule-schema-json-input:focus {
    outline: none;
    border-color: var(--color-border-strong);
  }

  .rule-json-error {
    font-size: 0.8rem;
    color: var(--color-danger);
  }

  .rule-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .severity-badge {
    display: inline-block;
    padding: 0.1rem 0.4rem;
    border-radius: 0.25rem;
    font-size: 0.68rem;
    font-weight: 600;
    color: var(--color-bg-surface);
    text-transform: uppercase;
  }

  .severity-badge.severity-error {
    background: var(--color-danger);
  }

  .severity-badge.severity-warning {
    background: var(--color-warning);
  }

  .severity-badge.severity-info {
    background: var(--color-info);
  }

  .rule-name {
    font-size: 0.85rem;
    font-weight: 500;
    flex: 1;
    color: var(--color-text-primary);
  }

  .rule-target {
    font-size: 0.75rem;
    color: var(--color-text-muted);
    font-family: monospace;
  }

  .rule-conditions {
    margin-top: 0.3rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
  }

  .rule-conditions code {
    font-size: 0.72rem;
    padding: 0.1rem 0.4rem;
    border-radius: 0.2rem;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-subtle);
    color: var(--color-text-secondary);
  }

  .spatial-ctx {
    margin-top: 0.25rem;
    font-size: 0.72rem;
    color: var(--color-text-muted);
    font-style: italic;
  }

  /* Validation results */
  .results-section {
    margin-top: 1.5rem;
    border-top: 1px solid var(--color-border-subtle);
    padding-top: 1rem;
  }

  .results-section h4 {
    margin: 0 0 0.5rem 0;
    color: var(--color-text-primary);
  }

  .results-summary {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }

  .result-badge {
    padding: 0.2rem 0.6rem;
    border-radius: 0.25rem;
    font-size: 0.75rem;
    font-weight: 600;
  }

  .result-badge.error {
    background: color-mix(in srgb, var(--color-danger) 15%, transparent);
    color: var(--color-danger);
  }

  .result-badge.warning {
    background: color-mix(in srgb, var(--color-warning) 15%, transparent);
    color: var(--color-warning);
  }

  .result-badge.info {
    background: color-mix(in srgb, var(--color-info) 15%, transparent);
    color: var(--color-info);
  }

  .result-badge.passed {
    background: color-mix(in srgb, var(--color-success) 15%, transparent);
    color: var(--color-text-primary);
  }

  .result-card {
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.75rem;
    padding: 0.5rem 0.8rem;
    margin-bottom: 0.4rem;
  }

  .result-card.failed {
    border-color: var(--color-danger);
  }

  .result-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
    color: var(--color-text-primary);
  }

  .result-status {
    margin-left: auto;
    font-size: 0.78rem;
    font-weight: 600;
  }

  details {
    margin-top: 0.3rem;
  }

  summary {
    cursor: pointer;
    font-size: 0.78rem;
    color: var(--color-text-secondary);
  }

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
    border-bottom: 1px solid var(--color-border-subtle);
    color: var(--color-text-secondary);
  }

  .violations-list code {
    color: var(--color-action-primary);
    font-size: 0.7rem;
  }

  .viol-class {
    color: var(--color-text-muted);
  }

  .viol-msg {
    color: var(--color-text-primary);
    flex: 1;
  }

  .empty-state {
    padding: 1.5rem;
    text-align: center;
    color: var(--color-text-muted);
    font-size: 0.82rem;
  }

  .empty-state-center {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--color-text-muted);
  }

  /* Shared controls: design tokens, focus states */
  .input-sm {
    padding: 0.35rem 0.5rem;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-default);
    border-radius: 0.5rem;
    color: var(--color-text-primary);
    font-size: 0.8rem;
    outline: none;
  }

  .input-sm::placeholder {
    color: var(--color-text-muted);
  }

  .input-sm:focus {
    border-color: var(--color-border-strong);
  }

  .input-sm:focus-visible {
    box-shadow: 0 0 0 2px
      color-mix(in srgb, var(--color-border-strong) 25%, transparent);
  }

  .btn-sm {
    padding: 0.2rem;
    border-radius: 0.5rem;
    font-size: 0.78rem;
    border: 1px solid var(--color-border-default);
    background: var(--color-bg-elevated);
    color: var(--color-text-secondary);
    cursor: pointer;
  }

  .btn-sm:hover {
    background: color-mix(
      in srgb,
      var(--color-text-primary) 6%,
      var(--color-bg-elevated)
    );
    color: var(--color-text-primary);
  }

  .btn-sm:focus-visible {
    outline: 2px solid var(--color-border-strong);
    outline-offset: 2px;
  }

  .btn-sm:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .btn-primary {
    background: var(--color-action-primary);
    color: var(--color-bg-surface);
    border-color: var(--color-action-primary);
  }

  .btn-primary:hover {
    background: var(--color-brand-500);
    border-color: var(--color-brand-500);
  }

  .btn-success {
    background: var(--color-success);
    color: var(--color-bg-surface);
    border-color: var(--color-success);
  }

  .btn-success:hover {
    background: var(--color-brand-500);
    border-color: var(--color-brand-500);
  }

  .btn-icon {
    background: none;
    border: none;
    color: var(--color-text-muted);
    cursor: pointer;
    padding: 0.2rem 0.4rem;
    font-size: 0.75rem;
    border-radius: 0.25rem;
  }

  .btn-icon:hover {
    color: var(--color-text-secondary);
  }

  .btn-icon:focus-visible {
    outline: 2px solid var(--color-border-strong);
    outline-offset: 2px;
  }

  .btn-danger:hover {
    color: var(--color-danger);
  }
</style>
