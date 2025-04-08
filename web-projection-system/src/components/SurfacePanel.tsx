import React from 'react';
import { Surface } from '../models/Surface';
import { formatWithUnit } from '../utils/projectionCalculations';
import './SurfacePanel.css';

interface SurfacePanelProps {
  surfaces: Surface[];
  activeSurfaceId: string | null;
  unitSystem: 'metric' | 'imperial' | 'millimeters';
  onAddSurface: () => void;
  onRemoveSurface: (id: string) => void;
  onUpdateSurface: (id: string, updates: Partial<Surface>) => void;
  onSelectSurface: (id: string | null) => void;
}

const SurfacePanel: React.FC<SurfacePanelProps> = ({
  surfaces,
  activeSurfaceId,
  unitSystem,
  onAddSurface,
  onRemoveSurface,
  onUpdateSurface,
  onSelectSurface
}) => {
  // Get the active surface
  const activeSurface = surfaces.find(s => s.id === activeSurfaceId);

  // Handle parameter updates
  const handleParameterChange = (
    parameter: keyof Surface['parameters'],
    value: any
  ) => {
    if (!activeSurfaceId || !activeSurface) return;

    // Create a copy of the surface to work with
    const surfaceCopy = new Surface(activeSurface.name);
    Object.assign(surfaceCopy, activeSurface);

    // Handle special cases
    switch (parameter) {
      case 'type':
        surfaceCopy.updateType(value);
        onUpdateSurface(activeSurfaceId, surfaceCopy);
        break;

      case 'width':
      case 'height':
        if (parameter === 'width') {
          surfaceCopy.updateDimensions(value, surfaceCopy.parameters.height);
        } else {
          surfaceCopy.updateDimensions(surfaceCopy.parameters.width, value);
        }
        onUpdateSurface(activeSurfaceId, surfaceCopy);
        break;

      case 'radius':
      case 'arc':
      case 'segments':
        // Update curved surface parameters
        const curvedParams: Partial<{ radius: number, arc: number, segments: number }> = {};
        curvedParams[parameter] = value;
        surfaceCopy.updateType(surfaceCopy.parameters.type, curvedParams);
        onUpdateSurface(activeSurfaceId, surfaceCopy);
        break;

      case 'position':
        surfaceCopy.updatePosition(value);
        onUpdateSurface(activeSurfaceId, surfaceCopy);
        break;

      case 'rotation':
        surfaceCopy.updateRotation(value);
        onUpdateSurface(activeSurfaceId, surfaceCopy);
        break;

      case 'material':
        surfaceCopy.updateMaterial(value);
        onUpdateSurface(activeSurfaceId, surfaceCopy);
        break;

      default:
        // For any other parameters, update directly
        const updatedParams = { ...surfaceCopy.parameters };
        // Use type assertion to handle the dynamic property access
        (updatedParams as any)[parameter] = value;
        surfaceCopy.parameters = updatedParams;
        onUpdateSurface(activeSurfaceId, surfaceCopy);
        break;
    }
  };

  return (
    <div className="surface-panel">
      <div className="panel-header">
        <h2>Surface Settings</h2>
        <button className="add-button" onClick={onAddSurface}>
          Add Surface
        </button>
      </div>

      <div className="surface-list">
        {surfaces.length === 0 ? (
          <div className="empty-state">No surfaces added yet</div>
        ) : (
          surfaces.map(surface => (
            <div
              key={surface.id}
              className={`surface-item ${surface.id === activeSurfaceId ? 'active' : ''}`}
              onClick={() => onSelectSurface(surface.id)}
            >
              <div className="surface-name">{surface.name}</div>
              <button
                className="remove-button"
                onClick={(e) => {
                  e.stopPropagation();
                  onRemoveSurface(surface.id);
                }}
              >
                ×
              </button>
            </div>
          ))
        )}
      </div>

      {activeSurface && (
        <div className="surface-details">
          <div className="parameter-group">
            <h3>Basic Parameters</h3>

            <div className="parameter-row">
              <label>Name:</label>
              <input
                type="text"
                value={activeSurface.name}
                onChange={(e) => onUpdateSurface(activeSurfaceId!, { name: e.target.value })}
              />
            </div>

            <div className="parameter-row">
              <label>Type:</label>
              <select
                value={activeSurface.parameters.type}
                onChange={(e) => handleParameterChange('type', e.target.value)}
              >
                <option value="flat">Flat</option>
                <option value="curved">Curved</option>
                <option value="cylindrical">Cylindrical</option>
                <option value="spherical">Spherical</option>
              </select>
            </div>

            <div className="parameter-row">
              <label>Width:</label>
              <div className="input-with-unit">
                <input
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={activeSurface.parameters.width}
                  onChange={(e) => handleParameterChange('width', parseFloat(e.target.value))}
                />
                <span className="unit">{unitSystem === 'metric' ? 'm' : 'ft'}</span>
              </div>
            </div>

            <div className="parameter-row">
              <label>Height:</label>
              <div className="input-with-unit">
                <input
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={activeSurface.parameters.height}
                  onChange={(e) => handleParameterChange('height', parseFloat(e.target.value))}
                />
                <span className="unit">{unitSystem === 'metric' ? 'm' : 'ft'}</span>
              </div>
            </div>
          </div>

          {activeSurface.parameters.type !== 'flat' && (
            <div className="parameter-group">
              <h3>Curved Surface Parameters</h3>

              <div className="parameter-row">
                <label>Radius:</label>
                <div className="input-with-unit">
                  <input
                    type="number"
                    min="0.1"
                    step="0.1"
                    value={activeSurface.parameters.radius || 5.0}
                    onChange={(e) => handleParameterChange('radius', parseFloat(e.target.value))}
                  />
                  <span className="unit">{unitSystem === 'metric' ? 'm' : 'ft'}</span>
                </div>
              </div>

              <div className="parameter-row">
                <label>Arc (degrees):</label>
                <input
                  type="number"
                  min="1"
                  max="360"
                  step="1"
                  value={(activeSurface.parameters.arc || Math.PI / 2) * (180 / Math.PI)}
                  onChange={(e) => handleParameterChange('arc', parseFloat(e.target.value) * (Math.PI / 180))}
                />
              </div>

              <div className="parameter-row">
                <label>Segments:</label>
                <input
                  type="number"
                  min="4"
                  max="128"
                  step="1"
                  value={activeSurface.parameters.segments || 32}
                  onChange={(e) => handleParameterChange('segments', parseInt(e.target.value))}
                />
              </div>
            </div>
          )}

          <div className="parameter-group">
            <h3>Position</h3>

            <div className="parameter-row">
              <label>X:</label>
              <div className="input-with-unit">
                <input
                  type="number"
                  step="0.1"
                  value={activeSurface.parameters.position.x}
                  onChange={(e) => handleParameterChange('position', { x: parseFloat(e.target.value) })}
                />
                <span className="unit">{unitSystem === 'metric' ? 'm' : 'ft'}</span>
              </div>
            </div>

            <div className="parameter-row">
              <label>Y:</label>
              <div className="input-with-unit">
                <input
                  type="number"
                  step="0.1"
                  value={activeSurface.parameters.position.y}
                  onChange={(e) => handleParameterChange('position', { y: parseFloat(e.target.value) })}
                />
                <span className="unit">{unitSystem === 'metric' ? 'm' : 'ft'}</span>
              </div>
            </div>

            <div className="parameter-row">
              <label>Z:</label>
              <div className="input-with-unit">
                <input
                  type="number"
                  step="0.1"
                  value={activeSurface.parameters.position.z}
                  onChange={(e) => handleParameterChange('position', { z: parseFloat(e.target.value) })}
                />
                <span className="unit">{unitSystem === 'metric' ? 'm' : 'ft'}</span>
              </div>
            </div>
          </div>

          <div className="parameter-group">
            <h3>Rotation (degrees)</h3>

            <div className="parameter-row">
              <label>X:</label>
              <input
                type="number"
                step="1"
                value={activeSurface.parameters.rotation.x}
                onChange={(e) => handleParameterChange('rotation', { x: parseFloat(e.target.value) })}
              />
            </div>

            <div className="parameter-row">
              <label>Y:</label>
              <input
                type="number"
                step="1"
                value={activeSurface.parameters.rotation.y}
                onChange={(e) => handleParameterChange('rotation', { y: parseFloat(e.target.value) })}
              />
            </div>

            <div className="parameter-row">
              <label>Z:</label>
              <input
                type="number"
                step="1"
                value={activeSurface.parameters.rotation.z}
                onChange={(e) => handleParameterChange('rotation', { z: parseFloat(e.target.value) })}
              />
            </div>
          </div>

          <div className="parameter-group">
            <h3>Material</h3>

            <div className="parameter-row">
              <label>Color:</label>
              <input
                type="color"
                value={activeSurface.parameters.material.color}
                onChange={(e) => handleParameterChange('material', { color: e.target.value })}
              />
            </div>

            <div className="parameter-row">
              <label>Gain:</label>
              <input
                type="range"
                min="0.1"
                max="2"
                step="0.1"
                value={activeSurface.parameters.material.gain}
                onChange={(e) => handleParameterChange('material', { gain: parseFloat(e.target.value) })}
              />
              <span className="value-display">
                {activeSurface.parameters.material.gain.toFixed(1)}
              </span>
            </div>

            <div className="parameter-row">
              <label>Reflection:</label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.01"
                value={activeSurface.parameters.material.reflection}
                onChange={(e) => handleParameterChange('material', { reflection: parseFloat(e.target.value) })}
              />
              <span className="value-display">
                {(activeSurface.parameters.material.reflection * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SurfacePanel;
