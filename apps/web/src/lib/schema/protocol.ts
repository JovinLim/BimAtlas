export const SCHEMA_CHANNEL = 'bimatlas-schema';

export type SchemaMessage =
	| { type: 'context'; branchId: string | null; projectId: string | null; revision: number | null }
	| { type: 'request-context' }
	| { type: 'schema:select'; globalId: string }
	| { type: 'schema:results'; schemaGlobalId: string };
