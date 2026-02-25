---
name: feature-task-tracking
description: Keep feature active_task files and lessons_learned.md in sync with work, following the rolling-summary rule. Use when executing tasks tied to plan TODOs under .cursor/plans/ or .cursor/product/features/.
---

# Feature Task Tracking

This skill coordinates feature-level task tracking using `active_task` files and `lessons_learned.md`, aligned with the `rolling-summary` rule.

## When to Use

Use this skill whenever:

- You are working on a TODO referenced from a `plan.md` (or `.plan.md`) under `.cursor/plans/`.
- The TODO corresponds to a specific feature under `.cursor/product/features/feature_*/`.
- You need to claim, update, or complete a task for a feature, or record lessons learned.

For the full policy, see `[rolling-summary.mdc](../rules/rolling-summary.mdc)`.

## Directory Conventions

- **Plans** live under `.cursor/plans/` (e.g. `database_schema_rebuild_*.plan.md`).
- **Features** live under `.cursor/product/features/feature_*/`.
- Each feature directory may contain:
  - `prd.md` – feature PRD.
  - `active_task.md` or `active_task.json` – current work state.
  - `lessons_learned.md` – accumulated constraints and pitfalls.

Always infer the correct feature directory from the TODO context (feature ID, PRD references, or file paths).

## Workflow

### 1. Claiming a Task

When you take ownership of a TODO from a plan:

1. **Identify the TODO**
   - Open the relevant `plan.md` or `.plan.md` under `.cursor/plans/`.
   - Locate the exact TODO you are executing.
   - Note its section heading and, if available, anchor ID or step label (e.g. `# step-4-database-schema`).

2. **Locate the Feature Directory**
   - Determine which feature the TODO belongs to (e.g. `feature_001_dynamic_filter_sets`).
   - Navigate to `.cursor/product/features/<feature_id>/`.

3. **Find or Create `active_task`**
   - Prefer `active_task.json` if it exists; otherwise use `active_task.md` or create a new `active_task.json`.
   - Preserve existing content; do not discard other agents’ tasks.

4. **Claim the Task in `active_task`**
   - Ensure the structure matches the template from `rolling-summary.mdc`:

     ```json
     {
       "metadata": {
         "feature_id": "<feature_id>",
         "plan_reference": "<plan-file>#<section-or-step>",
         "assigned_agent": "<agent_name_or_role>",
         "last_updated": "<ISO-8601 timestamp>"
       },
       "state": {
         "status": "in_progress",
         "current_objective": "<short, actionable description tied to the TODO>"
       },
       "execution_log": [
         {
           "step": "<first significant step you perform>",
           "status": "in_progress"
         }
       ],
       "handoff_notes": ""
     }
     ```

   - **Plan reference** must explicitly point to the exact TODO (file and section/anchor) so other agents can see it is claimed.
   - If multiple tasks are tracked in one file, append a new object or section rather than overwriting existing ones.

### 2. Execution and State Updates

While working on the task:

1. **Keep `state` current**
   - Update `"status"` between `in_progress`, `blocked`, and `complete` as appropriate.
   - Keep `"current_objective"` short but specific to your current sub-goal.

2. **Maintain `execution_log`**
   - Append entries for each meaningful step (e.g. “Read PRD for schema requirements”, “Update ingestion pipeline”, “Run geometry tests”).
   - For each entry, keep a `"status"` field such as `in_progress` or `complete`.
   - Never remove previous steps; treat this as a chronological log.

3. **Update timestamps**
   - Refresh `"metadata.last_updated"` with an accurate ISO-8601 timestamp whenever you modify the file.

4. **Respect other work**
   - If other tasks are present in the same `active_task` file, only modify the section/object associated with your claimed task.

### 3. Lessons Learned (Post-Execution)

On task completion or when abandoning/failing a loop:

1. **Open or create `lessons_learned.md`** in the same feature directory.
2. Ensure it contains, at minimum, the following sections:

   ```markdown
   # Hard Constraints
   - ...

   # Resolved Pitfalls
   - ...
   ```

3. **Record constraints and pitfalls**
   - **Hard Constraints**: Add bullets only for durable, system-level or cross-task constraints discovered (e.g. “AgeDB cannot store more than X nodes per graph for performance reasons”).
   - **Resolved Pitfalls**: For each blocker you encountered and solved, add a concise 2-sentence summary describing:
     - The trap (what went wrong or was surprising).
     - The solution (what you changed or how to avoid it next time).

4. **Apply the pruning rule**
   - If `lessons_learned.md` exceeds 50 lines:
     - Summarize older individual pitfalls into broader, higher-level bullets.
     - Keep all items in **Hard Constraints** unchanged.

5. **Update `active_task` status**
   - When the task is complete, set its `"state.status"` to `"complete"`.
   - Optionally add a final `"execution_log"` entry like “Task marked complete; lessons_learned.md updated”.
   - If handing off, use `"handoff_notes"` to describe remaining work and link to relevant plan sections.

## Examples

### Example: Claiming a Database Schema TODO

Given a TODO in `database_schema_rebuild_efb75060.plan.md` under “Step 4 – database schema”, for `feature_001_dynamic_filter_sets`:

- Set `metadata.feature_id` to `"feature_001_dynamic_filter_sets"`.
- Set `metadata.plan_reference` to `"database_schema_rebuild_efb75060.plan.md#step-4-database-schema"`.
- Set `state.current_objective` to a short description such as `"Align dynamic filter sets schema with new graph layout"`.

### Example: Recording a Resolved Pitfall

If you discovered that a certain ingestion path silently drops malformed geometry:

- Add under **Resolved Pitfalls** in `lessons_learned.md`:
  - “Malformed geometry records were being silently skipped during ingestion, causing missing nodes in AgeDB. We added explicit validation and logging, and now malformed records are flagged early with clear error messages.”

