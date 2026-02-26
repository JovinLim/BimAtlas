/**
 * Decodes Base64 blobs from GraphQL into THREE.BufferGeometry.
 * Binary format: vertices/normals are Float32Array, faces are Uint32Array.
 */
import * as THREE from 'three';

export interface RawMeshData {
	vertices: string; // Base64-encoded Float32Array (x,y,z triples)
	normals: string | null; // Base64-encoded Float32Array (nx,ny,nz triples) -- may be null
	faces: string; // Base64-encoded Uint32Array (triangle index triples)
}

/**
 * Create a THREE.BufferGeometry from Base64-encoded mesh data.
 * Computes bounding sphere and bounding box for efficient culling.
 */
export function createBufferGeometry(raw: RawMeshData): THREE.BufferGeometry {
	const vertBuf = new Float32Array(base64ToArrayBuffer(raw.vertices));
	const idxBuf = new Uint32Array(base64ToArrayBuffer(raw.faces));

	const geo = new THREE.BufferGeometry();
	geo.setAttribute('position', new THREE.BufferAttribute(vertBuf, 3));
	geo.setIndex(new THREE.BufferAttribute(idxBuf, 1));

	if (raw.normals) {
		const normBuf = new Float32Array(base64ToArrayBuffer(raw.normals));
		geo.setAttribute('normal', new THREE.BufferAttribute(normBuf, 3));
	} else {
		geo.computeVertexNormals();
	}

	geo.computeBoundingSphere();
	geo.computeBoundingBox();
	return geo;
}

/**
 * Batch-load multiple mesh records into a Map of globalId -> BufferGeometry.
 * Useful for populating the entire scene from a GraphQL products query.
 */
export function createBufferGeometries(
	records: { globalId: string; mesh: RawMeshData }[]
): Map<string, THREE.BufferGeometry> {
	const result = new Map<string, THREE.BufferGeometry>();
	for (const { globalId, mesh } of records) {
		result.set(globalId, createBufferGeometry(mesh));
	}
	return result;
}

/** Decode a Base64 string into an ArrayBuffer. */
function base64ToArrayBuffer(b64: string): ArrayBuffer {
	const bin = atob(b64);
	const buf = new Uint8Array(bin.length);
	for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
	return buf.buffer;
}
