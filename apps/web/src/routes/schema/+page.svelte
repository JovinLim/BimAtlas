<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { page } from "$app/stores";
  import { client } from "$lib/api/client";
import {
    VALIDATION_RULES_FOR_UPLOADED_SCHEMA_QUERY,
    CREATE_UPLOADED_SCHEMA_RULE_MUTATION,
    UPDATE_UPLOADED_SCHEMA_RULE_MUTATION,
    UPDATE_UPLOADED_SCHEMA_RULE_FULL_MUTATION,
    DELETE_UPLOADED_SCHEMA_RULE_MUTATION,
    CREATE_UPLOADED_SCHEMA_MUTATION,
    RUN_VALIDATION_BY_UPLOADED_SCHEMA_MUTATION,
    UPLOADED_SCHEMAS_QUERY,
    APPLY_SCHEMA_TO_PROJECT_MUTATION,
    UNAPPLY_SCHEMA_FROM_PROJECT_MUTATION,
    PROJECTS_QUERY,
    BRANCH_QUERY,
    DELETE_UPLOADED_SCHEMA_MUTATION,
    VALIDATION_RESULTS_QUERY,
  } from "$lib/api/client";
  import { SCHEMA_CHANNEL, type SchemaMessage } from "$lib/schema/protocol";
  import { loadSettings } from "$lib/state/persistence";

  let branchId = $state<string | null>(null);
  let projectId = $state<string | null>(null);
  let revision = $state<number | null>(null);

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
    revisionSeq: number;
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
    ruleSchemaJson?: string | null;
    displaySeverity: string;
    severity: string;
  };
  type ProjectInfo = { id: string; name: string; description: string | null };

  let ruleViewMode = $state<Record<string, "card" | "json">>({});
  let ruleDraftJson = $state<Record<string, string>>({});
  let ruleEditingAttr = $state<Record<string, number | null>>({});
  let ruleSaving = $state<Record<string, boolean>>({});
  let ruleJsonError = $state<Record<string, string | null>>({});
  let ruleIncludeSubclassesSaving = $state<Record<string, boolean>>({});

  let uploadedSchemas = $state<UploadedSchema[]>([]);
  let uploadedSchemaSearchQuery = $state("");
  let projects = $state<ProjectInfo[]>([]);
  let uploadedSchemasLoading = $state(false);
  let applyProjectId = $state<string | null>(null);
  let existingSchemasExpanded = $state(true);

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
  let activeAppliedSchema = $state<UploadedSchema | null>(null);
  let uploadedSchemaRules = $state<UploadedSchemaRule[]>([]);
  let uploadedSchemaRulesLoading = $state(false);
  let validationRuns = $state<RunResult[]>([]);

  const disabledSchemaIdsForRevision = $derived.by(() => {
    const rev = revision;
    if (rev == null) return new Set<string>();
    const ids = new Set<string>();
    for (const run of validationRuns) {
      if (run.revisionSeq === rev) {
        ids.add(run.schemaGlobalId);
      }
    }
    return ids;
  });

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

  // Schema creator state (uploaded schemas)
  let showSchemaCreator = $state(false);
  let newSchemaName = $state("");
  let newSchemaDescription = $state("");

  // Create rule modal state (editingRuleId set when editing existing rule)
  let editingRuleId = $state<string | null>(null);
  const CONDITION_OPERATORS = [
    { value: "equals", label: "equals" },
    { value: "not_equals", label: "not equals" },
    { value: "contains", label: "contains" },
    { value: "exists", label: "exists" },
    { value: "not_exists", label: "not exists" },
    { value: "greater_than", label: "greater than" },
    { value: "less_than", label: "less than" },
    { value: "matches", label: "matches (regex)" },
  ] as const;
  const SPATIAL_TRAVERSALS = [
    "IfcRelContainedInSpatialStructure",
    "IfcRelAggregates",
    "IfcRelConnectsElements",
    "IfcRelVoidsElement",
    "IfcRelFillsElement",
    "IfcRelDefinesByType",
  ] as const;
  let showCreateRuleModal = $state(false);
  let createRuleMode = $state<"card" | "json">("card");
  let createRuleName = $state("");
  let createRuleDescription = $state("");
  type CreateRuleSchema = {
    ruleType: string;
    TargetClass: string;
    ConditionLogic: "AND" | "OR";
    Conditions: { path: string; operator: string; value: string }[];
    SpatialContext: { traversal: string; scope_class: string; scope_name: string };
    severity: string;
    includeSubclasses?: boolean;
  };
  const DEFAULT_CREATE_RULE_SCHEMA: CreateRuleSchema = {
    ruleType: "attribute_check",
    TargetClass: "IfcWall",
    ConditionLogic: "OR",
    Conditions: [
      { path: "PropertySets.Pset_WallCommon.FireRating", operator: "greater_than", value: "2" },
      { path: "PropertySets.Pset_WallCommon.FireRating", operator: "less_than", value: "5" },
    ],
    SpatialContext: {
      traversal: "IfcRelContainedInSpatialStructure",
      scope_class: "IfcSpace",
      scope_name: "Room X",
    },
    severity: "Error",
    includeSubclasses: false,
  };
  let createRuleSchema = $state<CreateRuleSchema>({ ...DEFAULT_CREATE_RULE_SCHEMA });
  const createRuleSchemaJson = $derived(JSON.stringify(createRuleSchema, null, 2));
  let createRuleSaving = $state(false);

  // Upload schemas modal
  let showUploadSchemasModal = $state(false);
  let uploadSchemasDragOver = $state(false);
  let uploadSchemasFiles = $state<File[]>([]);
  let uploadSchemasUploading = $state(false);
  let uploadSchemasResults = $state<{ name: string; ok: boolean; error?: string }[]>([]);
  let showUploadSchemaGuide = $state(false);

  const API_BASE = typeof import.meta !== "undefined" && import.meta.env?.VITE_API_URL
    ? (import.meta.env.VITE_API_URL as string).replace("/graphql", "")
    : "/api";

  // Validation results
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
      const result = await client
        .query(UPLOADED_SCHEMAS_QUERY, {}, { requestPolicy: "network-only" })
        .toPromise();
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

  async function loadValidationRuns() {
    if (!branchId) return;
    try {
      const result = await client
        .query(VALIDATION_RESULTS_QUERY, { branchId }, { requestPolicy: "network-only" })
        .toPromise();
      if (result.error) {
        // Do not surface as top-level error; this is auxiliary state.
        return;
      }
      validationRuns = (result.data?.validationResults ?? []) as RunResult[];
    } catch {
      // Ignore; validation runs are optional for Schema Browser UI.
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
      // Optimistic update: add project to schema so Applied Schemas panel updates immediately
      uploadedSchemas = uploadedSchemas.map((us) =>
        us.id === schemaId
          ? { ...us, projectIds: us.projectIds.includes(pid) ? us.projectIds : [...us.projectIds, pid] }
          : us,
      );
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
      // Optimistic update: remove project from schema so Applied Schemas panel updates immediately
      uploadedSchemas = uploadedSchemas.map((us) =>
        us.id === schemaId
          ? { ...us, projectIds: us.projectIds.filter((id) => id !== pid) }
          : us,
      );
      await loadUploadedSchemas();
    } catch (e: any) {
      error = e.message;
    }
  }

  async function deleteUploadedSchema(schemaId: string) {
    try {
      const ok = await client
        .mutation(DELETE_UPLOADED_SCHEMA_MUTATION, { schemaId })
        .toPromise()
        .then((r) => r.data?.deleteUploadedSchema);
      if (ok) {
        uploadedSchemas = uploadedSchemas.filter((us) => us.id !== schemaId);
        if (activeAppliedSchema?.id === schemaId) {
          activeAppliedSchema = null;
          uploadedSchemaRules = [];
          uploadedSchemaValidationResult = null;
        }
      }
    } catch (e: any) {
      error = e.message;
    }
  }

  async function selectAppliedSchema(schema: UploadedSchema) {
    activeAppliedSchema = schema;
    uploadedSchemaValidationResult = null;
    await loadUploadedSchemaRules(schema.id);
  }

  async function loadUploadedSchemaRules(schemaId: string) {
    uploadedSchemaRulesLoading = true;
    try {
      const result = await client
        .query(VALIDATION_RULES_FOR_UPLOADED_SCHEMA_QUERY, { schemaId }, { requestPolicy: "network-only" })
        .toPromise();
      uploadedSchemaRules = result.data?.validationRulesForUploadedSchema ?? [];
    } catch {
      uploadedSchemaRules = [];
    } finally {
      uploadedSchemaRulesLoading = false;
    }
  }

  async function createSchema() {
    if (!newSchemaName.trim()) return;
    try {
      const result = await client
        .mutation(CREATE_UPLOADED_SCHEMA_MUTATION, {
          name: newSchemaName.trim(),
        })
        .toPromise();
      if (result.data?.createUploadedSchema) {
        await loadUploadedSchemas();
        showSchemaCreator = false;
        newSchemaName = "";
        newSchemaDescription = "";
      }
    } catch (e: any) {
      error = e.message;
    }
  }

  function parseJsonToCreateRuleSchema(jsonStr: string): CreateRuleSchema | null {
    try {
      const parsed = JSON.parse(jsonStr);
      if (!parsed || typeof parsed !== "object") return null;
      const conds = Array.isArray(parsed.Conditions)
        ? parsed.Conditions.map((c: { path?: string; operator?: string; value?: string }) => ({
            path: String(c?.path ?? ""),
            operator: String(c?.operator ?? "exists"),
            value: String(c?.value ?? ""),
          }))
        : [{ path: "", operator: "exists", value: "" }];
      const sc = parsed.SpatialContext && typeof parsed.SpatialContext === "object" ? parsed.SpatialContext : {};
      const sev = String(parsed.severity ?? "Error");
      return {
        ruleType: String(parsed.ruleType ?? "attribute_check"),
        TargetClass: String(parsed.TargetClass ?? parsed.entity ?? ""),
        ConditionLogic: (parsed.ConditionLogic === "AND" ? "AND" : "OR") as "AND" | "OR",
        Conditions: conds,
        SpatialContext: {
          traversal: String(sc.traversal ?? ""),
          scope_class: String(sc.scope_class ?? ""),
          scope_name: String(sc.scope_name ?? ""),
        },
        severity: ["Error", "Warning", "Info"].includes(sev) ? sev : "Error",
        includeSubclasses: Boolean(parsed.includeSubclasses),
      };
    } catch {
      return null;
    }
  }

  function openCreateRuleModal() {
    editingRuleId = null;
    showCreateRuleModal = true;
    createRuleMode = "card";
    createRuleName = "";
    createRuleDescription = "";
    createRuleSchema = JSON.parse(JSON.stringify(DEFAULT_CREATE_RULE_SCHEMA));
  }

  function openCreateRuleModalForEdit(rule: UploadedSchemaRule) {
    editingRuleId = rule.ruleId;
    showCreateRuleModal = true;
    createRuleName = rule.name;
    createRuleDescription = rule.description ?? "";
    const ruleSeverity = rule.severity === "Required" ? "Error" : rule.severity;
    if (rule.ruleSchemaJson) {
      const parsed = parseJsonToCreateRuleSchema(rule.ruleSchemaJson);
      createRuleSchema = (parsed ?? {
        ...DEFAULT_CREATE_RULE_SCHEMA,
        TargetClass: rule.targetIfcClass,
        Conditions: [{ path: "", operator: "exists", value: "" }],
      });
      createRuleSchema = { ...createRuleSchema, severity: ruleSeverity };
      createRuleMode = "json";
    } else {
      createRuleMode = "card";
      createRuleSchema = {
        ...DEFAULT_CREATE_RULE_SCHEMA,
        TargetClass: rule.targetIfcClass,
        Conditions: [{ path: "", operator: "exists", value: "" }],
        severity: ruleSeverity,
      };
    }
  }

  function closeCreateRuleModal() {
    showCreateRuleModal = false;
    editingRuleId = null;
    createRuleName = "";
    createRuleDescription = "";
    createRuleSchema = JSON.parse(JSON.stringify(DEFAULT_CREATE_RULE_SCHEMA));
  }

  function addCreateRuleCondition() {
    createRuleSchema = {
      ...createRuleSchema,
      Conditions: [...createRuleSchema.Conditions, { path: "", operator: "exists", value: "" }],
    };
  }

  function removeCreateRuleCondition(i: number) {
    createRuleSchema = {
      ...createRuleSchema,
      Conditions: createRuleSchema.Conditions.filter((_, idx) => idx !== i),
    };
  }

  function openUploadSchemasModal() {
    showUploadSchemasModal = true;
    uploadSchemasFiles = [];
    uploadSchemasResults = [];
    showUploadSchemaGuide = false;
  }

  function closeUploadSchemasModal() {
    showUploadSchemasModal = false;
    uploadSchemasFiles = [];
    uploadSchemasResults = [];
  }

  function handleUploadSchemasDragOver(e: DragEvent) {
    e.preventDefault();
    uploadSchemasDragOver = true;
  }

  function handleUploadSchemasDragLeave(e: DragEvent) {
    e.preventDefault();
    uploadSchemasDragOver = false;
  }

  function handleUploadSchemasDrop(e: DragEvent) {
    e.preventDefault();
    uploadSchemasDragOver = false;
    const files = Array.from(e.dataTransfer?.files ?? []).filter((f) =>
      f.name.toLowerCase().endsWith(".json"),
    );
    if (files.length > 0) {
      uploadSchemasFiles = [...uploadSchemasFiles, ...files];
      submitUploadSchemas();
    }
  }

  function handleUploadSchemasFileInput(e: Event) {
    const input = e.target as HTMLInputElement;
    const files = Array.from(input.files ?? []).filter((f) =>
      f.name.toLowerCase().endsWith(".json"),
    );
    if (files.length > 0) {
      uploadSchemasFiles = [...uploadSchemasFiles, ...files];
      input.value = "";
      submitUploadSchemas();
    }
  }

  function removeUploadSchemaFile(i: number) {
    uploadSchemasFiles = uploadSchemasFiles.filter((_, idx) => idx !== i);
  }

  async function submitUploadSchemas() {
    if (uploadSchemasFiles.length === 0) return;
    uploadSchemasUploading = true;
    uploadSchemasResults = [];
    error = null;
    try {
      for (const file of uploadSchemasFiles) {
        try {
          const text = await file.text();
          const json = JSON.parse(text);
          const schemaName = json?.schema;
          if (!schemaName || typeof schemaName !== "string") {
            uploadSchemasResults = [...uploadSchemasResults, { name: file.name, ok: false, error: "Missing top-level 'schema' string" }];
            continue;
          }
          const entities = json?.entities;
          if (!entities || typeof entities !== "object") {
            uploadSchemasResults = [...uploadSchemasResults, { name: file.name, ok: false, error: "Missing 'entities' object" }];
            continue;
          }
          const res = await fetch(`${API_BASE}/ifc-schema`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(json),
          });
          if (res.ok) {
            uploadSchemasResults = [...uploadSchemasResults, { name: file.name, ok: true }];
          } else {
            const err = await res.json().catch(() => ({}));
            uploadSchemasResults = [...uploadSchemasResults, {
              name: file.name,
              ok: false,
              error: err.detail ?? res.statusText,
            }];
          }
        } catch (e: any) {
          uploadSchemasResults = [...uploadSchemasResults, {
            name: file.name,
            ok: false,
            error: e.message ?? "Parse error",
          }];
        }
      }
      await loadUploadedSchemas();
      uploadSchemasFiles = [];
    } catch (e: any) {
      error = e.message;
    } finally {
      uploadSchemasUploading = false;
    }
  }

  async function createUploadedSchemaRule() {
    const schema = activeAppliedSchema;
    if (!schema) return;
    if (!createRuleName.trim()) {
      error = "Rule name is required.";
      return;
    }
    createRuleSaving = true;
    error = null;
    try {
      const targetIfcClass = createRuleSchema.TargetClass.trim();
      if (!targetIfcClass) {
        error = "Target IFC class is required.";
        createRuleSaving = false;
        return;
      }
      const conditions = createRuleSchema.Conditions.filter((c) => c.path.trim()).map((c) => ({
        path: c.path.trim(),
        operator: c.operator || "exists",
        value: c.value?.trim() || null,
      }));
      if (conditions.length === 0) {
        error = "At least one condition with a path is required.";
        createRuleSaving = false;
        return;
      }
      const ruleSchemaForApi = {
        ...createRuleSchema,
        includeSubclasses: Boolean(createRuleSchema.includeSubclasses),
        Conditions: conditions,
        SpatialContext:
          createRuleSchema.SpatialContext.traversal?.trim() ||
          createRuleSchema.SpatialContext.scope_class?.trim() ||
          createRuleSchema.SpatialContext.scope_name?.trim()
            ? {
                traversal: createRuleSchema.SpatialContext.traversal.trim() || null,
                scope_class: createRuleSchema.SpatialContext.scope_class.trim() || null,
                scope_name: createRuleSchema.SpatialContext.scope_name.trim() || null,
              }
            : undefined,
      };
      const ruleSchemaJson = JSON.stringify(ruleSchemaForApi);

      if (editingRuleId) {
        const result = await client
          .mutation(UPDATE_UPLOADED_SCHEMA_RULE_FULL_MUTATION, {
            ruleId: editingRuleId,
            name: createRuleName.trim(),
            description: createRuleDescription.trim() || null,
            targetIfcClass,
            severity: createRuleSchema.severity,
            ruleSchemaJson,
          })
          .toPromise();
        if (result.error) {
          error = result.error.message;
        } else if (result.data?.updateUploadedSchemaRule) {
          closeCreateRuleModal();
          await loadUploadedSchemaRules(activeAppliedSchema!.id);
        } else {
          error = "Failed to update rule.";
        }
      } else {
        const result = await client
          .mutation(CREATE_UPLOADED_SCHEMA_RULE_MUTATION, {
            schemaId: schema.id,
            name: createRuleName.trim(),
            targetIfcClass,
            description: createRuleDescription.trim() || null,
            severity: createRuleSchema.severity,
            effectiveRequiredAttributesJson: null,
            ruleSchemaJson: ruleSchemaJson ?? null,
          })
          .toPromise();

        if (result.data?.createUploadedSchemaRule) {
          uploadedSchemaRules = [...uploadedSchemaRules, result.data.createUploadedSchemaRule];
          closeCreateRuleModal();
          await loadUploadedSchemas();
        }
      }
    } catch (e: any) {
      error = e.message;
    } finally {
      createRuleSaving = false;
    }
  }

  async function deleteUploadedSchemaRule(ruleId: string) {
    if (!activeAppliedSchema) return;
    try {
      const ok = await client
        .mutation(DELETE_UPLOADED_SCHEMA_RULE_MUTATION, { ruleId })
        .toPromise()
        .then((r) => r.data?.deleteUploadedSchemaRule);
      if (ok) {
        uploadedSchemaRules = uploadedSchemaRules.filter((r) => r.ruleId !== ruleId);
        await loadUploadedSchemas();
      }
    } catch (e: any) {
      error = e.message;
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
        await loadValidationRuns();
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
        if (revision != null && disabledSchemaIdsForRevision.has(us.id)) {
          continue;
        }
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
      await loadValidationRuns();
    } catch (e: any) {
      error = e.message;
    } finally {
      runningAllValidations = false;
    }
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

  function getRuleIncludeSubclasses(rule: UploadedSchemaRule): boolean {
    const raw = rule.ruleSchemaJson;
    if (!raw?.trim()) return false;
    try {
      const schema = JSON.parse(raw);
      return Boolean(schema?.includeSubclasses);
    } catch {
      return false;
    }
  }

  async function setRuleIncludeSubclasses(
    rule: UploadedSchemaRule,
    value: boolean,
  ) {
    ruleIncludeSubclassesSaving = {
      ...ruleIncludeSubclassesSaving,
      [rule.ruleId]: true,
    };
    try {
      let schema: Record<string, unknown> = {};
      if (rule.ruleSchemaJson?.trim()) {
        try {
          schema = JSON.parse(rule.ruleSchemaJson);
          if (!schema || typeof schema !== "object") schema = {};
        } catch {
          schema = {};
        }
      }
      const ruleSchemaJson = JSON.stringify({
        ...schema,
        includeSubclasses: value,
      });
      await client
        .mutation(UPDATE_UPLOADED_SCHEMA_RULE_FULL_MUTATION, {
          ruleId: rule.ruleId,
          ruleSchemaJson,
        })
        .toPromise();
      if (activeAppliedSchema)
        await loadUploadedSchemaRules(activeAppliedSchema.id);
    } catch (e: any) {
      ruleJsonError = {
        ...ruleJsonError,
        [rule.ruleId]: e?.message ?? "Failed to update",
      };
    } finally {
      ruleIncludeSubclassesSaving = {
        ...ruleIncludeSubclassesSaving,
        [rule.ruleId]: false,
      };
    }
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
    if (!branchId) {
      validationRuns = [];
      return;
    }
    loadValidationRuns();
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
      <button
        type="button"
        class="section-toggle"
        aria-expanded={existingSchemasExpanded}
        aria-label="Toggle existing schemas"
        onclick={() => (existingSchemasExpanded = !existingSchemasExpanded)}
      >
        <span class="collapse-chevron" class:expanded={existingSchemasExpanded}>▾</span>
        <h3>Existing Schemas</h3>
      </button>
      <div class="uploaded-schemas-controls">
        <button
          type="button"
          class="btn-sm btn-primary"
          onclick={openUploadSchemasModal}
        >
          Upload Schemas
        </button>
        <button
          type="button"
          class="btn-sm btn-primary"
          onclick={() => (showSchemaCreator = true)}
        >
          Create Schema
        </button>
        <input
          class="uploaded-schema-search-input"
          type="text"
          placeholder="Search schemas…"
          bind:value={uploadedSchemaSearchQuery}
          aria-label="Search uploaded schemas"
        />
      </div>
    </div>
    {#if existingSchemasExpanded}
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
                  class="btn-sm uploaded-schema-action"
                  onclick={() => unapplySchemaFromProject(us.id)}
                  >Unapply</button
                >
              {:else}
                <button
                  class="btn-sm btn-primary uploaded-schema-action"
                  onclick={() => applySchemaToProject(us.id)}>Apply</button
                >
              {/if}
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
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
            disabled={runningAllValidations ||
              !branchId ||
              revision == null ||
              appliedSchemasForProject.every((us) =>
                disabledSchemaIdsForRevision.has(us.id),
              )}
          >
            {runningAllValidations ? "Running…" : "▶ Run all"}
          </button>
        {/if}
      </div>

      {#if !applyProjectId}
        <div class="empty-state">
          Open a project on the main page to apply schemas.
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
              <div class="schema-actions">
                <button
                  class="schema-delete-btn"
                  onclick={() => {
                    if (confirm("Delete this schema and all its rules?")) {
                      deleteUploadedSchema(us.id);
                    }
                  }}
                  aria-label={`Delete schema ${us.versionName}`}
                  title="Delete schema"
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 16 16"
                    aria-hidden="true"
                    focusable="false"
                  >
                    <path
                      d="M4 4L12 12M12 4L4 12"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                </button>
                <button
                  class="schema-run-btn btn-icon-primary"
                  onclick={() => runValidationByUploadedSchema(us.id)}
                  disabled={runningValidationSchemaId === us.id ||
                    runningAllValidations ||
                    !branchId ||
                    revision == null ||
                    disabledSchemaIdsForRevision.has(us.id)}
                  aria-label={disabledSchemaIdsForRevision.has(us.id) && revision != null
                    ? `Validation already run for ${us.versionName} on this revision`
                    : `Run validation for ${us.versionName}`}
                  title={disabledSchemaIdsForRevision.has(us.id) && revision != null
                    ? "Validation already run for this revision"
                    : "Run validation"}
                >
                  <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                    <polygon points="5,2.5 13,8 5,13.5" fill="currentColor" />
                  </svg>
                </button>
              </div>
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
        </div>

        <!-- Rules list (collapsible by severity) -->
        <div class="rules-section">
          <div class="rules-section-header">
            <h4>Rules ({uploadedSchemaRules.length})</h4>
            <button
              type="button"
              class="btn-sm btn-primary"
              onclick={openCreateRuleModal}
            >
              Create Rule
            </button>
          </div>
          {#if uploadedSchemaRulesLoading}
            <div class="empty-state">Loading rules…</div>
          {:else if uploadedSchemaRules.length === 0}
            <div class="empty-state empty-state-with-action">
              <p>No rules in this schema.</p>
              <button
                type="button"
                class="btn-sm btn-primary"
                onclick={openCreateRuleModal}
              >
                Create Rule
              </button>
            </div>
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
                          <div class="rule-header-actions">
                            <button
                              type="button"
                              class="btn-icon rule-action-btn"
                              onclick={(e) => { e.preventDefault(); e.stopPropagation(); openCreateRuleModalForEdit(rule); }}
                              aria-label="Edit rule"
                              title="Edit"
                            >
                              ✎
                            </button>
                            <button
                              type="button"
                              class="btn-icon rule-action-btn rule-delete-btn"
                              onclick={(e) => { e.preventDefault(); e.stopPropagation(); if (confirm("Delete this rule?")) deleteUploadedSchemaRule(rule.ruleId); }}
                              aria-label="Delete rule"
                              title="Delete"
                            >
                              ✕
                            </button>
                          </div>
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
                          <div class="rule-detail-row rule-include-subclasses-row">
                            <label
                              class="rule-include-subclasses-label"
                              title="Apply this rule to the target IFC class and all classes that inherit from it (e.g. IfcBuildingElement → IfcWall, IfcSlab)"
                            >
                              <input
                                type="checkbox"
                                checked={getRuleIncludeSubclasses(rule)}
                                disabled={ruleIncludeSubclassesSaving[rule.ruleId]}
                                onchange={(e) => {
                                  setRuleIncludeSubclasses(
                                    rule,
                                    (e.currentTarget as HTMLInputElement).checked,
                                  );
                                }}
                              />
                              <span>Include subclasses</span>
                            </label>
                            {#if ruleIncludeSubclassesSaving[rule.ruleId]}
                              <span class="rule-saving-hint">Saving…</span>
                            {/if}
                          </div>
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

  <!-- Create Schema modal -->
  {#if showSchemaCreator}
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="create-schema-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-schema-title"
      aria-label="Create schema"
      tabindex="-1"
      onclick={(e) => {
        if (e.target === e.currentTarget) {
          showSchemaCreator = false;
          newSchemaName = "";
        }
      }}
      onkeydown={(e) => {
        if (e.key === "Escape") {
          showSchemaCreator = false;
          newSchemaName = "";
        }
      }}
    >
      <div class="create-schema-modal">
        <header class="create-schema-modal-header">
          <h2 id="create-schema-title">Create Schema</h2>
          <button
            type="button"
            class="create-schema-close"
            onclick={() => {
              showSchemaCreator = false;
              newSchemaName = "";
            }}
            aria-label="Close"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path
                d="M4 4L12 12M12 4L4 12"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </button>
        </header>
        <div class="create-schema-body">
          <label for="create-schema-name">
            Name
          </label>
          <input
            id="create-schema-name"
            type="text"
            class="create-schema-input"
            placeholder="Schema name"
            bind:value={newSchemaName}
            onkeydown={(e) => e.key === "Enter" && createSchema()}
          />
        </div>
        <footer class="create-schema-footer">
          <button
            type="button"
            class="btn-sm"
            onclick={() => {
              showSchemaCreator = false;
              newSchemaName = "";
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            class="btn-sm btn-primary"
            disabled={!newSchemaName.trim()}
            onclick={createSchema}
          >
            Create
          </button>
        </footer>
      </div>
    </div>
  {/if}

  <!-- Create Rule modal -->
  {#if showCreateRuleModal && activeAppliedSchema}
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="create-schema-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-rule-title"
      aria-label="Create rule"
      tabindex="-1"
      onclick={(e) => {
        if (e.target === e.currentTarget) closeCreateRuleModal();
      }}
      onkeydown={(e) => {
        if (e.key === "Escape") closeCreateRuleModal();
      }}
    >
      <div class="create-rule-modal">
        <header class="create-schema-modal-header">
          <h2 id="create-rule-title">{editingRuleId ? "Edit Rule" : "Create Rule"}</h2>
          <button
            type="button"
            class="create-schema-close"
            onclick={closeCreateRuleModal}
            aria-label="Close"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path
                d="M4 4L12 12M12 4L4 12"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </button>
        </header>
        <div class="create-rule-body">
          <div class="create-rule-mode-toggle">
            <button
              type="button"
              class="btn-sm view-mode-toggle"
              class:card-active={createRuleMode === "card"}
              class:json-active={createRuleMode === "json"}
              onclick={() => (createRuleMode = createRuleMode === "card" ? "json" : "card")}
            >
              <span class="toggle-option">Card</span>
              <span class="toggle-option">JSON</span>
            </button>
          </div>

          <label for="create-rule-name">Name</label>
          <input
            id="create-rule-name"
            type="text"
            class="create-schema-input"
            placeholder="e.g. Wall Fire Rating Check"
            bind:value={createRuleName}
          />
          <label for="create-rule-desc">Description (optional)</label>
          <input
            id="create-rule-desc"
            type="text"
            class="create-schema-input"
            placeholder="e.g. Ensure fire rating is 2hr"
            bind:value={createRuleDescription}
          />

          {#if createRuleMode === "card"}
            <label for="create-rule-target">Target IFC class</label>
            <input
              id="create-rule-target"
              type="text"
              class="create-schema-input"
              placeholder="e.g. IfcWall"
              bind:value={createRuleSchema.TargetClass}
            />
            <label class="create-rule-include-subclasses-label" title="Apply this rule to the target IFC class and all classes that inherit from it (e.g. IfcBuildingElement → IfcWall, IfcSlab)">
              <input type="checkbox" bind:checked={createRuleSchema.includeSubclasses} />
              <span>Include subclasses</span>
            </label>
            <label for="create-rule-severity">Severity</label>
            <select
              id="create-rule-severity"
              class="create-schema-input"
              bind:value={createRuleSchema.severity}
            >
              <option value="Error">Error</option>
              <option value="Warning">Warning</option>
              <option value="Info">Info</option>
            </select>

            <div class="create-rule-conditions-block">
              <div class="create-rule-conditions-header">
                <strong>Conditions</strong>
                <label for="create-rule-condition-logic" class="create-rule-logic-label">
                  Combine with
                  <select
                    id="create-rule-condition-logic"
                    class="create-rule-logic-select"
                    bind:value={createRuleSchema.ConditionLogic}
                  >
                    <option value="AND">AND (all must pass)</option>
                    <option value="OR">OR (any can pass)</option>
                  </select>
                </label>
              </div>
              <p class="create-rule-hint">
                Path: nested key (e.g. PropertySets.Pset_WallCommon.FireRating). Use exists for required attributes. Example: FireRating &gt; 2 OR FireRating &lt; 5.
              </p>
              {#each createRuleSchema.Conditions as cond, i}
                  <div class="create-rule-condition-row">
                    <input
                      type="text"
                      placeholder="Path (e.g. PropertySets.Pset_WallCommon.FireRating)"
                      class="create-rule-path-input"
                      bind:value={cond.path}
                    />
                    <select class="create-rule-operator-select" bind:value={cond.operator}>
                      {#each CONDITION_OPERATORS as op}
                        <option value={op.value}>{op.label}</option>
                      {/each}
                    </select>
                    <input
                      type="text"
                      placeholder="Value (optional for exists/not_exists)"
                      class="create-rule-value-input"
                      bind:value={cond.value}
                    />
                    <button
                      type="button"
                      class="btn-sm"
                      onclick={() => removeCreateRuleCondition(i)}
                      aria-label="Remove condition"
                    >
                      ✕
                    </button>
                  </div>
                {/each}
              <button type="button" class="btn-sm" onclick={addCreateRuleCondition}>
                + Add condition
              </button>
            </div>
            <details class="create-rule-spatial-details">
                <summary>Spatial context (optional)</summary>
                <div class="create-rule-spatial-fields">
                  <label for="create-rule-traversal">Traversal</label>
                  <select
                    id="create-rule-traversal"
                    class="create-schema-input"
                    bind:value={createRuleSchema.SpatialContext.traversal}
                  >
                    <option value="">— None —</option>
                    {#each SPATIAL_TRAVERSALS as t}
                      <option value={t}>{t}</option>
                    {/each}
                  </select>
                  <label for="create-rule-scope-class">Scope class</label>
                  <input
                    id="create-rule-scope-class"
                    type="text"
                    placeholder="e.g. IfcSpace"
                    class="create-schema-input"
                    bind:value={createRuleSchema.SpatialContext.scope_class}
                  />
                  <label for="create-rule-scope-name">Scope name</label>
                  <input
                    id="create-rule-scope-name"
                    type="text"
                    placeholder="e.g. Room X"
                    class="create-schema-input"
                    bind:value={createRuleSchema.SpatialContext.scope_name}
                  />
                </div>
              </details>
          {:else}
            <label for="create-rule-target-json">Target IFC class (fallback if not in JSON)</label>
            <input
              id="create-rule-target-json"
              type="text"
              class="create-schema-input"
              placeholder="e.g. IfcWall"
              bind:value={createRuleSchema.TargetClass}
            />
            <label for="create-rule-json">Rule schema (JSON)</label>
            <textarea
              id="create-rule-json"
              class="rule-schema-json-input create-rule-json-textarea"
              rows="12"
              value={createRuleSchemaJson}
              oninput={(e) => {
                const parsed = parseJsonToCreateRuleSchema((e.currentTarget as HTMLTextAreaElement).value);
                if (parsed) createRuleSchema = parsed;
              }}
              spellcheck="false"
            ></textarea>
            <p class="create-rule-json-hint">
              ruleType, TargetClass, ConditionLogic (AND/OR), Conditions (path, operator, value), severity (Error/Warning/Info), optional SpatialContext (traversal, scope_class, scope_name).
            </p>
          {/if}
        </div>
        <footer class="create-schema-footer">
          <button type="button" class="btn-sm" onclick={closeCreateRuleModal}>
            Cancel
          </button>
          <button
            type="button"
            class="btn-sm btn-primary"
            disabled={!createRuleName.trim() || createRuleSaving}
            onclick={createUploadedSchemaRule}
          >
            {createRuleSaving ? (editingRuleId ? "Saving…" : "Creating…") : (editingRuleId ? "Save" : "Create")}
          </button>
        </footer>
      </div>
    </div>
  {/if}

  <!-- Upload Schemas modal -->
  {#if showUploadSchemasModal}
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="create-schema-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="upload-schemas-title"
      aria-label="Upload schemas"
      tabindex="-1"
      onclick={(e) => {
        if (e.target === e.currentTarget) closeUploadSchemasModal();
      }}
      onkeydown={(e) => {
        if (e.key === "Escape") closeUploadSchemasModal();
      }}
    >
      <div class="upload-schemas-modal">
        <header class="create-schema-modal-header">
          <h2 id="upload-schemas-title">Upload Schemas</h2>
          <div class="upload-schemas-header-actions">
            <button
              type="button"
              class="btn-icon upload-schemas-info-btn"
              onclick={() => (showUploadSchemaGuide = !showUploadSchemaGuide)}
              aria-label="Schema format guide"
              title="Schema format guide"
            >
              ℹ
            </button>
            <button
              type="button"
              class="create-schema-close"
              onclick={closeUploadSchemasModal}
              aria-label="Close"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path
                  d="M4 4L12 12M12 4L4 12"
                  stroke="currentColor"
                  stroke-width="1.5"
                  stroke-linecap="round"
                />
              </svg>
            </button>
          </div>
        </header>
        <div class="upload-schemas-body">
        {#if showUploadSchemaGuide}
          <div class="upload-schemas-guide">
            <h4>Schema JSON structure</h4>
            <p>Each schema JSON must include:</p>
            <ul>
              <li><strong>schema</strong> — schema identifier (e.g. "IFC4X3_ADD2")</li>
              <li><strong>entities</strong> — object mapping entity names to definitions with <code>parent</code> (optional, blank/null for root entities), <code>attributes</code> (array of objects with name, type, required), <code>abstract</code></li>
            </ul>
            <pre class="upload-schemas-example">{`{
  "schema": "IFC4X3_ADD2",
  "entities": {
    "IfcRoot": {
      "abstract": false,
      "parent": null,
      "attributes": [
        { "name": "Name", "type": "IfcLabel", "required": false }
      ]
    },
    "IfcWall": {
      "abstract": false,
      "parent": "IfcBuildingElement",
      "attributes": [
        { "name": "Name", "type": "IfcLabel", "required": false }
      ]
    }
  }
}`}</pre>
          </div>
        {/if}
        <div
          class="upload-schemas-drop-zone"
          class:drag-over={uploadSchemasDragOver}
          class:has-files={uploadSchemasFiles.length > 0}
          role="button"
          tabindex="0"
          ondragover={handleUploadSchemasDragOver}
          ondragleave={handleUploadSchemasDragLeave}
          ondrop={handleUploadSchemasDrop}
          onclick={() => document.getElementById("upload-schemas-file-input")?.click()}
          onkeydown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              document.getElementById("upload-schemas-file-input")?.click();
            }
          }}
        >
          <input
            id="upload-schemas-file-input"
            type="file"
            accept=".json"
            multiple
            class="sr-only"
            onchange={handleUploadSchemasFileInput}
          />
          {#if uploadSchemasFiles.length > 0}
            <ul class="upload-schemas-file-list">
              {#each uploadSchemasFiles as file, i}
                <li>
                  <span class="upload-schemas-file-name">{file.name}</span>
                  <button
                    type="button"
                    class="btn-sm"
                    onclick={(e) => { e.stopPropagation(); removeUploadSchemaFile(i); }}
                    aria-label="Remove"
                  >
                    ✕
                  </button>
                </li>
              {/each}
            </ul>
          {:else}
            <p class="upload-schemas-drop-label">Drag & drop JSON schema files here</p>
            <p class="upload-schemas-drop-hint">or click to browse (multiple files allowed)</p>
          {/if}
        </div>
        {#if uploadSchemasResults.length > 0}
          <div class="upload-schemas-results">
            {#each uploadSchemasResults as r}
              <div class="upload-schemas-result" class:ok={r.ok} class:fail={!r.ok}>
                <span>{r.name}</span>
                {#if r.ok}
                  <span class="upload-schemas-result-ok">✓</span>
                {:else}
                  <span class="upload-schemas-result-err">✗ {r.error ?? "Failed"}</span>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
        </div>
        <footer class="create-schema-footer">
          <button type="button" class="btn-sm btn-primary" onclick={closeUploadSchemasModal}>
            Close
          </button>
        </footer>
      </div>
    </div>
  {/if}
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

  .uploaded-schemas-section .section-toggle {
    display: inline-flex;
    align-items: center;
    gap: 0;
    padding: 0;
    margin: 0;
    background: none;
    border: none;
    cursor: pointer;
    font: inherit;
    color: var(--color-action-primary);
  }

  .uploaded-schemas-section .section-toggle:focus-visible {
    outline: 2px solid var(--color-border-strong);
    outline-offset: 2px;
    border-radius: 0.25rem;
  }

  .collapse-chevron {
    display: inline-block;
    margin-right: 0.35rem;
    transition: transform 0.2s ease;
  }

  .collapse-chevron:not(.expanded) {
    transform: rotate(-90deg);
  }

  .uploaded-schemas-section .section-toggle h3,
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

  .uploaded-schema-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
  }

  .uploaded-schema-item {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.75rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  }

  .uploaded-schema-info {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    flex: 1;
  }

  .uploaded-schema-name {
    font-weight: 500;
    font-size: 0.9rem;
    color: var(--color-text-primary);
  }

  .uploaded-schema-rules {
    font-size: 0.75rem;
    color: var(--color-text-muted);
  }

  .applied-badge {
    font-size: 0.7rem;
    padding: 0.15rem 0.45rem;
    border-radius: 0.25rem;
    background: color-mix(in srgb, var(--color-success) 15%, transparent);
    color: var(--color-text-primary);
    align-self: flex-start;
  }

  .uploaded-schema-action {
    margin-top: auto;
    width: 100%;
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

  .rule-include-subclasses-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .rule-include-subclasses-label {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.8rem;
    color: var(--color-text-secondary);
    cursor: pointer;
  }

  .rule-include-subclasses-label input {
    margin: 0;
  }

  .rule-saving-hint {
    font-size: 0.75rem;
    color: var(--color-text-muted);
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
    justify-content: space-between;
    gap: 0.5rem;
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .schema-items li.active {
    background: color-mix(in srgb, var(--color-action-primary) 8%, transparent);
  }

  .schema-items li:hover {
    background: color-mix(in srgb, var(--color-action-primary) 5%, var(--color-bg-elevated));
  }

  .schema-items li.active:hover {
    background: color-mix(in srgb, var(--color-action-primary) 14%, transparent);
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
    background: none;
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

  .schema-actions {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding-right: 0.5rem;
  }

  .schema-delete-btn {
    width: 1.75rem;
    height: 1.75rem;
    border-radius: 999px;
    border: 1px solid var(--color-border-subtle);
    background: var(--color-bg-surface);
    color: var(--color-text-secondary);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
  }

  .schema-delete-btn:hover {
    color: var(--color-danger);
    border-color: var(--color-danger);
  }



  .rules-section {
    margin-top: 1rem;
  }

  .rules-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .rules-section-header h4 {
    margin: 0;
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

  .create-rule-json-textarea {
    min-height: 72vh;
    height: 72vh;
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

  .rule-header-actions {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    margin-left: auto;
  }

  .rule-action-btn {
    padding: 0.2rem;
    opacity: 0.7;
  }

  .rule-action-btn:hover {
    opacity: 1;
  }

  .rule-delete-btn:hover {
    color: var(--color-danger);
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

  /* Create Schema modal overlay */
  .create-schema-backdrop {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: color-mix(in srgb, var(--color-text-primary) 35%, transparent);
    z-index: 1000;
  }

  .create-schema-modal {
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.75rem;
    box-shadow: 0 0.5rem 1.5rem color-mix(in srgb, var(--color-text-primary) 15%, transparent);
    min-width: 20rem;
    max-width: 90vw;
  }

  .create-schema-modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .create-schema-modal-header h2 {
    margin: 0;
    font-size: 0.95rem;
    color: var(--color-text-primary);
  }

  .create-schema-close {
    background: none;
    border: none;
    padding: 0.25rem;
    cursor: pointer;
    color: var(--color-text-secondary);
  }

  .create-schema-close:hover {
    color: var(--color-text-primary);
  }

  .create-schema-body {
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .create-schema-body label {
    font-size: 0.78rem;
    color: var(--color-text-secondary);
  }

  .create-schema-input {
    padding: 0.5rem 0.75rem;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-default);
    border-radius: 0.5rem;
    color: var(--color-text-primary);
    font-size: 0.9rem;
  }

  .create-schema-input::placeholder {
    color: var(--color-text-muted);
  }

  .create-schema-input:focus {
    outline: none;
    border-color: var(--color-border-strong);
  }

  .create-schema-input:focus-visible {
    box-shadow: 0 0 0 2px
      color-mix(in srgb, var(--color-border-strong) 25%, transparent);
  }

  .create-schema-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    border-top: 1px solid var(--color-border-subtle);
  }

  /* Create Rule modal */
  .create-rule-modal {
    width: 80%;
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.75rem;
    box-shadow: 0 0.5rem 1.5rem color-mix(in srgb, var(--color-text-primary) 15%, transparent);
    min-width: 24rem;
    max-width: 90vw;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
  }

  .create-rule-body {
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    overflow-y: auto;
  }

  .create-rule-body label {
    font-size: 0.78rem;
    color: var(--color-text-secondary);
  }

  .create-rule-include-subclasses-label {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.78rem;
    color: var(--color-text-secondary);
    cursor: pointer;
  }

  .create-rule-include-subclasses-label input {
    margin: 0;
  }

  .create-rule-mode-toggle {
    margin-bottom: 0.25rem;
  }

  .create-rule-conditions-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .create-rule-logic-label {
    font-size: 0.78rem;
    color: var(--color-text-secondary);
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }

  .create-rule-logic-select {
    padding: 0.25rem 0.4rem;
    font-size: 0.78rem;
    border: 1px solid var(--color-border-default);
    border-radius: 0.4rem;
    background: var(--color-bg-surface);
    color: var(--color-text-primary);
  }

  .create-rule-hint {
    font-size: 0.72rem;
    color: var(--color-text-muted);
    margin: 0.2rem 0 0.5rem;
  }

  .create-rule-conditions-block {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }

  .create-rule-conditions-block strong {
    font-size: 0.82rem;
    color: var(--color-text-secondary);
  }

  .create-rule-condition-row {
    display: grid;
    grid-template-columns: 1fr auto auto auto;
    gap: 0.4rem;
    align-items: center;
  }

  .create-rule-path-input {
    min-width: 0;
    padding: 0.4rem 0.5rem;
    font-size: 0.8rem;
    border: 1px solid var(--color-border-default);
    border-radius: 0.5rem;
    background: var(--color-bg-surface);
    color: var(--color-text-primary);
  }

  .create-rule-operator-select {
    padding: 0.4rem 0.5rem;
    font-size: 0.8rem;
    border: 1px solid var(--color-border-default);
    border-radius: 0.5rem;
    background: var(--color-bg-surface);
    color: var(--color-text-primary);
    min-width: 8rem;
  }

  .create-rule-value-input {
    min-width: 6rem;
    padding: 0.4rem 0.5rem;
    font-size: 0.8rem;
    border: 1px solid var(--color-border-default);
    border-radius: 0.5rem;
    background: var(--color-bg-surface);
    color: var(--color-text-primary);
  }

  .create-rule-spatial-details {
    margin-top: 0.75rem;
    padding: 0.5rem;
    background: var(--color-bg-elevated);
    border-radius: 0.5rem;
    border: 1px solid var(--color-border-subtle);
  }

  .create-rule-spatial-details summary {
    cursor: pointer;
    font-size: 0.82rem;
    color: var(--color-text-secondary);
  }

  .create-rule-spatial-fields {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    margin-top: 0.5rem;
  }

  .create-rule-spatial-fields label {
    font-size: 0.75rem;
  }

  .create-rule-attrs-block {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }

  .create-rule-json-hint {
    font-size: 0.75rem;
    color: var(--color-text-muted);
    margin: 0;
  }

  .empty-state-with-action {
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  .empty-state-with-action .btn-sm {
    margin-top: 0.75rem;
  }

  /* Upload Schemas modal */
  .upload-schemas-modal {
    background: var(--color-bg-surface);
    border: 1px solid var(--color-border-subtle);
    border-radius: 0.75rem;
    box-shadow: 0 0.5rem 1.5rem color-mix(in srgb, var(--color-text-primary) 15%, transparent);
    min-width: 28rem;
    max-width: 90vw;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .upload-schemas-body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
  }

  .upload-schemas-header-actions {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 0.5rem;
  }

  .upload-schemas-header-actions button {
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 2rem;
    min-height: 2rem;
    padding: 0;
  }

  .upload-schemas-info-btn {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--color-text-secondary);
    font-size: 1.1rem;
  }

  .upload-schemas-info-btn:hover {
    color: var(--color-text-primary);
  }

  .upload-schemas-guide {
    padding: 0 1rem 1rem;
    border-bottom: 1px solid var(--color-border-subtle);
    font-size: 0.82rem;
  }

  .upload-schemas-guide h4 {
    margin: 0 0 0.5rem;
    font-size: 0.9rem;
  }

  .upload-schemas-guide ul {
    margin: 0.25rem 0;
    padding-left: 1.25rem;
  }

  .upload-schemas-guide code {
    font-size: 0.8em;
    background: var(--color-bg-elevated);
    padding: 0.1rem 0.3rem;
    border-radius: 0.25rem;
  }

  .upload-schemas-example {
    margin: 0.5rem 0 0;
    padding: 0.75rem;
    background: var(--color-bg-elevated);
    border-radius: 0.5rem;
    font-size: 0.72rem;
    overflow-x: auto;
    white-space: pre-wrap;
  }

  .upload-schemas-drop-zone {
    margin: 1rem;
    padding: 1.5rem;
    border: 2px dashed var(--color-border-default);
    border-radius: 0.75rem;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
  }

  .upload-schemas-drop-zone:hover,
  .upload-schemas-drop-zone.drag-over {
    border-color: var(--color-border-strong);
    background: color-mix(in srgb, var(--color-action-primary) 8%, transparent);
  }

  .upload-schemas-drop-zone.has-files {
    border-style: solid;
  }

  .upload-schemas-drop-label {
    margin: 0 0 0.25rem;
    font-weight: 500;
    color: var(--color-text-primary);
  }

  .upload-schemas-drop-hint {
    margin: 0;
    font-size: 0.8rem;
    color: var(--color-text-muted);
  }

  .upload-schemas-file-list {
    list-style: none;
    margin: 0;
    padding: 0;
    text-align: left;
  }

  .upload-schemas-file-list li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.35rem 0;
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .upload-schemas-file-name {
    font-size: 0.85rem;
    color: var(--color-text-primary);
  }

  .upload-schemas-results {
    padding: 0 1rem;
    margin-bottom: 0.5rem;
    font-size: 0.8rem;
  }

  .upload-schemas-result {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.3rem 0;
  }

  .upload-schemas-result.ok {
    color: var(--color-text-secondary);
  }

  .upload-schemas-result.fail {
    color: var(--color-danger);
  }

  .upload-schemas-result-ok {
    color: var(--color-success);
  }

  .upload-schemas-result-err {
    color: var(--color-danger);
    font-size: 0.75rem;
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    border: 0;
  }
</style>
