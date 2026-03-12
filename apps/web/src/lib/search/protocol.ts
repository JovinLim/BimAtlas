/**
 * Shared types and constants for cross-window search communication
 * via the BroadcastChannel API.
 */

export const SEARCH_CHANNEL = 'bimatlas-search';

/** localStorage key for apply-filter-sets fallback (when BroadcastChannel fails). */
export const APPLY_FILTER_SETS_STORAGE_KEY = 'bimatlas-apply-filter-sets';

/** postMessage origin for apply-filter-sets (opener fallback). */
export const APPLY_FILTER_SETS_MESSAGE_TYPE = 'bimatlas-apply-filter-sets';

export interface ProductMeta {
	globalId: string;
	ifcClass: string;
	name: string | null;
	description: string | null;
	objectType: string | null;
	tag: string | null;
	attributes?: Record<string, unknown> | null;
}

/** String operators for attribute mode. */
export const STRING_OPERATORS = [
	'is',
	'is_not',
	'contains',
	'not_contains',
	'starts_with',
	'ends_with',
	'is_empty',
	'is_not_empty'
] as const;

/** Numeric operators for attribute mode (valueType: numeric). */
export const NUMERIC_OPERATORS = [
	'equals',
	'not_equals',
	'gt',
	'lt',
	'gte',
	'lte'
] as const;

/** Class mode operators. */
export const CLASS_OPERATORS = ['is', 'is_not', 'inherits_from'] as const;

export type StringOperator = (typeof STRING_OPERATORS)[number];
export type NumericOperator = (typeof NUMERIC_OPERATORS)[number];
export type ClassOperator = (typeof CLASS_OPERATORS)[number];

export interface SearchFilter {
	id: string;
	mode: 'class' | 'attribute' | 'relation';
	ifcClass?: string;
	attribute?: string;
	value?: string;
	relation?: string;
	operator?: string;
	valueType?: 'string' | 'numeric' | 'object';
	/** Relation mode: IFC class of the related entity (e.g. IFCBuildingStorey). */
	relationTargetClass?: string;
	/** Relation mode: attribute to filter on the related entity (e.g. Name). */
	relationTargetAttribute?: string;
	/** Relation mode: operator for the related entity attribute. */
	relationTargetOperator?: string;
	/** Relation mode: value for the related entity attribute. */
	relationTargetValue?: string;
	/** Relation mode: value type for the related entity attribute. */
	relationTargetValueType?: 'string' | 'numeric' | 'object';
}

/** Leaf node in filter logic tree (single condition). */
export interface FilterLeaf {
	kind: 'leaf';
	mode: 'class' | 'attribute' | 'relation';
	ifcClass?: string;
	attribute?: string;
	value?: string;
	relation?: string;
	operator?: string;
	valueType?: 'string' | 'numeric' | 'object';
	relationTargetClass?: string;
	relationTargetAttribute?: string;
	relationTargetOperator?: string;
	relationTargetValue?: string;
	relationTargetValueType?: 'string' | 'numeric' | 'object';
}

/** Group node: Match ALL or Match ANY of children. Max depth 2. */
export interface FilterGroup {
	kind: 'group';
	op: 'ALL' | 'ANY';
	children: Array<FilterGroup | FilterLeaf>;
}

export type FilterTreeNode = FilterGroup | FilterLeaf;

/** Root expression: single group. */
export interface FilterExpression {
	root: FilterGroup;
}

const MAX_TREE_DEPTH = 2;

/** Convert legacy flat filters + logic to canonical tree. */
export function flatFiltersToExpression(
	filters: SearchFilter[],
	logic: 'AND' | 'OR'
): FilterExpression {
	const op = logic === 'AND' ? 'ALL' : 'ANY';
	const children: FilterLeaf[] = filters
		.filter((f) => f.mode)
		.map((f) => ({
			kind: 'leaf' as const,
			mode: f.mode,
			ifcClass: f.ifcClass,
			attribute: f.attribute,
			value: f.value,
			relation: f.relation,
			operator: f.operator,
			valueType: f.valueType,
			relationTargetClass: f.relationTargetClass,
			relationTargetAttribute: f.relationTargetAttribute,
			relationTargetOperator: f.relationTargetOperator,
			relationTargetValue: f.relationTargetValue,
			relationTargetValueType: f.relationTargetValueType,
		}));
	return { root: { kind: 'group', op, children } };
}

