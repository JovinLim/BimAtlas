/**
 * Shared reactive state using Svelte 5 runes.
 *
 * Tracks the active project, branch, revision, and selected element.
 */

let activeGlobalId = $state<string | null>(null);
let subgraphDepth = $state(1);
let activeRevision = $state<number | null>(null); // null = latest
let activeProjectId = $state<string | null>(null);
let activeBranchId = $state<string | null>(null);

/**
 * Initialize state from saved settings.
 * Should be called before any effects that depend on this state.
 */
export function initializeFromSettings(settings: {
	activeProjectId?: string | null;
	activeBranchId?: string | null;
	activeRevision?: number | null;
	activeGlobalId?: string | null;
	subgraphDepth?: number;
}): void {
	if (settings.activeProjectId !== undefined) {
		activeProjectId = settings.activeProjectId;
	}
	if (settings.activeBranchId !== undefined) {
		activeBranchId = settings.activeBranchId;
	}
	if (settings.activeRevision !== undefined) {
		activeRevision = settings.activeRevision;
	}
	if (settings.activeGlobalId !== undefined) {
		activeGlobalId = settings.activeGlobalId;
	}
	if (settings.subgraphDepth !== undefined) {
		subgraphDepth = settings.subgraphDepth;
	}
}

export function getSelection() {
	return {
		get activeGlobalId() {
			return activeGlobalId;
		},
		set activeGlobalId(id: string | null) {
			activeGlobalId = id;
		},
		get subgraphDepth() {
			return subgraphDepth;
		},
		set subgraphDepth(d: number) {
			subgraphDepth = d;
		}
	};
}

export function getRevisionState() {
	return {
		get activeRevision() {
			return activeRevision;
		},
		set activeRevision(rev: number | null) {
			activeRevision = rev;
		}
	};
}

export function getProjectState() {
	return {
		get activeProjectId() {
			return activeProjectId;
		},
		set activeProjectId(id: string | null) {
			activeProjectId = id;
			// Reset branch and revision when project changes
			activeBranchId = null;
			activeRevision = null;
			activeGlobalId = null;
		},
		get activeBranchId() {
			return activeBranchId;
		},
		set activeBranchId(id: string | null) {
			activeBranchId = id;
			// Reset revision and selection when branch changes
			activeRevision = null;
			activeGlobalId = null;
		}
	};
}
