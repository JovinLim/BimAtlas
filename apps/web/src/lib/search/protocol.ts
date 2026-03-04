/**
 * Shared types and constants for cross-window search communication
 * via the BroadcastChannel API.
 */

export const SEARCH_CHANNEL = 'bimatlas-search';

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

/** A persisted, named collection of filters with AND/OR logic. */
export interface FilterSet {
	id: string;
	branchId: string;
	name: string;
	logic: 'AND' | 'OR';
	filters: SearchFilter[];
	createdAt: string;
	updatedAt: string;
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
	| { type: 'branch-context'; branchId: string; projectId: string }
	| { type: 'request-branch-context' };
