# Blender Projection System - Minimum Viable Product (MVP) PRD

**Version:** MVP 1.0
**Date:** 2025-03-29

## 1. Overview and Objectives (MVP Focus)

### 1.1 Purpose
The Minimum Viable Product (MVP) for the Blender Projection System add-on aims to provide AV System Design Engineers with a fundamental toolset within Blender for calculating and visualizing basic projector setups in 3D. It serves as the foundation for a more advanced simulation system, focusing initially on core calculations, visualization, and usability.

### 1.2 MVP Objectives
-   Validate the core value proposition: accurate 3D projection calculations integrated into Blender.
-   Provide a functional tool for single projector setup planning.
-   Enable basic visualization of multiple manually placed projectors.
-   Gather user feedback on core usability and calculation accuracy to inform future development.
-   Establish the core technical architecture (Python add-on structure, Geometry Nodes usage, data storage).

## 2. Target Audience

This add-on (including the MVP) is designed for professional **AV System Design Engineers** involved in:
-   Film production pre-visualization
-   Architectural lighting design
-   Live event staging
-   Corporate AV installations
-   Museum and immersive environment design

These users require precise tools to plan projector placement and ensure desired image size/coverage before physical installation.

## 3. MVP Core Features and Functionality

The MVP will include the following essential features:

### 3.1 Core Calculations (Single Projector)
-   **Functionality:** Provide interactive calculation for a selected projector object based on Throw Distance (D), Image Width (W), and Throw Ratio (TR). Implement the relationship `TR = D / W`.
-   **Bidirectional Linking:** Allow users to input or adjust any two of these parameters (D, W, TR) via the UI panel, and the third parameter should automatically calculate and update.
-   **Aspect Ratio (AR):** Allow users to set a fixed Aspect Ratio (e.g., 16:9). The calculated Image Height (`H = W / AR`) should be used implicitly for visualization but may not need a dedicated UI field in the MVP.
-   **Acceptance Criteria:**
    -   Changing the 'Throw Distance' input updates 'Image Width' correctly (assuming fixed TR) or updates 'Throw Ratio' (assuming fixed W).
    -   Changing the 'Image Width' input updates 'Throw Distance' correctly (assuming fixed TR) or updates 'Throw Ratio' (assuming fixed D).
    -   Changing the 'Throw Ratio' input updates 'Throw Distance' correctly (assuming fixed W) or updates 'Image Width' (assuming fixed D).
    -   Calculations are accurate to at least 3 decimal places.
    -   Edge cases (e.g., zero width/distance) are handled gracefully (e.g., display 'inf' or prevent invalid input).

### 3.2 Basic Visualization (Projection Cone)
-   **Functionality:** Display a visual representation of the selected projector's light cone (frustum) in the Blender 3D viewport.
-   **Implementation:** Use Blender's Geometry Nodes to procedurally generate the cone mesh.
-   **Real-time Update:** The cone visualization must update in near real-time when the projector object is moved/rotated or when its calculation parameters (Distance, Width, Ratio, AR) are changed in the UI panel.
-   **Acceptance Criteria:**
    -   A visible cone/frustum is attached to the selected projector object.
    -   The cone's dimensions (length, base size) accurately reflect the current Throw Distance, Image Width, and Aspect Ratio.
    -   The cone updates smoothly (< 100ms latency) when the projector transform or UI parameters are adjusted interactively.
    -   Only the cone for the *currently selected* projector is actively visualized (to keep MVP simple).

### 3.3 Unit System (Metric/Imperial Toggle)
-   **Functionality:** Allow users to switch the display units for distances and sizes between Metric (meters) and Imperial (feet/inches).
-   **Implementation:** Implement a toggle switch in the UI panel. Internal calculations will remain in Metric (meters).
-   **UI Update:** When the toggle is switched, all relevant numeric input fields and potentially viewport labels (if added later) should update their displayed values and unit indicators (e.g., "(m)" or "(ft)") instantly.
-   **Acceptance Criteria:**
    -   A UI toggle exists for Metric/Imperial units.
    -   Switching the toggle immediately updates the displayed values in the Distance and Width fields according to standard conversion factors (e.g., 1 m = 3.28084 ft).
    -   Inputting a value is interpreted based on the currently selected unit system.

