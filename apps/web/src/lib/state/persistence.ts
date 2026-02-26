/**
 * localStorage persistence for app settings and search filters.
 */

import type { SearchFilter } from '$lib/search/protocol';

export interface AppSettings {
	activeProjectId: string | null;
	activeBranchId: string | null;
	activeRevision: number | null;
	activeGlobalId: string | null;
	subgraphDepth: number;
	activeView: "viewport" | "graph";
}

const STORAGE_KEY = "bimatlas-settings";

/**
 * Load settings from localStorage.
 * Returns null if no settings found or if parsing fails.
 * Safe to call during SSR (returns null).
 */
export function loadSettings(): AppSettings | null {
	// Check if we're in the browser (not SSR)
	if (typeof window === 'undefined') {
		return null;
	}
	
	try {
		const stored = localStorage.getItem(STORAGE_KEY);
		if (!stored) return null;
		const parsed = JSON.parse(stored) as Partial<AppSettings>;
		
		// Validate and return with defaults for missing fields (coerce to string for UUIDs)
		return {
			activeProjectId: parsed.activeProjectId != null ? String(parsed.activeProjectId) : null,
			activeBranchId: parsed.activeBranchId != null ? String(parsed.activeBranchId) : null,
			activeRevision: parsed.activeRevision ?? null,
			activeGlobalId: parsed.activeGlobalId ?? null,
			subgraphDepth: parsed.subgraphDepth ?? 1,
			activeView: parsed.activeView ?? "viewport",
		};
	} catch (err) {
		console.warn("Failed to load settings from localStorage:", err);
		return null;
	}
}

/**
 * Save settings to localStorage.
 * Safe to call during SSR (no-op).
 */
export function saveSettings(settings: AppSettings): void {
	// Check if we're in the browser (not SSR)
	if (typeof window === 'undefined') {
		return;
	}
	
	try {
		localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
	} catch (err) {
		console.warn("Failed to save settings to localStorage:", err);
	}
}

// ---- Search filters ----

const SEARCH_FILTERS_KEY = 'bimatlas-search-filters';

/**
 * Load saved search filters from localStorage.
 * Returns empty array if none saved or on parse error.
 */
export function loadSearchFilters(): SearchFilter[] {
	if (typeof window === 'undefined') return [];
	try {
		const stored = localStorage.getItem(SEARCH_FILTERS_KEY);
		if (!stored) return [];
		const parsed = JSON.parse(stored) as unknown;
		if (!Array.isArray(parsed)) return [];
		return parsed.filter(
			(f): f is SearchFilter =>
				typeof f === 'object' &&
				f !== null &&
				typeof (f as SearchFilter).id === 'string' &&
				((f as SearchFilter).mode === 'class' || (f as SearchFilter).mode === 'attribute'),
		);
	} catch (err) {
		console.warn('Failed to load search filters from localStorage:', err);
		return [];
	}
}

/**
 * Save search filters to localStorage.
 */
export function saveSearchFilters(filters: SearchFilter[]): void {
	if (typeof window === 'undefined') return;
	try {
		localStorage.setItem(SEARCH_FILTERS_KEY, JSON.stringify(filters));
	} catch (err) {
		console.warn('Failed to save search filters to localStorage:', err);
	}
}
