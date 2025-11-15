import * as THREE from 'three';
import { Projector } from '../models/Projector';
import { Surface } from '../models/Surface';
import { createProjectionConeGeometry } from './projectionCalculations';

/**
 * ObjectRenderers
 *
 * Handles rendering and management of projectors, surfaces, and imported 3D models
 */
export class ObjectRenderers {
  // Scene objects
  projectorMeshes: Map<string, THREE.Group> = new Map();
  surfaceMeshes: Map<string, THREE.Mesh> = new Map();
  importedModels: Map<string, THREE.Object3D> = new Map();

  // Store references to the original objects
  projectors: Map<string, Projector> = new Map();
  surfaces: Map<string, Surface> = new Map();

  constructor(private scene: THREE.Scene) {}

  // ==================== PROJECTOR MANAGEMENT ====================

  addProjector(projector: Projector): void {
    const projectorGroup = new THREE.Group();
    projectorGroup.name = `projector-${projector.id}`;

    // Create projector body - adjusted for Z-up
    const bodyGeometry = new THREE.BoxGeometry(0.4, 0.3, 0.2);
    const bodyMaterial = new THREE.MeshStandardMaterial({ color: 0x333333 });
    const bodyMesh = new THREE.Mesh(bodyGeometry, bodyMaterial);
    bodyMesh.position.z = 0.1; // Half the height to place bottom at z=0
    projectorGroup.add(bodyMesh);

    // Create lens - adjusted for Z-up
    const lensGeometry = new THREE.CylinderGeometry(0.1, 0.1, 0.05, 16);
    lensGeometry.rotateZ(Math.PI / 2);
    lensGeometry.translate(0, 0.175, 0.1);
    const lensMaterial = new THREE.MeshStandardMaterial({ color: 0x666666 });
    const lensMesh = new THREE.Mesh(lensGeometry, lensMaterial);
    projectorGroup.add(lensMesh);

    // Create projection cone
    const targetSurface = this.findTargetSurface(projector);
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

    const rotationOrder = 'ZYX';
    const euler = new THREE.Euler(
      THREE.MathUtils.degToRad(projector.parameters.rotation.x),
      THREE.MathUtils.degToRad(projector.parameters.rotation.y),
      THREE.MathUtils.degToRad(projector.parameters.rotation.z),
      rotationOrder
    );
    projectorGroup.rotation.copy(euler);

    // Update projection cone
    const coneMesh = projectorGroup.children.find(
      child => child.name === `cone-${projector.id}`
    ) as THREE.Mesh;

    if (coneMesh) {
      const targetSurface = this.findTargetSurface(projector);
      coneMesh.geometry.dispose();
      coneMesh.geometry = createProjectionConeGeometry(projector, targetSurface);
      coneMesh.visible = projector.parameters.showCone;
      this.projectors.set(projector.id, projector);
    }
  }

  removeProjector(projectorId: string): void {
    const projectorGroup = this.projectorMeshes.get(projectorId);

    if (projectorGroup) {
      this.scene.remove(projectorGroup);

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

      this.projectorMeshes.delete(projectorId);
      this.projectors.delete(projectorId);
    }
  }

  // ==================== SURFACE MANAGEMENT ====================

  addSurface(surface: Surface): void {
    const geometry = surface.createGeometry();
    const material = surface.createMaterial();
    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = `surface-${surface.id}`;
    mesh.receiveShadow = true;

    // Position the surface based on its type
    if (surface.parameters.type === 'flat') {
      const halfHeight = surface.parameters.height / 2;
      mesh.position.set(
        surface.parameters.position.x,
        surface.parameters.position.y,
        surface.parameters.position.z + halfHeight
      );
    } else if (surface.parameters.type === 'curved') {
      const halfHeight = surface.parameters.height / 2;
      mesh.position.set(
        surface.parameters.position.x,
        surface.parameters.position.y,
        surface.parameters.position.z + halfHeight
      );
    } else {
      mesh.position.set(
        surface.parameters.position.x,
        surface.parameters.position.y,
        surface.parameters.position.z
      );
    }

    // Set rotation
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

    this.scene.add(mesh);
    this.surfaceMeshes.set(surface.id, mesh);
    this.surfaces.set(surface.id, surface);
    surface.mesh = mesh;

    // Update all projectors to check if they should project onto this surface
    this.projectors.forEach(projector => this.updateProjector(projector));
  }