### 3.4 Basic Model Import (OBJ/FBX)
-   **Functionality:** Provide a button in the UI panel to import 3D models representing the venue or environment.
-   **Supported Formats:** Initially support common mesh formats: `.obj` and `.fbx`. Leverage Blender's built-in importers.
-   **Workflow:** User clicks 'Import Model', selects a file. The model is imported into the current Blender scene.
-   **Acceptance Criteria:**
    -   An 'Import Model' button exists in the UI panel.
    -   Clicking the button opens a file browser.
    -   Selecting a valid `.obj` or `.fbx` file successfully imports the geometry into the scene.
    -   Basic import works for moderately complex models (e.g., up to 50k polygons) without crashing. (Note: Unit scaling/normalization is deferred post-MVP unless trivial to implement).

### 3.5 Manual Multi-Projector Placement
-   **Functionality:** Allow users to have multiple projector objects in the scene simultaneously, each with its own settings and visualization cone (when selected).
-   **Workflow:** Users can duplicate existing projector objects (using standard Blender methods `Shift+D`) or add new ones (method TBD, could be a simple "Add Projector" button later). Each projector object stores its own settings.
-   **Visualization:** Only the cone for the currently selected projector is visible. Users can select different projectors to see their respective cones and edit their parameters in the panel. This allows basic manual layout planning by seeing how cones overlap.
-   **Acceptance Criteria:**
    -   Multiple objects designated as 'projectors' can exist in the scene.
    -   Selecting a different projector object updates the UI panel to show its specific Distance/Width/Ratio values.
    -   Selecting a different projector object updates the viewport to show *only* its projection cone.
    -   Projector settings are stored independently per object.

## 4. MVP Technical Stack Recommendations

-   **Core Logic & UI:** Python (using Blender's `bpy` API)
-   **Visualization:** Blender Geometry Nodes (for procedural cone mesh)
-   **Data Storage:** Blender Custom Properties (stored directly on the projector objects within the `.blend` file)

## 5. MVP Conceptual Data Model

Projector-specific data will be stored using Blender's Custom Properties attached to each Blender object representing a projector.

-   **Projector Object:** (Blender Empty or Mesh)
    -   `is_projector`: Boolean (True) - Identifier
    -   `throw_distance`: Float (meters)
    -   `image_width`: Float (meters)
    -   `throw_ratio`: Float
    -   `aspect_ratio_w`: Integer (e.g., 16)
    -   `aspect_ratio_h`: Integer (e.g., 9)
    -   *(Other parameters like lens shift, lumens etc. are deferred post-MVP)*

This data is saved automatically within the `.blend` file.

## 6. MVP UI Design Principles

-   **Simplicity:** Keep the UI panel clean and focused on MVP features only.
-   **Discoverability:** Place controls logically within a dedicated sidebar panel (e.g., "Projection Planner" tab).
-   **Responsiveness:** Ensure UI controls and viewport visualization provide immediate feedback.
-   **Standard Blender Integration:** Follow Blender UI conventions for panels, buttons, and input fields. Use Custom Properties for data storage.

### MVP UI Panel Layout (Conceptual)

```
-----------------------------
 Projection Planner [Panel]
-----------------------------
 [ ] Unit System: [Metric | Imperial]

 --- Selected Projector ---
 Throw Distance: [__Input__] (m/ft)
 Image Width:    [__Input__] (m/ft)
 Throw Ratio:    [__Input__]
 Aspect Ratio:   [ 16 ] : [ 9 ]

 --- Scene ---
 [ Import Model (OBJ/FBX) ]
-----------------------------
```

### MVP Viewport Visualization

-   Display only the projection cone/frustum geometry for the currently selected projector object.
-   No other overlays (labels, heatmaps) in the MVP.

## 7. MVP Potential Challenges and Solutions

-   **Challenge:** Python performance for real-time Geometry Node updates when interactively dragging sliders or objects.
-   **Mitigation:** Write efficient Python update handlers. Ensure Geometry Node trees are simple for the MVP cone visualization. Profile code if lag is noticeable even with single projectors. Defer more complex calculations/visualizations.

## 8. Future Expansion Possibilities (Post-MVP)

This MVP establishes the foundation. Future versions will build upon this by adding features outlined in the full PRD, such as:
-   Advanced multi-projector management (auto-alignment, edge blending)
-   Illuminance calculations (Lux, lumens) and ambient light simulation
-   Support for more import formats (DWG, SKP, IFC) with unit normalization
-   Advanced visualizations (heatmaps, labels, surface projection)
-   Thermal simulation
-   VR/AR integration
-   Plugin API

---
*End of MVP PRD*