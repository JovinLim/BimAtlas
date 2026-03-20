import {
	getProjectState,
	getRevisionState,
	getSelection,
	initializeFromSettings,
} from "./selection.svelte";

type WorkspaceSettings = {
	activeProjectId?: string | null;
	activeBranchId?: string | null;
	activeRevision?: number | null;
	activeGlobalId?: string | null;
	subgraphDepth?: number;
};

const selection = getSelection();
const revisionState = getRevisionState();
const projectState = getProjectState();

const workspaceState = {
	get activeProjectId(): string | null {
		return projectState.activeProjectId;
	},
	set activeProjectId(id: string | null) {
		projectState.activeProjectId = id;
	},

	get activeBranchId(): string | null {
		return projectState.activeBranchId;
	},
	set activeBranchId(id: string | null) {
		projectState.activeBranchId = id;
	},

	get activeRevision(): number | null {
		return revisionState.activeRevision;
	},
	set activeRevision(revision: number | null) {
		revisionState.activeRevision = revision;
	},

	get activeGlobalId(): string | null {
		return selection.activeGlobalId;
	},
	set activeGlobalId(id: string | null) {
		selection.activeGlobalId = id;
	},

	get subgraphDepth(): number {
		return selection.subgraphDepth;
	},
	set subgraphDepth(depth: number) {
		selection.subgraphDepth = depth;
	},

	getWorkspaceContext() {
		return {
			activeBranchId: projectState.activeBranchId,
			activeRevision: revisionState.activeRevision,
			selectedGlobalId: selection.activeGlobalId,
		};
	},
};

export function getWorkspaceState() {
	return workspaceState;
}

export function initializeWorkspace(settings: WorkspaceSettings): void {
	initializeFromSettings(settings);
}
