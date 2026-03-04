---
name: optimize-compact-code
description: Optimize and compact code by analyzing function and variable usage, removing redundant or dead code, and validating behavior with Playwright tests. Use when the user asks to refactor for efficiency, reduce code wastage, or clean duplicate logic while preserving readability.
---

# Optimize and Compact Code

Refactor code to reduce waste without harming clarity. Favor small, safe improvements that keep intent obvious.

## When to Use

Use this skill when the user asks to:

- optimize code
- compact/refactor code
- remove redundant or duplicate logic
- clean unused functions/variables/imports
- improve maintainability while keeping behavior unchanged

## Core Principles

- Keep behavior stable; refactors are non-functional unless requested otherwise.
- Preserve readability; do not golf code.
- Prefer explicit, named helpers over clever one-liners.
- Remove only what is provably unused or redundant.
- Validate every meaningful cleanup with tests.

## Workflow

Copy this checklist and keep it updated:

```md
Code Compaction Progress
- [ ] Step 1: Map usage of functions/variables
- [ ] Step 2: Identify and classify redundancy
- [ ] Step 3: Refactor/remove with readability guardrails
- [ ] Step 4: Run Playwright tests and review failures
- [ ] Step 5: Report changes and residual risks
```

### Step 1: Map usage of functions and variables

1. Identify candidate files from the user request and related call sites.
2. Trace where each function, variable, and exported symbol is used.
3. Mark symbols as:
   - `actively used`
   - `possibly dead` (needs confirmation)
   - `duplicate behavior` (overlapping implementations)
4. Prefer project tools (`rg`, semantic search, static checks) over assumptions.

### Step 2: Find redundant code

Look for:

- unused variables/imports/params
- dead helper functions
- duplicated condition blocks
- repeated literal mappings/constants
- repeated transformation logic that should be centralized
- unnecessary indirection (thin wrappers with no value)

Classify each candidate before editing:

- **Safe remove:** no references, no side effects.
- **Safe merge:** duplicate logic can be consolidated clearly.
- **Review needed:** behavior unclear, external usage uncertain, or readability would drop.

### Step 3: Refactor with readability balance

Apply changes in this order:

1. Remove dead code and unused imports/locals.
2. Consolidate obvious duplication into small named helpers.
3. Simplify branching/control flow where meaning remains clear.

Readability guardrails:

- Keep function boundaries aligned with domain intent.
- Avoid over-abstraction for one-off logic.
- Keep descriptive names; do not shorten names just to reduce lines.
- Add brief comments only where logic is non-obvious.
- If a compact rewrite is less readable, prefer the longer readable version.

### Step 4: Run Playwright tests

After substantial refactors, run the spreadsheet Playwright suite:

```bash
cd apps/web
pnpm run test:spreadsheet
```

If failures occur:

1. Check whether failure is caused by the refactor.
2. Fix regressions first.
3. Re-run tests until green or clearly document blockers.

Optional extra validation for local confidence:

```bash
cd apps/web
pnpm run check
```

### Step 5: Report outcomes

Summarize:

- what redundancy was removed
- what was intentionally kept for readability
- Playwright test result (`pass`/`fail`) and any failing specs
- remaining risks or unverified areas

## Decision Rules

- If usage cannot be confidently proven, do not delete; flag for follow-up.
- If deduplication introduces complex generic code, revert to clearer duplication.
- Prefer incremental edits and test after each logical batch.
- Do not change public interfaces unless requested.

## Example Refactor Patterns

### A) Duplicate branches -> named helper

Before: repeated object-normalization code in multiple branches.

After: one `normalizeEntityRow()` helper used by both branches, with unchanged output shape.

### B) Dead utility removal

Before: helper imported in file but never called.

After: remove helper and import; verify no references remain and tests pass.

### C) Balance readability over compactness

Before: verbose but clear conditional data mapping.

After: minor extraction and early-return cleanup only. Avoid dense chained expressions that obscure intent.
