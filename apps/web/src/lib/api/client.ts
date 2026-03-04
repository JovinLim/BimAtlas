/**
 * GraphQL client (urql) and query definitions for communicating with the BimAtlas API.
 *
 * All IFC queries are scoped to a branch via `branchId`.
 * Project and branch management is done via mutations and queries.
 */
import { Client, cacheExchange, fetchExchange } from '@urql/core';
import { gql } from '@urql/core';

const API_URL = import.meta.env.VITE_API_URL ?? '/api/graphql';

export const client = new Client({
	url: API_URL,
	exchanges: [cacheExchange, fetchExchange]
});

// ---- Project / Branch Queries ----

/** Fetch all projects with their branches. */
export const PROJECTS_QUERY = gql`
	query Projects {
		projects {
			id
			name
			description
			createdAt
			branches {
				id
				projectId
				name
				createdAt
			}
		}
	}
`;

/** Fetch a single project by id. */
export const PROJECT_QUERY = gql`
	query Project($projectId: String!) {
		project(projectId: $projectId) {
			id
			name
			description
			createdAt
			branches {
				id
				projectId
				name
				createdAt
			}
		}
	}
`;

/** Fetch branches for a project. */
export const BRANCHES_QUERY = gql`
	query Branches($projectId: String!) {
		branches(projectId: $projectId) {
			id
			projectId
			name
			createdAt
		}
	}
`;

// ---- Mutations ----

/** Create a new project. */
export const CREATE_PROJECT_MUTATION = gql`
	mutation CreateProject($name: String!, $description: String) {
		createProject(name: $name, description: $description) {
			id
			name
			description
			createdAt
			branches {
				id
				projectId
				name
				createdAt
			}
		}
	}
`;

/** Create a new branch in a project. */
export const CREATE_BRANCH_MUTATION = gql`
	mutation CreateBranch($projectId: String!, $name: String!) {
		createBranch(projectId: $projectId, name: $name) {
			id
			projectId
			name
			createdAt
		}
	}
`;

/** Delete a project (and all its branches, revisions, and model data). */
export const DELETE_PROJECT_MUTATION = gql`
	mutation DeleteProject($id: String!) {
		deleteProject(id: $id)
	}
`;

/** Delete a branch (and all its revisions and model data). */
export const DELETE_BRANCH_MUTATION = gql`
	mutation DeleteBranch($id: String!) {
		deleteBranch(id: $id)
	}
`;

/** Delete a revision. */
export const DELETE_REVISION_MUTATION = gql`
	mutation DeleteRevision($id: String!) {
		deleteRevision(id: $id)
	}
`;

// ---- IFC Queries (branch-scoped) ----

/** Fetch a single IfcProduct by GlobalId on a branch, with mesh + relations. */
export const IFC_PRODUCT_QUERY = gql`
	query IfcProduct($branchId: String!, $globalId: String!, $revision: Int) {
		ifcProduct(branchId: $branchId, globalId: $globalId, revision: $revision) {
			globalId
			ifcClass
			name
			description
			objectType
			tag
			predefinedType
			attributes
			containedIn {
				globalId
				ifcClass
				name
			}
			mesh {
				vertices
				normals
				faces
			}
			representations {
				globalId
				representationIdentifier
				representationType
			}
			propertySets
			relations {
				globalId
				ifcClass
				name
				relationship
			}
		}
	}
`;

/** List IfcProducts on a branch with optional class/containment/attribute filters. */
export const IFC_PRODUCTS_QUERY = gql`
	query IfcProducts(
		$branchId: String!
		$ifcClass: String
		$ifcClasses: [String!]
		$containedIn: String
		$name: String
		$objectType: String
		$tag: String
		$description: String
		$globalId: String
		$revision: Int
	) {
		ifcProducts(
			branchId: $branchId
			ifcClass: $ifcClass
			ifcClasses: $ifcClasses
			containedIn: $containedIn
			name: $name
			objectType: $objectType
			tag: $tag
			description: $description
			globalId: $globalId
			revision: $revision
		) {
			globalId
			ifcClass
			name
			description
			objectType
			tag
			mesh {
				vertices
				normals
				faces
			}
		}
	}
`;