/** Flatten tree to legacy list (depth-first). */
export function expressionToFlatFilters(expr: FilterExpression): SearchFilter[] {
	const out: SearchFilter[] = [];
	let idCounter = 0;
	function visit(node: FilterTreeNode): void {
		if (node.kind === 'leaf') {
			out.push({
				id: `f-${idCounter++}`,
				mode: node.mode,
				ifcClass: node.ifcClass,
				attribute: node.attribute,
				value: node.value,
				relation: node.relation,
				operator: node.operator,
				valueType: node.valueType,
				relationTargetClass: node.relationTargetClass,
				relationTargetAttribute: node.relationTargetAttribute,
				relationTargetOperator: node.relationTargetOperator,
				relationTargetValue: node.relationTargetValue,
				relationTargetValueType: node.relationTargetValueType,
			});
		} else {
			for (const c of node.children) visit(c);
		}
	}
	visit(expr.root);
	return out;
}

/** Check if tree has depth > 2 (invalid). */
export function getTreeDepth(node: FilterTreeNode, depth = 0): number {
	if (node.kind === 'leaf') return depth;
	let max = depth;
	for (const c of node.children) {
		max = Math.max(max, getTreeDepth(c, depth + 1));
	}
	return max;
}

export function canAddSubgroup(node: FilterTreeNode, depth: number): boolean {
	return depth < MAX_TREE_DEPTH && node.kind === 'group';
}

/** Count leaf nodes in tree (for isEmpty check). */
export function countLeaves(node: FilterTreeNode): number {
	if (node.kind === 'leaf') return 1;
	return node.children.reduce((sum, c) => sum + countLeaves(c), 0);
}

/** Get parent path from child path. "0.1" -> "0", "0" -> "". */
export function getParentPath(path: string): string {
	const lastDot = path.lastIndexOf('.');
	return lastDot >= 0 ? path.slice(0, lastDot) : '';
}

/** Get depth from path. "" -> 0, "0" -> 1, "0.1" -> 2. */
export function getDepthFromPath(path: string): number {
	if (!path) return 0;
	return path.split('.').length;
}

export const FILTERABLE_ATTRIBUTES = [
	'globalId',
	'name',
	'objectType',
	'tag',
	'description',
	'height'
] as const;

export type FilterableAttribute = (typeof FILTERABLE_ATTRIBUTES)[number];

/** A persisted, named collection of filters with Match ALL/ANY logic. */
export interface FilterSet {
	id: string;
	branchId: string;
	name: string;
	logic: 'AND' | 'OR';
	filters: SearchFilter[];
	/** Canonical nested tree when available (from API). */
	filtersTree?: FilterGroup | null;
	color: string;
	createdAt: string;
	updatedAt: string;
}

/** UI label for logic: Match ALL / Match ANY. */
export function getLogicLabel(logic: 'AND' | 'OR'): string {
	return logic === 'AND' ? 'Match ALL' : 'Match ANY';
}

/** The set of currently-active filter sets for a branch. */
export interface AppliedFilterSets {
	filterSets: FilterSet[];
	combinationLogic: 'AND' | 'OR';
}

export type SearchScope = 'all' | 'project' | 'branch';

export type SearchMessage =
	| { type: 'apply-filters'; filters: SearchFilter[] }
	| {
			type: 'apply-filter-sets';
			filterSets: FilterSet[];
			combinationLogic: 'AND' | 'OR';
	  }
	| { type: 'filter-result-count'; count: number; total: number }
	| {
			type: 'branch-context';
			branchId: string;
			projectId: string;
			filterSetColorsEnabled?: boolean;
	  }
	| { type: 'request-branch-context' }
	| { type: 'request-applied-filter-sets' }
	| { type: 'set-filter-set-colors'; enabled: boolean };
