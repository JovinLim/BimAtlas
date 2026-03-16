# Hard Constraints

- Keep application view state strictly decoupled from immutable IFC model storage; do not add view payloads to `ifc_entity` or custom IFC classes.
- Broadcast payloads for cross-tab sync must be structured-clone safe; serialize and re-parse before posting if payloads may contain reactive proxies.
- Use UUID string identifiers consistently for app-level entities and relations.
- List endpoints that return views with linked filter sets must explicitly load filter_sets; the single-view fetch path (e.g. `fetch_app_view_with_filter_sets`) does not apply to list endpoints.

# Resolved Pitfalls

- **Filter sets not persisted when editing view:** `fetch_app_views_for_branch` returned only base view columns and never loaded linked filter sets. The list endpoint thus returned `filterSets: []` for every view. The editor initialized `editorFilterSetIds` from `view.filterSets`, so it was always empty, and save sent `idsToAttach = []`. Fix: extend `fetch_app_views_for_branch` to fetch filter sets for all views in one query and attach them to each view.
- **urql mutation errors silently ignored:** urql mutations resolve with `result.error` on GraphQL errors instead of throwing. The save flow did not check `result.error`, so failures (e.g. invalid filter set IDs) were ignored and the UI behaved as if save succeeded. Fix: add `checkMutationError()` and call it after each mutation to surface errors to the user.
