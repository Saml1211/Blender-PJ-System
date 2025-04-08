import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';
import { TransformControls } from 'three/examples/jsm/controls/TransformControls';
import { Projector } from '../models/Projector';
import { Surface } from '../models/Surface';
import { createProjectionConeGeometry } from './projectionCalculations';
import { MeasurementTool } from './measurementTool';

export class SceneManager {
  // Three.js components
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  renderer: THREE.WebGLRenderer;
  orbitControls: OrbitControls;
  transformControls: TransformControls;

  // Scene objects
  projectorMeshes: Map<string, THREE.Group> = new Map();
  surfaceMeshes: Map<string, THREE.Mesh> = new Map();
  importedModels: Map<string, THREE.Object3D> = new Map();

  // Store references to the original objects
  projectors: Map<string, Projector> = new Map();
  surfaces: Map<string, Surface> = new Map();

  // Grid settings
  gridSize: number = 0.5; // Grid cell size in units
  snapToGrid: boolean = false; // Whether to snap objects to grid

  // Helper objects
  grid: THREE.GridHelper;
  axes: THREE.AxesHelper;

  // State
  activeObjectId: string | null = null;

  // Measurement tool
  measurementTool: MeasurementTool;
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

    // Add event listener for object changes
    this.transformControls.addEventListener('objectChange', () => {
      // Apply snap to grid if enabled
      if (this.snapToGrid && this.transformControls.mode === 'translate') {
        this.applySnapToGrid();
      }

      this.updateObjectParameters();
    });

    // Add event listener for mouse up to ensure final update
    this.transformControls.addEventListener('mouseUp', () => {
      // Apply snap to grid if enabled
      if (this.snapToGrid && this.transformControls.mode === 'translate') {
        this.applySnapToGrid();
      }

      this.updateObjectParameters();
    });

    this.scene.add(this.transformControls);

    // Create grid for Z-up orientation
    // Use the same isDarkMode variable from above
    const gridColor = isDarkMode ? 0x555555 : 0x888888;

    this.grid = new THREE.GridHelper(20, 20, gridColor, gridColor);
    // Rotate grid to XY plane (Z-up)
    this.grid.rotation.x = Math.PI / 2;
    this.scene.add(this.grid);

    // Create axes
    this.axes = new THREE.AxesHelper(5);

    // Set axes colors based on theme
    if (this.axes.material instanceof THREE.Material) {
      // If it's a single material
      this.axes.material.opacity = 0.8;
      this.axes.material.transparent = true;
    } else if (Array.isArray(this.axes.material)) {
      // If it's an array of materials
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

    this.scene.add(this.axes);

    // Add lights
    this.setupLights();

    // Handle window resize
    window.addEventListener('resize', () => this.handleResize(container));

    // Initialize measurement tool
    this.measurementTool = new MeasurementTool(this.scene, this.camera, this.renderer);

    // Start animation loop
    this.animate();
  }

