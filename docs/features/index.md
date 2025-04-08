# Feature Reference

This section provides detailed reference information for all the features implemented in the Blender Projection System add-on. Each feature is documented with usage instructions, technical details, and examples.

## Core Features

### Projector Parameters

The core of the add-on revolves around three key parameters that are mathematically linked:

- **[Throw Distance](parameters.md#throw-distance)**: Distance from projector to projection surface
- **[Image Width](parameters.md#image-width)**: Width of the projected image
- **[Throw Ratio](parameters.md#throw-ratio)**: Ratio of throw distance to image width (TR = D/W)

When one parameter changes, the others update automatically to maintain the mathematical relationship.

### Visualization

The add-on provides several visualization tools:

- **[Projection Cone](visualization.md#projection-cone)**: Geometry Nodes-based visualization of the projection area
- **[Test Surface](visualization.md#test-surface)**: Optional plane for visualizing projection
- **[Projection Mapping](visualization.md#projection-mapping)**: Camera-based projection onto actual model surfaces

### Environment

Tools for creating and managing projection environments:

- **[Model Import](environment.md#model-import)**: Import OBJ and FBX models with proper scaling
- **[Basic Room Creation](environment.md#basic-room-creation)**: Quick creation of simple room environments
- **[Object Positioning](environment.md#object-positioning)**: Tools for positioning objects relative to projectors

### Multi-Projector Management

Features for working with multiple projectors:

- **[Projector Collections](multi-projector.md#projector-collections)**: Organize projectors into manageable groups
- **[Projector Duplication](multi-projector.md#projector-duplication)**: Create copies of projectors with preserved settings
- **[Overlap Detection](multi-projector.md#overlap-detection)**: Identify where projections overlap
- **[Edge Blending](multi-projector.md#edge-blending)**: Control blending in overlapping areas
- **[Projector Alignment](multi-projector.md#projector-alignment)**: Align projectors in organized arrangements

## User Interface

The add-on provides a comprehensive UI for all features:

- **[Projection Planner Panel](ui.md#projection-planner-panel)**: Main controls for projector operations
- **[Multi-Projector Setup Panel](ui.md#multi-projector-setup-panel)**: Collection and multi-projector management
- **[Unit System Toggle](ui.md#unit-system-toggle)**: Switch between Metric and Imperial units
- **[Parameter Controls](ui.md#parameter-controls)**: UI for projector parameters
- **[Visualization Controls](ui.md#visualization-controls)**: UI for visualization features

## Technical Components

For developers, the add-on includes several technical components:

- **[Property System](technical.md#property-system)**: Custom properties with bidirectional linking
- **[Update Callbacks](technical.md#update-callbacks)**: Preventing recursive updates
- **[Driver System](technical.md#driver-system)**: Connecting properties to visualization
- **[Operator Framework](technical.md#operator-framework)**: Implementation of add-on operations
- **[PropertyGroup Collections](technical.md#propertygroup-collections)**: Collection management structure

## Feature Status

The following table summarizes the implementation status of all features:

| Feature | Status | Milestone | Notes |
|---------|--------|-----------|-------|
| Add-on Structure | Completed | 1 | Core files, registration, modules |
| UI Panels | Completed | 1 | Sidebar panels, controls |
| Unit System Toggle | Completed | 1 | Metric/Imperial units |
| Projector Creation | Completed | 2 | Object hierarchy, properties |
| Parameter Linking | Completed | 3 | Bidirectional calculation |
| Projection Cone | Completed | 4 | Geometry Nodes visualization |
| Test Surface | Completed | 4 | Test plane creation |
| Model Import | Completed | 5 | OBJ/FBX support with scaling |
| Environment Creation | Completed | 5 | Basic room generator |
| Projection Mapping | Completed | 5 | Camera-based projection |
| Projector Collections | Completed | 6 | Organization of projectors |
| Projector Duplication | Completed | 6 | Copying with preserved settings |
| Overlap Detection | Completed | 6 | Finding overlapping areas |
| Edge Blending | Completed | 6 | Basic blending controls |
| Projector Alignment | Completed | 6 | Alignment tools |

## Next Steps

The following features are planned for future development:

- Enhanced edge blending visualization
- Save/load functionality for projector setups
- Detailed projection visualization (brightness, falloff)
- Interactive manipulation tools
- Ambient light simulation
- Thermal visualization for projector placement
- VR/AR integration 