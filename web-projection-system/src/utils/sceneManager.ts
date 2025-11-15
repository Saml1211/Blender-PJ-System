import * as THREE from 'three';
import { Projector } from '../models/Projector';
import { Surface } from '../models/Surface';
import { MeasurementTool } from './measurementTool';
import { ObjectRenderers } from './objectRenderers';
import { SceneControls } from './sceneControls';

/**
 * SceneManager
 *
 * Main class that orchestrates the 3D scene, camera, renderer, and delegates
 * object rendering and controls to specialized modules
 */
export class SceneManager {
  // Three.js components
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  renderer: THREE.WebGLRenderer;

  // Specialized modules
  objectRenderers: ObjectRenderers;
  sceneControls: SceneControls;
  measurementTool: MeasurementTool;

  // State
  measurementActive: boolean = false;

  constructor(container: HTMLElement) {
    // Create scene
    this.scene = new THREE.Scene();

    // Set background color based on theme
    const isDarkMode = document.documentElement.getAttribute('data-theme') === 'dark';
    this.scene.background = new THREE.Color(isDarkMode ? 0x1e1e1e : 0xf0f0f0);

    // Set up axis: Z is up
    THREE.Object3D.DEFAULT_UP.set(0, 0, 1);

    // Create camera
    this.camera = new THREE.PerspectiveCamera(
      50,
      container.clientWidth / container.clientHeight,
      0.1,
      1000
    );
    this.camera.position.set(5, -5, 3); // Position for Z-up view

    // Create renderer
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setSize(container.clientWidth, container.clientHeight);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.shadowMap.enabled = true;
    container.appendChild(this.renderer.domElement);

    // Initialize specialized modules
    this.objectRenderers = new ObjectRenderers(this.scene);
    this.sceneControls = new SceneControls(this.scene, this.camera, this.renderer);

    // Add lights
    this.setupLights();

    // Initialize measurement tool
    this.measurementTool = new MeasurementTool(this.scene, this.camera, this.renderer);

    // Handle window resize
    window.addEventListener('resize', () => this.handleResize(container));

    // Start animation loop
    this.animate();
  }

  // ==================== SCENE SETUP ====================

  private setupLights(): void {
    // Ambient light
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    this.scene.add(ambientLight);

    // Directional light (sun) - adjusted for Z-up
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(5, -5, 10);
    directionalLight.castShadow = true;

    // Configure shadow properties
    directionalLight.shadow.mapSize.width = 2048;
    directionalLight.shadow.mapSize.height = 2048;
    directionalLight.shadow.camera.near = 0.5;
    directionalLight.shadow.camera.far = 50;
    directionalLight.shadow.camera.left = -10;
    directionalLight.shadow.camera.right = 10;
    directionalLight.shadow.camera.top = 10;
    directionalLight.shadow.camera.bottom = -10;

    this.scene.add(directionalLight);
  }

  private handleResize(container: HTMLElement): void {
    this.camera.aspect = container.clientWidth / container.clientHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(container.clientWidth, container.clientHeight);
  }

  private animate(): void {
    requestAnimationFrame(() => this.animate());

    // Update controls
    this.sceneControls.update();

    // Render scene
    this.renderer.render(this.scene, this.camera);
  }

  // ==================== PROJECTOR DELEGATION ====================

  addProjector(projector: Projector): void {
    this.objectRenderers.addProjector(projector);
  }

  updateProjector(projector: Projector): void {
    this.objectRenderers.updateProjector(projector);
  }

  removeProjector(projectorId: string): void {
    this.objectRenderers.removeProjector(projectorId);
  }

  // ==================== SURFACE DELEGATION ====================

  addSurface(surface: Surface): void {
    this.objectRenderers.addSurface(surface);
  }

  updateSurface(surface: Surface): void {
    this.objectRenderers.updateSurface(surface);
  }

  removeSurface(surfaceId: string): void {
    this.objectRenderers.removeSurface(surfaceId);
  }

  // ==================== IMPORTED MODEL DELEGATION ====================

