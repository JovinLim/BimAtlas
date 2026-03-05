<script lang="ts">
	import { tick } from 'svelte';
	import { flattenTree, IFC_RELATION_TYPES, type FlatEntry } from '$lib/ifc/schema';
	import {
		CLASS_OPERATORS,
		NUMERIC_OPERATORS,
		STRING_OPERATORS,
		type SearchFilter
	} from '$lib/search/protocol';

	const OPERATOR_LABELS: Record<string, string> = {
		is: 'is',
		inherits_from: 'inherits from',
		contains: 'contains',
		not_contains: 'does not contain',
		starts_with: 'starts with',
		ends_with: 'ends with',
		is_empty: 'is empty',
		is_not_empty: 'is not empty',
		is_not: 'is not',
		equals: 'equals',
		not_equals: 'not equals',
		gt: '>',
		lt: '<',
		gte: '≥',
		lte: '≤'
	};

	const VALUE_OPTIONAL_OPERATORS = new Set(['is_empty', 'is_not_empty']);
	const COMMON_ATTRIBUTE_SUGGESTIONS = ['IFC Global Id', 'ObjectType', 'Name', 'Tag'] as const;

	let {
		filter,
		onupdate,
		onremove
	}: {
		filter: SearchFilter;
		onupdate: (patch: Partial<SearchFilter>) => void;
		onremove: () => void;
	} = $props();

	let classQuery = $state('');
	let classDropdownOpen = $state(false);
	let classHighlightIndex = $state(0);
	let classComboboxEl = $state<HTMLDivElement | null>(null);
	let classInputEl = $state<HTMLInputElement | null>(null);
	let classClosedBySelection = $state(false);
	let classDropdownRect = $state<{ top: number; left: number; width: number } | null>(null);

	function updateClassDropdownPosition() {
		if (classInputEl) {
			const r = classInputEl.getBoundingClientRect();
			classDropdownRect = {
				top: r.bottom + 4,
				left: r.left,
				width: r.width,
			};
		} else {
			classDropdownRect = null;
		}
	}

	$effect(() => {
		if (!classDropdownOpen) {
			classDropdownRect = null;
			return;
		}
		updateClassDropdownPosition();
		let raf = 0;
		function scheduleUpdate() {
			if (raf) cancelAnimationFrame(raf);
			raf = requestAnimationFrame(() => {
				raf = 0;
				updateClassDropdownPosition();
			});
		}
		tick().then(scheduleUpdate);
		const onResize = () => scheduleUpdate();
		const onScroll = () => scheduleUpdate();
		window.addEventListener('resize', onResize);
		window.addEventListener('scroll', onScroll, true);
		return () => {
			if (raf) cancelAnimationFrame(raf);
			window.removeEventListener('resize', onResize);
			window.removeEventListener('scroll', onScroll, true);
		};
	});

	let filteredClassEntries = $state<FlatEntry[]>(flattenTree());

	$effect(() => {
		const entries = flattenTree();
		filteredClassEntries =
			classQuery.trim() === ''
				? entries
				: entries.filter((e) =>
						e.name.toLowerCase().includes(classQuery.toLowerCase()),
					);
	});

	const selectedClassLabel = $derived.by(() => {
		if (!filter.ifcClass) return '';
		const entries = flattenTree();
		const entry = entries.find((e) => e.name === filter.ifcClass);
		// Show only the class name in the input (no indentation); indentation is for dropdown list only
		return entry ? entry.name : filter.ifcClass.trim();
	});

	function handleModeChange(mode: 'class' | 'attribute' | 'relation') {
		onupdate({
			mode,
			ifcClass: undefined,
			attribute: undefined,
			value: undefined,
			relation: undefined,
			operator: undefined,
			valueType: undefined
		});
	}

	function openClassDropdown() {
		classDropdownOpen = true;
		classHighlightIndex = 0;
	}

	function closeClassDropdown() {
		classDropdownOpen = false;
		classQuery = '';
		classHighlightIndex = 0;
	}

	function selectClass(name: string) {
		classClosedBySelection = true;
		onupdate({ ifcClass: name });
		closeClassDropdown();
	}

	function onClassInputFocus() {
		classQuery = filter.ifcClass ?? '';
		openClassDropdown();
	}

	function onClassInputInput(e: Event) {
		classQuery = (e.currentTarget as HTMLInputElement).value;
		classHighlightIndex = 0;
		if (!classDropdownOpen) classDropdownOpen = true;
	}

	function onClassInputKeydown(e: KeyboardEvent) {
		if (!classDropdownOpen) {
			if (e.key === 'ArrowDown' || e.key === 'Enter') {
				e.preventDefault();
				openClassDropdown();
			}
			return;
		}
		if (e.key === 'Escape') {
			e.preventDefault();
			closeClassDropdown();
			classInputEl?.blur();
			return;
		}
		if (e.key === 'ArrowDown') {
			e.preventDefault();
			classHighlightIndex = Math.min(
				classHighlightIndex + 1,
				filteredClassEntries.length - 1,
			);
			return;
		}
		if (e.key === 'ArrowUp') {
			e.preventDefault();
			classHighlightIndex = Math.max(classHighlightIndex - 1, 0);
			return;
		}
		if (e.key === 'Enter') {
			e.preventDefault();
			const entry = filteredClassEntries[classHighlightIndex];
			if (entry) selectClass(entry.name);
			return;
		}
	}

	function onClassComboboxBlur() {
		const hadEmptyQuery = classQuery === '';
		const closedBySelection = classClosedBySelection;
		setTimeout(() => {
			classClosedBySelection = false;
			closeClassDropdown();
			if (hadEmptyQuery && !closedBySelection) onupdate({ ifcClass: undefined });
		}, 150);
	}

	function getClassInputValue() {
		return classDropdownOpen ? classQuery : selectedClassLabel;
	}

	// ---- Attribute combobox state ----

	let attrQuery = $state('');
	let attrDropdownOpen = $state(false);
	let attrHighlightIndex = $state(0);
	let attrComboboxEl = $state<HTMLDivElement | null>(null);
	let attrInputEl = $state<HTMLInputElement | null>(null);
	let attrClosedBySelection = $state(false);
	let attrDropdownRect = $state<{ top: number; left: number; width: number } | null>(null);

	function updateAttrDropdownPosition() {
		if (attrInputEl) {
			const r = attrInputEl.getBoundingClientRect();
			attrDropdownRect = { top: r.bottom + 4, left: r.left, width: r.width };
		} else {
			attrDropdownRect = null;
		}
	}

	$effect(() => {
		if (!attrDropdownOpen) {
			attrDropdownRect = null;
			return;
		}
		updateAttrDropdownPosition();
		let raf = 0;
		function scheduleUpdate() {
			if (raf) cancelAnimationFrame(raf);
			raf = requestAnimationFrame(() => {
				raf = 0;
				updateAttrDropdownPosition();
			});
		}
		tick().then(scheduleUpdate);
		const onResize = () => scheduleUpdate();
		const onScroll = () => scheduleUpdate();
		window.addEventListener('resize', onResize);
		window.addEventListener('scroll', onScroll, true);
		return () => {
			if (raf) cancelAnimationFrame(raf);
			window.removeEventListener('resize', onResize);
			window.removeEventListener('scroll', onScroll, true);
		};
	});

	const selectedAttrLabel = $derived(filter.attribute ?? '');

	const filteredAttrSuggestions = $derived.by(() => {
		const q = attrQuery.trim().toLowerCase();
		if (!q) return COMMON_ATTRIBUTE_SUGGESTIONS;
		return COMMON_ATTRIBUTE_SUGGESTIONS.filter((attr) => attr.toLowerCase().includes(q));
	});

	function openAttrDropdown() {
		attrDropdownOpen = true;
		attrHighlightIndex = 0;
	}

	function closeAttrDropdown() {
		attrDropdownOpen = false;
		attrQuery = '';
		attrHighlightIndex = 0;
	}

	function selectAttribute(name: string) {
		attrClosedBySelection = true;
		onupdate({ attribute: name });
		closeAttrDropdown();
	}

	function onAttrInputFocus() {
		attrQuery = filter.attribute ?? '';
		openAttrDropdown();
	}

	function onAttrInputInput(e: Event) {
		const next = (e.currentTarget as HTMLInputElement).value;
		attrQuery = next;
		attrHighlightIndex = 0;
		onupdate({ attribute: next.trim() === '' ? undefined : next });
		if (!attrDropdownOpen) attrDropdownOpen = true;
	}

	function onAttrInputKeydown(e: KeyboardEvent) {
		if (!attrDropdownOpen) {
			if (e.key === 'ArrowDown' || e.key === 'Enter') {
				e.preventDefault();
				openAttrDropdown();
			}
			return;
		}
		if (e.key === 'Escape') {
			e.preventDefault();
			closeAttrDropdown();
			attrInputEl?.blur();
			return;
		}
		if (e.key === 'ArrowDown') {
			e.preventDefault();
			attrHighlightIndex = Math.min(attrHighlightIndex + 1, filteredAttrSuggestions.length - 1);
			return;
		}
		if (e.key === 'ArrowUp') {
			e.preventDefault();
			attrHighlightIndex = Math.max(attrHighlightIndex - 1, 0);
			return;
		}
		if (e.key === 'Enter') {
			const entry = filteredAttrSuggestions[attrHighlightIndex];
			if (entry) {
				e.preventDefault();
				selectAttribute(entry);
			}
		}
	}

	function onAttrComboboxBlur() {
		const hadEmptyQuery = attrQuery.trim() === '';
		const closedBySelection = attrClosedBySelection;
		setTimeout(() => {
			attrClosedBySelection = false;
			closeAttrDropdown();
			if (hadEmptyQuery && !closedBySelection) onupdate({ attribute: undefined });
		}, 150);
	}

	function getAttrInputValue() {
		return attrDropdownOpen ? attrQuery : selectedAttrLabel;
	}

	// ---- Relation combobox state ----

	const relationEntries: readonly string[] = IFC_RELATION_TYPES;
	let relQuery = $state('');
	let relDropdownOpen = $state(false);
	let relHighlightIndex = $state(0);
	let relComboboxEl = $state<HTMLDivElement | null>(null);
	let relInputEl = $state<HTMLInputElement | null>(null);
	let relClosedBySelection = $state(false);
	let relDropdownRect = $state<{ top: number; left: number; width: number } | null>(null);

	function updateRelDropdownPosition() {
		if (relInputEl) {
			const r = relInputEl.getBoundingClientRect();
			relDropdownRect = { top: r.bottom + 4, left: r.left, width: r.width };
		} else {
			relDropdownRect = null;
		}
	}

	$effect(() => {
		if (!relDropdownOpen) {
			relDropdownRect = null;
			return;
		}
		updateRelDropdownPosition();
		let raf = 0;
		function scheduleUpdate() {
			if (raf) cancelAnimationFrame(raf);
			raf = requestAnimationFrame(() => {
				raf = 0;
				updateRelDropdownPosition();
			});
		}
		tick().then(scheduleUpdate);
		const onResize = () => scheduleUpdate();
		const onScroll = () => scheduleUpdate();
		window.addEventListener('resize', onResize);
		window.addEventListener('scroll', onScroll, true);
		return () => {
			if (raf) cancelAnimationFrame(raf);
			window.removeEventListener('resize', onResize);
			window.removeEventListener('scroll', onScroll, true);
		};
	});

	const filteredRelEntries = $derived(
		relQuery.trim() === ''
			? relationEntries
			: relationEntries.filter((name) =>
					name.toLowerCase().includes(relQuery.toLowerCase()),
				),
	);

	const selectedRelLabel = $derived(filter.relation ?? '');

	function openRelDropdown() {
		relDropdownOpen = true;
		relHighlightIndex = 0;
	}

	function closeRelDropdown() {
		relDropdownOpen = false;
		relQuery = '';
		relHighlightIndex = 0;
	}

	function selectRelation(name: string) {
		relClosedBySelection = true;
		onupdate({ relation: name });
		closeRelDropdown();
	}

	function onRelInputFocus() {
		relQuery = filter.relation ?? '';
		openRelDropdown();
	}

	function onRelInputInput(e: Event) {
		relQuery = (e.currentTarget as HTMLInputElement).value;
		relHighlightIndex = 0;
		if (!relDropdownOpen) relDropdownOpen = true;
	}

	function onRelInputKeydown(e: KeyboardEvent) {
		if (!relDropdownOpen) {
			if (e.key === 'ArrowDown' || e.key === 'Enter') {
				e.preventDefault();
				openRelDropdown();
			}
			return;
		}
		if (e.key === 'Escape') {
			e.preventDefault();
			closeRelDropdown();
			relInputEl?.blur();
			return;
		}
		if (e.key === 'ArrowDown') {
			e.preventDefault();
			relHighlightIndex = Math.min(relHighlightIndex + 1, filteredRelEntries.length - 1);
			return;
		}
		if (e.key === 'ArrowUp') {
			e.preventDefault();
			relHighlightIndex = Math.max(relHighlightIndex - 1, 0);
			return;
		}
		if (e.key === 'Enter') {
			e.preventDefault();
			const entry = filteredRelEntries[relHighlightIndex];
			if (entry) selectRelation(entry);
			return;
		}
	}

	function onRelComboboxBlur() {
		const hadEmptyQuery = relQuery === '';
		const closedBySelection = relClosedBySelection;
		setTimeout(() => {
			relClosedBySelection = false;
			closeRelDropdown();
			if (hadEmptyQuery && !closedBySelection) onupdate({ relation: undefined });
		}, 150);
	}

	function getRelInputValue() {
		return relDropdownOpen ? relQuery : selectedRelLabel;
	}
