import { v4 as uuidv4 } from 'uuid';
import { Projector } from './Projector';

export interface CollectionLayout {
  type: 'manual' | 'grid' | 'custom';
  rows?: number;
  columns?: number;
  spacing?: number;
  overlap?: number;
}

export class ProjectorCollection {
  id: string;
  name: string;
  projectors: Projector[];
  layout: CollectionLayout;

  constructor(name: string, layout: CollectionLayout = { type: 'manual' }) {
    this.id = uuidv4();
    this.name = name;
    this.projectors = [];
    this.layout = layout;
  }

  // Add a projector to the collection
  addProjector(projector: Projector): void {
    projector.setCollection(this.id);
    this.projectors.push(projector);
  }

  // Remove a projector from the collection
  removeProjector(projectorId: string): void {
    const projector = this.projectors.find(p => p.id === projectorId);
    if (projector) {
      projector.setCollection('');
    }
    this.projectors = this.projectors.filter(p => p.id !== projectorId);
  }

  // Get all projectors in the collection
  getProjectors(): Projector[] {
    return this.projectors;
  }

  // Get a specific projector by ID
  getProjector(projectorId: string): Projector | undefined {
    return this.projectors.find(p => p.id === projectorId);
  }

  // Update the collection layout
  updateLayout(layout: Partial<CollectionLayout>): void {
    this.layout = { ...this.layout, ...layout };
    
    // If layout type is grid, arrange projectors in a grid
    if (this.layout.type === 'grid' && this.layout.rows && this.layout.columns && this.layout.spacing) {
      this.arrangeInGrid();
    }
  }

  // Arrange projectors in a grid layout
  private arrangeInGrid(): void {
    if (!this.layout.rows || !this.layout.columns || !this.layout.spacing) {
      return;
    }

    const rows = this.layout.rows;
    const columns = this.layout.columns;
    const spacing = this.layout.spacing;
    const overlap = this.layout.overlap || 0;

    // Calculate the total width and height of the grid
    const totalWidth = columns * spacing * (1 - overlap);
    const totalHeight = rows * spacing * (1 - overlap);
    
    // Calculate the starting position (top-left of the grid)
    const startX = -totalWidth / 2;
    const startY = totalHeight / 2;
    
    // Arrange projectors in the grid
    let index = 0;
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < columns; col++) {
        if (index < this.projectors.length) {
          const projector = this.projectors[index];
          
          // Calculate position in the grid
          const x = startX + col * spacing * (1 - overlap);
          const y = startY - row * spacing * (1 - overlap);
          
          // Update projector position
          projector.updatePosition({ x, y, z: 0 });
          
          index++;
        }
      }
    }
  }

  // Detect overlapping projectors
  detectOverlaps(): void {
    // Reset all overlaps
    this.projectors.forEach(p => {
      p.overlappingWith = [];
    });

    // Check each pair of projectors for overlap
    for (let i = 0; i < this.projectors.length; i++) {
      for (let j = i + 1; j < this.projectors.length; j++) {
        const p1 = this.projectors[i];
        const p2 = this.projectors[j];
        
        if (this.doProjectorsOverlap(p1, p2)) {
          p1.addOverlap(p2.id);
          p2.addOverlap(p1.id);
        }
      }
    }
  }

  // Check if two projectors overlap
  private doProjectorsOverlap(p1: Projector, p2: Projector): boolean {
    // This is a simplified check - in a real implementation, 
    // we would need to calculate the actual intersection of the projection cones
    
    // For now, we'll just check if the projection rectangles overlap
    // at the throw distance
    
    // Calculate the corners of the projection rectangles
    const rect1 = this.calculateProjectionRectangle(p1);
    const rect2 = this.calculateProjectionRectangle(p2);
    
    // Check if the rectangles overlap
    return !(
      rect1.right < rect2.left ||
      rect1.left > rect2.right ||
      rect1.bottom < rect2.top ||
      rect1.top > rect2.bottom
    );
  }

  // Calculate the projection rectangle at the throw distance
  private calculateProjectionRectangle(projector: Projector) {
    const { position, throwDistance, imageWidth } = projector.parameters;
    const imageHeight = projector.imageHeight;
    
    // This is a simplified calculation assuming the projector is facing along the z-axis
    // In a real implementation, we would need to account for the projector's rotation
    
    const halfWidth = imageWidth / 2;
    const halfHeight = imageHeight / 2;
    
    return {
      left: position.x - halfWidth,
      right: position.x + halfWidth,
      top: position.y + halfHeight,
      bottom: position.y - halfHeight,
      z: position.z + throwDistance
    };
  }
}
