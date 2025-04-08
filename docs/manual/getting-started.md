# Getting Started

This guide will help you get up and running with the Blender Projection System add-on, covering installation, interface overview, and your first steps.

## Installation

### Requirements
- Blender 4.2 or newer
- At least 4GB of RAM recommended
- Graphics card with OpenGL 4.3 support

### Installation Steps

1. **Download the Add-on**:
   - Visit the [Releases page](https://github.com/yourusername/Blender-PJ-System/releases) on GitHub
   - Download the latest `blender_projection_system.zip` file

2. **Install in Blender**:
   - Open Blender
   - Go to Edit > Preferences
   - Select the "Add-ons" tab
   - Click "Install..." button at the top right
   - Navigate to and select the downloaded zip file
   - Click "Install Add-on"

3. **Enable the Add-on**:
   - In the Add-ons list, search for "Projection"
   - Check the box next to "3D View: Blender Projection System"
   - Wait for the add-on to initialize

4. **Verify Installation**:
   - The add-on should now be active
   - You should see a "Projection" tab in the sidebar of the 3D Viewport (press N if the sidebar is not visible)

## Interface Overview

The Blender Projection System add-on adds two main panels to the Blender interface:

### Projection Planner Panel

Located in the sidebar (N-panel) of the 3D Viewport under the "Projection" tab:

![Projection Planner Panel](../images/ui-projection-panel.png)

This panel contains:

1. **Unit System Toggle**: Switch between Metric and Imperial units
2. **Environment Section**: Tools for importing models and creating environments
3. **Projector Controls**: Add, configure, and visualize projectors
4. **Projector Parameters**: When a projector is selected, displays its throw distance, image width, throw ratio, and aspect ratio settings
5. **Visualization Controls**: Options for visualization features like projection cones and test surfaces

### Multi-Projector Setup Panel

Located in the same sidebar, below the Projection Planner panel:

![Multi-Projector Panel](../images/ui-multi-projector-panel.png)

This panel contains:

1. **Projector Collections**: Tools for creating and managing collections of projectors
2. **Collection Management**: Options for adding projectors to collections
3. **Alignment Tools**: Operators for aligning projectors in groups
4. **Overlap Detection**: Tools for finding and managing overlapping projections
5. **Statistics**: Information about your current projector setup

## First Steps

Let's create a basic projection setup to get you familiar with the add-on.

### 1. Create a Basic Environment

First, let's create a simple room to project in:

1. Open the Projection Planner panel (N key > Projection tab)
2. In the Environment section, click "Create Basic Room"
3. Adjust the room parameters if desired and click OK
4. A simple room with walls and floor will be created

### 2. Add a Projector

Now let's add a projector:

1. Click the "Add Projector" button
2. A new projector will be created at the current 3D cursor location
3. Note that the projector consists of:
   - An empty object (the main projector handle)
   - A projector body (visual representation)
   - A projection source (camera for projection mapping)

### 3. Adjust Projector Parameters

With the projector selected:

1. In the Projector Parameters section, adjust:
   - **Throw Distance**: Distance from projector to projection surface
   - **Image Width**: Width of the projected image
   - **Throw Ratio**: Ratio of throw distance to image width (updates automatically)
   - **Aspect Ratio**: Ratio of width to height (e.g., 16:9)

2. Notice that when you change one parameter, others update automatically:
   - Change throw distance → throw ratio updates
   - Change image width → throw ratio updates
   - Change throw ratio → image width updates

### 4. Position the Projector

To position your projector:

1. Use the standard Blender transformation tools (G, R, S) to move, rotate, and scale the projector
2. Position the projector facing one of the walls

### 5. Create a Test Surface

To visualize the projection:

1. With the projector selected, click "Create Test Surface"
2. A plane will be created at the projection distance
3. This surface shows what would be projected

### 6. Multiple Projectors

To work with multiple projectors:

1. Select your projector
2. Click "Duplicate Projector" to create a copy
3. Position the new projector as desired

### 7. Create a Projector Collection

To organize multiple projectors:

1. Go to the Multi-Projector Setup panel
2. Click "Create Collection"
3. Give it a name like "Main Projectors"
4. Select both projectors
5. Click "Add Selected" to add them to the collection

### 8. Align Projector Group

To align your projectors in a row:

1. With the collection selected, click "Align Projectors"
2. Adjust the spacing as needed
3. Your projectors will be aligned in a row

### 9. Detect Overlapping Projections

If you have projectors that might overlap:

1. Position your projectors so their projection areas might intersect
2. Click "Detect Overlapping"
3. The add-on will identify potential overlapping areas
4. You can then adjust the edge blend amount for smooth transitions

## Next Steps

Now that you're familiar with the basics, you can explore more advanced features:

- [Basic Usage](basic-usage.md) for more details on projector parameters
- [Environment Setup](environment-setup.md) for importing models and positioning
- [Projection Mapping](projection-mapping.md) for projecting onto surfaces
- [Multi-Projector Management](multi-projector.md) for complex setups

Congratulations! You've taken your first steps with the Blender Projection System add-on. 