/** Spatial decomposition tree on a branch. */
export const SPATIAL_TREE_QUERY = gql`
	query SpatialTree($branchId: String!, $revision: Int) {
		spatialTree(branchId: $branchId, revision: $revision) {
			globalId
			ifcClass
			name
			children {
				globalId
				ifcClass
				name
				children {
					globalId
					ifcClass
					name
					children {
						globalId
						ifcClass
						name
						containedElements {
							globalId
							ifcClass
							name
							relationship
						}
					}
					containedElements {
						globalId
						ifcClass
						name
						relationship
					}
				}
				containedElements {
					globalId
					ifcClass
					name
					relationship
				}
			}
			containedElements {
				globalId
				ifcClass
				name
				relationship
			}
		}
	}
`;

/** IFC product class tree rooted at IfcProduct, pruned to classes present in DB. */
export const IFC_PRODUCT_TREE_QUERY = gql`
	query IfcProductTree($branchId: String!, $revision: Int) {
		ifcProductTree(branchId: $branchId, revision: $revision) {
			ifcClass
			children {
				ifcClass
				children {
					ifcClass
					children {
						ifcClass
						children {
							ifcClass
							children {
								ifcClass
							}
						}
					}
				}
			}
		}
	}
`;

/** Non-spatial element relations (voids, fills, connects, type-defines, shape reps) on a branch. */
export const ELEMENT_RELATIONS_QUERY = gql`
	query ElementRelations($branchId: String!, $revision: Int) {
		elementRelations(branchId: $branchId, revision: $revision) {
			sourceId
			sourceIfcClass
			sourceName
			targetId
			targetIfcClass
			targetName
			relationship
		}
	}
`;

/** List revisions on a branch, optionally filtered by search (author, filename, message, date). */
export const REVISIONS_QUERY = gql`
	query Revisions(
		$branchId: String!
		$search: String
		$authorSearch: String
		$ifcFilenameSearch: String
		$commitMessageSearch: String
		$createdAfter: String
		$createdBefore: String
	) {
		revisions(
			branchId: $branchId
			search: $search
			authorSearch: $authorSearch
			ifcFilenameSearch: $ifcFilenameSearch
			commitMessageSearch: $commitMessageSearch
			createdAfter: $createdAfter
			createdBefore: $createdBefore
		) {
			id
			branchId
			revisionSeq
			label
			ifcFilename
			authorId
			createdAt
		}
	}
`;

/** Compute the diff between two revisions on the same branch. */
export const REVISION_DIFF_QUERY = gql`
	query RevisionDiff($branchId: String!, $fromRev: Int!, $toRev: Int!) {
		revisionDiff(branchId: $branchId, fromRev: $fromRev, toRev: $toRev) {
			fromRevision
			toRevision
			added {
				globalId
				ifcClass
				name
				changeType
			}
			modified {
				globalId
				ifcClass
				name
				changeType
			}
			deleted {
				globalId
				ifcClass
				name
				changeType
			}
		}
	}
`;

// ---- Filter Set Queries / Mutations ----

const FILTER_SET_FIELDS = `
	id
	branchId
	name
	logic
	filters {
		mode
		ifcClass
		attribute
		value
		relation
		operator
		valueType
	}
	createdAt
	updatedAt
`;

/** List all filter sets for a branch. */
export const FILTER_SETS_QUERY = gql`
	query FilterSets($branchId: String!) {
		filterSets(branchId: $branchId) {
			${FILTER_SET_FIELDS}
		}
	}
`;

/** Search filter sets by name, optionally scoped. */
export const SEARCH_FILTER_SETS_QUERY = gql`
	query SearchFilterSets($query: String!, $branchId: String, $projectId: String) {
		searchFilterSets(query: $query, branchId: $branchId, projectId: $projectId) {
			${FILTER_SET_FIELDS}
		}
	}
`;

/** Get the currently active filter sets for a branch. */
export const APPLIED_FILTER_SETS_QUERY = gql`
	query AppliedFilterSets($branchId: String!) {
		appliedFilterSets(branchId: $branchId) {
			combinationLogic
			filterSets {
				${FILTER_SET_FIELDS}
			}
		}
	}
`;