  // Set up scene lighting
  private setupLights(): void {
    // Ambient light
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    this.scene.add(ambientLight);

    // Directional light (sun) - adjusted for Z-up
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(5, -5, 10); // X, Y, Z with Z being up
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

  // Handle window resize
  private handleResize(container: HTMLElement): void {
    this.camera.aspect = container.clientWidth / container.clientHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(container.clientWidth, container.clientHeight);
  }

  // Animation loop
  private animate(): void {
    requestAnimationFrame(() => this.animate());

    // Update orbit controls
    this.orbitControls.update();

    // Handle transform controls
    if (this.transformControls.object) {
      // Make sure transform controls are visible
      this.transformControls.visible = true;

      // Check if the object is still in the scene
      // This prevents issues with deleted objects
      const objectInScene = this.scene.getObjectById(this.transformControls.object.id);
      if (!objectInScene) {
        console.log('Object no longer in scene, detaching transform controls');
        this.transformControls.detach();
      }
    }

    // Render scene
    this.renderer.render(this.scene, this.camera);
  }

  // Add a projector to the scene
  addProjector(projector: Projector): void {
    // Create projector mesh
    const projectorGroup = new THREE.Group();
    projectorGroup.name = `projector-${projector.id}`;

    // Create projector body - adjusted for Z-up
    const bodyGeometry = new THREE.BoxGeometry(0.4, 0.3, 0.2); // X, Y, Z with Z being up
    const bodyMaterial = new THREE.MeshStandardMaterial({ color: 0x333333 });
    const bodyMesh = new THREE.Mesh(bodyGeometry, bodyMaterial);
    // Align to floor (bottom at z=0)
    bodyMesh.position.z = 0.1; // Half the height to place bottom at z=0
    projectorGroup.add(bodyMesh);

    // Create lens - adjusted for Z-up
    const lensGeometry = new THREE.CylinderGeometry(0.1, 0.1, 0.05, 16);
    // Rotate for Z-up (lens points along Y axis)
    lensGeometry.rotateZ(Math.PI / 2);
    lensGeometry.translate(0, 0.175, 0.1); // Position at center of projector
    const lensMaterial = new THREE.MeshStandardMaterial({ color: 0x666666 });
    const lensMesh = new THREE.Mesh(lensGeometry, lensMaterial);
    projectorGroup.add(lensMesh);

    // Create projection cone
    // Check if there are any surfaces to project onto
    let targetSurface: Surface | undefined;

    // Find the closest surface in front of the projector
    if (this.surfaceMeshes.size > 0) {
      const projectorPos = new THREE.Vector3(
        projector.parameters.position.x,
        projector.parameters.position.y,
        projector.parameters.position.z
      );

      const projectorRot = new THREE.Euler(
        THREE.MathUtils.degToRad(projector.parameters.rotation.x),
        THREE.MathUtils.degToRad(projector.parameters.rotation.y),
        THREE.MathUtils.degToRad(projector.parameters.rotation.z),
        'XYZ'
      );

      // Calculate forward direction
      const forward = new THREE.Vector3(0, 1, 0); // Forward is along Y axis
      forward.applyEuler(projectorRot).normalize();

      // Create a raycaster
      const raycaster = new THREE.Raycaster(projectorPos, forward);

      // Get all surface meshes
      const surfaceMeshes: THREE.Mesh[] = [];
      this.surfaceMeshes.forEach(mesh => {
        surfaceMeshes.push(mesh);
      });

      // Find intersections
      const intersects = raycaster.intersectObjects(surfaceMeshes, false);

      if (intersects.length > 0) {
        // Get the closest intersection
        const closestIntersect = intersects[0];
        const surfaceMesh = closestIntersect.object as THREE.Mesh;

        // Find the corresponding Surface object
        this.surfaceMeshes.forEach((mesh, id) => {
          if (mesh === surfaceMesh) {
            // Get the Surface object from our stored references
            targetSurface = this.surfaces.get(id);
          }
        });
      }
    }

    // Create the projection cone geometry (either standard or targeting a surface)
    const coneGeometry = createProjectionConeGeometry(projector, targetSurface);
    const coneMaterial = new THREE.MeshBasicMaterial({
      color: 0x2a7fff,
      transparent: true,
      opacity: 0.2,
      wireframe: true,
      side: THREE.DoubleSide
    });
    const coneMesh = new THREE.Mesh(coneGeometry, coneMaterial);
    coneMesh.name = `cone-${projector.id}`;
    projectorGroup.add(coneMesh);

    // Set position and rotation
    projectorGroup.position.set(
      projector.parameters.position.x,
      projector.parameters.position.y,
      projector.parameters.position.z
    );

    // Set rotation - adjusted for Z-up
    // Use ZYX order for more intuitive rotation in Z-up system
    const rotationOrder = 'ZYX';
    const euler = new THREE.Euler(
      THREE.MathUtils.degToRad(projector.parameters.rotation.x),
      THREE.MathUtils.degToRad(projector.parameters.rotation.y),
      THREE.MathUtils.degToRad(projector.parameters.rotation.z),
      rotationOrder
    );
    projectorGroup.rotation.copy(euler);

    console.log(`Projector ${projector.id} added with rotation:`, {
      degrees: projector.parameters.rotation,
      radians: { x: euler.x, y: euler.y, z: euler.z },
      order: rotationOrder
    });

    // Add to scene and store references
    this.scene.add(projectorGroup);
    this.projectorMeshes.set(projector.id, projectorGroup);
    this.projectors.set(projector.id, projector);
    projector.mesh = projectorGroup;
    projector.projectionCone = coneMesh;
  }

  // Update a projector in the scene
  updateProjector(projector: Projector): void {
    const projectorGroup = this.projectorMeshes.get(projector.id);

    if (!projectorGroup) {
      console.warn(`Projector with ID ${projector.id} not found in scene`);
      return;
    }

    // Update position and rotation
    projectorGroup.position.set(
      projector.parameters.position.x,
      projector.parameters.position.y,
      projector.parameters.position.z
    );

    // Set rotation - adjusted for Z-up with ZYX order
    const rotationOrder = 'ZYX';
    const euler = new THREE.Euler(
      THREE.MathUtils.degToRad(projector.parameters.rotation.x),
      THREE.MathUtils.degToRad(projector.parameters.rotation.y),
      THREE.MathUtils.degToRad(projector.parameters.rotation.z),
      rotationOrder
    );
    projectorGroup.rotation.copy(euler);

    // Update projection cone
    const coneMesh = projectorGroup.children.find(child => child.name === `cone-${projector.id}`) as THREE.Mesh;

    if (coneMesh) {
      // Check if there are any surfaces to project onto
      let targetSurface: Surface | undefined;

      // Find the closest surface in front of the projector
      if (this.surfaceMeshes.size > 0) {
        const projectorPos = new THREE.Vector3(
          projector.parameters.position.x,
          projector.parameters.position.y,
          projector.parameters.position.z
        );

        const projectorRot = new THREE.Euler(
          THREE.MathUtils.degToRad(projector.parameters.rotation.x),
          THREE.MathUtils.degToRad(projector.parameters.rotation.y),
          THREE.MathUtils.degToRad(projector.parameters.rotation.z),
          'XYZ'
        );

        // Calculate forward direction
        const forward = new THREE.Vector3(0, 1, 0); // Forward is along Y axis
        forward.applyEuler(projectorRot).normalize();

        // Create a raycaster
        const raycaster = new THREE.Raycaster(projectorPos, forward);

        // Get all surface meshes
        const surfaceMeshes: THREE.Mesh[] = [];
        this.surfaceMeshes.forEach(mesh => {
          surfaceMeshes.push(mesh);
        });

        // Find intersections
        const intersects = raycaster.intersectObjects(surfaceMeshes, false);

        if (intersects.length > 0) {
          // Get the closest intersection
          const closestIntersect = intersects[0];
          const surfaceMesh = closestIntersect.object as THREE.Mesh;

          // Find the corresponding Surface object
          this.surfaceMeshes.forEach((mesh, id) => {
            if (mesh === surfaceMesh) {
              // Get the Surface object from our stored references
              targetSurface = this.surfaces.get(id);
            }
          });
        }
      }

      // Update geometry
      coneMesh.geometry.dispose();
      coneMesh.geometry = createProjectionConeGeometry(projector, targetSurface);

      // Update visibility
      coneMesh.visible = projector.parameters.showCone;

      // Store updated projector reference
      this.projectors.set(projector.id, projector);
    }
  }

  // Remove a projector from the scene
  removeProjector(projectorId: string): void {
    const projectorGroup = this.projectorMeshes.get(projectorId);

    if (projectorGroup) {
      // Remove from scene
      this.scene.remove(projectorGroup);

      // Dispose of geometries and materials
      projectorGroup.traverse((child) => {
        if (child instanceof THREE.Mesh) {
          child.geometry.dispose();

          if (Array.isArray(child.material)) {
            child.material.forEach(material => material.dispose());
          } else {
            child.material.dispose();
          }
        }
      });

      // Remove from maps
      this.projectorMeshes.delete(projectorId);
      this.projectors.delete(projectorId);
    }
  }

  // Add a surface to the scene
  addSurface(surface: Surface): void {
    // Create geometry based on surface type
    const geometry = surface.createGeometry();

    // Create material
    const material = surface.createMaterial();

    // Create mesh
    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = `surface-${surface.id}`;
    mesh.receiveShadow = true;

    // Position the surface based on its type
    if (surface.parameters.type === 'flat') {
      // For flat surfaces with Z-up, we need to adjust the position
      // to align the bottom edge with the floor (Z=0)
      // Since we've rotated the geometry, the height is now along the Z axis
      const halfHeight = surface.parameters.height / 2;

      // Set position with Z adjusted to place bottom at floor level
      mesh.position.set(
        surface.parameters.position.x,
        surface.parameters.position.y,
        surface.parameters.position.z + halfHeight // Add half height to align bottom with Z=0
      );
    } else if (surface.parameters.type === 'curved') {
      // For curved surfaces, we need to adjust based on our Z-up parametric function
      const halfHeight = surface.parameters.height / 2;

      mesh.position.set(
        surface.parameters.position.x,
        surface.parameters.position.y,
        surface.parameters.position.z + halfHeight // Add half height to align bottom with Z=0
      );
    } else {
      // For cylindrical and spherical surfaces, use the original position
      // as they're already centered properly
      mesh.position.set(
        surface.parameters.position.x,
        surface.parameters.position.y,
        surface.parameters.position.z
      );
    }

    // Set rotation - adjusted for Z-up
    // Use ZYX order for more intuitive rotation in Z-up system
    const rotationOrder = 'ZYX';
    const euler = new THREE.Euler(
      THREE.MathUtils.degToRad(surface.parameters.rotation.x),
      THREE.MathUtils.degToRad(surface.parameters.rotation.y),
      THREE.MathUtils.degToRad(surface.parameters.rotation.z),
      rotationOrder
    );
    mesh.rotation.copy(euler);

    console.log(`Surface ${surface.id} added with rotation:`, {
      degrees: surface.parameters.rotation,
      radians: { x: euler.x, y: euler.y, z: euler.z },
      order: rotationOrder
    });

    // Add to scene and store references
    this.scene.add(mesh);
    this.surfaceMeshes.set(surface.id, mesh);
    this.surfaces.set(surface.id, surface);
    surface.mesh = mesh;

    // Update all projectors to check if they should project onto this surface
    this.projectors.forEach((projector, id) => {
      this.updateProjector(projector);
    });
  }

  // Update a surface in the scene
  updateSurface(surface: Surface): void {
    const mesh = this.surfaceMeshes.get(surface.id);

    if (!mesh) {
      console.warn(`Surface with ID ${surface.id} not found in scene`);
      return;
    }

    // Update position based on surface type - with floor alignment for Z-up
    if (surface.parameters.type === 'flat') {
      // For flat surfaces with Z-up, we need to adjust the position
      // to align the bottom edge with the floor (Z=0)
      const halfHeight = surface.parameters.height / 2;

      // Set position with Z adjusted to place bottom at floor level
      mesh.position.set(
        surface.parameters.position.x,
        surface.parameters.position.y,
        surface.parameters.position.z + halfHeight // Add half height to align bottom with Z=0
      );
    } else if (surface.parameters.type === 'curved') {
      // For curved surfaces, we need to adjust based on our Z-up parametric function
      const halfHeight = surface.parameters.height / 2;

      mesh.position.set(
        surface.parameters.position.x,
        surface.parameters.position.y,
        surface.parameters.position.z + halfHeight // Add half height to align bottom with Z=0
      );
    } else {
      // For cylindrical and spherical surfaces, use the original position
      // as they're already centered properly
      mesh.position.set(
        surface.parameters.position.x,
        surface.parameters.position.y,
        surface.parameters.position.z
      );
    }

    // Update rotation - adjusted for Z-up with ZYX order
    const rotationOrder = 'ZYX';
    const euler = new THREE.Euler(
      THREE.MathUtils.degToRad(surface.parameters.rotation.x),
      THREE.MathUtils.degToRad(surface.parameters.rotation.y),
      THREE.MathUtils.degToRad(surface.parameters.rotation.z),
      rotationOrder
    );
    mesh.rotation.copy(euler);

    // Update geometry if surface type or dimensions changed
    mesh.geometry.dispose();
    mesh.geometry = surface.createGeometry();

    // Update material
    if (Array.isArray(mesh.material)) {
      mesh.material.forEach(material => material.dispose());
    } else {
      mesh.material.dispose();
    }

    mesh.material = surface.createMaterial();

    // Store updated surface reference
    this.surfaces.set(surface.id, surface);

    // Update all projectors to check if they should project onto this updated surface
    this.projectors.forEach((projector, id) => {
      this.updateProjector(projector);
    });
  }

  // Remove a surface from the scene
  removeSurface(surfaceId: string): void {
    const mesh = this.surfaceMeshes.get(surfaceId);

    if (mesh) {
      // Remove from scene
      this.scene.remove(mesh);

      // Dispose of geometry and material
      mesh.geometry.dispose();

      if (Array.isArray(mesh.material)) {
        mesh.material.forEach(material => material.dispose());
      } else {
        mesh.material.dispose();
      }

      // Remove from maps
      this.surfaceMeshes.delete(surfaceId);
      this.surfaces.delete(surfaceId);

      // Update all projectors since a surface was removed
      this.projectors.forEach((projector, id) => {
        this.updateProjector(projector);
      });
    }
  }

  // Add an imported model to the scene
  addImportedModel(id: string, object: THREE.Object3D): void {
    // Add to scene and store reference
    this.scene.add(object);
    this.importedModels.set(id, object);
  }

  // Remove an imported model from the scene
  removeImportedModel(id: string): void {
    const object = this.importedModels.get(id);

    if (object) {
      // Remove from scene
      this.scene.remove(object);

      // Dispose of geometries and materials
      object.traverse((child) => {
        if (child instanceof THREE.Mesh) {
          if (child.geometry) {
            child.geometry.dispose();
          }

          if (child.material) {
            if (Array.isArray(child.material)) {
              child.material.forEach(material => material.dispose());
            } else {
              child.material.dispose();
            }
          }
        }
      });

      // Remove from map
      this.importedModels.delete(id);
    }
  }

  // Set active object for transform controls
  setActiveObject(id: string | null, type: 'projector' | 'surface' | 'model'): void {
    console.log(`Setting active object: ${type} with ID ${id}`);

    // Detach transform controls from previous object
    this.transformControls.detach();
    this.activeObjectId = id;

    if (!id) {
      console.log('No ID provided, detaching transform controls');
      return;
    }

    // Attach transform controls to new object
    let object: THREE.Object3D | undefined;

    switch (type) {
      case 'projector':
        object = this.projectorMeshes.get(id);
        console.log('Found projector object:', object ? 'yes' : 'no');
        break;
      case 'surface':
        object = this.surfaceMeshes.get(id);
        console.log('Found surface object:', object ? 'yes' : 'no');
        break;
      case 'model':
        object = this.importedModels.get(id);
        console.log('Found model object:', object ? 'yes' : 'no');
        break;
    }

    if (object) {
      // Make sure transform controls are added to the scene
      if (!this.scene.children.includes(this.transformControls)) {
        console.log('Adding transform controls to scene');
        this.scene.add(this.transformControls);
      }

      // Set transform controls to translate mode by default
      this.transformControls.setMode('translate');

      // Set the space to 'world' for more intuitive control in Z-up orientation
      this.transformControls.setSpace('world');

      // Set the size of the transform controls to be more visible
      this.transformControls.size = 1.2;

      // Attach transform controls to the object
      this.transformControls.attach(object);

      // Make sure the transform controls are visible
      this.transformControls.visible = true;

      // Force a render to ensure transform controls are visible
      this.renderer.render(this.scene, this.camera);

      // Log for debugging
      console.log(`Transform controls attached to ${type} with ID ${id}`);
    } else {
      console.warn(`Object with ID ${id} and type ${type} not found`);
    }
  }

  // Set transform controls mode
  setTransformMode(mode: 'translate' | 'rotate' | 'scale'): void {
    console.log(`Setting transform mode to: ${mode}`);

    // Set the mode
    this.transformControls.setMode(mode);

    // Adjust space based on mode for better Z-up handling
    if (mode === 'rotate') {
      // Use local space for rotation to make it more intuitive
      this.transformControls.setSpace('local');
    } else {
      // Use world space for translation and scaling
      this.transformControls.setSpace('world');
    }

    // Make sure transform controls are visible
    this.transformControls.visible = true;

    // Force a render to ensure transform controls are updated
    this.renderer.render(this.scene, this.camera);
  }

  // Toggle grid visibility
  toggleGrid(visible: boolean): void {
    this.grid.visible = visible;
  }

  // Toggle axes visibility
  toggleAxes(visible: boolean): void {
    this.axes.visible = visible;
  }

  // Toggle snap to grid
  toggleSnapToGrid(enabled: boolean): void {
    this.snapToGrid = enabled;
  }

  // Set grid size
  setGridSize(size: number): void {
    this.gridSize = size;

    // Update grid helper
    this.scene.remove(this.grid);
    this.grid = new THREE.GridHelper(20, Math.round(20 / this.gridSize));
    this.grid.rotation.x = Math.PI / 2; // Rotate for Z-up
    this.scene.add(this.grid);
  }

  // Apply snap to grid
  private applySnapToGrid(): void {
    if (!this.transformControls.object) return;

    const object = this.transformControls.object;

    // Get current world position
    const worldPosition = new THREE.Vector3();
    object.getWorldPosition(worldPosition);

    // Get parent's world position and rotation
    const parent = object.parent;
    const parentWorldPosition = new THREE.Vector3();
    const parentWorldQuaternion = new THREE.Quaternion();

    if (parent) {
      parent.getWorldPosition(parentWorldPosition);
      parent.getWorldQuaternion(parentWorldQuaternion);
    }

    // Calculate local position
    const localPosition = worldPosition.clone();
    if (parent) {
      // Convert world position to local position
      localPosition.sub(parentWorldPosition);
      localPosition.applyQuaternion(parentWorldQuaternion.invert());
    }

    // Snap to grid
    const snappedLocalPosition = new THREE.Vector3(
      Math.round(localPosition.x / this.gridSize) * this.gridSize,
      Math.round(localPosition.y / this.gridSize) * this.gridSize,
      Math.round(localPosition.z / this.gridSize) * this.gridSize
    );

    // Apply snapped position
    object.position.copy(snappedLocalPosition);

    console.log('Snapped to grid:', {
      original: { x: localPosition.x, y: localPosition.y, z: localPosition.z },
      snapped: { x: snappedLocalPosition.x, y: snappedLocalPosition.y, z: snappedLocalPosition.z }
    });
  }

  // Toggle measurement tool
  toggleMeasurementTool(active: boolean): void {
    this.measurementActive = active;

    if (active) {
      // Activate measurement tool
      this.measurementTool.activate();

      // Add all objects to the measurement tool
      const measureableObjects: THREE.Object3D[] = [];

      // Add projector meshes
      this.projectorMeshes.forEach(mesh => {
        measureableObjects.push(mesh);
      });

      // Add surface meshes
      this.surfaceMeshes.forEach(mesh => {
        measureableObjects.push(mesh);
      });

      // Add imported models
      this.importedModels.forEach(model => {
        measureableObjects.push(model);
      });

      // Add grid
      measureableObjects.push(this.grid);

      this.measurementTool.addMeasureableObjects(measureableObjects);
    } else {
      // Deactivate measurement tool
      this.measurementTool.deactivate();
    }
  }

  // Update measurement tool unit system
  updateMeasurementUnitSystem(unitSystem: 'metric' | 'imperial' | 'millimeters'): void {
    this.measurementTool.setUnitSystem(unitSystem);
  }

  // Update theme
  updateTheme(isDarkMode: boolean): void {
    // Update scene background
    this.scene.background = new THREE.Color(isDarkMode ? 0x1e1e1e : 0xf0f0f0);

    // Update grid color
    const gridColor = isDarkMode ? 0x555555 : 0x888888;

    // Remove old grid and create a new one
    this.scene.remove(this.grid);
    this.grid = new THREE.GridHelper(20, Math.round(20 / this.gridSize), gridColor, gridColor);
    this.grid.rotation.x = Math.PI / 2; // Rotate for Z-up
    this.scene.add(this.grid);

    // Update axes colors
    this.scene.remove(this.axes);
    this.axes = new THREE.AxesHelper(5);

    // Set axes colors based on theme
    if (this.axes.material instanceof THREE.Material) {
      // If it's a single material
      this.axes.material.opacity = 0.8;
      this.axes.material.transparent = true;
    } else if (Array.isArray(this.axes.material)) {
      // If it's an array of materials
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

    this.scene.add(this.axes);
  }

  // Update object parameters based on transform controls
  private updateObjectParameters(): void {
    if (!this.activeObjectId) return;

    // Find the active object
    let object: THREE.Object3D | undefined;
    let type: 'projector' | 'surface' | 'model' | undefined;

    if (this.projectorMeshes.has(this.activeObjectId)) {
      object = this.projectorMeshes.get(this.activeObjectId);
      type = 'projector';
    } else if (this.surfaceMeshes.has(this.activeObjectId)) {
      object = this.surfaceMeshes.get(this.activeObjectId);
      type = 'surface';
    } else if (this.importedModels.has(this.activeObjectId)) {
      object = this.importedModels.get(this.activeObjectId);
      type = 'model';
    }

    if (!object || !type) return;

    // Get the world position and rotation
    const position = new THREE.Vector3();
    object.getWorldPosition(position);

    // Get world quaternion
    const quaternion = new THREE.Quaternion();
    object.getWorldQuaternion(quaternion);

    // Convert quaternion to Euler with the correct order for Z-up
    // Use 'ZYX' order which is more intuitive for Z-up orientation
    const rotation = new THREE.Euler().setFromQuaternion(quaternion, 'ZYX');

    // Convert rotation from radians to degrees
    const rotationDegrees = {
      x: THREE.MathUtils.radToDeg(rotation.x),
      y: THREE.MathUtils.radToDeg(rotation.y),
      z: THREE.MathUtils.radToDeg(rotation.z)
    };

    // Log for debugging
    console.log(`Object ${type} ${this.activeObjectId} transformed:`, {
      position: { x: position.x.toFixed(2), y: position.y.toFixed(2), z: position.z.toFixed(2) },
      rotation: { x: rotationDegrees.x.toFixed(2), y: rotationDegrees.y.toFixed(2), z: rotationDegrees.z.toFixed(2) }
    });

    // Dispatch a custom event with the updated parameters
    const event = new CustomEvent('object-transform-changed', {
      detail: {
        id: this.activeObjectId,
        type,
        position: {
          x: position.x,
          y: position.y,
          z: position.z
        },
        rotation: rotationDegrees
      }
    });

    window.dispatchEvent(event);
  }

  // Apply projection mapping to a surface
  applyProjectionMapping(surfaceId: string, projectorId: string): void {
    const surface = this.surfaceMeshes.get(surfaceId);
    const projector = this.projectorMeshes.get(projectorId);

    if (!surface || !projector) {
      console.warn(`Surface or projector not found for mapping`);
      return;
    }

    // Find the projector and surface in our models
    const projectorModel = Array.from(this.projectorMeshes.entries())
      .find(([id]) => id === projectorId)?.[1];

    const surfaceModel = Array.from(this.surfaceMeshes.entries())
      .find(([id]) => id === surfaceId)?.[1];

    if (!projectorModel || !surfaceModel) {
      console.warn(`Models not found for projection mapping`);
      return;
    }

    // Create a texture for projection
    const texture = new THREE.TextureLoader().load('/projection-test-pattern.png');
    texture.wrapS = THREE.ClampToEdgeWrapping;
    texture.wrapT = THREE.ClampToEdgeWrapping;

    // Create a material with the texture
    const material = new THREE.MeshBasicMaterial({
      map: texture,
      side: THREE.DoubleSide
    });

    // Apply the material to the surface
    if (Array.isArray(surface.material)) {
      surface.material.forEach(m => m.dispose());
    } else {
      surface.material.dispose();
    }

    surface.material = material;
  }

  // Calculate and visualize edge blending
  visualizeEdgeBlending(projectorId1: string, projectorId2: string, blendAmount: number): void {
    // This is a placeholder for edge blending visualization
    // In a real implementation, we would create a custom shader material
    // that visualizes the blend region between two projectors

    console.log(`Visualizing edge blending between ${projectorId1} and ${projectorId2} with amount ${blendAmount}`);
  }
}
