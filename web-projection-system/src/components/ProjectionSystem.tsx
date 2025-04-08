import React, { useEffect, useRef, useState } from 'react';
import { useTheme } from '../context/ThemeContext';
import * as THREE from 'three';
import { useProjectionStore } from '../store/projectionStore';
import { SceneManager } from '../utils/sceneManager';
import { Projector } from '../models/Projector';
import { Surface } from '../models/Surface';
import { ProjectorCollection } from '../models/ProjectorCollection';
import { createDragDropHandler, ImportResult } from '../utils/modelImporter';
import { v4 as uuidv4 } from 'uuid';

import './ProjectionSystem.css';
import ControlPanel from './ControlPanel';
import ProjectorPanel from './ProjectorPanel';
import SurfacePanel from './SurfacePanel';
import MultiProjectorPanel from './MultiProjectorPanel';
import ImportPanel from './ImportPanel';

const ProjectionSystem: React.FC = () => {
  // Refs
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneManagerRef = useRef<SceneManager | null>(null);

  // State
  const [activeTab, setActiveTab] = useState<'projector' | 'surface' | 'multi' | 'import'>('projector');
  const [isImporting, setIsImporting] = useState(false);
  const [importProgress, setImportProgress] = useState(0);
  const [snapToGrid, setSnapToGrid] = useState(false);
  const [gridSize, setGridSize] = useState(0.5);
  const [measurementActive, setMeasurementActive] = useState(false);

  // Store state
  const {
    projectors,
    activeProjectorId,
    surfaces,
    activeSurfaceId,
    collections,
    activeCollectionId,
    unitSystem,
    showGrid,
    showAxes,
    showMeasurements,
    addProjector,
    removeProjector,
    updateProjector,
    setActiveProjector,
    addSurface,
    removeSurface,
    updateSurface,
    setActiveSurface,
    addCollection,
    removeCollection,
    updateCollection,
    setActiveCollection,
    addProjectorToCollection,
    removeProjectorFromCollection,
    setUnitSystem,
    toggleGrid,
    toggleAxes,
    toggleMeasurements
  } = useProjectionStore();

  // Initialize scene
  useEffect(() => {
    if (containerRef.current && !sceneManagerRef.current) {
      sceneManagerRef.current = new SceneManager(containerRef.current);

      // Set up drag-and-drop for model import
      const cleanup = createDragDropHandler(
        containerRef.current,
        handleModelImport,
        {
          onProgress: (event) => {
            if (event.lengthComputable) {
              setImportProgress(Math.round((event.loaded / event.total) * 100));
            }
          },
          onError: (error) => {
            console.error('Error importing model:', error);
            setIsImporting(false);
          }
        }
      );

      return cleanup;
    }
  }, []);

  // Update scene when projectors change
  useEffect(() => {
    if (!sceneManagerRef.current) return;

    // Add new projectors to scene
    projectors.forEach(projector => {
      if (!sceneManagerRef.current) return;

      if (!sceneManagerRef.current.projectorMeshes.has(projector.id)) {
        sceneManagerRef.current.addProjector(projector);
      } else {
        sceneManagerRef.current.updateProjector(projector);
      }
    });

    // Remove deleted projectors from scene
    Array.from(sceneManagerRef.current.projectorMeshes.keys()).forEach(id => {
      if (!projectors.some(p => p.id === id)) {
        sceneManagerRef.current?.removeProjector(id);
      }
    });

    // Update active projector
    if (activeProjectorId) {
      // Clear any active surface selection
      if (activeSurfaceId) {
        setActiveSurface(null);
      }
      sceneManagerRef.current.setActiveObject(activeProjectorId, 'projector');
    }
  }, [projectors, activeProjectorId, activeSurfaceId, setActiveSurface]);

  // Update scene when surfaces change
  useEffect(() => {
    if (!sceneManagerRef.current) return;

    // Add new surfaces to scene
    surfaces.forEach(surface => {
      if (!sceneManagerRef.current) return;

      if (!sceneManagerRef.current.surfaceMeshes.has(surface.id)) {
        sceneManagerRef.current.addSurface(surface);
      } else {
        sceneManagerRef.current.updateSurface(surface);
      }
    });

    // Remove deleted surfaces from scene
    Array.from(sceneManagerRef.current.surfaceMeshes.keys()).forEach(id => {
      if (!surfaces.some(s => s.id === id)) {
        sceneManagerRef.current?.removeSurface(id);
      }
    });

    // Update active surface
    if (activeSurfaceId) {
      // Clear any active projector selection
      if (activeProjectorId) {
        setActiveProjector(null);
      }
      sceneManagerRef.current.setActiveObject(activeSurfaceId, 'surface');
    }
  }, [surfaces, activeSurfaceId, activeProjectorId, setActiveProjector]);

  // Update scene when UI settings change
  useEffect(() => {
    if (!sceneManagerRef.current) return;

    sceneManagerRef.current.toggleGrid(showGrid);
    sceneManagerRef.current.toggleAxes(showAxes);
  }, [showGrid, showAxes]);

  // Update snap-to-grid settings
  useEffect(() => {
    if (!sceneManagerRef.current) return;

    sceneManagerRef.current.toggleSnapToGrid(snapToGrid);
  }, [snapToGrid]);

  // Update grid size
  useEffect(() => {
    if (!sceneManagerRef.current) return;

    sceneManagerRef.current.setGridSize(gridSize);
  }, [gridSize]);

  // Update measurement tool
  useEffect(() => {
    if (!sceneManagerRef.current) return;

    sceneManagerRef.current.toggleMeasurementTool(measurementActive);
  }, [measurementActive]);

  // Update measurement tool unit system
  useEffect(() => {
    if (!sceneManagerRef.current) return;

    sceneManagerRef.current.updateMeasurementUnitSystem(unitSystem);
  }, [unitSystem]);

  // Get theme from context
  const { theme } = useTheme();

  // Update theme in scene manager
  useEffect(() => {
    if (!sceneManagerRef.current) return;

    sceneManagerRef.current.updateTheme(theme === 'dark');
  }, [theme]);

  // Listen for transform changes from the scene manager
  useEffect(() => {
    const handleTransformChange = (event: CustomEvent) => {
      const { id, type, position, rotation } = event.detail;
      console.log('Transform change event received:', { id, type, position, rotation });

      if (type === 'projector') {
        const projector = projectors.find(p => p.id === id);
        if (projector) {
          // Create a deep copy of the projector to update
          const updatedProjector = new Projector(projector.name);

          // Copy all properties
          updatedProjector.id = projector.id;
          updatedProjector.collection = projector.collection;
          updatedProjector.isActive = projector.isActive;
          updatedProjector.overlappingWith = [...projector.overlappingWith];
          updatedProjector.parameters = JSON.parse(JSON.stringify(projector.parameters));

          // Update position and rotation with the new values
          updatedProjector.updatePosition(position);
          updatedProjector.updateRotation(rotation);

          console.log('Updating projector:', {
            id,
            oldPosition: projector.parameters.position,
            newPosition: updatedProjector.parameters.position,
            oldRotation: projector.parameters.rotation,
            newRotation: updatedProjector.parameters.rotation
          });

          // Update the store
          updateProjector(id, updatedProjector);
        }
      } else if (type === 'surface') {
        const surface = surfaces.find(s => s.id === id);
        if (surface) {
          // Create a deep copy of the surface to update
          const updatedSurface = new Surface(surface.name);

          // Copy all properties
          updatedSurface.id = surface.id;
          updatedSurface.parameters = JSON.parse(JSON.stringify(surface.parameters));

          // Update position and rotation with the new values
          updatedSurface.updatePosition(position);
          updatedSurface.updateRotation(rotation);

          console.log('Updating surface:', {
            id,
            oldPosition: surface.parameters.position,
            newPosition: updatedSurface.parameters.position,
            oldRotation: surface.parameters.rotation,
            newRotation: updatedSurface.parameters.rotation
          });

          // Update the store
          updateSurface(id, updatedSurface);
        }
      }
    };

    // Add event listener
    window.addEventListener('object-transform-changed', handleTransformChange as EventListener);

    // Clean up
    return () => {
      window.removeEventListener('object-transform-changed', handleTransformChange as EventListener);
    };
  }, [projectors, surfaces, updateProjector, updateSurface]);

  // Handle model import
  const handleModelImport = (result: ImportResult) => {
    setIsImporting(false);

    // Add the imported model to the scene
    const modelId = uuidv4();
    sceneManagerRef.current?.addImportedModel(modelId, result.object);
  };

  // Handle adding a new projector
  const handleAddProjector = () => {
    const newProjector = new Projector(`Projector ${projectors.length + 1}`);
    addProjector(newProjector);
  };

  // Handle adding a new surface
  const handleAddSurface = () => {
    // Only allow adding a surface if at least one projector exists
    if (projectors.length === 0) {
      alert('Please add at least one projector before adding a surface.');
      return;
    }

    // Create a new surface
    const newSurface = new Surface(`Surface ${surfaces.length + 1}`);

    // If there's an active projector, position the surface in front of it
    if (activeProjectorId) {
      const activeProjector = projectors.find(p => p.id === activeProjectorId);
      if (activeProjector && sceneManagerRef.current) {
        // Calculate the position in front of the projector
        // We'll use the projector's position and rotation to determine where to place the surface
        const projectorPos = activeProjector.parameters.position;
        const projectorRot = activeProjector.parameters.rotation;

        // Convert rotation from degrees to radians
        const rotX = THREE.MathUtils.degToRad(projectorRot.x);
        const rotY = THREE.MathUtils.degToRad(projectorRot.y);
        const rotZ = THREE.MathUtils.degToRad(projectorRot.z);

        // Calculate direction vector based on rotation
        // For Z-up, we need to adjust how we calculate the direction
        const direction = new THREE.Vector3(0, 1, 0); // Forward is along Y axis in our coordinate system
        const rotationMatrix = new THREE.Matrix4().makeRotationFromEuler(
          new THREE.Euler(rotX, rotY, rotZ, 'XYZ')
        );
        direction.applyMatrix4(rotationMatrix).normalize();

        // Calculate distance based on projector's throw ratio and image width
        const throwRatio = activeProjector.parameters.throwRatio;
        const imageWidth = activeProjector.parameters.imageWidth;
        const distance = throwRatio * imageWidth;

        // Calculate surface position
        const surfacePos = {
          x: projectorPos.x + direction.x * distance,
          y: projectorPos.y + direction.y * distance,
          z: projectorPos.z + direction.z * distance
        };

        // Set surface dimensions based on projector's image size
        newSurface.parameters.width = activeProjector.parameters.imageWidth;
        newSurface.parameters.height = activeProjector.parameters.imageHeight;

        // Set surface position
        newSurface.parameters.position = surfacePos;

        // Set surface rotation to face the projector
        // We need to rotate the surface to face back toward the projector
        newSurface.parameters.rotation = {
          // Invert the projector's rotation to make the surface face it
          x: projectorRot.x + 180,
          y: projectorRot.y,
          z: projectorRot.z
        };
      }
    }

    // Add the surface to the store
    addSurface(newSurface);

    // Set it as the active surface
    setActiveSurface(newSurface.id);
  };

  // Handle adding a new collection
  const handleAddCollection = () => {
    const newCollection = new ProjectorCollection(`Collection ${collections.length + 1}`);
    addCollection(newCollection);
  };

  return (
    <div className="projection-system">
      <div className="viewport" ref={containerRef}>
        {isImporting && (
          <div className="import-overlay">
            <div className="import-progress">
              <div className="progress-bar" style={{ width: `${importProgress}%` }}></div>
            </div>
            <div className="import-text">Importing model: {importProgress}%</div>
          </div>
        )}
      </div>

      <div className="control-container">
        <div className="tabs">
          <button
            className={activeTab === 'projector' ? 'active' : ''}
            onClick={() => setActiveTab('projector')}
          >
            Projector
          </button>
          <button
            className={activeTab === 'surface' ? 'active' : ''}
            onClick={() => setActiveTab('surface')}
          >
            Surface
          </button>
          <button
            className={activeTab === 'multi' ? 'active' : ''}
            onClick={() => setActiveTab('multi')}
          >
            Multi-Projector
          </button>
          <button
            className={activeTab === 'import' ? 'active' : ''}
            onClick={() => setActiveTab('import')}
          >
            Import
          </button>
        </div>

        <div className="panel-container">
          {activeTab === 'projector' && (
            <ProjectorPanel
              projectors={projectors}
              activeProjectorId={activeProjectorId}
              unitSystem={unitSystem}
              onAddProjector={handleAddProjector}
              onRemoveProjector={removeProjector}
              onUpdateProjector={(id, updates) => {
                const projector = projectors.find(p => p.id === id);
                if (projector) {
                  updateProjector(id, updates);
                  if (sceneManagerRef.current) {
                    sceneManagerRef.current.updateProjector(projector);
                  }
                }
              }}
              onSelectProjector={setActiveProjector}
            />
          )}

          {activeTab === 'surface' && (
            <SurfacePanel
              surfaces={surfaces}
              activeSurfaceId={activeSurfaceId}
              unitSystem={unitSystem}
              onAddSurface={handleAddSurface}
              onRemoveSurface={removeSurface}
              onUpdateSurface={(id, updates) => {
                const surface = surfaces.find(s => s.id === id);
                if (surface) {
                  updateSurface(id, updates);
                  if (sceneManagerRef.current) {
                    sceneManagerRef.current.updateSurface(surface);
                  }
                }
              }}
              onSelectSurface={setActiveSurface}
            />
          )}

          {activeTab === 'multi' && (
            <MultiProjectorPanel
              collections={collections}
              activeCollectionId={activeCollectionId}
              projectors={projectors}
              onAddCollection={handleAddCollection}
              onRemoveCollection={removeCollection}
              onUpdateCollection={updateCollection}
              onSelectCollection={setActiveCollection}
              onAddProjectorToCollection={addProjectorToCollection}
              onRemoveProjectorFromCollection={removeProjectorFromCollection}
            />
          )}

          {activeTab === 'import' && (
            <ImportPanel
              onImportStart={() => setIsImporting(true)}
              onImportComplete={() => setIsImporting(false)}
            />
          )}
        </div>

        <ControlPanel
          unitSystem={unitSystem}
          showGrid={showGrid}
          showAxes={showAxes}
          showMeasurements={showMeasurements}
          snapToGrid={snapToGrid}
          gridSize={gridSize}
          measurementActive={measurementActive}
          onUnitSystemChange={setUnitSystem}
          onToggleGrid={toggleGrid}
          onToggleAxes={toggleAxes}
          onToggleMeasurements={toggleMeasurements}
          onToggleSnapToGrid={setSnapToGrid}
          onSetGridSize={setGridSize}
          onToggleMeasurementTool={setMeasurementActive}
          onSetTransformMode={(mode) => {
            if (sceneManagerRef.current) {
              sceneManagerRef.current.setTransformMode(mode);
            }
          }}
        />
      </div>
    </div>
  );
};

export default ProjectionSystem;
