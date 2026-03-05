/**
 * Manages the Three.js lifecycle, mesh registry, raycasting, and highlight state.
 * Provides OrbitControls for camera navigation and click-to-select via raycasting.
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export type ElementClickCallback = (globalId: string | null) => void;

export class SceneManager {
	private scene: THREE.Scene;
	private camera: THREE.PerspectiveCamera;
	private renderer: THREE.WebGLRenderer;
	private controls: OrbitControls;
	private meshMap: Map<string, THREE.Mesh> = new Map();
	private idByMesh: Map<THREE.Mesh, string> = new Map();
	private highlightMaterial: THREE.MeshStandardMaterial;
	private defaultMaterial: THREE.MeshStandardMaterial;
	private ghostMaterial: THREE.MeshStandardMaterial;
	private colorMaterialCache: Map<number, THREE.MeshStandardMaterial> = new Map();
	private animationId: number | null = null;
	private raycaster: THREE.Raycaster;
	private pointer: THREE.Vector2;
	private onElementClick: ElementClickCallback | null = null;
	private canvas: HTMLCanvasElement;
	private currentHighlight: string | null = null;
	private mouseDownPos: { x: number; y: number } | null = null;
	private hasDragged: boolean = false;

	constructor(canvas: HTMLCanvasElement) {
		this.canvas = canvas;
		this.scene = new THREE.Scene();
		this.scene.background = new THREE.Color(0xf7f7f2);

		const w = canvas.clientWidth || 1;
		const h = canvas.clientHeight || 1;

		this.camera = new THREE.PerspectiveCamera(60, w / h, 0.1, 10000);
		// Set Z as the up axis
		this.camera.up.set(0, 0, 1);
		this.camera.position.set(20, 20, 20);
		this.camera.lookAt(0, 0, 0);

		this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
		this.renderer.setSize(w, h);
		this.renderer.setPixelRatio(window.devicePixelRatio);
		this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
		this.renderer.toneMappingExposure = 1.0;

		// OrbitControls for camera navigation
		this.controls = new OrbitControls(this.camera, canvas);
		this.controls.enableDamping = true;
		this.controls.dampingFactor = 0.1;
		this.controls.minDistance = 1;
		this.controls.maxDistance = 5000;
		// Set Z as the up axis for controls
		this.controls.target.set(0, 0, 0);

		// Lighting setup (adjusted for Z-up)
		const ambient = new THREE.AmbientLight(0xffffff, 0.6);
		this.scene.add(ambient);

		const directional = new THREE.DirectionalLight(0xffffff, 0.8);
		directional.position.set(50, 50, 50);
		this.scene.add(directional);

		const fillLight = new THREE.DirectionalLight(0xffffff, 0.3);
		fillLight.position.set(-30, -30, 10);
		this.scene.add(fillLight);

		const hemi = new THREE.HemisphereLight(0xddeeff, 0x0f0e0d, 0.4);
		hemi.position.set(0, 0, 1); // Up direction for Z-up
		this.scene.add(hemi);

		// Materials
		this.defaultMaterial = new THREE.MeshStandardMaterial({
			color: 0x8899aa,
			flatShading: true,
			metalness: 0.1,
			roughness: 0.8
		});
		this.highlightMaterial = new THREE.MeshStandardMaterial({
			color: 0x334155,
			flatShading: true,
			emissive: 0x1e293b,
			metalness: 0.1,
			roughness: 0.6
		});
		this.ghostMaterial = new THREE.MeshStandardMaterial({
			color: 0xd4d4ce,
			flatShading: true,
			metalness: 0.05,
			roughness: 0.9,
			transparent: true,
			opacity: 0.25,
			depthWrite: false
		});

		// Raycasting for click-to-select
		this.raycaster = new THREE.Raycaster();
		this.pointer = new THREE.Vector2();
		canvas.addEventListener('mousedown', this.handleMouseDown);
		canvas.addEventListener('mousemove', this.handleMouseMove);
		canvas.addEventListener('mouseup', this.handleMouseUp);
		canvas.addEventListener('click', this.handleClick);

		// Ground grid (rotated to XZ plane for Z-up)
		const grid = new THREE.GridHelper(100, 50, 0xd4d4ce, 0xe5e5e0);
		grid.rotation.x = Math.PI / 2; // Rotate 90 degrees to lay on XZ plane
		this.scene.add(grid);

		this.animate();
	}

	/** Register a callback invoked when the user clicks on an element (or background). */
	setClickCallback(cb: ElementClickCallback): void {
		this.onElementClick = cb;
	}

	/** Add a mesh to the scene, keyed by IFC GlobalId. Skips if already present. */
	addElement(globalId: string, geometry: THREE.BufferGeometry): void {
		if (this.meshMap.has(globalId)) return;
		const mesh = new THREE.Mesh(geometry, this.defaultMaterial);
		mesh.userData.globalId = globalId;
		this.meshMap.set(globalId, mesh);
		this.idByMesh.set(mesh, globalId);
		this.scene.add(mesh);
	}

	/** Remove a single element from the scene and dispose its geometry. */
	removeElement(globalId: string): void {
		const mesh = this.meshMap.get(globalId);
		if (mesh) {
			this.scene.remove(mesh);
			mesh.geometry.dispose();
			this.meshMap.delete(globalId);
			this.idByMesh.delete(mesh);
			if (this.currentHighlight === globalId) {
				this.currentHighlight = null;
			}
		}
	}

	/** Remove all elements from the scene and dispose geometries. */
	clearAll(): void {
		for (const mesh of this.meshMap.values()) {
			this.scene.remove(mesh);
			mesh.geometry.dispose();
		}
		this.meshMap.clear();
		this.idByMesh.clear();
		this.currentHighlight = null;
	}

	/** Highlight a single element by globalId. Pass null to clear highlight. */
	highlight(globalId: string | null): void {
		// Reset previous highlight
		if (this.currentHighlight) {
			const prev = this.meshMap.get(this.currentHighlight);
			if (prev) prev.material = this.defaultMaterial;
		}
		// Apply new highlight
		this.currentHighlight = globalId;
		if (globalId) {
			const mesh = this.meshMap.get(globalId);
			if (mesh) mesh.material = this.highlightMaterial;
		}
	}

	/**
	 * Apply a subgraph visibility filter.
	 *
	 * - selectedId/subgraphIds both null → reset all meshes to visible + default material.
	 * - Otherwise: selected mesh gets highlight, subgraph meshes get default + visible,
	 *   everything else is ghosted (dim, semi-transparent) but still visible.
	 */
	applySubgraphFilter(selectedId: string | null, subgraphIds: Set<string> | null): void {
		if (selectedId === null || subgraphIds === null) {
			for (const [id, mesh] of this.meshMap) {
				mesh.visible = true;
				mesh.material = this.defaultMaterial;
			}
			this.currentHighlight = null;
			return;
		}

		for (const [id, mesh] of this.meshMap) {
			if (id === selectedId) {
				mesh.material = this.highlightMaterial;
				mesh.visible = true;
			} else if (subgraphIds.has(id)) {
				mesh.material = this.defaultMaterial;
				mesh.visible = true;
			} else {
				mesh.material = this.ghostMaterial;
				mesh.visible = true;
			}
		}
		this.currentHighlight = selectedId;
	}

	/**
	 * Apply a search visibility filter.
	 *
	 * - null → reset all meshes to visible + default material.
	 * - Set → meshes in the set get default material; all others are ghosted but still visible.
	 */
	applySearchFilter(matchingIds: Set<string> | null): void {
		if (matchingIds === null) {
			for (const [, mesh] of this.meshMap) {
				mesh.visible = true;
				mesh.material = this.defaultMaterial;
			}
			this.currentHighlight = null;
			return;
		}

		for (const [id, mesh] of this.meshMap) {
			if (matchingIds.has(id)) {
				mesh.material = this.defaultMaterial;
				mesh.visible = true;
			} else {
				mesh.material = this.ghostMaterial;
				mesh.visible = true;
			}
		}
		this.currentHighlight = null;
	}

	/**
	 * Apply per-entity coloring based on filter set matches.
	 *
	 * - null colorMap → reset all meshes to default material.
	 * - Map → meshes with a color get that material; others are ghosted.
	 */
	applyFilterSetColors(colorMap: Map<string, number> | null): void {
		if (colorMap === null) {
			for (const [, mesh] of this.meshMap) {
				mesh.visible = true;
				mesh.material = this.defaultMaterial;
			}
			this.currentHighlight = null;
			return;
		}

		for (const [id, mesh] of this.meshMap) {
			const colorHex = colorMap.get(id);
			if (colorHex !== undefined) {
				mesh.material = this.getOrCreateColorMaterial(colorHex);
				mesh.visible = true;
			} else {
				mesh.material = this.ghostMaterial;
				mesh.visible = true;
			}
		}
		this.currentHighlight = null;
	}

	private getOrCreateColorMaterial(colorHex: number): THREE.MeshStandardMaterial {
		let mat = this.colorMaterialCache.get(colorHex);
		if (!mat) {
			mat = new THREE.MeshStandardMaterial({
				color: colorHex,
				flatShading: true,
				metalness: 0.1,
				roughness: 0.8
			});
			this.colorMaterialCache.set(colorHex, mat);
		}
		return mat;
	}

	/** Auto-fit the camera to encompass all loaded elements. */
	fitToContent(): void {
		if (this.meshMap.size === 0) return;

		const box = new THREE.Box3();
		for (const mesh of this.meshMap.values()) {
			box.expandByObject(mesh);
		}

		const center = box.getCenter(new THREE.Vector3());
		const size = box.getSize(new THREE.Vector3());
		const maxDim = Math.max(size.x, size.y, size.z);
		const fov = this.camera.fov * (Math.PI / 180);
		const dist = maxDim / (2 * Math.tan(fov / 2)) * 1.5; // 1.5x padding

		// Position camera for Z-up orientation
		this.camera.position.set(center.x + dist * 0.7, center.y + dist * 0.7, center.z + dist * 0.5);
		this.camera.lookAt(center);
		this.controls.target.copy(center);
		this.controls.update();
	}

	/** Check whether an element with the given globalId is already loaded. */
	hasElement(globalId: string): boolean {
		return this.meshMap.has(globalId);
	}

	/** Number of elements currently in the scene. */
	get elementCount(): number {
		return this.meshMap.size;
	}

	/** Update renderer and camera for a new viewport size. */
	resize(w: number, h: number): void {
		if (w === 0 || h === 0) return;
		this.camera.aspect = w / h;
		this.camera.updateProjectionMatrix();
		this.renderer.setSize(w, h);
	}

	/** Dispose all resources -- call when unmounting. */
	dispose(): void {
		if (this.animationId !== null) {
			cancelAnimationFrame(this.animationId);
			this.animationId = null;
		}
		this.canvas.removeEventListener('mousedown', this.handleMouseDown);
		this.canvas.removeEventListener('mousemove', this.handleMouseMove);
		this.canvas.removeEventListener('mouseup', this.handleMouseUp);
		this.canvas.removeEventListener('click', this.handleClick);
		this.controls.dispose();
		this.renderer.dispose();
		this.defaultMaterial.dispose();
		this.highlightMaterial.dispose();
		this.ghostMaterial.dispose();
		for (const mat of this.colorMaterialCache.values()) {
			mat.dispose();
		}
		this.colorMaterialCache.clear();
		for (const mesh of this.meshMap.values()) {
			mesh.geometry.dispose();
		}
		this.meshMap.clear();
		this.idByMesh.clear();
	}

	// ---- Private ----

	private handleMouseDown = (event: MouseEvent): void => {
		const rect = this.canvas.getBoundingClientRect();
		this.mouseDownPos = {
			x: event.clientX - rect.left,
			y: event.clientY - rect.top
		};
		this.hasDragged = false;
	};

	private handleMouseMove = (event: MouseEvent): void => {
		if (this.mouseDownPos === null) return;
		
		const rect = this.canvas.getBoundingClientRect();
		const dx = Math.abs((event.clientX - rect.left) - this.mouseDownPos.x);
		const dy = Math.abs((event.clientY - rect.top) - this.mouseDownPos.y);
		
		// If mouse moved more than 5 pixels, consider it a drag
		if (dx > 5 || dy > 5) {
			this.hasDragged = true;
		}
	};

	private handleMouseUp = (): void => {
		this.mouseDownPos = null;
	};

	private handleClick = (event: MouseEvent): void => {
		// Don't trigger selection if the user was dragging to orbit
		if (this.hasDragged) {
			this.hasDragged = false;
			return;
		}

		const rect = this.canvas.getBoundingClientRect();
		this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
		this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

		this.raycaster.setFromCamera(this.pointer, this.camera);
		const meshes = Array.from(this.meshMap.values()).filter(
			(m) => m.material !== this.ghostMaterial
		);
		const intersects = this.raycaster.intersectObjects(meshes, false);

		if (intersects.length > 0) {
			const hit = intersects[0].object as THREE.Mesh;
			const globalId = this.idByMesh.get(hit) ?? null;
			this.onElementClick?.(globalId);
		} else {
			this.onElementClick?.(null);
		}
	};

	private animate = (): void => {
		this.animationId = requestAnimationFrame(this.animate);
		this.controls.update();
		this.renderer.render(this.scene, this.camera);
	};
}
