import React from 'react';
import { Projector } from '../models/Projector';
import { formatWithUnit } from '../utils/projectionCalculations';
import './ProjectorPanel.css';

interface ProjectorPanelProps {
  projectors: Projector[];
  activeProjectorId: string | null;
  unitSystem: 'metric' | 'imperial' | 'millimeters';
  onAddProjector: () => void;
  onRemoveProjector: (id: string) => void;
  onUpdateProjector: (id: string, updates: Partial<Projector>) => void;
  onSelectProjector: (id: string | null) => void;
}

const ProjectorPanel: React.FC<ProjectorPanelProps> = ({
  projectors,
  activeProjectorId,
  unitSystem,
  onAddProjector,
  onRemoveProjector,
  onUpdateProjector,
  onSelectProjector
}) => {
  // Get the active projector
  const activeProjector = projectors.find(p => p.id === activeProjectorId);

  // Handle parameter updates
  const handleParameterChange = (
    parameter: keyof Projector['parameters'],
    value: any
  ) => {
    if (!activeProjectorId || !activeProjector) return;

    // Create a copy of the projector to work with
    const projectorCopy = new Projector(activeProjector.name);
    Object.assign(projectorCopy, activeProjector);

    // Handle special cases for linked parameters
    switch (parameter) {
      case 'throwDistance':
        projectorCopy.updateThrowDistance(value);
        onUpdateProjector(activeProjectorId, projectorCopy);
        break;

      case 'imageWidth':
        projectorCopy.updateImageWidth(value);
        onUpdateProjector(activeProjectorId, projectorCopy);
        break;

      case 'throwRatio':
        projectorCopy.updateThrowRatio(value);
        onUpdateProjector(activeProjectorId, projectorCopy);
        break;

      case 'aspectRatio':
        const [width, height] = value.split(':').map(Number);
        projectorCopy.updateAspectRatio(width, height);
        onUpdateProjector(activeProjectorId, projectorCopy);
        break;

      case 'position':
        projectorCopy.updatePosition(value);
        onUpdateProjector(activeProjectorId, projectorCopy);
        break;

      case 'rotation':
        projectorCopy.updateRotation(value);
        onUpdateProjector(activeProjectorId, projectorCopy);
        break;

      case 'showCone':
        projectorCopy.toggleCone(value);
        onUpdateProjector(activeProjectorId, projectorCopy);
        break;

      case 'blending':
        projectorCopy.updateBlending(value);
        onUpdateProjector(activeProjectorId, projectorCopy);
        break;

      default:
        // For any other parameters, update directly
        const updatedParams = { ...projectorCopy.parameters };
        // Use type assertion to handle the dynamic property access
        (updatedParams as any)[parameter] = value;
        projectorCopy.parameters = updatedParams;
        onUpdateProjector(activeProjectorId, projectorCopy);
        break;
    }
  };

  return (
    <div className="projector-panel">
      <div className="panel-header">
        <h2>Projector Settings</h2>
        <button className="add-button" onClick={onAddProjector}>
          Add Projector
        </button>
      </div>

      <div className="projector-list">
        {projectors.length === 0 ? (
          <div className="empty-state">No projectors added yet</div>
        ) : (
          projectors.map(projector => (
            <div
              key={projector.id}
              className={`projector-item ${projector.id === activeProjectorId ? 'active' : ''}`}
              onClick={() => onSelectProjector(projector.id)}
            >
              <div className="projector-name">{projector.name}</div>
              <button
                className="remove-button"
                onClick={(e) => {
                  e.stopPropagation();
                  onRemoveProjector(projector.id);
                }}
              >
                ×
              </button>
            </div>
          ))
        )}
      </div>

      {activeProjector && (
        <div className="projector-details">
          <div className="parameter-group">
            <h3>Basic Parameters</h3>

            <div className="parameter-row">
              <label>Name:</label>
              <input
                type="text"
                value={activeProjector.name}
                onChange={(e) => onUpdateProjector(activeProjectorId!, { name: e.target.value })}
              />
            </div>

            <div className="parameter-row">
              <label>Throw Distance:</label>
              <div className="input-with-unit">
                <input
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={activeProjector.parameters.throwDistance}
                  onChange={(e) => handleParameterChange('throwDistance', parseFloat(e.target.value))}
                />
                <span className="unit">{unitSystem === 'metric' ? 'm' : 'ft'}</span>
              </div>
            </div>

            <div className="parameter-row">
              <label>Image Width:</label>
              <div className="input-with-unit">
                <input
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={activeProjector.parameters.imageWidth}
                  onChange={(e) => handleParameterChange('imageWidth', parseFloat(e.target.value))}
                />
                <span className="unit">{unitSystem === 'metric' ? 'm' : 'ft'}</span>
              </div>
            </div>

            <div className="parameter-row">
              <label>Throw Ratio:</label>
              <input
                type="number"
                min="0.1"
                step="0.1"
                value={activeProjector.parameters.throwRatio}
                onChange={(e) => handleParameterChange('throwRatio', parseFloat(e.target.value))}
              />
            </div>

            <div className="parameter-row">
              <label>Aspect Ratio:</label>
              <select
                value={`${activeProjector.parameters.aspectRatio.width}:${activeProjector.parameters.aspectRatio.height}`}
                onChange={(e) => handleParameterChange('aspectRatio', e.target.value)}
              >
                <option value="16:9">16:9 (HD/UHD)</option>
                <option value="16:10">16:10 (WUXGA)</option>
                <option value="4:3">4:3 (XGA)</option>
                <option value="2.35:1">2.35:1 (Cinemascope)</option>
              </select>
            </div>

            <div className="parameter-row">
              <label>Show Cone:</label>
              <input
                type="checkbox"
                checked={activeProjector.parameters.showCone}
                onChange={(e) => handleParameterChange('showCone', e.target.checked)}
              />
            </div>
          </div>

          <div className="parameter-group">
            <h3>Position</h3>

            <div className="parameter-row">
              <label>X:</label>
              <div className="input-with-unit">
                <input
                  type="number"
                  step="0.1"
                  value={activeProjector.parameters.position.x}
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
                  value={activeProjector.parameters.position.y}
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
                  value={activeProjector.parameters.position.z}
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
                value={activeProjector.parameters.rotation.x}
                onChange={(e) => handleParameterChange('rotation', { x: parseFloat(e.target.value) })}
              />
            </div>

            <div className="parameter-row">
              <label>Y:</label>
              <input
                type="number"
                step="1"
                value={activeProjector.parameters.rotation.y}
                onChange={(e) => handleParameterChange('rotation', { y: parseFloat(e.target.value) })}
              />
            </div>

            <div className="parameter-row">
              <label>Z:</label>
              <input
                type="number"
                step="1"
                value={activeProjector.parameters.rotation.z}
                onChange={(e) => handleParameterChange('rotation', { z: parseFloat(e.target.value) })}
              />
            </div>
          </div>

          <div className="parameter-group">
            <h3>Edge Blending</h3>

            <div className="parameter-row">
              <label>Enabled:</label>
              <input
                type="checkbox"
                checked={activeProjector.parameters.blending.enabled}
                onChange={(e) => handleParameterChange('blending', {
                  ...activeProjector.parameters.blending,
                  enabled: e.target.checked
                })}
              />
            </div>

            <div className="parameter-row">
              <label>Amount:</label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.01"
                value={activeProjector.parameters.blending.amount}
                onChange={(e) => handleParameterChange('blending', {
                  ...activeProjector.parameters.blending,
                  amount: parseFloat(e.target.value)
                })}
              />
              <span className="value-display">
                {(activeProjector.parameters.blending.amount * 100).toFixed(0)}%
              </span>
            </div>

            <div className="parameter-row">
              <label>Curve:</label>
              <select
                value={activeProjector.parameters.blending.curve}
                onChange={(e) => handleParameterChange('blending', {
                  ...activeProjector.parameters.blending,
                  curve: e.target.value as 'linear' | 'cosine' | 'smoothstep'
                })}
              >
                <option value="linear">Linear</option>
                <option value="cosine">Cosine</option>
                <option value="smoothstep">Smoothstep</option>
              </select>
            </div>
          </div>

          <div className="parameter-group">
            <h3>Calculated Values</h3>

            <div className="info-row">
              <label>Image Height:</label>
              <span>{formatWithUnit(activeProjector.imageHeight, unitSystem)}</span>
            </div>

            <div className="info-row">
              <label>Projection Angle:</label>
              <span>{(activeProjector.projectionAngle * (180 / Math.PI)).toFixed(1)}°</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProjectorPanel;
