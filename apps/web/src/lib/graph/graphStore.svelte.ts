/**
 * Reactive graph data store for 3d-force-graph integration.
 * Fetches spatial tree from the GraphQL API and flattens it into
 * nodes + links suitable for the force graph visualisation.
 *
 * All queries are scoped to a branch via `branchId`.
 */
import { client, SPATIAL_TREE_QUERY } from '$lib/api/client';

// ---- Types ----

export interface GraphNode {
	id: string; // IFC GlobalId
	name: string;
	ifcClass: string;
	group: string; // used for colour coding
}

export interface GraphLink {
	source: string; // globalId
	target: string; // globalId
	relType: string; // IFC relationship entity name
}

export interface GraphData {
	nodes: GraphNode[];
	links: GraphLink[];
}

// ---- Reactive State ----

let graphData = $state<GraphData>({ nodes: [], links: [] });
let loading = $state(false);
let error = $state<string | null>(null);

// ---- Public API ----

export function getGraphStore() {
	return {
		get data() {
			return graphData;
		},
		get loading() {
			return loading;
		},
		get error() {
			return error;
		},
		fetchGraph
	};
}

/**
 * Fetch the spatial tree from the API and flatten it into graph data.
 * Scoped to a branch and optionally a specific revision (null = latest).
 */
async function fetchGraph(branchId: string, revision?: number | null): Promise<void> {
	loading = true;
	error = null;
	try {
		const result = await client
			.query(SPATIAL_TREE_QUERY, { branchId, revision: revision ?? undefined })
			.toPromise();

		if (result.error) {
			error = result.error.message;
			return;
		}

		if (result.data?.spatialTree) {
			graphData = flattenSpatialTree(result.data.spatialTree);
		}
	} catch (err) {
		error = err instanceof Error ? err.message : 'Failed to fetch graph data';
	} finally {
		loading = false;
	}
}

// ---- Helpers ----

/** IFC class names that represent spatial structure (larger nodes in graph). */
const SPATIAL_CLASSES = new Set([
	'IfcProject',
	'IfcSite',
	'IfcBuilding',
	'IfcBuildingStorey',
	'IfcSpace'
]);

/** Walk the recursive spatial tree and flatten into nodes + links arrays. */
function flattenSpatialTree(tree: SpatialTreeNode[]): GraphData {
	const nodes: GraphNode[] = [];
	const links: GraphLink[] = [];
	const seen = new Set<string>();

	function addNode(id: string, name: string | null, ifcClass: string): void {
		if (seen.has(id)) return;
		seen.add(id);
		nodes.push({
			id,
			name: name ?? ifcClass,
			ifcClass,
			group: SPATIAL_CLASSES.has(ifcClass) ? 'spatial' : ifcClass
		});
	}

	function walk(node: SpatialTreeNode, parentId?: string): void {
		addNode(node.globalId, node.name, node.ifcClass);

		if (parentId) {
			links.push({
				source: parentId,
				target: node.globalId,
				relType: 'IfcRelAggregates'
			});
		}

		// Recurse into spatial children (decomposition)
		for (const child of node.children ?? []) {
			walk(child, node.globalId);
		}

		// Contained elements (containment relationship)
		for (const elem of node.containedElements ?? []) {
			addNode(elem.globalId, elem.name, elem.ifcClass);
			links.push({
				source: node.globalId,
				target: elem.globalId,
				relType: elem.relationship ?? 'IfcRelContainedInSpatialStructure'
			});
		}
	}

	for (const root of tree) {
		walk(root);
	}

	return { nodes, links };
}

// ---- Internal Types (match GraphQL response shape) ----

interface ContainedElement {
	globalId: string;
	ifcClass: string;
	name: string | null;
	relationship: string | null;
}

interface SpatialTreeNode {
	globalId: string;
	ifcClass: string;
	name: string | null;
	children?: SpatialTreeNode[];
	containedElements?: ContainedElement[];
}
