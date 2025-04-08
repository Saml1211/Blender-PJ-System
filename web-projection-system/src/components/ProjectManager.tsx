import React, { useState, useRef } from 'react';
import { useProjectionStore } from '../store/projectionStore';
import { saveProject, loadProject, exportProject, importProject, getBackups, loadBackup } from '../utils/projectManager';
import { Projector } from '../models/Projector';
import { Surface } from '../models/Surface';
import { ProjectorCollection } from '../models/ProjectorCollection';
import './ProjectManager.css';

const ProjectManager: React.FC = () => {
  const [showBackups, setShowBackups] = useState(false);
  const [backups, setBackups] = useState<{ key: string; timestamp: string }[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  const {
    projectors,
    surfaces,
    collections,
    addProjector,
    addSurface,
    addCollection,
    removeProjector,
    removeSurface,
    removeCollection
  } = useProjectionStore();
  
  // Handle save project
  const handleSaveProject = () => {
    saveProject(projectors, surfaces, collections);
    alert('Project saved successfully!');
  };
  
  // Handle load project
  const handleLoadProject = () => {
    const projectData = loadProject();
    
    if (!projectData) {
      alert('No saved project found.');
      return;
    }
    
    // Clear existing data
    projectors.forEach(p => removeProjector(p.id));
    surfaces.forEach(s => removeSurface(s.id));
    collections.forEach(c => removeCollection(c.id));
    
    // Load projectors
    projectData.projectors.forEach(projectorData => {
      const projector = new Projector(projectorData.name);
      projector.id = projectorData.id;
      projector.parameters = projectorData.parameters;
      projector.collection = projectorData.collection;
      projector.isActive = projectorData.isActive;
      projector.overlappingWith = projectorData.overlappingWith;
      addProjector(projector);
    });
    
    // Load surfaces
    projectData.surfaces.forEach(surfaceData => {
      const surface = new Surface(surfaceData.name);
      surface.id = surfaceData.id;
      surface.parameters = surfaceData.parameters;
      addSurface(surface);
    });
    
    // Load collections
    projectData.collections.forEach(collectionData => {
      const collection = new ProjectorCollection(collectionData.name);
      collection.id = collectionData.id;
      collection.layout = collectionData.layout;
      addCollection(collection);
    });
    
    alert('Project loaded successfully!');
  };
  
  // Handle export project
  const handleExportProject = () => {
    exportProject(projectors, surfaces, collections);
  };
  
  // Handle import project
  const handleImportClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };
  
  const handleImportProject = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    
    if (!files || files.length === 0) {
      return;
    }
    
    try {
      const projectData = await importProject(files[0]);
      
      // Clear existing data
      projectors.forEach(p => removeProjector(p.id));
      surfaces.forEach(s => removeSurface(s.id));
      collections.forEach(c => removeCollection(c.id));
      
      // Load projectors
      projectData.projectors.forEach(projectorData => {
        const projector = new Projector(projectorData.name);
        projector.id = projectorData.id;
        projector.parameters = projectorData.parameters;
        projector.collection = projectorData.collection;
        projector.isActive = projectorData.isActive;
        projector.overlappingWith = projectorData.overlappingWith;
        addProjector(projector);
      });
      
      // Load surfaces
      projectData.surfaces.forEach(surfaceData => {
        const surface = new Surface(surfaceData.name);
        surface.id = surfaceData.id;
        surface.parameters = surfaceData.parameters;
        addSurface(surface);
      });
      
      // Load collections
      projectData.collections.forEach(collectionData => {
        const collection = new ProjectorCollection(collectionData.name);
        collection.id = collectionData.id;
        collection.layout = collectionData.layout;
        addCollection(collection);
      });
      
      alert('Project imported successfully!');
    } catch (error) {
      console.error('Error importing project:', error);
      alert('Error importing project. Please check the file format.');
    }
    
    // Reset the file input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };
  
  // Handle show backups
  const handleShowBackups = () => {
    const backupsList = getBackups();
    setBackups(backupsList);
    setShowBackups(true);
  };
  
  // Handle load backup
  const handleLoadBackup = (key: string) => {
    const projectData = loadBackup(key);
    
    if (!projectData) {
      alert('Error loading backup.');
      return;
    }
    
    // Clear existing data
    projectors.forEach(p => removeProjector(p.id));
    surfaces.forEach(s => removeSurface(s.id));
    collections.forEach(c => removeCollection(c.id));
    
    // Load projectors
    projectData.projectors.forEach(projectorData => {
      const projector = new Projector(projectorData.name);
      projector.id = projectorData.id;
      projector.parameters = projectorData.parameters;
      projector.collection = projectorData.collection;
      projector.isActive = projectorData.isActive;
      projector.overlappingWith = projectorData.overlappingWith;
      addProjector(projector);
    });
    
    // Load surfaces
    projectData.surfaces.forEach(surfaceData => {
      const surface = new Surface(surfaceData.name);
      surface.id = surfaceData.id;
      surface.parameters = surfaceData.parameters;
      addSurface(surface);
    });
    
    // Load collections
    projectData.collections.forEach(collectionData => {
      const collection = new ProjectorCollection(collectionData.name);
      collection.id = collectionData.id;
      collection.layout = collectionData.layout;
      addCollection(collection);
    });
    
    setShowBackups(false);
    alert('Backup loaded successfully!');
  };
  
  return (
    <div className="project-manager">
      <h3>Project Management</h3>
      
      <div className="project-buttons">
        <button onClick={handleSaveProject}>Save Project</button>
        <button onClick={handleLoadProject}>Load Project</button>
        <button onClick={handleExportProject}>Export Project</button>
        <button onClick={handleImportClick}>Import Project</button>
        <button onClick={handleShowBackups}>Show Backups</button>
      </div>
      
      <input
        type="file"
        ref={fileInputRef}
        style={{ display: 'none' }}
        accept=".json"
        onChange={handleImportProject}
      />
      
      {showBackups && (
        <div className="backups-list">
          <h4>Available Backups</h4>
          {backups.length === 0 ? (
            <p>No backups found.</p>
          ) : (
            <ul>
              {backups.map(backup => (
                <li key={backup.key}>
                  <span>{new Date(backup.timestamp).toLocaleString()}</span>
                  <button onClick={() => handleLoadBackup(backup.key)}>Load</button>
                </li>
              ))}
            </ul>
          )}
          <button className="close-button" onClick={() => setShowBackups(false)}>Close</button>
        </div>
      )}
    </div>
  );
};

export default ProjectManager;