  addImportedModel(id: string, object: THREE.Object3D): void {
    this.objectRenderers.addImportedModel(id, object);
  }

  removeImportedModel(id: string): void {
    this.objectRenderers.removeImportedModel(id);
  }

  // ==================== CONTROLS DELEGATION ====================

  setActiveObject(id: string | null, type: 'projector' | 'surface' | 'model'): void {
    let object: THREE.Object3D | undefined;

    switch (type) {
      case 'projector':
        object = this.objectRenderers.projectorMeshes.get(id || '');
        break;
      case 'surface':
        object = this.objectRenderers.surfaceMeshes.get(id || '');
        break;
      case 'model':
        object = this.objectRenderers.importedModels.get(id || '');
        break;
    }

    this.sceneControls.setActiveObject(id, type, object);
  }

  setTransformMode(mode: 'translate' | 'rotate' | 'scale'): void {
    this.sceneControls.setTransformMode(mode);
  }

  toggleGrid(visible: boolean): void {
    this.sceneControls.toggleGrid(visible);
  }

  toggleAxes(visible: boolean): void {
    this.sceneControls.toggleAxes(visible);
  }

  toggleSnapToGrid(enabled: boolean): void {
    this.sceneControls.toggleSnapToGrid(enabled);
  }

  setGridSize(size: number): void {
    this.sceneControls.setGridSize(size);
  }

  updateTheme(isDarkMode: boolean): void {
    // Update scene background
    this.scene.background = new THREE.Color(isDarkMode ? 0x1e1e1e : 0xf0f0f0);

    // Update controls theme
    this.sceneControls.updateTheme(isDarkMode);
  }

  // ==================== MEASUREMENT TOOL DELEGATION ====================

  toggleMeasurementTool(active: boolean): void {
    this.measurementActive = active;

    if (active) {
      this.measurementTool.activate();

      const measureableObjects: THREE.Object3D[] = [];

      this.objectRenderers.projectorMeshes.forEach(mesh => {
        measureableObjects.push(mesh);
      });

      this.objectRenderers.surfaceMeshes.forEach(mesh => {
        measureableObjects.push(mesh);
      });

      this.objectRenderers.importedModels.forEach(model => {
        measureableObjects.push(model);
      });

      measureableObjects.push(this.sceneControls.grid);

      this.measurementTool.addMeasureableObjects(measureableObjects);
    } else {
      this.measurementTool.deactivate();
    }
  }

  updateMeasurementUnitSystem(unitSystem: 'metric' | 'imperial' | 'millimeters'): void {
    this.measurementTool.setUnitSystem(unitSystem);
  }

  // ==================== PROJECTION MAPPING DELEGATION ====================

  applyProjectionMapping(surfaceId: string, projectorId: string): void {
    this.objectRenderers.applyProjectionMapping(surfaceId, projectorId);
  }

  visualizeEdgeBlending(projectorId1: string, projectorId2: string, blendAmount: number): void {
    this.objectRenderers.visualizeEdgeBlending(projectorId1, projectorId2, blendAmount);
  }

  // ==================== ACCESSORS ====================

  get projectorMeshes() {
    return this.objectRenderers.projectorMeshes;
  }

  get surfaceMeshes() {
    return this.objectRenderers.surfaceMeshes;
  }

  get importedModels() {
    return this.objectRenderers.importedModels;
  }

  get projectors() {
    return this.objectRenderers.projectors;
  }

  get surfaces() {
    return this.objectRenderers.surfaces;
  }

  get orbitControls() {
    return this.sceneControls.orbitControls;
  }

  get transformControls() {
    return this.sceneControls.transformControls;
  }

  get grid() {
    return this.sceneControls.grid;
  }

  get axes() {
    return this.sceneControls.axes;
  }

  get gridSize() {
    return this.sceneControls.gridSize;
  }

  get snapToGrid() {
    return this.sceneControls.snapToGrid;
  }

  get activeObjectId() {
    return this.sceneControls.activeObjectId;
  }
}
