import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';
import { TransformControls } from 'three/examples/jsm/controls/TransformControls';

/**
 * SceneControls
 *
 * Manages transform controls, grid, axes, and interaction with scene objects
 */
export class SceneControls {
  orbitControls: OrbitControls;
  transformControls: TransformControls;
  grid: THREE.GridHelper;
  axes: THREE.AxesHelper;

  // Grid settings
  gridSize: number = 0.5;
  snapToGrid: boolean = false;

  // State
  activeObjectId: string | null = null;

  constructor(
    private scene: THREE.Scene,
    private camera: THREE.PerspectiveCamera,
    private renderer: THREE.WebGLRenderer
  ) {
    // Create orbit controls
    this.orbitControls = new OrbitControls(this.camera, this.renderer.domElement);
    this.orbitControls.enableDamping = true;
    this.orbitControls.dampingFactor = 0.05;

    // Create transform controls
    this.transformControls = new TransformControls(this.camera, this.renderer.domElement);

    // Disable orbit controls during transform
    this.transformControls.addEventListener('dragging-changed', (event) => {
      this.orbitControls.enabled = !event.value;
    });

    // Add event listeners for object changes
    this.transformControls.addEventListener('objectChange', () => {
      if (this.snapToGrid && this.transformControls.mode === 'translate') {
        this.applySnapToGrid();
      }
      this.dispatchTransformEvent();
    });

    this.transformControls.addEventListener('mouseUp', () => {
      if (this.snapToGrid && this.transformControls.mode === 'translate') {
        this.applySnapToGrid();
      }
      this.dispatchTransformEvent();
    });

    this.scene.add(this.transformControls);

    // Create grid for Z-up orientation
    const isDarkMode = document.documentElement.getAttribute('data-theme') === 'dark';
    const gridColor = isDarkMode ? 0x555555 : 0x888888;
    this.grid = new THREE.GridHelper(20, 20, gridColor, gridColor);
    this.grid.rotation.x = Math.PI / 2; // Rotate to XY plane (Z-up)
    this.scene.add(this.grid);

    // Create axes
    this.axes = new THREE.AxesHelper(5);
    this.updateAxesColors(isDarkMode);
    this.scene.add(this.axes);
  }

  // ==================== TRANSFORM CONTROLS ====================

  setActiveObject(
    id: string | null,
    type: 'projector' | 'surface' | 'model',
    object?: THREE.Object3D
  ): void {
    console.log(`Setting active object: ${type} with ID ${id}`);

    this.transformControls.detach();
    this.activeObjectId = id;

    if (!id || !object) {
      console.log('No ID or object provided, detaching transform controls');
      return;
    }

    if (!this.scene.children.includes(this.transformControls)) {
      console.log('Adding transform controls to scene');
      this.scene.add(this.transformControls);
    }

    this.transformControls.setMode('translate');
    this.transformControls.setSpace('world');
    this.transformControls.size = 1.2;
    this.transformControls.attach(object);
    this.transformControls.visible = true;

    this.renderer.render(this.scene, this.camera);
    console.log(`Transform controls attached to ${type} with ID ${id}`);
  }

  setTransformMode(mode: 'translate' | 'rotate' | 'scale'): void {
    console.log(`Setting transform mode to: ${mode}`);

    this.transformControls.setMode(mode);

    if (mode === 'rotate') {
      this.transformControls.setSpace('local');
    } else {
      this.transformControls.setSpace('world');
    }

    this.transformControls.visible = true;
    this.renderer.render(this.scene, this.camera);
  }

  update(): void {
    this.orbitControls.update();

    // Check if transform controls object is still in scene
    if (this.transformControls.object) {
      this.transformControls.visible = true;

      const objectInScene = this.scene.getObjectById(this.transformControls.object.id);
      if (!objectInScene) {
        console.log('Object no longer in scene, detaching transform controls');
        this.transformControls.detach();
      }
    }
  }

  // ==================== GRID & AXES ====================

  toggleGrid(visible: boolean): void {
    this.grid.visible = visible;
  }

  toggleAxes(visible: boolean): void {
    this.axes.visible = visible;
  }

  toggleSnapToGrid(enabled: boolean): void {
    this.snapToGrid = enabled;
  }

  setGridSize(size: number): void {
    this.gridSize = size;

    const isDarkMode = document.documentElement.getAttribute('data-theme') === 'dark';
    const gridColor = isDarkMode ? 0x555555 : 0x888888;

    this.scene.remove(this.grid);
    this.grid = new THREE.GridHelper(20, Math.round(20 / this.gridSize), gridColor, gridColor);
    this.grid.rotation.x = Math.PI / 2; // Rotate for Z-up
    this.scene.add(this.grid);
  }

