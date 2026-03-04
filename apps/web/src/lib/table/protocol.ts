/**
 * Shared types and constants for cross-window Table popup communication
 * via the BroadcastChannel API.
 */

import type { ProductMeta } from "$lib/search/protocol";

export const TABLE_CHANNEL = "bimatlas-table";

export const TABLE_PROTOCOL_VERSION = 1;

/** When true, table selection and viewer selection stay in sync (row highlight, cell focus). When false, use "Find selected element" to locate the viewer selection in the table. */
export const ENABLE_TABLE_VIEWER_SELECTION_SYNC = false;

export interface TableContextPayload {
  branchId: string | null;
  projectId: string | null;
  branchName: string | null;
  projectName: string | null;
  revision: number | null;
  products: ProductMeta[];
  version: number;
  /** Current selection in the main viewer (for "Find selected element"). */
  activeGlobalId?: string | null;
}

/** Follow-up payload to attach attributes to products already sent via a lean context. */
export interface TableContextAttributesPayload {
  type: "context-attributes";
  /** globalId -> attributes (entity JSON). Table merges into existing products. */
  attributesByGlobalId: Record<string, Record<string, unknown> | null>;
}

export type TableMessage =
  | { type: "request-context" }
  | { type: "request-attributes" }
  | ({ type: "context" } & TableContextPayload)
  | TableContextAttributesPayload
  | { type: "selection-changed"; globalId: string | null }
  | { type: "selection-sync"; globalId: string | null };
