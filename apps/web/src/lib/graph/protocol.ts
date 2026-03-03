/**
 * Shared types and constants for cross-window Graph popup communication
 * via the BroadcastChannel API.
 */

export const GRAPH_CHANNEL = "bimatlas-graph";

export interface GraphContextPayload {
  branchId: string | null;
  projectId: string | null;
  revision: number | null;
  globalId: string | null;
  subgraphDepth: number;
}

export type GraphMessage =
  | { type: "request-context" }
  | ({ type: "context" } & GraphContextPayload)
  | { type: "selection-changed"; globalId: string | null };
