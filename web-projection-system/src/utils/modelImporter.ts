import * as THREE from 'three';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader';
import { FBXLoader } from 'three/examples/jsm/loaders/FBXLoader';

export interface ImportOptions {
  scale?: number;
  position?: { x: number; y: number; z: number };
  rotation?: { x: number; y: number; z: number };
  onProgress?: (event: ProgressEvent) => void;
  onError?: (error: Error) => void;
}

export interface ImportResult {
  object: THREE.Object3D;
  format: 'obj' | 'fbx';
  filename: string;
}

/**
 * Import a 3D model from a file
 */
export async function importModel(
  file: File,
  options: ImportOptions = {}
): Promise<ImportResult> {
  const { scale = 1.0, position, rotation, onProgress, onError } = options;

  // Get file extension to determine loader
  const filename = file.name;
  const extension = filename.split('.').pop()?.toLowerCase();

  if (!extension) {
    throw new Error('Unable to determine file format');
  }

  // Create URL for the file
  const url = URL.createObjectURL(file);

  try {
    let object: THREE.Object3D;
    let format: 'obj' | 'fbx';

    // Load the model based on file extension
    if (extension === 'obj') {
      object = await loadOBJ(url, onProgress);
      format = 'obj';
    } else if (extension === 'fbx') {
      object = await loadFBX(url, onProgress);
      format = 'fbx';
    } else {
      throw new Error(`Unsupported file format: ${extension}`);
    }

    // Apply transformations
    object.scale.set(scale, scale, scale);

    if (position) {
      object.position.set(position.x, position.y, position.z);
    }

    if (rotation) {
      object.rotation.set(
        THREE.MathUtils.degToRad(rotation.x),
        THREE.MathUtils.degToRad(rotation.y),
        THREE.MathUtils.degToRad(rotation.z)
      );
    }

    // Clean up the URL
    URL.revokeObjectURL(url);

    return { object, format, filename };
  } catch (error) {
    // Clean up the URL
    URL.revokeObjectURL(url);

    // Handle error
    if (onError && error instanceof Error) {
      onError(error);
    }

    throw error;
  }
}

/**
 * Load an OBJ model
 */
function loadOBJ(
  url: string,
  onProgress?: (event: ProgressEvent) => void
): Promise<THREE.Object3D> {
  return new Promise((resolve, reject) => {
    const loader = new OBJLoader();

    loader.load(
      url,
      (object) => resolve(object),
      onProgress,
      (error) => reject(error)
    );
  });
}

/**
 * Load an FBX model
 */
function loadFBX(
  url: string,
  onProgress?: (event: ProgressEvent) => void
): Promise<THREE.Object3D> {
  return new Promise((resolve, reject) => {
    const loader = new FBXLoader();

    loader.load(
      url,
      (object) => resolve(object),
      onProgress,
      (error) => reject(error)
    );
  });
}

/**
 * Create a drag-and-drop handler for model import
 */
export function createDragDropHandler(
  element: HTMLElement,
  onImport: (result: ImportResult) => void,
  options: ImportOptions = {}
): () => void {
  const handleDragOver = (event: DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
  };

  const handleDrop = async (event: DragEvent) => {
    event.preventDefault();
    event.stopPropagation();

    if (!event.dataTransfer) return;

    const files = event.dataTransfer.files;

    if (files.length === 0) return;

    // Process only the first file
    const file = files[0];

    try {
      const result = await importModel(file, options);
      onImport(result);
    } catch (error) {
      console.error('Error importing model:', error);
      if (options.onError && error instanceof Error) {
        options.onError(error);
      }
    }
  };

  // Add event listeners
  element.addEventListener('dragover', handleDragOver as unknown as EventListener);
  element.addEventListener('drop', handleDrop as unknown as EventListener);

  // Return a cleanup function
  return () => {
    element.removeEventListener('dragover', handleDragOver as unknown as EventListener);
    element.removeEventListener('drop', handleDrop as unknown as EventListener);
  };
}
