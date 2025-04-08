import * as THREE from 'three';
import { formatWithUnit } from './projectionCalculations';

export class MeasurementTool {
  private scene: THREE.Scene;
  private camera: THREE.Camera;
  private renderer: THREE.WebGLRenderer;
  private raycaster: THREE.Raycaster;
  private mouse: THREE.Vector2;
  private unitSystem: 'metric' | 'imperial' | 'millimeters';

  private startPoint: THREE.Vector3 | null = null;
  private endPoint: THREE.Vector3 | null = null;
  private measurementLine: THREE.Line | null = null;
  private measurementText: THREE.Sprite | null = null;
  private isActive: boolean = false;
  private measureableObjects: THREE.Object3D[] = [];

  constructor(
    scene: THREE.Scene,
    camera: THREE.Camera,
    renderer: THREE.WebGLRenderer,
    unitSystem: 'metric' | 'imperial' | 'millimeters' = 'metric'
  ) {
    this.scene = scene;
    this.camera = camera;
    this.renderer = renderer;
    this.unitSystem = unitSystem;
    this.raycaster = new THREE.Raycaster();
    this.mouse = new THREE.Vector2();

    // Bind methods
    this.onMouseDown = this.onMouseDown.bind(this);
    this.onMouseMove = this.onMouseMove.bind(this);
    this.onKeyDown = this.onKeyDown.bind(this);
  }

  // Add objects that can be measured
  addMeasureableObjects(objects: THREE.Object3D[]): void {
    this.measureableObjects.push(...objects);
  }

  // Set unit system
  setUnitSystem(unitSystem: 'metric' | 'imperial' | 'millimeters'): void {
    this.unitSystem = unitSystem;
    this.updateMeasurementText();
  }

  // Activate the measurement tool
  activate(): void {
    if (this.isActive) return;

    this.isActive = true;
    this.startPoint = null;
    this.endPoint = null;

    // Add event listeners
    window.addEventListener('mousedown', this.onMouseDown);
    window.addEventListener('mousemove', this.onMouseMove);
    window.addEventListener('keydown', this.onKeyDown);

    // Change cursor
    this.renderer.domElement.style.cursor = 'crosshair';
  }

  // Deactivate the measurement tool
  deactivate(): void {
    if (!this.isActive) return;

    this.isActive = false;

    // Remove event listeners
    window.removeEventListener('mousedown', this.onMouseDown);
    window.removeEventListener('mousemove', this.onMouseMove);
    window.removeEventListener('keydown', this.onKeyDown);

    // Reset cursor
    this.renderer.domElement.style.cursor = 'auto';

    // Clear measurement
    this.clearMeasurement();
  }

  // Clear the current measurement
  clearMeasurement(): void {
    if (this.measurementLine) {
      this.scene.remove(this.measurementLine);
      this.measurementLine = null;
    }

    if (this.measurementText) {
      this.scene.remove(this.measurementText);
      this.measurementText = null;
    }

    this.startPoint = null;
    this.endPoint = null;
  }

  // Handle mouse down event
  private onMouseDown(event: MouseEvent): void {
    // Only handle left mouse button
    if (event.button !== 0) return;

    // Calculate mouse position in normalized device coordinates
    this.mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    this.mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

    // Update the picking ray with the camera and mouse position
    this.raycaster.setFromCamera(this.mouse, this.camera);

    // Calculate objects intersecting the picking ray
    const intersects = this.raycaster.intersectObjects(this.measureableObjects, true);

    if (intersects.length > 0) {
      const point = intersects[0].point.clone();

      if (!this.startPoint) {
        // Set start point
        this.startPoint = point;
      } else if (!this.endPoint) {
        // Set end point
        this.endPoint = point;

        // Create or update measurement line
        this.createMeasurementLine();

        // Create or update measurement text
        this.createMeasurementText();
      } else {
        // Clear previous measurement and start a new one
        this.clearMeasurement();
        this.startPoint = point;
      }
    }
  }

  // Handle mouse move event
  private onMouseMove(event: MouseEvent): void {
    if (!this.startPoint || this.endPoint) return;

    // Calculate mouse position in normalized device coordinates
    this.mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    this.mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

    // Update the picking ray with the camera and mouse position
    this.raycaster.setFromCamera(this.mouse, this.camera);

    // Calculate objects intersecting the picking ray
    const intersects = this.raycaster.intersectObjects(this.measureableObjects, true);

    if (intersects.length > 0) {
      const point = intersects[0].point.clone();

      // Temporarily set end point for preview
      this.endPoint = point;

      // Create or update measurement line
      this.createMeasurementLine();

      // Create or update measurement text
      this.createMeasurementText();
    }
  }

  // Handle key down event
  private onKeyDown(event: KeyboardEvent): void {
    // Cancel measurement on Escape
    if (event.key === 'Escape') {
      this.clearMeasurement();
    }
  }

  // Create or update the measurement line
  private createMeasurementLine(): void {
    if (!this.startPoint || !this.endPoint) return;

    // Remove existing line
    if (this.measurementLine) {
      this.scene.remove(this.measurementLine);
    }

    // Create line geometry
    const geometry = new THREE.BufferGeometry().setFromPoints([
      this.startPoint,
      this.endPoint
    ]);

    // Create line material
    const material = new THREE.LineBasicMaterial({
      color: 0xffff00,
      linewidth: 2
    });

    // Create line
    this.measurementLine = new THREE.Line(geometry, material);
    this.scene.add(this.measurementLine);
  }

  // Create or update the measurement text
  private createMeasurementText(): void {
    if (!this.startPoint || !this.endPoint) return;

    // Remove existing text
    if (this.measurementText) {
      this.scene.remove(this.measurementText);
    }

    // Calculate distance
    const distance = this.startPoint.distanceTo(this.endPoint);

    // Format distance with unit
    const formattedDistance = formatWithUnit(distance, this.unitSystem);

    // Create canvas for text
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    if (!context) return;

    canvas.width = 256;
    canvas.height = 64;

    // Draw background
    context.fillStyle = 'rgba(0, 0, 0, 0.5)';
    context.fillRect(0, 0, canvas.width, canvas.height);

    // Draw text
    context.font = 'bold 24px Arial';
    context.fillStyle = 'white';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(formattedDistance, canvas.width / 2, canvas.height / 2);

    // Create texture
    const texture = new THREE.CanvasTexture(canvas);

    // Create sprite material
    const material = new THREE.SpriteMaterial({
      map: texture,
      transparent: true
    });

    // Create sprite
    this.measurementText = new THREE.Sprite(material);

    // Position sprite at midpoint of line
    const midpoint = new THREE.Vector3().addVectors(
      this.startPoint,
      this.endPoint
    ).multiplyScalar(0.5);

    this.measurementText.position.copy(midpoint);

    // Scale sprite
    this.measurementText.scale.set(1, 0.25, 1);

    this.scene.add(this.measurementText);
  }

  // Update measurement text (e.g., when unit system changes)
  private updateMeasurementText(): void {
    if (this.startPoint && this.endPoint) {
      this.createMeasurementText();
    }
  }
}
