import * as THREE from 'three';
import { Projector } from '../models/Projector';
import { Surface } from '../models/Surface';

/**
 * Calculate throw ratio from distance and width
 * TR = D/W
 */
export function calculateThrowRatio(distance: number, width: number): number {
  if (width <= 0) return 0;
  return distance / width;
}

/**
 * Calculate image width from throw distance and throw ratio
 * W = D/TR
 */
export function calculateImageWidth(distance: number, throwRatio: number): number {
  if (throwRatio <= 0) return 0;
  return distance / throwRatio;
}

/**
 * Calculate throw distance from image width and throw ratio
 * D = W * TR
 */
export function calculateThrowDistance(width: number, throwRatio: number): number {
  return width * throwRatio;
}

/**
 * Calculate image height from width and aspect ratio
 * H = W * (AR_h / AR_w)
 */
export function calculateImageHeight(width: number, aspectRatioWidth: number, aspectRatioHeight: number): number {
  if (aspectRatioWidth <= 0) return 0;
  return width * (aspectRatioHeight / aspectRatioWidth);
}

/**
 * Calculate projection angle (horizontal field of view)
 * angle = 2 * atan(W / (2 * D))
 */
export function calculateProjectionAngle(width: number, distance: number): number {
  return Math.atan(width / (2 * distance)) * 2;
}

/**
 * Calculate vertical projection angle based on aspect ratio
 */
export function calculateVerticalProjectionAngle(horizontalAngle: number, aspectRatioWidth: number, aspectRatioHeight: number): number {
  if (aspectRatioWidth <= 0) return 0;
  const aspectRatio = aspectRatioHeight / aspectRatioWidth;
  return 2 * Math.atan(Math.tan(horizontalAngle / 2) * aspectRatio);
}

/**
 * Create projection cone geometry
 * @param projector The projector to create the cone for
 * @param targetSurface Optional target surface to project onto
 */