  updateTheme(isDarkMode: boolean): void {
    // Update grid color
    const gridColor = isDarkMode ? 0x555555 : 0x888888;

    this.scene.remove(this.grid);
    this.grid = new THREE.GridHelper(20, Math.round(20 / this.gridSize), gridColor, gridColor);
    this.grid.rotation.x = Math.PI / 2;
    this.scene.add(this.grid);

    // Update axes colors
    this.scene.remove(this.axes);
    this.axes = new THREE.AxesHelper(5);
    this.updateAxesColors(isDarkMode);
    this.scene.add(this.axes);
  }

  // ==================== SNAP TO GRID ====================

  private applySnapToGrid(): void {
    if (!this.transformControls.object) return;

    const object = this.transformControls.object;
    const worldPosition = new THREE.Vector3();
    object.getWorldPosition(worldPosition);

    const parent = object.parent;
    const parentWorldPosition = new THREE.Vector3();
    const parentWorldQuaternion = new THREE.Quaternion();

    if (parent) {
      parent.getWorldPosition(parentWorldPosition);
      parent.getWorldQuaternion(parentWorldQuaternion);
    }

    const localPosition = worldPosition.clone();
    if (parent) {
      localPosition.sub(parentWorldPosition);
      localPosition.applyQuaternion(parentWorldQuaternion.invert());
    }

    const snappedLocalPosition = new THREE.Vector3(
      Math.round(localPosition.x / this.gridSize) * this.gridSize,
      Math.round(localPosition.y / this.gridSize) * this.gridSize,
      Math.round(localPosition.z / this.gridSize) * this.gridSize
    );

    object.position.copy(snappedLocalPosition);

    console.log('Snapped to grid:', {
      original: { x: localPosition.x, y: localPosition.y, z: localPosition.z },
      snapped: { x: snappedLocalPosition.x, y: snappedLocalPosition.y, z: snappedLocalPosition.z }
    });
  }

  // ==================== HELPER METHODS ====================

  private updateAxesColors(isDarkMode: boolean): void {
    if (this.axes.material instanceof THREE.Material) {
      this.axes.material.opacity = 0.8;
      this.axes.material.transparent = true;
    } else if (Array.isArray(this.axes.material)) {
      const xAxisColor = isDarkMode ? 0xff5252 : 0xff3352;
      const yAxisColor = isDarkMode ? 0x69F0AE : 0x4CAF50;
      const zAxisColor = isDarkMode ? 0x40C4FF : 0x2196F3;

      if (this.axes.geometry instanceof THREE.BufferGeometry) {
        const colors = new Float32Array(6);
        colors[0] = ((xAxisColor >> 16) & 255) / 255;
        colors[1] = ((xAxisColor >> 8) & 255) / 255;
        colors[2] = ((yAxisColor >> 16) & 255) / 255;
        colors[3] = ((yAxisColor >> 8) & 255) / 255;
        colors[4] = ((zAxisColor >> 16) & 255) / 255;
        colors[5] = ((zAxisColor >> 8) & 255) / 255;

        this.axes.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
      }
    }
  }

  private dispatchTransformEvent(): void {
    if (!this.activeObjectId || !this.transformControls.object) return;

    const object = this.transformControls.object;
    const position = new THREE.Vector3();
    object.getWorldPosition(position);

    const quaternion = new THREE.Quaternion();
    object.getWorldQuaternion(quaternion);

    const rotation = new THREE.Euler().setFromQuaternion(quaternion, 'ZYX');
    const rotationDegrees = {
      x: THREE.MathUtils.radToDeg(rotation.x),
      y: THREE.MathUtils.radToDeg(rotation.y),
      z: THREE.MathUtils.radToDeg(rotation.z)
    };

    console.log(`Object ${this.activeObjectId} transformed:`, {
      position: { x: position.x.toFixed(2), y: position.y.toFixed(2), z: position.z.toFixed(2) },
      rotation: { x: rotationDegrees.x.toFixed(2), y: rotationDegrees.y.toFixed(2), z: rotationDegrees.z.toFixed(2) }
    });

    const event = new CustomEvent('object-transform-changed', {
      detail: {
        id: this.activeObjectId,
        position: { x: position.x, y: position.y, z: position.z },
        rotation: rotationDegrees
      }
    });

    window.dispatchEvent(event);
  }
}
