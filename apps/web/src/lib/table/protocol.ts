/**
 * Shared types and constants for cross-window Table popup communication
 * via the BroadcastChannel API.
 */

import type { ProductMeta } from "$lib/search/protocol";

export const TABLE_CHANNEL = "bimatlas-table";

export const TABLE_PROTOCOL_VERSION = 1;

export interface TableContextPayload {
  branchId: string | null;
  projectId: string | null;
  branchName: string | null;
  projectName: string | null;
  revision: number | null;
  products: ProductMeta[];
  version: number;
}

export type TableMessage =
  | { type: "request-context" }
  | ({ type: "context" } & TableContextPayload)
  | { type: "selection-changed"; globalId: string | null };
