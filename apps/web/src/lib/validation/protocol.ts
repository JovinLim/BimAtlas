/**
 * Shared types and constants for cross-window Validation popup communication
 * via the BroadcastChannel API.
 */

export const VALIDATION_CHANNEL = "bimatlas-validation";

export interface ValidationContextPayload {
  branchId: string | null;
  projectId: string | null;
  branchName: string | null;
  projectName: string | null;
  revision: number | null;
}

export type ValidationMessage =
  | { type: "request-context" }
  | ({ type: "context" } & ValidationContextPayload);
