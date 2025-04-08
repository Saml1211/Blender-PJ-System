import { create } from 'zustand';
import { Projector } from '../models/Projector';
import { ProjectorCollection } from '../models/ProjectorCollection';
import { Surface } from '../models/Surface';

interface ProjectionState {
  // Projectors
  projectors: Projector[];
  activeProjectorId: string | null;

  // Collections
  collections: ProjectorCollection[];
  activeCollectionId: string | null;

  // Surfaces
  surfaces: Surface[];
  activeSurfaceId: string | null;

  // UI state
  unitSystem: 'metric' | 'imperial' | 'millimeters';
  showGrid: boolean;
  showAxes: boolean;
  showMeasurements: boolean;

  // Actions
  // Projector actions
  addProjector: (projector: Projector) => void;
  removeProjector: (id: string) => void;
  updateProjector: (id: string, updates: Partial<Projector>) => void;
  setActiveProjector: (id: string | null) => void;

  // Collection actions
  addCollection: (collection: ProjectorCollection) => void;
  removeCollection: (id: string) => void;
  updateCollection: (id: string, updates: Partial<ProjectorCollection>) => void;
  setActiveCollection: (id: string | null) => void;
  addProjectorToCollection: (projectorId: string, collectionId: string) => void;
  removeProjectorFromCollection: (projectorId: string, collectionId: string) => void;

  // Surface actions
  addSurface: (surface: Surface) => void;
  removeSurface: (id: string) => void;
  updateSurface: (id: string, updates: Partial<Surface>) => void;
  setActiveSurface: (id: string | null) => void;

  // UI actions
  setUnitSystem: (system: 'metric' | 'imperial' | 'millimeters') => void;
  toggleGrid: (show: boolean) => void;
  toggleAxes: (show: boolean) => void;
  toggleMeasurements: (show: boolean) => void;
}

