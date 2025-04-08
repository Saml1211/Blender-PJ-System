# System Patterns

## System Architecture
The Blender Projection System is structured as a Blender add-on following Blender's Python API architecture. The system is designed with modularity in mind, separating concerns into distinct Python modules:

1. **__init__.py**: Entry point that defines add-on metadata and handles registration/unregistration
2. **properties.py**: Defines custom properties for projectors and system settings
3. **operators.py**: Implements operator classes for user interactions and calculations
4. **ui.py**: Defines user interface components like panels and buttons
5. **visualization.py**: Handles Geometry Nodes and visual representation of projections

## Key Technical Decisions

### 1. Bidirectional Parameter Relationships
- Uses Blender's property update callbacks to maintain mathematically accurate relationships between:
  - Throw Distance
  - Image Width
  - Throw Ratio
- When one parameter changes, the others update accordingly based on the projection formula

### 2. Visualization Approach
- Utilizes Geometry Nodes for real-time projection cone visualization
- Employs driver system to connect property changes to visual updates
- Represents projection as a cone with accurate aspect ratio

### 3. Multi-Projector Management
- Collections-based organization for logical grouping
- Instance duplication for efficient handling of multiple similar projectors
- Overlap detection through computational geometry

### 4. Integration with Blender's Ecosystem
- Adheres to Blender's add-on architecture
- Uses Blender's built-in property system
- Leverages Geometry Nodes for visualization rather than custom mesh generation

## Design Patterns

### Module Pattern
- Each file represents a specific module with related functionality
- Clear separation of concerns between UI, properties, operators, and visualization

### Observer Pattern
- Property updates trigger callbacks that update other properties and visualizations
- Changes propagate through the system automatically

### Factory Pattern
- Operator classes that create and configure projector objects
- Standardized creation process for consistent object hierarchies

### Command Pattern
- Operators implement execute() and invoke() methods for user actions
- Allows for undoing actions through Blender's undo system

## Component Relationships
- **Property Definitions** → **Operator Logic** → **UI Display**
- **Property Changes** → **Update Callbacks** → **Visual Representation**
- **User Input** → **Operators** → **Property Updates** → **Visual Feedback** 