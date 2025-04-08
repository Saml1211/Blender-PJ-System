# Blender Projection System

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Blender Version](https://img.shields.io/badge/Blender-4.2%2B-orange)](https://www.blender.org/)

A comprehensive Blender add-on for AV System Design Engineers to accurately calculate, visualize, and plan projector setups in 3D environments.

![Projection System Preview](docs/images/preview.png)

## 🎯 MVP Status

The Minimum Viable Product (MVP) has been successfully completed! All planned milestones have been implemented, from basic add-on structure to multi-projector support.

## 🔑 Key Features

- **Accurate Projection Calculations**: Precise bidirectional relationships between throw distance, image width, and throw ratio
- **Real-time 3D Visualization**: Geometry Nodes-based visualization of projection cones with accurate aspect ratios
- **Multi-Projector Management**: Collections, duplication, edge blending, and overlap detection for complex setups
- **Model Import Support**: OBJ/FBX import with scale control and environment tagging
- **Environment Creation**: Quick room setup tools with positioning controls
- **Projection Mapping**: Camera-based projection visualization onto model surfaces
- **Unit System Flexibility**: Support for both metric and imperial measurements

## 📋 Quick Start

### Installation

1. Download the `projection_system_v0.1.0.zip` file from this repository
2. Open Blender and navigate to Edit > Preferences > Add-ons
3. Click "Install..." and select the downloaded zip file
4. Enable the add-on by checking the box next to "3D View: Projection Planner MVP"

**Note**: If you encounter any issues during installation, you can use the `cleanup_addon.py` script to clean up any previous installations:

1. Open Blender's Scripting workspace
2. Create a new script and paste the contents of `cleanup_addon.py`
3. Run the script
4. Close and reopen Blender
5. Try installing the addon again

### Basic Usage

1. Open the Sidebar in the 3D View (press N if not visible)
2. Select the "Projection Planner" tab
3. Add a projector to your scene by clicking "Add Projector"
4. Adjust parameters like Throw Distance, Image Width, or Throw Ratio
5. See the projection cone update in real-time in the viewport
6. Import models or create a basic environment using the Environment section
7. Use the "Multi-Projector Setup" tab to manage collections of projectors

## 📖 Documentation

- [User Manual](docs/manual/index.md) - Complete instructions for using the add-on
- [Feature Reference](docs/features/index.md) - Detailed information about all features
- [Tutorial Videos](docs/tutorials/index.md) - Step-by-step tutorial videos

## 🛠️ Development

### Prerequisites

- Blender 4.2 or newer
- Python 3.10+ (included with Blender)
- Git for version control

### Setting Up Development Environment

1. Clone this repository:

   ```bash
   git clone https://github.com/Saml1211/Blender-PJ-System.git
   ```

2. Create a symlink from the repository to your Blender addons folder:
   - **Windows**: `mklink /D %APPDATA%\Blender Foundation\Blender\4.2\scripts\addons\blender_projection_system path\to\repo\blender_projection_system`
   - **macOS**: `ln -s /path/to/repo/blender_projection_system ~/Library/Application\ Support/Blender/4.2/scripts/addons/`
   - **Linux**: `ln -s /path/to/repo/blender_projection_system ~/.config/blender/4.2/scripts/addons/`

3. Restart Blender or reload scripts (F3 > "Reload Scripts")

### Project Structure

```plaintext
Blender-PJ-System/
├── .github/                   # GitHub-specific files
├── blender_projection_system/ # Main add-on package
│   ├── __init__.py           # Add-on registration
│   ├── properties.py         # Property definitions
│   ├── operators.py          # Operator classes
│   ├── ui.py                 # User interface components
│   ├── visualization.py      # Geometry nodes and visualization
├── docs/                     # Documentation
├── memory-bank/              # Project documentation
├── tests/                    # Test cases
├── CONTRIBUTING.md           # Contribution guidelines
├── LICENSE                   # MIT License
└── README.md                 # This file
```

### Implemented Milestones

1. **Basic Add-on Structure**: Core framework, UI panel, unit toggle
2. **Projector Object Creation**: Object hierarchy, custom properties, operators
3. **Core Calculations**: Bidirectional parameter linking with throw distance, image width, and throw ratio
4. **Projection Visualization**: Geometry Nodes cone visualization with drivers
5. **Model Import**: OBJ/FBX import with environment tagging
6. **Multi-Projector Support**: Collections, duplication, overlap detection

## 🚀 Upcoming Features

- Enhanced edge blending visualization
- Save/load functionality for projector setups
- Detailed projection visualization (brightness, falloff)
- Interactive manipulation tools
- Ambient light simulation
- Thermal visualization for projector placement
- VR/AR integration

## ✨ Contributing

Contributions are welcome! Please check out our [Contributing Guidelines](CONTRIBUTING.md) for details on how to submit changes and the process for submitting pull requests.

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- The Blender Foundation for their amazing open-source 3D creation suite
- AV professionals for their insights and requirements input
- All contributors who help improve this tool
