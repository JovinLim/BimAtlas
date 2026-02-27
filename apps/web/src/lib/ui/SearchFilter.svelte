<script lang="ts">
	import { tick } from 'svelte';
	import { flattenTree, IFC_RELATION_TYPES, type FlatEntry } from '$lib/ifc/schema';
	import { FILTERABLE_ATTRIBUTES, type SearchFilter } from '$lib/search/protocol';

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
		onupdate({ mode, ifcClass: undefined, attribute: undefined, value: undefined, relation: undefined });
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

	<div class="filter-fields">
		{#if filter.mode === 'class'}
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
			<select
				class="filter-select filter-select--attr"
				value={filter.attribute ?? ''}
				onchange={(e) => onupdate({ attribute: e.currentTarget.value || undefined })}
			>
				<option value="">Attribute…</option>
				{#each FILTERABLE_ATTRIBUTES as attr}
					<option value={attr}>{attr}</option>
				{/each}
			</select>
			<input
				class="filter-input"
				type="text"
				placeholder="Value…"
				value={filter.value ?? ''}
				oninput={(e) => onupdate({ value: e.currentTarget.value })}
			/>
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
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0;
	}

	.mode-toggle {
		display: flex;
		border: 1px solid rgba(255, 255, 255, 0.1);
		border-radius: 0.3rem;
		overflow: hidden;
		flex-shrink: 0;
	}

	.mode-btn {
		background: rgba(255, 255, 255, 0.04);
		border: none;
		color: #888;
		padding: 0.3rem 0.55rem;
		font-size: 0.7rem;
		cursor: pointer;
		transition:
			background 0.15s,
			color 0.15s;
	}

	.mode-btn:hover {
		color: #ccc;
	}

	.mode-btn.active {
		background: rgba(255, 136, 102, 0.18);
		color: #ff8866;
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

	.filter-select,
	.filter-input-combo {
		width: 100%;
		box-sizing: border-box;
		background: rgba(255, 255, 255, 0.06);
		border: 1px solid rgba(255, 255, 255, 0.1);
		border-radius: 0.3rem;
		color: #ddd;
		padding: 0.3rem 0.45rem;
		font-size: 0.78rem;
		outline: none;
	}

	.filter-input-combo {
		cursor: text;
	}

	.filter-select:focus,
	.filter-input-combo:focus {
		border-color: rgba(255, 136, 102, 0.4);
	}

	.filter-select option {
		background: #1e1e30;
		color: #ddd;
		white-space: pre;
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
		background: #1e1e30;
		border: 1px solid rgba(255, 255, 255, 0.12);
		border-radius: 0.3rem;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
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
		font-size: 0.78rem;
		color: #ddd;
		cursor: pointer;
		white-space: pre;
	}

	.filter-combobox-option:hover,
	.filter-combobox-option.highlighted {
		background: rgba(255, 136, 102, 0.15);
		color: #ff8866;
	}

	.filter-combobox-option--empty {
		color: #666;
		cursor: default;
	}

	.filter-combobox-option--empty:hover {
		background: transparent;
		color: #666;
	}

	.filter-select--attr {
		flex: 0 0 auto;
		width: 110px;
	}

	.filter-input {
		flex: 1;
		min-width: 0;
		background: rgba(255, 255, 255, 0.06);
		border: 1px solid rgba(255, 255, 255, 0.1);
		border-radius: 0.3rem;
		color: #ddd;
		padding: 0.3rem 0.45rem;
		font-size: 0.78rem;
		outline: none;
	}

	.filter-input:focus {
		border-color: rgba(255, 136, 102, 0.4);
	}

	.filter-input::placeholder {
		color: #555;
	}

	.remove-btn {
		background: none;
		border: none;
		color: #666;
		cursor: pointer;
		padding: 0.2rem;
		border-radius: 0.25rem;
		display: flex;
		align-items: center;
		flex-shrink: 0;
		transition: color 0.15s;
	}

	.remove-btn:hover {
		color: #ff6b6b;
	}
</style>
