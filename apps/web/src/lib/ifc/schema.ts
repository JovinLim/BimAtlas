/**
 * Static IFC 4.3 product type hierarchy for search filter dropdowns.
 * Covers the classes tracked by IfcProductCategory on the backend.
 */

export interface IfcSchemaNode {
	name: string;
	children?: IfcSchemaNode[];
}

export const IFC_PRODUCT_TREE: IfcSchemaNode = {
	name: 'IfcProduct',
	children: [
		{
			name: 'IfcElement',
			children: [
				{
					name: 'IfcBuildingElement',
					children: [
						{ name: 'IfcWall' },
						{ name: 'IfcSlab' },
						{ name: 'IfcBeam' },
						{ name: 'IfcColumn' },
						{ name: 'IfcDoor' },
						{ name: 'IfcWindow' },
						{ name: 'IfcRoof' },
						{ name: 'IfcStair' },
						{ name: 'IfcRailing' },
						{ name: 'IfcCovering' },
						{ name: 'IfcCurtainWall' },
						{ name: 'IfcPlate' },
						{ name: 'IfcMember' },
						{ name: 'IfcFooting' },
						{ name: 'IfcPile' }
					]
				},
				{ name: 'IfcDistributionElement' },
				{ name: 'IfcFurnishingElement' },
				{ name: 'IfcOpeningElement' }
			]
		},
		{
			name: 'IfcSpatialStructureElement',
			children: [
				{ name: 'IfcSite' },
				{ name: 'IfcBuilding' },
				{ name: 'IfcBuildingStorey' },
				{ name: 'IfcSpace' }
			]
		}
	]
};

export interface FlatEntry {
	name: string;
	depth: number;
}

/** Flatten the tree into a list with indent depth, suitable for <select> dropdowns. */
export function flattenTree(node: IfcSchemaNode = IFC_PRODUCT_TREE, depth = 0): FlatEntry[] {
	const result: FlatEntry[] = [{ name: node.name, depth }];
	for (const child of node.children ?? []) {
		result.push(...flattenTree(child, depth + 1));
	}
	return result;
}

/**
 * Return a Set containing `className` and all its descendant class names.
 * Selecting IfcBuildingElement will match IfcWall, IfcSlab, etc.
 */
export function getDescendantClasses(className: string): Set<string> {
	const result = new Set<string>();

	function collect(node: IfcSchemaNode): boolean {
		if (node.name === className) {
			addAll(node, result);
			return true;
		}
		for (const child of node.children ?? []) {
			if (collect(child)) return true;
		}
		return false;
	}

	collect(IFC_PRODUCT_TREE);
	if (result.size === 0) {
		result.add(className);
	}
	return result;
}

export const IFC_RELATION_TYPES = [
	'IfcRelAggregates',
	'IfcRelContainedInSpatialStructure',
	'IfcRelConnectsElements',
	'IfcRelVoidsElement',
	'IfcRelFillsElement',
	'IfcRelAssociatesMaterial',
	'IfcRelDefinesByType'
] as const;

export type IfcRelationType = (typeof IFC_RELATION_TYPES)[number];

function addAll(node: IfcSchemaNode, set: Set<string>): void {
	set.add(node.name);
	for (const child of node.children ?? []) {
		addAll(child, set);
	}
}
