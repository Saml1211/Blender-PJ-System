import * as THREE from 'three';
import { v4 as uuidv4 } from 'uuid';

export interface AspectRatio {
  width: number;
  height: number;
}

export interface ProjectorPosition {
  x: number;
  y: number;
  z: number;
}

export interface ProjectorRotation {
  x: number;
  y: number;
  z: number;
}

export interface ProjectorBlending {
  enabled: boolean;
  amount: number;
  curve: 'linear' | 'cosine' | 'smoothstep';
}

export interface ProjectorParameters {
  throwRatio: number;
  aspectRatio: AspectRatio;
  throwDistance: number;
  imageWidth: number;
  imageHeight: number;
  brightness: number;
  position: ProjectorPosition;
  rotation: ProjectorRotation;
  blending: ProjectorBlending;
  showCone: boolean;
}

export class Projector {
  id: string;
  name: string;
  parameters: ProjectorParameters;
  mesh?: THREE.Group;
  projectionCone?: THREE.Mesh;
  isActive: boolean;
  collection: string;
  overlappingWith: string[];

  constructor(name: string, params?: Partial<ProjectorParameters>) {
    this.id = uuidv4();
    this.name = name;
    this.isActive = true;
    this.collection = '';
    this.overlappingWith = [];

    // Default parameters
    this.parameters = {
      throwRatio: 2.0,
      aspectRatio: { width: 16, height: 9 },
      throwDistance: 4.0,
      imageWidth: 2.0,
      imageHeight: 0, // Will be calculated below
      brightness: 1.0,
      position: { x: 0, y: 0, z: 0 },
      rotation: { x: 0, y: 0, z: 0 },
      blending: {
        enabled: false,
        amount: 0.2,
        curve: 'cosine'
      },
      showCone: true,
      ...params
    };

    // Calculate imageHeight based on aspect ratio if not provided
    if (!params?.imageHeight) {
      const { width, height } = this.parameters.aspectRatio;
      this.parameters.imageHeight = this.parameters.imageWidth * (height / width);
    }
  }

  // Calculate image height based on aspect ratio and width
  get imageHeight(): number {
    const { width, height } = this.parameters.aspectRatio;
    return this.parameters.imageWidth * (height / width);
  }

  // Calculate projection angle (horizontal field of view)
  get projectionAngle(): number {
    return Math.atan(this.parameters.imageWidth / (2 * this.parameters.throwDistance)) * 2;
  }

  // Update throw distance and recalculate dependent parameters
  updateThrowDistance(distance: number): void {
    this.parameters.throwDistance = distance;
    // When throw distance changes, update throw ratio (TR = D/W)
    if (this.parameters.imageWidth > 0) {
      this.parameters.throwRatio = distance / this.parameters.imageWidth;
    }
  }

  // Update image width and recalculate dependent parameters
  updateImageWidth(width: number): void {
    this.parameters.imageWidth = width;
    // When image width changes, update throw ratio (TR = D/W)
    if (width > 0) {
      this.parameters.throwRatio = this.parameters.throwDistance / width;

      // Update imageHeight based on aspect ratio
      const { width: aspectWidth, height: aspectHeight } = this.parameters.aspectRatio;
      this.parameters.imageHeight = width * (aspectHeight / aspectWidth);
    }
  }

  // Update throw ratio and recalculate dependent parameters
  updateThrowRatio(ratio: number): void {
    this.parameters.throwRatio = ratio;
    // When throw ratio changes, update image width (W = D/TR)
    if (ratio > 0) {
      this.parameters.imageWidth = this.parameters.throwDistance / ratio;

      // Update imageHeight based on aspect ratio
      const { width: aspectWidth, height: aspectHeight } = this.parameters.aspectRatio;
      this.parameters.imageHeight = this.parameters.imageWidth * (aspectHeight / aspectWidth);
    }
  }

  // Update aspect ratio
  updateAspectRatio(width: number, height: number): void {
    this.parameters.aspectRatio = { width, height };

    // Update imageHeight based on new aspect ratio
    this.parameters.imageHeight = this.parameters.imageWidth * (height / width);
  }

  // Update position
  updatePosition(position: Partial<ProjectorPosition>): void {
    this.parameters.position = { ...this.parameters.position, ...position };
  }

  // Update rotation
  updateRotation(rotation: Partial<ProjectorRotation>): void {
    this.parameters.rotation = { ...this.parameters.rotation, ...rotation };
  }

  // Toggle projection cone visibility
  toggleCone(show: boolean): void {
    this.parameters.showCone = show;
    if (this.projectionCone) {
      this.projectionCone.visible = show;
    }
  }

  // Update blending settings
  updateBlending(blending: Partial<ProjectorBlending>): void {
    this.parameters.blending = { ...this.parameters.blending, ...blending };
  }

  // Set collection
  setCollection(collection: string): void {
    this.collection = collection;
  }

  // Add overlapping projector
  addOverlap(projectorId: string): void {
    if (!this.overlappingWith.includes(projectorId)) {
      this.overlappingWith.push(projectorId);
    }
  }

  // Remove overlapping projector
  removeOverlap(projectorId: string): void {
    this.overlappingWith = this.overlappingWith.filter(id => id !== projectorId);
  }

  // Toggle active state
  toggleActive(active: boolean): void {
    this.isActive = active;
    if (this.mesh) {
      this.mesh.visible = active;
    }
  }
}
