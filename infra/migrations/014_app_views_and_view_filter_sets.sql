-- Migration 014: app_views and view_filter_sets for BCF-compliant saved views
--
-- Saved views store camera/clipping state (BCF viewpoint schema) and UI filter
-- state, strictly decoupled from ifc_entity. view_filter_sets links views to
-- existing filter_sets for many-to-many reuse.

CREATE TABLE IF NOT EXISTS app_views (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id         UUID NOT NULL REFERENCES branch(branch_id) ON DELETE CASCADE,
    name              VARCHAR NOT NULL,
    bcf_camera_state  JSONB NOT NULL DEFAULT '{}',
    ui_filters        JSONB NOT NULL DEFAULT '{}',
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_app_views_branch ON app_views (branch_id);

CREATE TABLE IF NOT EXISTS view_filter_sets (
    view_id       UUID NOT NULL REFERENCES app_views(id) ON DELETE CASCADE,
    filter_set_id UUID NOT NULL REFERENCES filter_sets(filter_set_id) ON DELETE CASCADE,
    display_order INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (view_id, filter_set_id)
);

CREATE INDEX IF NOT EXISTS idx_view_filter_sets_view ON view_filter_sets (view_id);
CREATE INDEX IF NOT EXISTS idx_view_filter_sets_filter_set ON view_filter_sets (filter_set_id);
