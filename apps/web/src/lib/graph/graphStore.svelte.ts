/**
 * Reactive graph data store for 3d-force-graph integration.
 * Fetches spatial tree from the GraphQL API and flattens it into
 * nodes + links suitable for the force graph visualisation.
 *
 * All queries are scoped to a branch via `branchId`.
 */
import { client, SPATIAL_TREE_QUERY, ELEMENT_RELATIONS_QUERY } from '$lib/api/client';

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

		let base: GraphData = { nodes: [], links: [] };
		if (result.data?.spatialTree) {
			base = flattenSpatialTree(result.data.spatialTree);
		}

		// Enrich with non-spatial element relations (voids, fills, connects, type-defines, shape reps)
		let enriched: GraphData = base;
		try {
			const relResult = await client
				.query(ELEMENT_RELATIONS_QUERY, { branchId, revision: revision ?? undefined })
				.toPromise();
			if (!relResult.error && relResult.data?.elementRelations) {
				enriched = mergeElementRelations(
					base,
					relResult.data.elementRelations as ElementRelationEdge[]
				);
			}
		} catch {
			// Non-fatal: if relations query fails, fall back to spatial-only graph.
			enriched = base;
		}

		graphData = enriched;
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

/** Merge non-spatial element relations into an existing graph. */
function mergeElementRelations(base: GraphData, relations: ElementRelationEdge[]): GraphData {
	const nodes = [...base.nodes];
	const links = [...base.links];

	const nodeById = new Map<string, GraphNode>();
	for (const n of nodes) {
		nodeById.set(n.id, n);
	}

	const linkKeys = new Set<string>();
	for (const l of links) {
		linkKeys.add(`${l.source}|${l.target}|${l.relType}`);
	}

	function ensureNode(id: string, name: string | null, ifcClass: string): void {
		if (nodeById.has(id)) return;
		const node: GraphNode = {
			id,
			name: name ?? ifcClass,
			ifcClass,
			group: SPATIAL_CLASSES.has(ifcClass) ? 'spatial' : ifcClass
		};
		nodeById.set(id, node);
		nodes.push(node);
	}

	for (const rel of relations ?? []) {
		ensureNode(rel.sourceId, rel.sourceName, rel.sourceIfcClass);
		ensureNode(rel.targetId, rel.targetName, rel.targetIfcClass);

		const key = `${rel.sourceId}|${rel.targetId}|${rel.relationship}`;
		if (linkKeys.has(key)) continue;
		linkKeys.add(key);

		links.push({
			source: rel.sourceId,
			target: rel.targetId,
			relType: rel.relationship
		});
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

interface ElementRelationEdge {
	sourceId: string;
	sourceIfcClass: string;
	sourceName: string | null;
	targetId: string;
	targetIfcClass: string;
	targetName: string | null;
	relationship: string;
}
