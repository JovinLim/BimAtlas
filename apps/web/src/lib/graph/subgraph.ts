import type { GraphData } from './graphStore.svelte';

/**
 * BFS from `startId` up to `depth` hops over the undirected graph
 * defined by `graphData.links`. Returns the set of globalIds within range.
 *
 * Depth 0 = only the start node itself.
 * Depth 1 = start node + immediate neighbors, etc.
 */
export function computeSubgraph(graphData: GraphData, startId: string, depth: number): Set<string> {
	const adj = new Map<string, string[]>();
	for (const link of graphData.links) {
		const src = typeof link.source === 'object' ? (link.source as { id: string }).id : link.source;
		const tgt = typeof link.target === 'object' ? (link.target as { id: string }).id : link.target;

		if (!adj.has(src)) adj.set(src, []);
		if (!adj.has(tgt)) adj.set(tgt, []);
		adj.get(src)!.push(tgt);
		adj.get(tgt)!.push(src);
	}

	const visited = new Set<string>();
	let frontier = [startId];
	visited.add(startId);

	for (let d = 0; d < depth; d++) {
		const next: string[] = [];
		for (const id of frontier) {
			for (const neighbor of adj.get(id) ?? []) {
				if (!visited.has(neighbor)) {
					visited.add(neighbor);
					next.push(neighbor);
				}
			}
		}
		frontier = next;
		if (frontier.length === 0) break;
	}

	return visited;
}
