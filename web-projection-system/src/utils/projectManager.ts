import { Projector } from '../models/Projector';
import { Surface } from '../models/Surface';
import { ProjectorCollection } from '../models/ProjectorCollection';

export interface ProjectData {
  projectors: {
    id: string;
    name: string;
    parameters: any;
    collection: string;
    isActive: boolean;
    overlappingWith: string[];
  }[];
  surfaces: {
    id: string;
    name: string;
    parameters: any;
  }[];
  collections: {
    id: string;
    name: string;
    layout: any;
  }[];
}

/**
 * Save the current project state
 */
export const saveProject = (
  projectors: Projector[],
  surfaces: Surface[],
  collections: ProjectorCollection[]
): void => {
  try {
    const projectData: ProjectData = {
      projectors: projectors.map(p => ({
        id: p.id,
        name: p.name,
        parameters: p.parameters,
        collection: p.collection,
        isActive: p.isActive,
        overlappingWith: p.overlappingWith
      })),
      surfaces: surfaces.map(s => ({
        id: s.id,
        name: s.name,
        parameters: s.parameters
      })),
      collections: collections.map(c => ({
        id: c.id,
        name: c.name,
        layout: c.layout
      }))
    };
    
    localStorage.setItem('projectionSystemProject', JSON.stringify(projectData));
    
    // Also create a timestamped backup
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    localStorage.setItem(`projectionSystemProject_${timestamp}`, JSON.stringify(projectData));
    
    // Keep only the 5 most recent backups
    const backupKeys = Object.keys(localStorage)
      .filter(key => key.startsWith('projectionSystemProject_'))
      .sort()
      .reverse();
    
    if (backupKeys.length > 5) {
      backupKeys.slice(5).forEach(key => {
        localStorage.removeItem(key);
      });
    }
  } catch (error) {
    console.error('Error saving project:', error);
  }
};

/**
 * Load a saved project
 */
export const loadProject = (): ProjectData | null => {
  try {
    const savedData = localStorage.getItem('projectionSystemProject');
    
    if (!savedData) {
      return null;
    }
    
    return JSON.parse(savedData) as ProjectData;
  } catch (error) {
    console.error('Error loading project:', error);
    return null;
  }
};

/**
 * Get a list of available backups
 */
export const getBackups = (): { key: string; timestamp: string }[] => {
  return Object.keys(localStorage)
    .filter(key => key.startsWith('projectionSystemProject_'))
    .map(key => {
      const timestamp = key.replace('projectionSystemProject_', '').replace(/-/g, ':');
      return { key, timestamp };
    })
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp));
};

/**
 * Load a specific backup
 */
export const loadBackup = (key: string): ProjectData | null => {
  try {
    const savedData = localStorage.getItem(key);
    
    if (!savedData) {
      return null;
    }
    
    return JSON.parse(savedData) as ProjectData;
  } catch (error) {
    console.error('Error loading backup:', error);
    return null;
  }
};

/**
 * Export project to a file
 */
export const exportProject = (
  projectors: Projector[],
  surfaces: Surface[],
  collections: ProjectorCollection[]
): void => {
  try {
    const projectData: ProjectData = {
      projectors: projectors.map(p => ({
        id: p.id,
        name: p.name,
        parameters: p.parameters,
        collection: p.collection,
        isActive: p.isActive,
        overlappingWith: p.overlappingWith
      })),
      surfaces: surfaces.map(s => ({
        id: s.id,
        name: s.name,
        parameters: s.parameters
      })),
      collections: collections.map(c => ({
        id: c.id,
        name: c.name,
        layout: c.layout
      }))
    };
    
    const dataStr = JSON.stringify(projectData, null, 2);
    const dataUri = `data:application/json;charset=utf-8,${encodeURIComponent(dataStr)}`;
    
    const exportName = `projection_system_${new Date().toISOString().slice(0, 10)}.json`;
    
    const linkElement = document.createElement('a');
    linkElement.setAttribute('href', dataUri);
    linkElement.setAttribute('download', exportName);
    linkElement.click();
  } catch (error) {
    console.error('Error exporting project:', error);
  }
};

/**
 * Import project from a file
 */
export const importProject = (file: File): Promise<ProjectData> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    
    reader.onload = (event) => {
      try {
        if (!event.target || typeof event.target.result !== 'string') {
          reject(new Error('Invalid file content'));
          return;
        }
        
        const projectData = JSON.parse(event.target.result) as ProjectData;
        resolve(projectData);
      } catch (error) {
        reject(error);
      }
    };
    
    reader.onerror = () => {
      reject(new Error('Error reading file'));
    };
    
    reader.readAsText(file);
  });
};
