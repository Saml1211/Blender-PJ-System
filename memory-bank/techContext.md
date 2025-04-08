# Technical Context

## Technologies Used

### Core Technologies
- **Blender**: Version 4.2+
- **Python**: Version 3.10+ (included with Blender)
- **Blender Python API**: Used for add-on development and integration
- **Geometry Nodes**: Used for visualization of projection cones

### Development Tools
- **Git**: Version control system
- **GitHub**: Hosting repository and collaboration

## Development Setup

### Prerequisites
- Blender 4.2 or newer installed
- Git for version control
- Text editor or IDE for Python development

### Installation for Development
1. Clone the repository:
   ```bash
   git clone https://github.com/Saml1211/Blender-PJ-System.git
   ```

2. Create a symlink from the repository to your Blender addons folder:
   - **Windows**: 
     ```
     mklink /D %APPDATA%\Blender Foundation\Blender\4.2\scripts\addons\blender_projection_system path\to\repo\blender_projection_system
     ```
   - **macOS**: 
     ```
     ln -s /path/to/repo/blender_projection_system ~/Library/Application\ Support/Blender/4.2/scripts/addons/
     ```
   - **Linux**: 
     ```
     ln -s /path/to/repo/blender_projection_system ~/.config/blender/4.2/scripts/addons/
     ```

3. Restart Blender or reload scripts (F3 > "Reload Scripts")

## Technical Constraints

### Blender Version Compatibility
- Must be compatible with Blender 4.2+
- Uses features specific to Blender's Geometry Nodes system
- Must accommodate Blender's Python API constraints

### Performance Considerations
- Real-time visualization must be efficient
- Complex calculations should not impact the user experience
- Multiple projector setups need efficient handling

### Dependencies
- No external Python packages beyond what's included with Blender
- Relies on Blender's built-in modules and systems

### Testing Environment
- Needs testing across different operating systems (Windows, macOS, Linux)
- Requires validation with various Blender versions (starting from 4.2)

## Integration Points

### Blender Core Integration
- Add-on integrates with Blender's sidebar (N-panel)
- Uses Blender's property system for data management
- Leverages Blender's operator system for user interactions
- Employs Blender's Geometry Nodes for visualization

### File Formats
- Supports OBJ and FBX import for environment models
- Works with standard Blender file format (.blend)

## Development Workflow
1. Local development with linked add-on
2. Testing within Blender environment
3. Version control through Git/GitHub
4. Documentation maintained alongside code
5. Issue tracking and feature requests on GitHub 