export function createProjectionConeGeometry(projector: Projector, targetSurface?: Surface): THREE.BufferGeometry {
  const { throwDistance, imageWidth } = projector.parameters;
  const imageHeight = projector.imageHeight;

  // If we have a target surface, we'll adjust the projection to hit that surface
  if (targetSurface) {
    // Create a geometry that projects onto the target surface
    return createProjectionToSurfaceGeometry(projector, targetSurface);
  }

  // Otherwise, create a standard projection cone
  // Create vertices for the cone - adjusted for Z-up
  const vertices = new Float32Array([
    // Projector lens point (apex of the cone)
    0, 0, 0,

    // Corners of the projection rectangle (Y is forward, Z is up)
    -imageWidth / 2, throwDistance, imageHeight / 2,  // Top-left
    imageWidth / 2, throwDistance, imageHeight / 2,   // Top-right
    imageWidth / 2, throwDistance, -imageHeight / 2,  // Bottom-right
    -imageWidth / 2, throwDistance, -imageHeight / 2  // Bottom-left
  ]);

  // Create faces (triangles)
  const indices = [
    0, 1, 2, // Front face (top triangle)
    0, 2, 3, // Front face (bottom triangle)
    0, 3, 4, // Right face
    0, 4, 1, // Back face
    1, 4, 3, // Bottom face (diagonal)
    1, 3, 2  // Bottom face (diagonal)
  ];

  // Create the geometry
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(vertices, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();

  return geometry;
}

/**
 * Create a projection geometry that projects onto a specific surface
 */
export function createProjectionToSurfaceGeometry(projector: Projector, surface: Surface): THREE.BufferGeometry {
  // Get projector position and rotation
  const projectorPos = new THREE.Vector3(
    projector.parameters.position.x,
    projector.parameters.position.y,
    projector.parameters.position.z
  );

  // Get projector rotation in radians
  const projectorRot = new THREE.Euler(
    THREE.MathUtils.degToRad(projector.parameters.rotation.x),
    THREE.MathUtils.degToRad(projector.parameters.rotation.y),
    THREE.MathUtils.degToRad(projector.parameters.rotation.z),
    'XYZ'
  );

  // Calculate direction vector based on rotation
  const direction = new THREE.Vector3(0, 1, 0); // Forward is along Y axis in our coordinate system
  const rotationMatrix = new THREE.Matrix4().makeRotationFromEuler(projectorRot);
  direction.applyMatrix4(rotationMatrix).normalize();

  // Create a temporary surface mesh to perform raycasting
  const surfaceGeometry = surface.createGeometry();
  const surfaceMaterial = new THREE.MeshBasicMaterial({ visible: false });
  const surfaceMesh = new THREE.Mesh(surfaceGeometry, surfaceMaterial);

  // Position and rotate the surface mesh
  surfaceMesh.position.set(
    surface.parameters.position.x,
    surface.parameters.position.y,
    surface.parameters.position.z
  );

  surfaceMesh.rotation.set(
    THREE.MathUtils.degToRad(surface.parameters.rotation.x),
    THREE.MathUtils.degToRad(surface.parameters.rotation.y),
    THREE.MathUtils.degToRad(surface.parameters.rotation.z)
  );

  // For flat surfaces, adjust position to align bottom with floor (Z=0)
  if (surface.parameters.type === 'flat') {
    const halfHeight = surface.parameters.height / 2;
    surfaceMesh.position.z += halfHeight;
  }

  // Create a raycaster
  const raycaster = new THREE.Raycaster();

  // Calculate the corners of the projection at the throw distance
  const { imageWidth, imageHeight, throwDistance } = projector.parameters;

  // Calculate the corners in projector local space
  const corners = [
    new THREE.Vector3(-imageWidth / 2, throwDistance, imageHeight / 2),  // Top-left
    new THREE.Vector3(imageWidth / 2, throwDistance, imageHeight / 2),   // Top-right
    new THREE.Vector3(imageWidth / 2, throwDistance, -imageHeight / 2),  // Bottom-right
    new THREE.Vector3(-imageWidth / 2, throwDistance, -imageHeight / 2), // Bottom-left
  ];

  // Transform corners to world space
  const worldCorners = corners.map(corner => {
    const worldCorner = corner.clone();
    worldCorner.applyEuler(projectorRot);
    worldCorner.add(projectorPos);
    return worldCorner;
  });

  // Cast rays from projector to each corner to find intersection with surface
  const intersectionPoints: THREE.Vector3[] = [projectorPos.clone()];

  worldCorners.forEach(corner => {
    // Calculate direction from projector to corner
    const rayDirection = corner.clone().sub(projectorPos).normalize();

    // Set up raycaster
    raycaster.set(projectorPos, rayDirection);

    // Check for intersection with surface
    const intersects = raycaster.intersectObject(surfaceMesh);

    if (intersects.length > 0) {
      // Use the intersection point
      intersectionPoints.push(intersects[0].point.clone());
    } else {
      // If no intersection, use the original corner
      intersectionPoints.push(corner);
    }
  });

  // Create vertices array from intersection points
  const vertices = new Float32Array(intersectionPoints.length * 3);

  intersectionPoints.forEach((point, i) => {
    vertices[i * 3] = point.x;
    vertices[i * 3 + 1] = point.y;
    vertices[i * 3 + 2] = point.z;
  });

  // Create indices for the cone faces
  const indices = [
    0, 1, 2, // Face 1
    0, 2, 3, // Face 2
    0, 3, 4, // Face 3
    0, 4, 1, // Face 4
    1, 4, 2, // Base triangle 1
    2, 4, 3  // Base triangle 2
  ];

  // Create the geometry
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(vertices, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();

  return geometry;
}

/**
 * Calculate UV mapping for curved surfaces
 */
export function calculateCurvedSurfaceUVMapping(surface: Surface, projector: Projector): THREE.BufferAttribute {
  // This is a simplified implementation
  // In a real-world scenario, we would need to perform ray-casting from the projector
  // to each point on the surface to determine the correct UV coordinates

  const geometry = surface.createGeometry();
  const positionAttribute = geometry.getAttribute('position');
  const count = positionAttribute.count;

  // Create UV array
  const uvs = new Float32Array(count * 2);

  // Get projector and surface positions
  const projectorPos = new THREE.Vector3(
    projector.parameters.position.x,
    projector.parameters.position.y,
    projector.parameters.position.z
  );

  const surfacePos = new THREE.Vector3(
    surface.parameters.position.x,
    surface.parameters.position.y,
    surface.parameters.position.z
  );

  // Calculate direction from projector to surface center
  const direction = new THREE.Vector3().subVectors(surfacePos, projectorPos).normalize();

  // Create a coordinate system for the projection - adjusted for Z-up
  const up = new THREE.Vector3(0, 0, 1); // Z is up
  const right = new THREE.Vector3().crossVectors(direction, up).normalize();
  up.crossVectors(right, direction).normalize();

  // For each vertex in the geometry
  for (let i = 0; i < count; i++) {
    const x = positionAttribute.getX(i);
    const y = positionAttribute.getY(i);
    const z = positionAttribute.getZ(i);

    // Create a vertex position in world space
    const vertex = new THREE.Vector3(x, y, z);

    // Calculate the ray from projector to this vertex
    const ray = new THREE.Vector3().subVectors(vertex, projectorPos).normalize();

    // Project the ray onto the right and up vectors to get UV coordinates
    const u = 0.5 + 0.5 * right.dot(ray);
    const v = 0.5 + 0.5 * up.dot(ray);

    // Set the UV coordinates
    uvs[i * 2] = u;
    uvs[i * 2 + 1] = v;
  }

  return new THREE.BufferAttribute(uvs, 2);
}

/**
 * Calculate edge blending between two projectors
 */
export function calculateEdgeBlending(projector1: Projector, projector2: Projector): {
  hasOverlap: boolean,
  overlapRegion?: {
    left: number,
    right: number,
    top: number,
    bottom: number
  }
} {
  // Calculate projection rectangles at the throw distance
  const rect1 = calculateProjectionRectangle(projector1);
  const rect2 = calculateProjectionRectangle(projector2);

  // Check if the rectangles overlap
  const hasOverlap = !(
    rect1.right < rect2.left ||
    rect1.left > rect2.right ||
    rect1.bottom < rect2.top ||
    rect1.top > rect2.bottom
  );

  if (!hasOverlap) {
    return { hasOverlap: false };
  }

  // Calculate the overlap region
  const overlapRegion = {
    left: Math.max(rect1.left, rect2.left),
    right: Math.min(rect1.right, rect2.right),
    top: Math.min(rect1.top, rect2.top),
    bottom: Math.max(rect1.bottom, rect2.bottom)
  };

  return { hasOverlap, overlapRegion };
}

/**
 * Calculate projection rectangle at the throw distance
 */
function calculateProjectionRectangle(projector: Projector) {
  const { position, throwDistance, imageWidth } = projector.parameters;
  const imageHeight = projector.imageHeight;

  // This is a simplified calculation assuming the projector is facing along the z-axis
  // In a real implementation, we would need to account for the projector's rotation

  const halfWidth = imageWidth / 2;
  const halfHeight = imageHeight / 2;

  return {
    left: position.x - halfWidth,
    right: position.x + halfWidth,
    top: position.y + halfHeight,
    bottom: position.y - halfHeight,
    z: position.z + throwDistance
  };
}

/**
 * Calculate blend factor for a point in the overlap region
 * Uses cosine falloff: α(x) = 0.5 * (1 + cos(π * (x - x0) / w))
 */
export function calculateBlendFactor(position: number, start: number, end: number): number {
  if (position <= start) return 1.0;
  if (position >= end) return 0.0;

  const width = end - start;
  const normalizedPosition = (position - start) / width;

  // Cosine falloff
  return 0.5 * (1 + Math.cos(Math.PI * normalizedPosition));
}

/**
 * Convert between metric and imperial units
 */
export function convertUnits(value: number, fromUnit: 'metric' | 'imperial', toUnit: 'metric' | 'imperial'): number {
  if (fromUnit === toUnit) return value;

  // Convert from metric to imperial (meters to feet)
  if (fromUnit === 'metric' && toUnit === 'imperial') {
    return value * 3.28084;
  }

  // Convert from imperial to metric (feet to meters)
  return value / 3.28084;
}

/**
 * Format a value with the appropriate unit
 */
export function formatWithUnit(value: number, unit: 'metric' | 'imperial' | 'millimeters'): string {
  if (unit === 'metric') {
    return `${value.toFixed(1)} m`;
  } else if (unit === 'millimeters') {
    // Convert meters to millimeters
    const mm = value * 1000;
    return `${Math.round(mm)} mm`;
  } else {
    // Imperial (feet)
    return `${value.toFixed(1)} ft`;
  }
}
