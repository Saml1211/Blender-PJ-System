import * as THREE from 'three';
import { ParametricGeometry } from 'three/examples/jsm/geometries/ParametricGeometry';
import { v4 as uuidv4 } from 'uuid';

export type SurfaceType = 'flat' | 'curved' | 'cylindrical' | 'spherical';

export interface SurfaceParameters {
  type: SurfaceType;
  width: number;
  height: number;
  radius?: number;
  arc?: number;
  segments?: number;
  position: {
    x: number;
    y: number;
    z: number;
  };
  rotation: {
    x: number;
    y: number;
    z: number;
  };
  material: {
    color: string;
    gain: number;
    reflection: number;
  };
}

export class Surface {
  id: string;
  name: string;
  parameters: SurfaceParameters;
  mesh?: THREE.Mesh;

  constructor(name: string, params?: Partial<SurfaceParameters>) {
    this.id = uuidv4();
    this.name = name;

    // Default parameters
    this.parameters = {
      type: 'flat',
      width: 4.0,
      height: 2.25,
      position: { x: 0, y: 0, z: 5 },
      rotation: { x: 0, y: 0, z: 0 },
      material: {
        color: '#ffffff',
        gain: 1.0,
        reflection: 0.1
      },
      ...params
    };

    // Add default parameters for curved surfaces
    if (this.parameters.type !== 'flat') {
      this.parameters.radius = this.parameters.radius || 5.0;
      this.parameters.arc = this.parameters.arc || Math.PI / 2;
      this.parameters.segments = this.parameters.segments || 32;
    }
  }

  // Update surface dimensions
  updateDimensions(width: number, height: number): void {
    this.parameters.width = width;
    this.parameters.height = height;
  }

  // Update surface position
  updatePosition(position: Partial<{ x: number, y: number, z: number }>): void {
    this.parameters.position = { ...this.parameters.position, ...position };
  }

  // Update surface rotation
  updateRotation(rotation: Partial<{ x: number, y: number, z: number }>): void {
    this.parameters.rotation = { ...this.parameters.rotation, ...rotation };
  }

  // Update surface type and related parameters
  updateType(type: SurfaceType, params?: Partial<{ radius: number, arc: number, segments: number }>): void {
    this.parameters.type = type;

    if (type !== 'flat') {
      this.parameters.radius = params?.radius || this.parameters.radius || 5.0;
      this.parameters.arc = params?.arc || this.parameters.arc || Math.PI / 2;
      this.parameters.segments = params?.segments || this.parameters.segments || 32;
    }
  }

  // Update material properties
  updateMaterial(material: Partial<{ color: string, gain: number, reflection: number }>): void {
    this.parameters.material = { ...this.parameters.material, ...material };
  }

  // Create geometry based on surface type
  createGeometry(): THREE.BufferGeometry {
    switch (this.parameters.type) {
      case 'flat':
        // Create a plane geometry with Z as up axis
        // By default, PlaneGeometry is created in the XY plane with normal along Z
        // For Z-up, we want the plane to be in the XZ plane with normal along Y
        const planeGeometry = new THREE.PlaneGeometry(
          this.parameters.width,
          this.parameters.height,
          1,
          1
        );

        // Rotate the geometry to align with Z-up orientation
        // This rotates the plane to be in the XZ plane
        planeGeometry.rotateX(-Math.PI / 2);

        return planeGeometry;

      case 'curved':
        return this.createCurvedGeometry();

      case 'cylindrical':
        return this.createCylindricalGeometry();

      case 'spherical':
        return this.createSphericalGeometry();

      default:
        const defaultPlaneGeometry = new THREE.PlaneGeometry(
          this.parameters.width,
          this.parameters.height,
          1,
          1
        );
        defaultPlaneGeometry.rotateX(-Math.PI / 2);
        return defaultPlaneGeometry;
    }
  }

  // Create curved surface geometry
  private createCurvedGeometry(): THREE.BufferGeometry {
    if (!this.parameters.radius || !this.parameters.arc || !this.parameters.segments) {
      // Return a flat plane rotated for Z-up
      const planeGeometry = new THREE.PlaneGeometry(this.parameters.width, this.parameters.height);
      planeGeometry.rotateX(-Math.PI / 2);
      return planeGeometry;
    }

    const { width, height, radius, arc, segments } = this.parameters;

    // Create a parametric geometry for the curved surface
    // For Z-up, we need to adjust the parametric function
    const parametricFunction = (u: number, v: number, target: THREE.Vector3): void => {
      const theta = arc * (u - 0.5);
      // For Z-up, what was previously y becomes z
      const z = height * (v - 0.5);

      // Adjust coordinates for Z-up orientation
      // X remains the same, Y becomes what was Z, Z becomes what was Y
      target.set(
        radius * Math.sin(theta),  // X remains the same
        radius * Math.cos(theta),  // Y was Z in Y-up
        z                          // Z was Y in Y-up
      );
    };

    const geometry = new ParametricGeometry(
      parametricFunction,
      segments,
      Math.floor(segments * height / width)
    );

    return geometry;
  }

  // Create cylindrical surface geometry
  private createCylindricalGeometry(): THREE.BufferGeometry {
    if (!this.parameters.radius || !this.parameters.arc || !this.parameters.segments) {
      // Return a flat plane rotated for Z-up
      const planeGeometry = new THREE.PlaneGeometry(this.parameters.width, this.parameters.height);
      planeGeometry.rotateX(-Math.PI / 2);
      return planeGeometry;
    }

    const { height, radius, arc, segments } = this.parameters;

    // Create a cylindrical geometry
    const geometry = new THREE.CylinderGeometry(
      radius,
      radius,
      height,
      segments,
      1,
      true,
      -arc / 2,
      arc
    );

    // For Z-up, we need to rotate differently
    // By default, CylinderGeometry is created with its axis along the Y axis
    // For Z-up, we want to keep it that way, but rotate it to face the right direction
    // No need to rotate for Z-up as the default orientation works with our Z-up system

    return geometry;
  }

  // Create spherical surface geometry
  private createSphericalGeometry(): THREE.BufferGeometry {
    if (!this.parameters.radius || !this.parameters.arc || !this.parameters.segments) {
      // Return a flat plane rotated for Z-up
      const planeGeometry = new THREE.PlaneGeometry(this.parameters.width, this.parameters.height);
      planeGeometry.rotateX(-Math.PI / 2);
      return planeGeometry;
    }

    const { radius, arc, segments } = this.parameters;

    // Create a spherical geometry
    const geometry = new THREE.SphereGeometry(
      radius,
      segments,
      Math.floor(segments / 2),
      0,
      arc,
      0,
      arc / 2
    );

    return geometry;
  }

  // Create material based on surface properties
  createMaterial(): THREE.Material {
    const { color, gain, reflection } = this.parameters.material;

    return new THREE.MeshStandardMaterial({
      color: new THREE.Color(color),
      roughness: 1 - reflection,
      metalness: 0,
      side: THREE.DoubleSide
    });
  }
}
