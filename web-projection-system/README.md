# 3D Projection System

A web-based projection system visualization and calculation tool built with Three.js and React. This tool helps AV professionals design and visualize projector setups in 3D space.

## Features

- **Accurate Projection Calculations**: Precise bidirectional relationships between throw distance, image width, and throw ratio
- **Real-time 3D Visualization**: Three.js-based visualization of projection cones with accurate aspect ratios
- **Multi-Projector Management**: Collections, grouping, edge blending, and overlap detection for complex setups
- **Curved Surface Support**: Create and manipulate curved, cylindrical, and spherical projection surfaces
- **Model Import**: OBJ/FBX import with scale control and positioning
- **Interactive Controls**: Transform controls for positioning and orienting projectors and surfaces
- **Unit System Flexibility**: Support for both metric and imperial measurements

## Getting Started

### Prerequisites

- Node.js (v14 or newer)
- npm or yarn

### Installation

1. Clone the repository
2. Navigate to the project directory
3. Install dependencies:

```bash
npm install
```

4. Start the development server:

```bash
npm start
```

5. Open your browser and navigate to `http://localhost:3000`

## Usage

### Basic Workflow

1. Add a projector using the "Add Projector" button in the Projector panel
2. Adjust projector parameters (throw distance, image width, throw ratio, etc.)
3. Add a surface using the "Add Surface" button in the Surface panel
4. Position the projector and surface in 3D space using the transform controls
5. Import venue models using the Import panel (drag and drop OBJ or FBX files)
6. Create multi-projector setups using the Multi-Projector panel

### Projector Parameters

- **Throw Distance**: Distance from projector to projection surface
- **Image Width**: Width of the projected image on the surface
- **Throw Ratio**: Ratio of throw distance to image width (TR = D/W)
- **Aspect Ratio**: Ratio of image width to height (e.g., 16:9, 4:3)

### Surface Types

- **Flat**: Standard flat projection surface
- **Curved**: Single-axis curved surface
- **Cylindrical**: Cylindrical surface with constant radius
- **Spherical**: Spherical surface with constant radius

### Multi-Projector Features

- **Collections**: Group projectors for easier management
- **Grid Layout**: Automatically arrange projectors in a grid pattern
- **Edge Blending**: Configure overlap regions for seamless multi-projector setups

## Technical Details

### Core Technologies

- **React**: UI framework
- **TypeScript**: Type-safe JavaScript
- **Three.js**: 3D rendering
- **Zustand**: State management

### Project Structure

```
web-projection-system/
├── public/                 # Static assets
├── src/
│   ├── components/         # React components
│   ├── models/             # Data models
│   ├── store/              # State management
│   ├── utils/              # Utility functions
│   ├── App.tsx             # Main application component
│   └── index.tsx           # Entry point
└── package.json            # Dependencies and scripts
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