export const useProjectionStore = create<ProjectionState>((set) => ({
  // Initial state
  projectors: [],
  activeProjectorId: null,
  collections: [],
  activeCollectionId: null,
  surfaces: [],
  activeSurfaceId: null,
  unitSystem: 'metric',
  showGrid: true,
  showAxes: true,
  showMeasurements: true,

  // Projector actions
  addProjector: (projector) => set((state) => ({
    projectors: [...state.projectors, projector],
    activeProjectorId: projector.id
  })),

  removeProjector: (id) => set((state) => ({
    projectors: state.projectors.filter(p => p.id !== id),
    activeProjectorId: state.activeProjectorId === id ? null : state.activeProjectorId
  })),

  updateProjector: (id, updates) => set((state) => {
    const updatedProjectors = state.projectors.map(p => {
      if (p.id === id) {
        // Create a proper Projector instance with the updates
        const updatedProjector = new Projector(updates.name || p.name);
        // Copy all properties from the original projector
        Object.assign(updatedProjector, p);
        // Apply the updates
        Object.assign(updatedProjector, updates);
        return updatedProjector;
      }
      return p;
    });
    return { projectors: updatedProjectors };
  }),

  setActiveProjector: (id) => set({ activeProjectorId: id }),

  // Collection actions
  addCollection: (collection) => set((state) => ({
    collections: [...state.collections, collection],
    activeCollectionId: collection.id
  })),

  removeCollection: (id) => set((state) => {
    // Get the collection to be removed
    const collection = state.collections.find(c => c.id === id);

    // If collection exists, update its projectors to remove collection reference
    if (collection) {
      const updatedProjectors = state.projectors.map(p => {
        if (p.collection === id) {
          // Create a new projector instance with updated collection
          const updatedProjector = new Projector(p.name);
          Object.assign(updatedProjector, p);
          updatedProjector.setCollection('');
          return updatedProjector;
        }
        return p;
      });

      return {
        collections: state.collections.filter(c => c.id !== id),
        activeCollectionId: state.activeCollectionId === id ? null : state.activeCollectionId,
        projectors: updatedProjectors
      };
    }

    return {
      collections: state.collections.filter(c => c.id !== id),
      activeCollectionId: state.activeCollectionId === id ? null : state.activeCollectionId
    };
  }),

  updateCollection: (id, updates) => set((state) => {
    const updatedCollections = state.collections.map(c => {
      if (c.id === id) {
        // Create a proper ProjectorCollection instance with the updates
        const updatedCollection = new ProjectorCollection(updates.name || c.name);
        // Copy all properties from the original collection
        Object.assign(updatedCollection, c);
        // Apply the updates
        Object.assign(updatedCollection, updates);
        return updatedCollection;
      }
      return c;
    });
    return { collections: updatedCollections };
  }),

  setActiveCollection: (id) => set({ activeCollectionId: id }),

  addProjectorToCollection: (projectorId, collectionId) => set((state) => {
    // Find the projector and collection
    const projector = state.projectors.find(p => p.id === projectorId);
    const collection = state.collections.find(c => c.id === collectionId);

    if (!projector || !collection) {
      return state;
    }

    // Update the projector's collection
    const updatedProjectors = state.projectors.map(p => {
      if (p.id === projectorId) {
        // Create a new projector instance with updated collection
        const updatedProjector = new Projector(p.name);
        Object.assign(updatedProjector, p);
        updatedProjector.setCollection(collectionId);
        return updatedProjector;
      }
      return p;
    });

    // Add the projector to the collection
    const updatedCollections = state.collections.map(c => {
      if (c.id === collectionId) {
        // Create a new collection instance
        const updatedCollection = new ProjectorCollection(c.name);
        Object.assign(updatedCollection, c);
        // Add the projector to the collection
        updatedCollection.addProjector(projector);
        return updatedCollection;
      }
      return c;
    });

    return {
      projectors: updatedProjectors,
      collections: updatedCollections
    };
  }),

  removeProjectorFromCollection: (projectorId, collectionId) => set((state) => {
    // Find the collection
    const collection = state.collections.find(c => c.id === collectionId);

    if (!collection) {
      return state;
    }

    // Update the projector's collection
    const updatedProjectors = state.projectors.map(p => {
      if (p.id === projectorId && p.collection === collectionId) {
        // Create a new projector instance with updated collection
        const updatedProjector = new Projector(p.name);
        Object.assign(updatedProjector, p);
        updatedProjector.setCollection('');
        return updatedProjector;
      }
      return p;
    });

    // Remove the projector from the collection
    const updatedCollections = state.collections.map(c => {
      if (c.id === collectionId) {
        // Create a new collection instance
        const updatedCollection = new ProjectorCollection(c.name);
        Object.assign(updatedCollection, c);
        // Remove the projector from the collection
        updatedCollection.removeProjector(projectorId);
        return updatedCollection;
      }
      return c;
    });

    return {
      projectors: updatedProjectors,
      collections: updatedCollections
    };
  }),

  // Surface actions
  addSurface: (surface) => set((state) => ({
    surfaces: [...state.surfaces, surface],
    activeSurfaceId: surface.id
  })),

  removeSurface: (id) => set((state) => ({
    surfaces: state.surfaces.filter(s => s.id !== id),
    activeSurfaceId: state.activeSurfaceId === id ? null : state.activeSurfaceId
  })),

  updateSurface: (id, updates) => set((state) => {
    const updatedSurfaces = state.surfaces.map(s => {
      if (s.id === id) {
        // Create a proper Surface instance with the updates
        const updatedSurface = new Surface(updates.name || s.name);
        // Copy all properties from the original surface
        Object.assign(updatedSurface, s);
        // Apply the updates
        Object.assign(updatedSurface, updates);
        return updatedSurface;
      }
      return s;
    });
    return { surfaces: updatedSurfaces };
  }),

  setActiveSurface: (id) => set({ activeSurfaceId: id }),

  // UI actions
  setUnitSystem: (system) => set({ unitSystem: system }),
  toggleGrid: (show) => set({ showGrid: show }),
  toggleAxes: (show) => set({ showAxes: show }),
  toggleMeasurements: (show) => set({ showMeasurements: show })
}));
