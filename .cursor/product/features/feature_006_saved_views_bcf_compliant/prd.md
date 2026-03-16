---
feature_id: "FEAT-006"
status: "implemented"
priority: "high"
---

# Feature: Saved Views (BCF-Compliant)

## 1. Problem Statement

Users need the ability to save, load, and manage specific 3D model states. The saved state must preserve viewer context (camera, clipping, and visibility intent) while remaining decoupled from immutable IFC source records.

## 2. Core Requirements

- **Req 1 (Strict Decoupling):** Do not modify `ifc_entities` or introduce custom IFC classes for application view state.
- **Req 2 (BCF Camera Compliance):** Persist camera and clipping in a `bcf_camera_state` JSONB payload aligned with the buildingSMART BCF Viewpoint schema, including `perspective_camera`, `orthogonal_camera`, and `clipping_planes`.
- **Req 3 (View Persistence Model):** Add `app_views` for core saved view metadata and `view_filter_sets` as a many-to-many bridge to existing filter sets.
- **Req 4 (UI Filter Reconstruction):** Persist literal filter UI control state in `ui_filters` JSONB (for example level/class selections) to rebuild the popup controls when loading a view.
- **Req 5 (Backend CRUD + Resolution):** Implement create/read/update/delete endpoints for views. Read payloads must resolve linked filter sets via join and return one aggregate response.
- **Req 6 (Popup Views Interface):** Add a dedicated popup route/layout for views management with list, editor form, and filter-set attachment UI.
- **Req 7 (Cross-Tab Sync):** Use BroadcastChannel (or robust localStorage fallback) with explicit event types `LOAD_VIEW`, `UPDATE_VIEW`, and `TOGGLE_GHOST_MODE`.
- **Req 8 (Single Active View):** Enforce mutual exclusivity so only one saved view can be active at once; loading a new view fully overwrites prior camera/clipping/visibility state.
- **Req 9 (View Execution):** On `LOAD_VIEW`, main tab applies BCF camera/clipping state and executes linked filter sets to isolate the intended entities.
- **Req 10 (Ghost Mode):** On `TOGGLE_GHOST_MODE`, temporarily render targeted entities with a visual override (e.g., low opacity/desaturation) instead of hiding them; this must not persist to DB.

## 3. Out of Scope (Strict Constraints)

- Do not write view state into IFC tables (`ifc_entity`/`ifc_entities`) or any IFC class representation.
- Do not persist ghost-mode temporary toggles into saved view records.
- Do not weaken BCF alignment by storing ad-hoc camera structures that cannot be mapped to BCF viewpoint shape.

## 4. Success Criteria

- [x] Database migrations create `app_views` and `view_filter_sets`.
- [x] Backend create/read returns BCF camera data plus associated filter set definitions in a single payload.
- [x] Popup views tab opens and synchronizes with main viewer without race conditions.
- [x] Loading a saved view transitions camera, applies clipping planes, and updates visibility from linked filter sets.
- [x] Ghost mode toggles affect targeted entities visually without altering persisted saved view data.
