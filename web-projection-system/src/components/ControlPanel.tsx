import React from 'react';
import './ControlPanel.css';
import ProjectManager from './ProjectManager';
import ThemeToggle from './ThemeToggle';

interface ControlPanelProps {
  unitSystem: 'metric' | 'imperial' | 'millimeters';
  showGrid: boolean;
  showAxes: boolean;
  showMeasurements: boolean;
  snapToGrid: boolean;
  gridSize: number;
  measurementActive: boolean;
  onUnitSystemChange: (system: 'metric' | 'imperial' | 'millimeters') => void;
  onToggleGrid: (show: boolean) => void;
  onToggleAxes: (show: boolean) => void;
  onToggleMeasurements: (show: boolean) => void;
  onToggleSnapToGrid: (enabled: boolean) => void;
  onSetGridSize: (size: number) => void;
  onToggleMeasurementTool: (active: boolean) => void;
  onSetTransformMode: (mode: 'translate' | 'rotate' | 'scale') => void;
}

const ControlPanel: React.FC<ControlPanelProps> = ({
  unitSystem,
  showGrid,
  showAxes,
  showMeasurements,
  snapToGrid,
  gridSize,
  measurementActive,
  onUnitSystemChange,
  onToggleGrid,
  onToggleAxes,
  onToggleMeasurements,
  onToggleSnapToGrid,
  onSetGridSize,
  onToggleMeasurementTool,
  onSetTransformMode
}) => {
  return (
    <div className="control-panel">
      <div className="control-section">
        <h3>Display Settings</h3>

        <div className="control-row theme-row">
          <label>Theme:</label>
          <ThemeToggle />
        </div>

        <div className="control-row">
          <label>Unit System:</label>
          <div className="toggle-buttons unit-buttons">
            <button
              className={unitSystem === 'metric' ? 'active' : ''}
              onClick={() => onUnitSystemChange('metric')}
              title="Meters"
            >
              m
            </button>
            <button
              className={unitSystem === 'millimeters' ? 'active' : ''}
              onClick={() => onUnitSystemChange('millimeters')}
              title="Millimeters"
            >
              mm
            </button>
            <button
              className={unitSystem === 'imperial' ? 'active' : ''}
              onClick={() => onUnitSystemChange('imperial')}
              title="Feet/Inches"
            >
              ft
            </button>
          </div>
        </div>

        <div className="control-row">
          <label>Show Grid:</label>
          <input
            type="checkbox"
            checked={showGrid}
            onChange={(e) => onToggleGrid(e.target.checked)}
          />
        </div>

        <div className="control-row">
          <label>Show Axes:</label>
          <input
            type="checkbox"
            checked={showAxes}
            onChange={(e) => onToggleAxes(e.target.checked)}
          />
        </div>

        <div className="control-row">
          <label>Show Measurements:</label>
          <input
            type="checkbox"
            checked={showMeasurements}
            onChange={(e) => onToggleMeasurements(e.target.checked)}
          />
        </div>

        <div className="control-row">
          <label>Snap to Grid:</label>
          <input
            type="checkbox"
            checked={snapToGrid}
            onChange={(e) => onToggleSnapToGrid(e.target.checked)}
          />
        </div>

        <div className="control-row">
          <label>Grid Size:</label>
          <div className="grid-size-controls">
            <input
              type="range"
              min="0.1"
              max="2"
              step="0.1"
              value={gridSize}
              onChange={(e) => onSetGridSize(parseFloat(e.target.value))}
              disabled={!snapToGrid}
            />
            <span className="value-display">{gridSize.toFixed(1)}</span>
          </div>
        </div>

        <div className="control-row">
          <label>Measurement Tool:</label>
          <input
            type="checkbox"
            checked={measurementActive}
            onChange={(e) => onToggleMeasurementTool(e.target.checked)}
          />
        </div>
      </div>

      <div className="control-section">
        <h3>Transform Tools</h3>

        <div className="transform-buttons">
          <button onClick={() => onSetTransformMode('translate')}>
            <span className="icon">↔</span>
            Move
          </button>
          <button onClick={() => onSetTransformMode('rotate')}>
            <span className="icon">⟳</span>
            Rotate
          </button>
          <button onClick={() => onSetTransformMode('scale')}>
            <span className="icon">⤢</span>
            Scale
          </button>
        </div>
      </div>

      <div className="control-section">
        <h3>Help</h3>
        <div className="help-text">
          <p><strong>Navigation:</strong></p>
          <ul>
            <li>Rotate View: Left-click + drag</li>
            <li>Pan View: Middle-click + drag</li>
            <li>Zoom: Mouse wheel</li>
          </ul>
          <p><strong>Selection:</strong></p>
          <ul>
            <li>Select object: Click on it</li>
            <li>Transform: Use transform tools</li>
          </ul>
        </div>
      </div>

      <ProjectManager />
    </div>
  );
};

export default ControlPanel;
