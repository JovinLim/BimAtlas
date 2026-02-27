/**
 * Shared types and constants for cross-window Attribute panel communication
 * via the BroadcastChannel API.
 */

export const ATTRIBUTES_CHANNEL = "bimatlas-attributes";

export interface AttributesContextPayload {
  branchId: string | null;
  projectId: string | null;
  revision: number | null;
  globalId: string | null;
}

export type AttributesMessage =
  | { type: "request-context" }
  | ({ type: "context" } & AttributesContextPayload)
  | { type: "selection-changed"; globalId: string | null }
  | { type: "close-panel" };