</script>

<div class="filter-row">
	<div class="mode-toggle">
		<button
			class="mode-btn"
			class:active={filter.mode === 'class'}
			aria-label="Filter by class"
			onclick={() => handleModeChange('class')}
		>
			Class
		</button>
		<button
			class="mode-btn"
			class:active={filter.mode === 'attribute'}
			aria-label="Filter by attribute"
			onclick={() => handleModeChange('attribute')}
		>
			Attribute
		</button>
		<button
			class="mode-btn"
			class:active={filter.mode === 'relation'}
			aria-label="Filter by relation"
			onclick={() => handleModeChange('relation')}
		>
			Relation
		</button>
	</div>

	<div class="filter-fields" class:filter-fields--attribute={filter.mode === 'attribute'}>
		{#if filter.mode === 'class'}
			<select
				class="filter-select filter-select--op"
				value={filter.operator ?? 'is'}
				onchange={(e) => onupdate({ operator: e.currentTarget.value || undefined })}
			>
				{#each CLASS_OPERATORS as op}
					<option value={op}>{OPERATOR_LABELS[op] ?? op}</option>
				{/each}
			</select>
			<div
				class="filter-combobox"
				bind:this={classComboboxEl}
				onfocusout={onClassComboboxBlur}
			>
				<input
					bind:this={classInputEl}
					class="filter-select filter-input-combo"
					type="text"
					autocomplete="off"
					role="combobox"
					aria-expanded={classDropdownOpen}
					aria-haspopup="listbox"
					aria-controls="ifc-class-listbox"
					aria-activedescendant={classDropdownOpen && filteredClassEntries[classHighlightIndex]
						? `ifc-class-option-${classHighlightIndex}`
						: undefined}
					id="ifc-class-combobox"
					placeholder="Select IFC class…"
					value={getClassInputValue()}
					onfocus={onClassInputFocus}
					oninput={onClassInputInput}
					onkeydown={onClassInputKeydown}
				/>
				{#if classDropdownOpen}
					<ul
						id="ifc-class-listbox"
						class="filter-combobox-list filter-combobox-list--fixed"
						role="listbox"
						aria-label="IFC class"
						style={classDropdownRect
							? `top: ${classDropdownRect.top}px; left: ${classDropdownRect.left}px; width: ${classDropdownRect.width}px;`
							: ''}
					>
						{#each filteredClassEntries as entry, i}
							<li
								id="ifc-class-option-{i}"
								role="option"
								tabindex="-1"
								aria-selected={i === classHighlightIndex}
								class="filter-combobox-option"
								class:highlighted={i === classHighlightIndex}
								onmousedown={(e) => e.preventDefault()}
								onclick={() => selectClass(entry.name)}
								onkeydown={(e) => {
									if (e.key === 'Enter' || e.key === ' ') {
										e.preventDefault();
										selectClass(entry.name);
									}
								}}
							>
								{'  '.repeat(entry.depth)}{entry.name}
							</li>
						{/each}
						{#if filteredClassEntries.length === 0}
							<li class="filter-combobox-option filter-combobox-option--empty">
								No matching class
							</li>
						{/if}
					</ul>
				{/if}
			</div>
		{:else if filter.mode === 'attribute'}
			<div
				class="filter-combobox filter-combobox--attr"
				bind:this={attrComboboxEl}
				onfocusout={onAttrComboboxBlur}
			>
				<input
					bind:this={attrInputEl}
					class="filter-select filter-input-combo"
					type="text"
					autocomplete="off"
					role="combobox"
					aria-expanded={attrDropdownOpen}
					aria-haspopup="listbox"
					aria-controls="ifc-attr-listbox"
					aria-activedescendant={attrDropdownOpen && filteredAttrSuggestions[attrHighlightIndex]
						? `ifc-attr-option-${attrHighlightIndex}`
						: undefined}
					id="ifc-attr-combobox"
					placeholder="Enter attribute here..."
					value={getAttrInputValue()}
					onfocus={onAttrInputFocus}
					oninput={onAttrInputInput}
					onkeydown={onAttrInputKeydown}
				/>
				{#if attrDropdownOpen}
					<ul
						id="ifc-attr-listbox"
						class="filter-combobox-list filter-combobox-list--fixed"
						role="listbox"
						aria-label="Common attributes"
						style={attrDropdownRect
							? `top: ${attrDropdownRect.top}px; left: ${attrDropdownRect.left}px; width: ${attrDropdownRect.width}px;`
							: ''}
					>
						{#each filteredAttrSuggestions as attr, i}
							<li
								id="ifc-attr-option-{i}"
								role="option"
								tabindex="-1"
								aria-selected={i === attrHighlightIndex}
								class="filter-combobox-option"
								class:highlighted={i === attrHighlightIndex}
								onmousedown={(e) => e.preventDefault()}
								onclick={() => selectAttribute(attr)}
								onkeydown={(e) => {
									if (e.key === 'Enter' || e.key === ' ') {
										e.preventDefault();
										selectAttribute(attr);
									}
								}}
							>
								{attr}
							</li>
						{/each}
					</ul>
				{/if}
			</div>
			<select
				class="filter-select filter-select--op"
				value={
					filter.valueType === 'numeric'
						? (NUMERIC_OPERATORS.includes(filter.operator as (typeof NUMERIC_OPERATORS)[number])
								? filter.operator
								: 'equals')
						: (filter.operator ?? 'contains')
				}
				onchange={(e) => onupdate({ operator: e.currentTarget.value || undefined })}
			>
				{#each (filter.valueType === 'numeric' ? NUMERIC_OPERATORS : STRING_OPERATORS) as op}
					<option value={op}>{OPERATOR_LABELS[op] ?? op}</option>
				{/each}
			</select>
			<select
				class="filter-select filter-select--value-type"
				value={filter.valueType ?? 'string'}
				onchange={(e) =>
					onupdate({
						valueType: (e.currentTarget.value as 'string' | 'numeric' | 'object') || undefined,
						operator: undefined
					})}
			>
				<option value="string">String</option>
				<option value="numeric">Numeric</option>
				<option value="object">Object</option>
			</select>
			{#if !VALUE_OPTIONAL_OPERATORS.has(filter.operator ?? '')}
				<input
					class="filter-input"
					type={filter.valueType === 'numeric' ? 'number' : 'text'}
					placeholder="Value…"
					value={filter.value ?? ''}
					oninput={(e) => onupdate({ value: e.currentTarget.value })}
				/>
			{/if}
		{:else if filter.mode === 'relation'}
			<div
				class="filter-combobox"
				bind:this={relComboboxEl}
				onfocusout={onRelComboboxBlur}
			>
				<input
					bind:this={relInputEl}
					class="filter-select filter-input-combo"
					type="text"
					autocomplete="off"
					role="combobox"
					aria-expanded={relDropdownOpen}
					aria-haspopup="listbox"
					aria-controls="ifc-rel-listbox"
					aria-activedescendant={relDropdownOpen && filteredRelEntries[relHighlightIndex]
						? `ifc-rel-option-${relHighlightIndex}`
						: undefined}
					id="ifc-rel-combobox"
					placeholder="Select IFC relation…"
					value={getRelInputValue()}
					onfocus={onRelInputFocus}
					oninput={onRelInputInput}
					onkeydown={onRelInputKeydown}
				/>
				{#if relDropdownOpen}
					<ul
						id="ifc-rel-listbox"
						class="filter-combobox-list filter-combobox-list--fixed"
						role="listbox"
						aria-label="IFC relation"
						style={relDropdownRect
							? `top: ${relDropdownRect.top}px; left: ${relDropdownRect.left}px; width: ${relDropdownRect.width}px;`
							: ''}
					>
						{#each filteredRelEntries as name, i}
							<li
								id="ifc-rel-option-{i}"
								role="option"
								tabindex="-1"
								aria-selected={i === relHighlightIndex}
								class="filter-combobox-option"
								class:highlighted={i === relHighlightIndex}
								onmousedown={(e) => e.preventDefault()}
								onclick={() => selectRelation(name)}
								onkeydown={(e) => {
									if (e.key === 'Enter' || e.key === ' ') {
										e.preventDefault();
										selectRelation(name);
									}
								}}
							>
								{name}
							</li>
						{/each}
						{#if filteredRelEntries.length === 0}
							<li class="filter-combobox-option filter-combobox-option--empty">
								No matching relation
							</li>
						{/if}
					</ul>
				{/if}
			</div>
		{/if}
	</div>

	<button class="remove-btn" onclick={onremove} aria-label="Remove filter">
		<svg width="14" height="14" viewBox="0 0 16 16" fill="none">
			<path
				d="M4 4L12 12M12 4L4 12"
				stroke="currentColor"
				stroke-width="1.5"
				stroke-linecap="round"
			/>
		</svg>
	</button>
</div>

<style>
	.filter-row {
		--control-height: 28px;
		--control-padding-x: 0.45rem;
		--control-padding-y: 0.25rem;
		--control-font-size: 0.78rem;
		--control-border: 1px solid var(--color-border-default);
		--control-radius: 0.3rem;
		--control-bg: var(--color-bg-elevated);
		--control-focus-border: var(--color-brand-500);
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0;
	}

	.mode-toggle {
		display: flex;
		height: var(--control-height);
		border: var(--control-border);
		border-radius: var(--control-radius);
		overflow: hidden;
		flex-shrink: 0;
	}

	.mode-btn {
		height: 100%;
		background: var(--color-bg-elevated);
		border: none;
		color: var(--color-text-muted);
		padding: 0 var(--control-padding-x);
		font-size: var(--control-font-size);
		cursor: pointer;
		transition:
			background 0.15s,
			color 0.15s;
	}

	.mode-btn:hover {
		color: var(--color-text-secondary);
	}

	.mode-btn.active {
		background: color-mix(in srgb, var(--color-brand-500) 12%, transparent);
		color: var(--color-brand-500);
	}

	.filter-fields {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		flex: 1;
		min-width: 0;
	}

	.filter-combobox {
		position: relative;
		flex: 1;
		min-width: 0;
	}

	/* Shared control base for select, input, combobox */
	.filter-select,
	.filter-input-combo,
	.filter-input {
		height: var(--control-height);
		box-sizing: border-box;
		background: var(--control-bg);
		border: var(--control-border);
		border-radius: var(--control-radius);
		color: var(--color-text-primary);
		padding: var(--control-padding-y) var(--control-padding-x);
		font-size: var(--control-font-size);
		outline: none;
	}

	.filter-select,
	.filter-input-combo {
		width: 100%;
	}

	.filter-input-combo {
		cursor: text;
	}

	.filter-select:focus,
	.filter-input-combo:focus,
	.filter-input:focus {
		border-color: var(--control-focus-border);
	}

	.filter-select option {
		background: var(--color-bg-surface);
		color: var(--color-text-primary);
		white-space: pre;
	}

	.filter-input::placeholder {
		color: var(--color-text-muted);
	}

	.filter-combobox-list {
		position: absolute;
		top: 100%;
		left: 0;
		right: 0;
		margin: 0.15rem 0 0;
		padding: 0.25rem 0;
		max-height: 220px;
		overflow-y: auto;
		list-style: none;
		background: var(--color-bg-surface);
		border: 1px solid var(--color-border-default);
		border-radius: var(--control-radius);
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
		z-index: 20;
	}

	.filter-combobox-list--fixed {
		position: fixed;
		right: auto;
		bottom: auto;
		margin: 0;
		z-index: 9999;
	}

	.filter-combobox-option {
		padding: 0.3rem 0.45rem;
		font-size: var(--control-font-size);
		color: var(--color-text-primary);
		cursor: pointer;
		white-space: pre;
	}

	.filter-combobox-option:hover,
	.filter-combobox-option.highlighted {
		background: color-mix(in srgb, var(--color-brand-500) 10%, transparent);
		color: var(--color-brand-500);
	}

	.filter-combobox-option--empty {
		color: var(--color-text-muted);
		cursor: default;
	}

	.filter-combobox-option--empty:hover {
		background: transparent;
		color: var(--color-text-muted);
	}

	.filter-combobox--attr {
		flex: 1.35;
		min-width: 220px;
	}

	.filter-select--op {
		flex: 0 0 auto;
		width: 120px;
	}

	.filter-select--value-type {
		flex: 0 0 auto;
		width: 80px;
	}

	.filter-input {
		flex: 1;
		min-width: 0;
	}

	.filter-fields--attribute .filter-input {
		flex: 2;
		min-width: 240px;
	}

	.remove-btn {
		background: none;
		border: none;
		color: var(--color-text-muted);
		cursor: pointer;
		padding: 0.2rem;
		border-radius: 0.25rem;
		display: flex;
		align-items: center;
		flex-shrink: 0;
		transition: color 0.15s;
	}

	.remove-btn:hover {
		color: var(--color-danger);
	}
</style>
