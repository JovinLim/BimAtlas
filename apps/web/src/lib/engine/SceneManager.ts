/**
 * Manages the Three.js lifecycle, mesh registry, raycasting, and highlight state.
 * Provides OrbitControls for camera navigation and click-to-select via raycasting.
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export type ElementClickCallback = (globalId: string | null) => void;
export type ElementCountListener = (count: number) => void;

export class SceneManager {
	private scene: THREE.Scene;
	private camera: THREE.PerspectiveCamera;
	private orthoCamera: THREE.OrthographicCamera;
	private isOrthographic = false;
	private renderer: THREE.WebGLRenderer;
	private controls: OrbitControls;
	private overlayScene: THREE.Scene;
	private overlayCamera: THREE.PerspectiveCamera;
	private gumballRoot: THREE.Group;
	private gumballRaycaster: THREE.Raycaster;
	private gumballZones: Array<{
		id: string;
		mesh: THREE.Mesh;
		direction: THREE.Vector3;
		baseColor: number;
		hoverColor: number;
	}> = [];
	private gumballZoneByMesh: Map<THREE.Mesh, string> = new Map();
	private gumballDirectionMap: Record<string, THREE.Vector3> = {};
	private gumballHoveredZoneId: string | null = null;
	private gumballRect = {
		left: 0,
		top: 0,
		size: 120,
		margin: 16,
		projectionToggleHeight: 36
	};
	private gumballMaterialSet: Set<THREE.Material> = new Set();
	private gumballGeometrySet: Set<THREE.BufferGeometry> = new Set();
	private orbitAnimation: {
		startTimeMs: number;
		durationMs: number;
		fromPosition: THREE.Vector3;
		toPosition: THREE.Vector3;
		target: THREE.Vector3;
	} | null = null;
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
	private elementCountListener: ElementCountListener | null = null;
	private canvas: HTMLCanvasElement;
	private currentHighlight: string | null = null;
	private mouseDownPos: { x: number; y: number } | null = null;
	private hasDragged: boolean = false;
	private ghostedGlobalIds: Set<string> = new Set();

	constructor(canvas: HTMLCanvasElement) {
		this.canvas = canvas;
		this.scene = new THREE.Scene();
		this.scene.background = new THREE.Color(0xf7f7f2);

		const w = canvas.clientWidth || 1;
		const h = canvas.clientHeight || 1;

		this.camera = new THREE.PerspectiveCamera(60, w / h, 0.1, 10000);
		this.camera.up.set(0, 0, 1);
		this.camera.position.set(20, 20, 20);
		this.camera.lookAt(0, 0, 0);

		this.orthoCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10000);
		this.orthoCamera.up.set(0, 0, 1);
		this.orthoCamera.position.copy(this.camera.position);
		this.orthoCamera.lookAt(0, 0, 0);

		this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
		this.renderer.setSize(w, h);
		this.renderer.setPixelRatio(window.devicePixelRatio);
		this.renderer.autoClear = false;
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
		this.gumballRaycaster = new THREE.Raycaster();

		// Overlay scene/camera for the orientation gumball.
		this.overlayScene = new THREE.Scene();
		this.overlayCamera = new THREE.PerspectiveCamera(32, 1, 0.1, 20);
		this.overlayCamera.position.set(0, 0, 6);
		this.overlayCamera.lookAt(0, 0, 0);
		this.gumballRoot = new THREE.Group();
		this.overlayScene.add(this.gumballRoot);
		this.initializeGumball();
		this.updateGumballRect(w, h);

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

	/** Optional listener that is notified whenever the element count changes. */
	setElementCountListener(listener: ElementCountListener | null): void {
		this.elementCountListener = listener;
		if (listener) {
			listener(this.meshMap.size);
		}
	}

	/** Add a mesh to the scene, keyed by IFC GlobalId. Skips if already present. */
	addElement(globalId: string, geometry: THREE.BufferGeometry): void {
		if (this.meshMap.has(globalId)) return;
		const mesh = new THREE.Mesh(geometry, this.defaultMaterial);
		mesh.userData.globalId = globalId;
		this.meshMap.set(globalId, mesh);
		this.idByMesh.set(mesh, globalId);
		this.scene.add(mesh);
		if (this.elementCountListener) {
			this.elementCountListener(this.meshMap.size);
		}
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
			if (this.elementCountListener) {
				this.elementCountListener(this.meshMap.size);
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
		if (this.elementCountListener) {
			this.elementCountListener(0);
		}
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
	 * Set global IDs that should render with ghost material (temporary override).
	 * Cleared on view load. Does not persist.
	 */
	setGhostedGlobalIds(ids: Set<string>): void {
		this.ghostedGlobalIds = ids;
	}

	/**
	 * Apply per-entity coloring based on filter set matches.
	 *
	 * - null colorMap → reset all meshes to default material.
	 * - Map → meshes with a color get that material; others are ghosted.
	 * - Meshes whose globalId is in ghostedGlobalIds always get ghost material.
	 */
	applyFilterSetColors(colorMap: Map<string, number> | null): void {
		if (colorMap === null) {
			for (const [id, mesh] of this.meshMap) {
				mesh.visible = true;
				mesh.material = this.ghostedGlobalIds.has(id) ? this.ghostMaterial : this.defaultMaterial;
			}
			this.currentHighlight = null;
			return;
		}

		for (const [id, mesh] of this.meshMap) {
			if (this.ghostedGlobalIds.has(id)) {
				mesh.material = this.ghostMaterial;
				mesh.visible = true;
			} else {
				const colorHex = colorMap.get(id);
				if (colorHex !== undefined) {
					mesh.material = this.getOrCreateColorMaterial(colorHex);
					mesh.visible = true;
				} else {
					mesh.material = this.ghostMaterial;
					mesh.visible = true;
				}
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

	/**
	 * Apply BCF-compliant camera state (position, direction, up_vector).
	 * Supports perspective_camera and orthogonal_camera. For orthogonal, view_to_world_scale
	 * is applied to set the ortho zoom so the visible area matches the saved view.
	 * Uses scene bounding box center as orbit target so zoom/orbit behave naturally.
	 * Clipping planes are not yet implemented.
	 */
	applyBcfCamera(bcf: {
		perspective_camera?: { position: number[]; direction: number[]; up_vector: number[]; field_of_view?: number };
		orthogonal_camera?: { position: number[]; direction: number[]; up_vector: number[]; view_to_world_scale?: number };
	}): void {
		const cam = bcf.perspective_camera ?? bcf.orthogonal_camera;
		if (!cam?.position || !cam.direction || cam.position.length < 3 || cam.direction.length < 3) return;
		this.camera.position.set(cam.position[0], cam.position[1], cam.position[2]);
		this.orthoCamera.position.copy(this.camera.position);
		const dir = new THREE.Vector3(cam.direction[0], cam.direction[1], cam.direction[2]).normalize();
		if (cam.up_vector && cam.up_vector.length >= 3) {
			this.camera.up.set(cam.up_vector[0], cam.up_vector[1], cam.up_vector[2]);
			this.orthoCamera.up.copy(this.camera.up);
		}
		if (bcf.perspective_camera?.field_of_view != null) {
			this.camera.fov = bcf.perspective_camera.field_of_view;
			this.camera.updateProjectionMatrix();
		}

		const target = this.getSceneCenter();
		const targetDist = this.camera.position.distanceTo(target) || 1;
		this.controls.target.copy(target);

		const oc = bcf.orthogonal_camera;
		if (oc?.view_to_world_scale != null && oc.view_to_world_scale > 0) {
			const fovRad = (this.camera.fov * Math.PI) / 180;
			const halfHeight = targetDist * Math.tan(fovRad / 2);
			this.orthoCamera.zoom = (2 * halfHeight) / oc.view_to_world_scale;
		}
		this.updateOrthographicFrustum();
		this.controls.update();
	}

	private getSceneCenter(): THREE.Vector3 {
		if (this.meshMap.size === 0) return new THREE.Vector3(0, 0, 0);
		const box = new THREE.Box3();
		for (const mesh of this.meshMap.values()) box.expandByObject(mesh);
		return box.getCenter(new THREE.Vector3());
	}

	/**
	 * Get current camera state in BCF-compliant format for saving views.
	 * Returns perspective_camera or orthogonal_camera depending on projection mode.
	 */
	getBcfCameraState(): {
		perspective_camera?: { position: [number, number, number]; direction: [number, number, number]; up_vector: [number, number, number]; field_of_view?: number };
		orthogonal_camera?: { position: [number, number, number]; direction: [number, number, number]; up_vector: [number, number, number]; view_to_world_scale: number };
	} {
		const cam = this.isOrthographic ? this.orthoCamera : this.camera;
		const pos = cam.position;
		const target = this.controls.target;
		const dir = target.clone().sub(pos).normalize();
		const up = cam.up;

		const position: [number, number, number] = [pos.x, pos.y, pos.z];
		const direction: [number, number, number] = [dir.x, dir.y, dir.z];
		const up_vector: [number, number, number] = [up.x, up.y, up.z];

		if (this.isOrthographic) {
			const dist = pos.distanceTo(target);
			const fovRad = (this.camera.fov * Math.PI) / 180;
			const halfHeight = dist * Math.tan(fovRad / 2);
			const viewToWorldScale = (2 * halfHeight) / this.orthoCamera.zoom;
			return {
				orthogonal_camera: {
					position,
					direction,
					up_vector,
					view_to_world_scale: viewToWorldScale,
				},
			};
		}
		return {
			perspective_camera: {
				position,
				direction,
				up_vector,
				field_of_view: this.camera.fov,
			},
		};
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
		const pos = new THREE.Vector3(
			center.x + dist * 0.7,
			center.y + dist * 0.7,
			center.z + dist * 0.5
		);
		this.camera.position.copy(pos);
		this.camera.lookAt(center);
		this.orthoCamera.position.copy(pos);
		this.orthoCamera.lookAt(center);
		this.controls.target.copy(center);
		this.updateOrthographicFrustum();
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
		this.updateOrthographicFrustum();
		this.renderer.setSize(w, h);
		this.updateGumballRect(w, h);
	}

	/** Switch between perspective and isometric (orthographic) projection. */
	setProjectionMode(isometric: boolean): void {
		if (this.isOrthographic === isometric) return;
		const target = this.controls.target.clone();
		if (isometric) {
			const pos = this.camera.position.clone();
			this.orthoCamera.position.copy(pos);
			this.orthoCamera.up.copy(this.camera.up);
			this.orthoCamera.lookAt(target);
			this.orthoCamera.zoom = 1;
			this.updateOrthographicFrustum();
			this.controls.object = this.orthoCamera;
		} else {
			const pos = this.orthoCamera.position.clone();
			const zoom = this.orthoCamera.zoom;
			this.camera.position.copy(pos);
			this.camera.up.copy(this.orthoCamera.up);
			if (zoom !== 1) {
				const dir = pos.clone().sub(target).normalize();
				const dist = pos.distanceTo(target);
				this.camera.position.copy(target).add(dir.multiplyScalar(dist / zoom));
			}
			this.controls.object = this.camera;
		}
		this.isOrthographic = isometric;
		this.controls.target.copy(target);
		this.controls.update();
	}

	/** Whether the camera is in isometric (orthographic) mode. */
	get projectionIsometric(): boolean {
		return this.isOrthographic;
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
		for (const material of this.gumballMaterialSet) {
			material.dispose();
		}
		for (const geometry of this.gumballGeometrySet) {
			geometry.dispose();
		}
		this.meshMap.clear();
		this.idByMesh.clear();
		this.gumballZones = [];
		this.gumballZoneByMesh.clear();
		this.gumballMaterialSet.clear();
		this.gumballGeometrySet.clear();
	}

	// ---- Private ----

	private handleMouseDown = (event: MouseEvent): void => {
		const gumballHit = this.hitTestGumball(event.clientX, event.clientY) !== null;
		if (gumballHit) {
			this.controls.enabled = false;
		}
		const rect = this.canvas.getBoundingClientRect();
		this.mouseDownPos = {
			x: event.clientX - rect.left,
			y: event.clientY - rect.top
		};
		this.hasDragged = false;
	};

	private handleMouseMove = (event: MouseEvent): void => {
		this.updateGumballHover(event.clientX, event.clientY);
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
		if (this.orbitAnimation === null) {
			this.controls.enabled = true;
		}
	};

	private handleClick = (event: MouseEvent): void => {
		const hitZone = this.hitTestGumball(event.clientX, event.clientY);
		if (hitZone) {
			this.startOrbitToDirection(hitZone.direction);
			this.hasDragged = false;
			return;
		}

		// Don't trigger selection if the user was dragging to orbit
		if (this.hasDragged) {
			this.hasDragged = false;
			return;
		}

		const rect = this.canvas.getBoundingClientRect();
		this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
		this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

		this.raycaster.setFromCamera(this.pointer, this.getActiveCamera());
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
		if (this.orbitAnimation) {
			this.updateOrbitAnimation();
		} else {
			this.controls.update();
		}
		this.syncGumballRotation();
		this.renderer.clear();
		this.renderer.render(this.scene, this.getActiveCamera());
		this.renderer.clearDepth();
		this.renderer.setViewport(
			this.gumballRect.left,
			this.canvas.clientHeight - this.gumballRect.top - this.gumballRect.size,
			this.gumballRect.size,
			this.gumballRect.size
		);
		this.renderer.setScissor(
			this.gumballRect.left,
			this.canvas.clientHeight - this.gumballRect.top - this.gumballRect.size,
			this.gumballRect.size,
			this.gumballRect.size
		);
		this.renderer.setScissorTest(true);
		this.renderer.render(this.overlayScene, this.overlayCamera);
		this.renderer.setScissorTest(false);
		this.renderer.setViewport(0, 0, this.canvas.clientWidth, this.canvas.clientHeight);
	};

	private updateGumballRect(width: number, _height: number): void {
		const maxSize = 140;
		const minSize = 96;
		const preferred = Math.round(width * 0.14);
		this.gumballRect.size = Math.max(minSize, Math.min(maxSize, preferred));
		this.gumballRect.left = width - this.gumballRect.size - this.gumballRect.margin;
		this.gumballRect.top = this.gumballRect.margin + this.gumballRect.projectionToggleHeight;
	}

	private getActiveCamera(): THREE.PerspectiveCamera | THREE.OrthographicCamera {
		return this.isOrthographic ? this.orthoCamera : this.camera;
	}

	private updateOrthographicFrustum(): void {
		const target = this.controls.target;
		const dist = this.orthoCamera.position.distanceTo(target);
		const fovRad = (this.camera.fov * Math.PI) / 180;
		const halfHeight = dist * Math.tan(fovRad / 2);
		const halfWidth = halfHeight * this.camera.aspect;
		this.orthoCamera.left = -halfWidth;
		this.orthoCamera.right = halfWidth;
		this.orthoCamera.top = halfHeight;
		this.orthoCamera.bottom = -halfHeight;
		this.orthoCamera.near = 0.1;
		this.orthoCamera.far = 10000;
		this.orthoCamera.updateProjectionMatrix();
	}

	private initializeGumball(): void {
		const faceColors = {
			top: 0x5da8ff,
			bottom: 0x4b5563,
			front: 0x34d399,
			back: 0xf59e0b,
			left: 0xf472b6,
			right: 0xf87171
		};
		const edgeColor = 0x64748b;
		const cornerColor = 0x475569;

		// Exact chamfered cube math
		const R = 1.0; // Radius to main faces
		const A = 0.64; // Half-width of the flat square face (0 < A < R)

		const faceSize = 2 * A;
		const faceOffset = R;

		const edgeLong = 2 * A;
		const edgeShort = (R - A) * Math.SQRT2; // Chamfer width
		const edgeOffset = (R + A) / Math.SQRT2;

		const cornerSide = (R - A) * Math.SQRT2;
		const cornerOffset = (R + 2 * A) / Math.sqrt(3);

		const backgroundGeometry = new THREE.CircleGeometry(1.6, 48);
		this.gumballGeometrySet.add(backgroundGeometry);
		const backgroundMaterial = new THREE.MeshBasicMaterial({
			color: 0x0f172a,
			transparent: true,
			opacity: 0.2,
			depthWrite: false
		});
		this.gumballMaterialSet.add(backgroundMaterial);
		const background = new THREE.Mesh(backgroundGeometry, backgroundMaterial);
		background.position.set(0, 0, -0.6);
		this.gumballRoot.add(background);

		const faceDefs: Array<{ id: string; dir: [number, number, number]; color: number; label: string }> = [
			{ id: 'top', dir: [0, 0, 1], color: faceColors.top, label: 'TOP' },
			{ id: 'bottom', dir: [0, 0, -1], color: faceColors.bottom, label: 'BOTTOM' },
			{ id: 'front', dir: [0, 1, 0], color: faceColors.front, label: 'FRONT' },
			{ id: 'back', dir: [0, -1, 0], color: faceColors.back, label: 'BACK' },
			{ id: 'left', dir: [-1, 0, 0], color: faceColors.left, label: 'LEFT' },
			{ id: 'right', dir: [1, 0, 0], color: faceColors.right, label: 'RIGHT' }
		];
		for (const face of faceDefs) {
			const direction = new THREE.Vector3(face.dir[0], face.dir[1], face.dir[2]).normalize();
			this.addPlaneZone(face.id, direction, faceSize, faceSize, faceOffset, face.color);
			const labelSprite = this.createFaceLabel(face.label);
			labelSprite.position.copy(direction.clone().multiplyScalar(faceOffset + 0.02));
			this.gumballRoot.add(labelSprite);
		}

		const edgeDefs: Array<{ id: string; dir: [number, number, number] }> = [
			{ id: 'top-front', dir: [0, 1, 1] },
			{ id: 'top-back', dir: [0, -1, 1] },
			{ id: 'top-right', dir: [1, 0, 1] },
			{ id: 'top-left', dir: [-1, 0, 1] },
			{ id: 'bottom-front', dir: [0, 1, -1] },
			{ id: 'bottom-back', dir: [0, -1, -1] },
			{ id: 'bottom-right', dir: [1, 0, -1] },
			{ id: 'bottom-left', dir: [-1, 0, -1] },
			{ id: 'front-right', dir: [1, 1, 0] },
			{ id: 'front-left', dir: [-1, 1, 0] },
			{ id: 'back-right', dir: [1, -1, 0] },
			{ id: 'back-left', dir: [-1, -1, 0] }
		];
		for (const edge of edgeDefs) {
			const direction = new THREE.Vector3(edge.dir[0], edge.dir[1], edge.dir[2]).normalize();
			const axis = this.getEdgeAxis(edge.dir);
			// Pass chamfer width as 'width' (local X) and edge length as 'height' (local Y)
			// because we align local Y to the long axis of the edge.
			this.addPlaneZone(
				edge.id,
				direction,
				edgeShort,
				edgeLong,
				edgeOffset,
				edgeColor,
				axis
			);
		}

		const cornerDefs: Array<{ id: string; dir: [number, number, number] }> = [
			{ id: 'top-front-right', dir: [1, 1, 1] },
			{ id: 'top-front-left', dir: [-1, 1, 1] },
			{ id: 'top-back-right', dir: [1, -1, 1] },
			{ id: 'top-back-left', dir: [-1, -1, 1] },
			{ id: 'bottom-front-right', dir: [1, 1, -1] },
			{ id: 'bottom-front-left', dir: [-1, 1, -1] },
			{ id: 'bottom-back-right', dir: [1, -1, -1] },
			{ id: 'bottom-back-left', dir: [-1, -1, -1] }
		];
		for (const corner of cornerDefs) {
			const direction = new THREE.Vector3(corner.dir[0], corner.dir[1], corner.dir[2]).normalize();
			this.addTriangleZone(
				corner.id,
				direction,
				cornerSide,
				cornerOffset,
				cornerColor,
				new THREE.Vector3(0, 0, corner.dir[2])
			);
		}
	}

	private addPlaneZone(
		id: string,
		direction: THREE.Vector3,
		width: number,
		height: number,
		offset: number,
		baseColor: number,
		tangentAxis?: THREE.Vector3
	): void {
		const geometry = new THREE.PlaneGeometry(width, height);
		this.gumballGeometrySet.add(geometry);
		const material = new THREE.MeshBasicMaterial({
			color: baseColor,
			transparent: true,
			opacity: 0.95
		});
		this.gumballMaterialSet.add(material);
		const mesh = new THREE.Mesh(geometry, material);
		mesh.position.copy(direction.clone().multiplyScalar(offset));
		mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), direction);
		if (tangentAxis) {
			this.alignLocalYToTangent(mesh, direction, tangentAxis);
		}
		this.registerZone(id, mesh, direction, baseColor);
	}

	private addTriangleZone(
		id: string,
		direction: THREE.Vector3,
		sideLength: number,
		offset: number,
		baseColor: number,
		tangentAxis?: THREE.Vector3
	): void {
		const geometry = new THREE.BufferGeometry();
		const R = sideLength / Math.sqrt(3);
		const r = R * 0.5;
		const w = sideLength * 0.5;
		const vertices = new Float32Array([
			0, R, 0,
			-w, -r, 0,
			w, -r, 0
		]);
		geometry.setAttribute('position', new THREE.BufferAttribute(vertices, 3));
		geometry.setIndex([0, 1, 2]);
		geometry.computeVertexNormals();
		this.gumballGeometrySet.add(geometry);
		const material = new THREE.MeshBasicMaterial({
			color: baseColor,
			transparent: true,
			opacity: 0.95,
			side: THREE.DoubleSide
		});
		this.gumballMaterialSet.add(material);
		const mesh = new THREE.Mesh(geometry, material);
		mesh.position.copy(direction.clone().multiplyScalar(offset));
		mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), direction);
		if (tangentAxis) {
			this.alignLocalYToTangent(mesh, direction, tangentAxis);
		}
		this.registerZone(id, mesh, direction, baseColor);
	}

	private alignLocalYToTangent(
		mesh: THREE.Mesh,
		faceNormal: THREE.Vector3,
		tangentAxis: THREE.Vector3
	): void {
		const projectedTangent = tangentAxis
			.clone()
			.projectOnPlane(faceNormal)
			.normalize();
		if (projectedTangent.lengthSq() < 1e-6) return;
		const localY = new THREE.Vector3(0, 1, 0).applyQuaternion(mesh.quaternion);
		const angle = localY.angleTo(projectedTangent);
		const cross = new THREE.Vector3().crossVectors(localY, projectedTangent);
		const sign = cross.dot(faceNormal) < 0 ? -1 : 1;
		// Rotate around local Z (the face normal in local space)
		const localNormal = new THREE.Vector3(0, 0, 1);
		mesh.rotateOnAxis(localNormal, sign * angle);
	}

	private getEdgeAxis(direction: [number, number, number]): THREE.Vector3 {
		if (direction[0] === 0) return new THREE.Vector3(1, 0, 0);
		if (direction[1] === 0) return new THREE.Vector3(0, 1, 0);
		return new THREE.Vector3(0, 0, 1);
	}

	private registerZone(
		id: string,
		mesh: THREE.Mesh,
		direction: THREE.Vector3,
		baseColor: number
	): void {
		const hoverColor = this.adjustColor(baseColor, 0.2);
		this.gumballZones.push({
			id,
			mesh,
			direction: direction.clone().normalize(),
			baseColor,
			hoverColor
		});
		this.gumballDirectionMap[id] = direction.clone().normalize();
		this.gumballZoneByMesh.set(mesh, id);
		this.gumballRoot.add(mesh);
	}

	private createFaceLabel(text: string): THREE.Sprite {
		const canvas = document.createElement('canvas');
		canvas.width = 256;
		canvas.height = 128;
		const ctx = canvas.getContext('2d');
		if (ctx) {
			ctx.clearRect(0, 0, canvas.width, canvas.height);
			ctx.fillStyle = '#ffffff';
			ctx.font = 'bold 48px -apple-system, "Segoe UI", sans-serif';
			ctx.textAlign = 'center';
			ctx.textBaseline = 'middle';
			ctx.strokeStyle = 'rgba(0, 0, 0, 0.5)';
			ctx.lineWidth = 4;
			ctx.strokeText(text, canvas.width / 2, canvas.height / 2);
			ctx.fillText(text, canvas.width / 2, canvas.height / 2);
		}
		const texture = new THREE.CanvasTexture(canvas);
		const material = new THREE.SpriteMaterial({
			map: texture,
			transparent: true,
			depthTest: false,
			depthWrite: false
		});
		this.gumballMaterialSet.add(material);
		const sprite = new THREE.Sprite(material);
		sprite.scale.set(0.9, 0.45, 1);
		return sprite;
	}

	private adjustColor(hex: number, amount: number): number {
		const color = new THREE.Color(hex);
		color.lerp(new THREE.Color(0xffffff), amount);
		return color.getHex();
	}

	private syncGumballRotation(): void {
		this.gumballRoot.quaternion.copy(this.getActiveCamera().quaternion).invert();
	}

	private hitTestGumball(clientX: number, clientY: number): { id: string; direction: THREE.Vector3 } | null {
		const rect = this.canvas.getBoundingClientRect();
		const x = clientX - rect.left;
		const y = clientY - rect.top;
		const withinX = x >= this.gumballRect.left && x <= this.gumballRect.left + this.gumballRect.size;
		const withinY = y >= this.gumballRect.top && y <= this.gumballRect.top + this.gumballRect.size;
		if (!withinX || !withinY) return null;

		const localX = (x - this.gumballRect.left) / this.gumballRect.size;
		const localY = (y - this.gumballRect.top) / this.gumballRect.size;
		const ndc = new THREE.Vector2(localX * 2 - 1, -(localY * 2 - 1));
		this.gumballRaycaster.setFromCamera(ndc, this.overlayCamera);
		const intersects = this.gumballRaycaster.intersectObjects(
			this.gumballZones.map((zone) => zone.mesh),
			false
		);
		if (intersects.length === 0) return null;
		const mesh = intersects[0].object as THREE.Mesh;
		const id = this.gumballZoneByMesh.get(mesh);
		if (!id) return null;
		const direction = this.gumballDirectionMap[id];
		return direction ? { id, direction } : null;
	}

	private updateGumballHover(clientX: number, clientY: number): void {
		const hit = this.hitTestGumball(clientX, clientY);
		const nextId = hit?.id ?? null;
		if (nextId === this.gumballHoveredZoneId) {
			return;
		}

		this.gumballHoveredZoneId = nextId;
		for (const zone of this.gumballZones) {
			const material = zone.mesh.material as THREE.MeshBasicMaterial;
			const color = zone.id === nextId ? zone.hoverColor : zone.baseColor;
			material.color.setHex(color);
		}
		this.canvas.style.cursor = nextId ? 'pointer' : '';
	}

	private startOrbitToDirection(rawDirection: THREE.Vector3): void {
		const cam = this.getActiveCamera();
		const direction = rawDirection.clone().normalize();
		const target = this.controls.target.clone();
		const distance = cam.position.distanceTo(target);
		const toPosition = target.clone().add(direction.multiplyScalar(distance));
		this.orbitAnimation = {
			startTimeMs: performance.now(),
			durationMs: 500,
			fromPosition: cam.position.clone(),
			toPosition,
			target
		};
		this.controls.enabled = false;
	}

	private updateOrbitAnimation(): void {
		if (!this.orbitAnimation) return;
		const elapsed = performance.now() - this.orbitAnimation.startTimeMs;
		const t = Math.min(1, elapsed / this.orbitAnimation.durationMs);
		const eased = 1 - Math.pow(1 - t, 3);

		const cam = this.getActiveCamera();
		cam.position.lerpVectors(
			this.orbitAnimation.fromPosition,
			this.orbitAnimation.toPosition,
			eased
		);
		cam.lookAt(this.orbitAnimation.target);
		this.controls.target.copy(this.orbitAnimation.target);
		if (this.isOrthographic) {
			this.updateOrthographicFrustum();
		}

		if (t >= 1) {
			this.orbitAnimation = null;
			this.controls.enabled = true;
			this.controls.update();
		}
	}
}
