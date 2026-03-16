/**
 * Shared types and constants for cross-window Views communication
 * via the BroadcastChannel API.
 *
 * Use JSON.parse(JSON.stringify(message)) before posting to ensure
 * structured-clone safety (no proxies, functions, etc.).
 */

export const VIEWS_CHANNEL = "bimatlas-views";

/** BCF-compliant camera state (perspective or orthogonal + optional clipping). */
export interface BcfCameraState {
	perspective_camera?: {
		position: [number, number, number];
		direction: [number, number, number];
		up_vector: [number, number, number];
		field_of_view?: number;
	};
	orthogonal_camera?: {
		position: [number, number, number];
		direction: [number, number, number];
		up_vector: [number, number, number];
		view_to_world_scale: number;
	};
	clipping_planes?: Array<{
		location: [number, number, number];
		direction: [number, number, number];
	}>;
}

/** Filter set reference for view execution. */
export interface ViewFilterSetRef {
	id?: string;
	filterSetId?: string;
	name?: string;
	logic: string;
	filters: unknown;
	filtersTree?: unknown;
	color?: string;
}

/** Full saved view payload for LOAD_VIEW. */
export interface SavedViewPayload {
	id: string;
	branchId: string;
	name: string;
	bcfCameraState: BcfCameraState;
	uiFilters: Record<string, unknown>;
	filterSets: ViewFilterSetRef[];
}

export type ViewsMessage =
	| { type: "LOAD_VIEW"; view: SavedViewPayload }
	| { type: "UPDATE_VIEW"; view: Partial<SavedViewPayload> }
	| { type: "TOGGLE_GHOST_MODE"; filterSetId: string; enabled: boolean }
	| { type: "request-context" }
	| { type: "context"; branchId: string | null; projectId: string | null;
		branchName?: string | null; projectName?: string | null; revision?: number | null }
	| { type: "request-camera" }
	| { type: "camera"; bcfCameraState: BcfCameraState };

/** Clone payload for safe postMessage (structured-clone). */
export function cloneForPost<T>(obj: T): T {
	return JSON.parse(JSON.stringify(obj)) as T;
}