/** Create a new filter set. */
export const CREATE_FILTER_SET_MUTATION = gql`
	mutation CreateFilterSet(
		$branchId: String!
		$name: String!
		$logic: String!
		$filters: [FilterInput!]!
	) {
		createFilterSet(branchId: $branchId, name: $name, logic: $logic, filters: $filters) {
			${FILTER_SET_FIELDS}
		}
	}
`;

/** Update an existing filter set. */
export const UPDATE_FILTER_SET_MUTATION = gql`
	mutation UpdateFilterSet(
		$id: String!
		$name: String
		$logic: String
		$filters: [FilterInput!]
	) {
		updateFilterSet(id: $id, name: $name, logic: $logic, filters: $filters) {
			${FILTER_SET_FIELDS}
		}
	}
`;

/** Delete a filter set. */
export const DELETE_FILTER_SET_MUTATION = gql`
	mutation DeleteFilterSet($id: String!) {
		deleteFilterSet(id: $id)
	}
`;

/** Set which filter sets are active on a branch. */
export const APPLY_FILTER_SETS_MUTATION = gql`
	mutation ApplyFilterSets(
		$branchId: String!
		$filterSetIds: [String!]!
		$combinationLogic: String!
	) {
		applyFilterSets(
			branchId: $branchId
			filterSetIds: $filterSetIds
			combinationLogic: $combinationLogic
		) {
			combinationLogic
			filterSets {
				${FILTER_SET_FIELDS}
			}
		}
	}
`;

// ---- Sheet template queries / mutations (FEAT-003 table page) ----

const SHEET_TEMPLATE_FIELDS = `
	id
	projectId
	name
	sheet
	open
	createdAt
	updatedAt
`;

/** List all sheet templates for a project. */
export const SHEET_TEMPLATES_QUERY = gql`
	query SheetTemplates($projectId: String!) {
		sheetTemplates(projectId: $projectId) {
			${SHEET_TEMPLATE_FIELDS}
		}
	}
`;

/** List opened sheet templates for a project (for initial page load). */
export const OPENED_SHEET_TEMPLATES_QUERY = gql`
	query OpenedSheetTemplates($projectId: String!) {
		openedSheetTemplates(projectId: $projectId) {
			${SHEET_TEMPLATE_FIELDS}
		}
	}
`;

/** Search sheet templates by name within a project. */
export const SEARCH_SHEET_TEMPLATES_QUERY = gql`
	query SearchSheetTemplates($query: String!, $projectId: String!) {
		searchSheetTemplates(query: $query, projectId: $projectId) {
			${SHEET_TEMPLATE_FIELDS}
		}
	}
`;

/** Fetch a single sheet template by id. */
export const SHEET_TEMPLATE_QUERY = gql`
	query SheetTemplate($id: String!) {
		sheetTemplate(id: $id) {
			${SHEET_TEMPLATE_FIELDS}
		}
	}
`;

/** Create a new sheet template. Name is required. */
export const CREATE_SHEET_TEMPLATE_MUTATION = gql`
	mutation CreateSheetTemplate(
		$projectId: String!
		$name: String!
		$sheet: JSON!
		$open: Boolean
	) {
		createSheetTemplate(projectId: $projectId, name: $name, sheet: $sheet, open: $open) {
			${SHEET_TEMPLATE_FIELDS}
		}
	}
`;

/** Update a sheet template (open, name, or sheet content). */
export const UPDATE_SHEET_TEMPLATE_MUTATION = gql`
	mutation UpdateSheetTemplate($id: String!, $open: Boolean, $name: String, $sheet: JSON) {
		updateSheetTemplate(id: $id, open: $open, name: $name, sheet: $sheet) {
			${SHEET_TEMPLATE_FIELDS}
		}
	}
`;

/** Delete a sheet template by id. */
export const DELETE_SHEET_TEMPLATE_MUTATION = gql`
	mutation DeleteSheetTemplate($id: String!) {
		deleteSheetTemplate(id: $id)
	}
`;
