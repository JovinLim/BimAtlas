/**
 * Reactive search state for the main window.
 *
 * Holds the product metadata list, the total unfiltered count,
 * active ad-hoc filters, and applied filter sets with their
 * combination logic.
 */

import type { FilterSet, ProductMeta, SearchFilter } from '$lib/search/protocol';

let productsList = $state<ProductMeta[]>([]);
let totalProductCount = $state(0);
let activeFilters = $state<SearchFilter[]>([]);
let appliedFilterSets = $state<FilterSet[]>([]);
let combinationLogic = $state<'AND' | 'OR'>('OR');

export function getSearchState() {
	return {
		get products() {
			return productsList;
		},
		setProducts(list: ProductMeta[]) {
			productsList = list;
		},
		get totalProductCount() {
			return totalProductCount;
		},
		set totalProductCount(count: number) {
			totalProductCount = count;
		},
		get activeFilters() {
			return activeFilters;
		},
		set activeFilters(filters: SearchFilter[]) {
			activeFilters = filters;
		},
		get appliedFilterSets() {
			return appliedFilterSets;
		},
		set appliedFilterSets(sets: FilterSet[]) {
			appliedFilterSets = sets;
		},
		get combinationLogic() {
			return combinationLogic;
		},
		set combinationLogic(logic: 'AND' | 'OR') {
			combinationLogic = logic;
		}
	};
}