  updateSurface(surface: Surface): void {
    const mesh = this.surfaceMeshes.get(surface.id);

    if (!mesh) {
      console.warn(`Surface with ID ${surface.id} not found in scene`);
      return;
    }

    // Update position based on surface type
    if (surface.parameters.type === 'flat') {
      const halfHeight = surface.parameters.height / 2;
      mesh.position.set(
        surface.parameters.position.x,
        surface.parameters.position.y,
        surface.parameters.position.z + halfHeight
      );
    } else if (surface.parameters.type === 'curved') {
      const halfHeight = surface.parameters.height / 2;
      mesh.position.set(
        surface.parameters.position.x,
        surface.parameters.position.y,
        surface.parameters.position.z + halfHeight
      );
    } else {
      mesh.position.set(
        surface.parameters.position.x,
        surface.parameters.position.y,
        surface.parameters.position.z
      );
    }

    // Update rotation
    const rotationOrder = 'ZYX';
    const euler = new THREE.Euler(
      THREE.MathUtils.degToRad(surface.parameters.rotation.x),
      THREE.MathUtils.degToRad(surface.parameters.rotation.y),
      THREE.MathUtils.degToRad(surface.parameters.rotation.z),
      rotationOrder
    );
    mesh.rotation.copy(euler);

    // Update geometry and material
    mesh.geometry.dispose();
    mesh.geometry = surface.createGeometry();

    if (Array.isArray(mesh.material)) {
      mesh.material.forEach(material => material.dispose());
    } else {
      mesh.material.dispose();
    }
    mesh.material = surface.createMaterial();

    this.surfaces.set(surface.id, surface);

    // Update all projectors
    this.projectors.forEach(projector => this.updateProjector(projector));
  }

  removeSurface(surfaceId: string): void {
    const mesh = this.surfaceMeshes.get(surfaceId);

    if (mesh) {
      this.scene.remove(mesh);
      mesh.geometry.dispose();

      if (Array.isArray(mesh.material)) {
        mesh.material.forEach(material => material.dispose());
      } else {
        mesh.material.dispose();
      }

      this.surfaceMeshes.delete(surfaceId);
      this.surfaces.delete(surfaceId);

      // Update all projectors since a surface was removed
      this.projectors.forEach(projector => this.updateProjector(projector));
    }
  }

  // ==================== IMPORTED MODEL MANAGEMENT ====================

  addImportedModel(id: string, object: THREE.Object3D): void {
    this.scene.add(object);
    this.importedModels.set(id, object);
  }

  removeImportedModel(id: string): void {
    const object = this.importedModels.get(id);

    if (object) {
      this.scene.remove(object);

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

      this.importedModels.delete(id);
    }
  }

  // ==================== PROJECTION MAPPING ====================

  applyProjectionMapping(surfaceId: string, projectorId: string): void {
    const surface = this.surfaceMeshes.get(surfaceId);
    const projector = this.projectorMeshes.get(projectorId);

    if (!surface || !projector) {
      console.warn(`Surface or projector not found for mapping`);
      return;
    }

    const texture = new THREE.TextureLoader().load('/projection-test-pattern.png');
    texture.wrapS = THREE.ClampToEdgeWrapping;
    texture.wrapT = THREE.ClampToEdgeWrapping;

    const material = new THREE.MeshBasicMaterial({
      map: texture,
      side: THREE.DoubleSide
    });

    if (Array.isArray(surface.material)) {
      surface.material.forEach(m => m.dispose());
    } else {
      surface.material.dispose();
    }

    surface.material = material;
  }

  visualizeEdgeBlending(projectorId1: string, projectorId2: string, blendAmount: number): void {
    console.log(`Visualizing edge blending between ${projectorId1} and ${projectorId2} with amount ${blendAmount}`);
  }

  // ==================== HELPER METHODS ====================

  private findTargetSurface(projector: Projector): Surface | undefined {
    if (this.surfaceMeshes.size === 0) return undefined;

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

    const forward = new THREE.Vector3(0, 1, 0);
    forward.applyEuler(projectorRot).normalize();

    const raycaster = new THREE.Raycaster(projectorPos, forward);
    const surfaceMeshes: THREE.Mesh[] = [];
    this.surfaceMeshes.forEach(mesh => surfaceMeshes.push(mesh));

    const intersects = raycaster.intersectObjects(surfaceMeshes, false);

    if (intersects.length > 0) {
      const surfaceMesh = intersects[0].object as THREE.Mesh;
      for (const [id, mesh] of this.surfaceMeshes) {
        if (mesh === surfaceMesh) {
          return this.surfaces.get(id);
        }
      }
    }

    return undefined;
  }
}
