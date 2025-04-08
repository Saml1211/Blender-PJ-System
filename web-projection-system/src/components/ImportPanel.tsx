import React, { useRef, useState } from 'react';
import './ImportPanel.css';

interface ImportPanelProps {
  onImportStart: () => void;
  onImportComplete: () => void;
}

const ImportPanel: React.FC<ImportPanelProps> = ({
  onImportStart,
  onImportComplete
}) => {
  // Refs
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // State
  const [importScale, setImportScale] = useState(1.0);
  const [importPosition, setImportPosition] = useState({ x: 0, y: 0, z: 0 });
  const [importRotation, setImportRotation] = useState({ x: 0, y: 0, z: 0 });
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  
  // Handle file selection
  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (files && files.length > 0) {
      setSelectedFile(files[0]);
    }
  };
  
  // Handle import button click
  const handleImport = () => {
    if (!selectedFile) return;
    
    onImportStart();
    
    // In a real implementation, this would use the modelImporter utility
    // For now, we'll just simulate a successful import after a delay
    setTimeout(() => {
      onImportComplete();
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }, 2000);
  };
  
  return (
    <div className="import-panel">
      <div className="panel-header">
        <h2>Import Models</h2>
      </div>
      
      <div className="parameter-group">
        <h3>Import File</h3>
        
        <div className="file-input-container">
          <input
            type="file"
            ref={fileInputRef}
            accept=".obj,.fbx"
            onChange={handleFileSelect}
          />
          <div className="file-info">
            {selectedFile ? (
              <span>{selectedFile.name} ({Math.round(selectedFile.size / 1024)} KB)</span>
            ) : (
              <span>No file selected</span>
            )}
          </div>
        </div>
        
        <div className="drag-drop-area">
          <div className="drag-drop-text">
            <p>Drag and drop OBJ or FBX files here</p>
            <p className="drag-drop-subtext">or use the file selector above</p>
          </div>
        </div>
      </div>
      
      <div className="parameter-group">
        <h3>Import Settings</h3>
        
        <div className="parameter-row">
          <label>Scale:</label>
          <input
            type="number"
            min="0.01"
            step="0.1"
            value={importScale}
            onChange={(e) => setImportScale(parseFloat(e.target.value))}
          />
        </div>
        
        <div className="parameter-subgroup">
          <h4>Position</h4>
          
          <div className="parameter-row">
            <label>X:</label>
            <input
              type="number"
              step="0.1"
              value={importPosition.x}
              onChange={(e) => setImportPosition({ ...importPosition, x: parseFloat(e.target.value) })}
            />
          </div>
          
          <div className="parameter-row">
            <label>Y:</label>
            <input
              type="number"
              step="0.1"
              value={importPosition.y}
              onChange={(e) => setImportPosition({ ...importPosition, y: parseFloat(e.target.value) })}
            />
          </div>
          
          <div className="parameter-row">
            <label>Z:</label>
            <input
              type="number"
              step="0.1"
              value={importPosition.z}
              onChange={(e) => setImportPosition({ ...importPosition, z: parseFloat(e.target.value) })}
            />
          </div>
        </div>
        
        <div className="parameter-subgroup">
          <h4>Rotation (degrees)</h4>
          
          <div className="parameter-row">
            <label>X:</label>
            <input
              type="number"
              step="1"
              value={importRotation.x}
              onChange={(e) => setImportRotation({ ...importRotation, x: parseFloat(e.target.value) })}
            />
          </div>
          
          <div className="parameter-row">
            <label>Y:</label>
            <input
              type="number"
              step="1"
              value={importRotation.y}
              onChange={(e) => setImportRotation({ ...importRotation, y: parseFloat(e.target.value) })}
            />
          </div>
          
          <div className="parameter-row">
            <label>Z:</label>
            <input
              type="number"
              step="1"
              value={importRotation.z}
              onChange={(e) => setImportRotation({ ...importRotation, z: parseFloat(e.target.value) })}
            />
          </div>
        </div>
      </div>
      
      <button
        className="import-button"
        disabled={!selectedFile}
        onClick={handleImport}
      >
        Import Model
      </button>
      
      <div className="import-info">
        <h3>Supported Formats</h3>
        <ul>
          <li><strong>OBJ</strong> - Wavefront OBJ format</li>
          <li><strong>FBX</strong> - Autodesk FBX format</li>
        </ul>
        <p>For best results, export models with proper scale and orientation.</p>
      </div>
    </div>
  );
};

export default ImportPanel;
