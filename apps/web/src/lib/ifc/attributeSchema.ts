/**
 * IFC attribute schema utilities.
 * Loads the IFC 4.3 schema and resolves whether attributes are required or optional
 * for a given entity (including inherited attributes).
 */

interface SchemaAttribute {
  name: string;
  required: boolean;
  type: string;
}

interface SchemaEntity {
  parent: string | null;
  attributes: SchemaAttribute[];
}

interface SchemaData {
  entities: Record<string, SchemaEntity>;
}

let schemaCache: Map<string, boolean> | null = null;

async function loadSchema(): Promise<SchemaData> {
  const res = await fetch('/schema/ifc_4_3_schema.json');
  if (!res.ok) throw new Error(`Failed to load IFC schema: ${res.status}`);
  return res.json();
}

/**
 * Build a map of (entityName, attributeName) -> required.
 * Walks the inheritance chain from entity up to root, collecting attributes in order.
 */
function buildAttributeMap(entities: Record<string, SchemaEntity>): Map<string, boolean> {
  const map = new Map<string, boolean>();

  function getParent(name: string): string | null {
    const ent = entities[name];
    return ent?.parent ?? null;
  }

  function getAttributeChain(name: string): SchemaAttribute[] {
    const chain: string[] = [];
    let current: string | null = name;
    while (current) {
      chain.push(current);
      current = getParent(current);
    }
    // Walk root -> leaf
    const attrs: SchemaAttribute[] = [];
    for (let i = chain.length - 1; i >= 0; i--) {
      const ent = entities[chain[i]];
      if (ent?.attributes) attrs.push(...ent.attributes);
    }
    return attrs;
  }

  for (const entityName of Object.keys(entities)) {
    const attrs = getAttributeChain(entityName);
    for (const attr of attrs) {
      const key = `${entityName}::${attr.name}`;
      map.set(key, attr.required);
    }
  }
  return map;
}

/**
 * Return whether the given attribute is required for the given IFC entity.
 * Returns undefined if the entity or attribute is not found in the schema.
 */
export async function isAttributeRequired(
  ifcClass: string,
  attributeName: string
): Promise<boolean | undefined> {
  if (!schemaCache) {
    const data = await loadSchema();
    schemaCache = buildAttributeMap(data.entities);
  }
  const key = `${ifcClass}::${attributeName}`;
  const required = schemaCache.get(key);
  return required;
}

/**
 * Synchronous lookup. Requires schema to be preloaded via ensureSchemaLoaded().
 */
export function isAttributeRequiredSync(
  ifcClass: string,
  attributeName: string
): boolean | undefined {
  if (!schemaCache) return undefined;
  const key = `${ifcClass}::${attributeName}`;
  return schemaCache.get(key);
}

/**
 * Preload the schema. Call early (e.g. when opening the Attribute panel) to avoid
 * delay on first attribute lookup.
 */
export async function ensureSchemaLoaded(): Promise<void> {
  if (schemaCache) return;
  const data = await loadSchema();
  schemaCache = buildAttributeMap(data.entities);
}
