import React, { useState } from 'react';
import { ProjectorCollection, CollectionLayout } from '../models/ProjectorCollection';
import { Projector } from '../models/Projector';
import './MultiProjectorPanel.css';

interface MultiProjectorPanelProps {
  collections: ProjectorCollection[];
  activeCollectionId: string | null;
  projectors: Projector[];
  onAddCollection: () => void;
  onRemoveCollection: (id: string) => void;
  onUpdateCollection: (id: string, updates: Partial<ProjectorCollection>) => void;
  onSelectCollection: (id: string | null) => void;
  onAddProjectorToCollection: (projectorId: string, collectionId: string) => void;
  onRemoveProjectorFromCollection: (projectorId: string, collectionId: string) => void;
}

const MultiProjectorPanel: React.FC<MultiProjectorPanelProps> = ({
  collections,
  activeCollectionId,
  projectors,
  onAddCollection,
  onRemoveCollection,
  onUpdateCollection,
  onSelectCollection,
  onAddProjectorToCollection,
  onRemoveProjectorFromCollection
}) => {
  // Get the active collection
  const activeCollection = collections.find(c => c.id === activeCollectionId);
  
  // State for layout form
  const [layoutType, setLayoutType] = useState<'manual' | 'grid' | 'custom'>('grid');
  const [rows, setRows] = useState(2);
  const [columns, setColumns] = useState(2);
  const [spacing, setSpacing] = useState(1.0);
  const [overlap, setOverlap] = useState(0.1);
  
  // Handle layout update
  const handleUpdateLayout = () => {
    if (!activeCollectionId) return;
    
    const layout: CollectionLayout = {
      type: layoutType,
      rows,
      columns,
      spacing,
      overlap
    };
    
    onUpdateCollection(activeCollectionId, { layout });
  };
  
  // Get available projectors (not in any collection)
  const availableProjectors = projectors.filter(p => !p.collection);
  
  // Get projectors in the active collection
  const collectionProjectors = activeCollection
    ? projectors.filter(p => p.collection === activeCollection.id)
    : [];
  
  return (
    <div className="multi-projector-panel">
      <div className="panel-header">
        <h2>Multi-Projector Setup</h2>
        <button className="add-button" onClick={onAddCollection}>
          Add Collection
        </button>
      </div>
      
      <div className="collection-list">
        {collections.length === 0 ? (
          <div className="empty-state">No collections added yet</div>
        ) : (
          collections.map(collection => (
            <div
              key={collection.id}
              className={`collection-item ${collection.id === activeCollectionId ? 'active' : ''}`}
              onClick={() => onSelectCollection(collection.id)}
            >
              <div className="collection-name">{collection.name}</div>
              <div className="collection-info">
                {projectors.filter(p => p.collection === collection.id).length} projectors
              </div>
              <button
                className="remove-button"
                onClick={(e) => {
                  e.stopPropagation();
                  onRemoveCollection(collection.id);
                }}
              >
                ×
              </button>
            </div>
          ))
        )}
      </div>
      
      {activeCollection && (
        <div className="collection-details">
          <div className="parameter-group">
            <h3>Collection Settings</h3>
            
            <div className="parameter-row">
              <label>Name:</label>
              <input
                type="text"
                value={activeCollection.name}
                onChange={(e) => onUpdateCollection(activeCollectionId!, { name: e.target.value })}
              />
            </div>
          </div>
          
          <div className="parameter-group">
            <h3>Layout Configuration</h3>
            
            <div className="parameter-row">
              <label>Layout Type:</label>
              <select
                value={layoutType}
                onChange={(e) => setLayoutType(e.target.value as 'manual' | 'grid' | 'custom')}
              >
                <option value="manual">Manual</option>
                <option value="grid">Grid</option>
                <option value="custom">Custom</option>
              </select>
            </div>
            
            {layoutType === 'grid' && (
              <>
                <div className="parameter-row">
                  <label>Rows:</label>
                  <input
                    type="number"
                    min="1"
                    max="8"
                    value={rows}
                    onChange={(e) => setRows(parseInt(e.target.value))}
                  />
                </div>
                
                <div className="parameter-row">
                  <label>Columns:</label>
                  <input
                    type="number"
                    min="1"
                    max="8"
                    value={columns}
                    onChange={(e) => setColumns(parseInt(e.target.value))}
                  />
                </div>
                
                <div className="parameter-row">
                  <label>Spacing:</label>
                  <input
                    type="number"
                    min="0.1"
                    step="0.1"
                    value={spacing}
                    onChange={(e) => setSpacing(parseFloat(e.target.value))}
                  />
                </div>
                
                <div className="parameter-row">
                  <label>Overlap:</label>
                  <input
                    type="range"
                    min="0"
                    max="0.5"
                    step="0.01"
                    value={overlap}
                    onChange={(e) => setOverlap(parseFloat(e.target.value))}
                  />
                  <span className="value-display">
                    {(overlap * 100).toFixed(0)}%
                  </span>
                </div>
                
                <button className="apply-button" onClick={handleUpdateLayout}>
                  Apply Layout
                </button>
              </>
            )}
          </div>
          
          <div className="parameter-group">
            <h3>Projectors in Collection</h3>
            
            {collectionProjectors.length === 0 ? (
              <div className="empty-state">No projectors in this collection</div>
            ) : (
              <div className="collection-projectors">
                {collectionProjectors.map(projector => (
                  <div key={projector.id} className="collection-projector-item">
                    <div className="projector-name">{projector.name}</div>
                    <button
                      className="remove-button"
                      onClick={() => onRemoveProjectorFromCollection(projector.id, activeCollection.id)}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
          
          <div className="parameter-group">
            <h3>Available Projectors</h3>
            
            {availableProjectors.length === 0 ? (
              <div className="empty-state">No available projectors</div>
            ) : (
              <div className="available-projectors">
                {availableProjectors.map(projector => (
                  <div key={projector.id} className="available-projector-item">
                    <div className="projector-name">{projector.name}</div>
                    <button
                      className="add-button small"
                      onClick={() => onAddProjectorToCollection(projector.id, activeCollection.id)}
                    >
                      Add
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
          
          <div className="parameter-group">
            <h3>Edge Blending</h3>
            
            <div className="info-text">
              Edge blending is automatically calculated for overlapping projectors in the collection.
              Adjust individual projector blending settings in the Projector panel.
            </div>
            
            <button
              className="detect-button"
              onClick={() => {
                // This would trigger overlap detection in a real implementation
                console.log('Detecting overlaps for collection:', activeCollection.id);
              }}
            >
              Detect Overlaps
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default MultiProjectorPanel;
