# Multi-Projector Management

The multi-projector management features allow you to work with multiple projectors in your scene, organizing them into collections, duplicating existing setups, detecting overlaps, and managing edge blending.

![Multi-Projector Panel](../images/multi-projector-panel.png)

## Projector Collections

Projector collections allow you to organize related projectors into logical groups for easier management and operations.

### Creating Collections

To create a new projector collection:

1. Navigate to the "Multi-Projector Setup" panel in the sidebar
2. Click the "Create Collection" button
3. Enter a name for your collection in the dialog
4. Click "OK" to create the collection

If you have projectors selected when creating a collection, they will be automatically added to the new collection.

### Collection Management

The collections panel displays all available projector collections with controls for:

- **Setting the active collection**: Click the radio button next to a collection name
- **Deleting a collection**: Click the X button next to a collection name
- **Adding projectors to a collection**: Select projectors and click "Add Selected"
- **Removing projectors from collections**: Select projectors and click "Remove from Collection"

### Collection Properties

Collections are implemented as named references stored as string properties on projector objects:

- Each projector has a `pj_collection` property that stores the collection name
- The scene maintains a list of collection names in `scene.pj_projector_collections`
- The active collection is tracked by `scene.pj_active_collection_index`

## Projector Duplication

The duplicator feature allows you to create copies of existing projectors with all their settings preserved.

### Duplicating Projectors

To duplicate a projector:

1. Select the projector you want to duplicate
2. Click the "Duplicate Projector" button in the main panel
3. A new projector will be created with the same settings
4. By default, it will be offset to the right of the original projector

### Duplication Options

When duplicating, you can adjust:

- **Offset Distance**: The distance between the original and duplicated projector

### What Gets Duplicated

The following properties are preserved when duplicating a projector:

- Throw distance
- Image width
- Throw ratio
- Aspect ratio (width and height)
- Collection membership
- Rotation (relative to the original)

## Overlap Detection

The overlap detection system identifies where multiple projectors' projection areas intersect, which is useful for edge blending and coordinated displays.

### Detecting Overlaps

To detect overlapping projections:

1. Position your projectors so their projection areas might intersect
2. Make sure the projectors are in the same collection
3. Click the "Detect Overlapping" button in the Multi-Projector panel
4. The add-on will analyze projector positions and parameters
5. Projectors with overlapping areas will be marked with the `pj_overlaps_with` property

### How Overlap Detection Works

The system uses the following criteria to determine potential overlaps:

1. **Collection Membership**: Projectors must be in the same collection
2. **Throw Distance Similarity**: Projection distances should be within 20% of each other
3. **Physical Proximity**: Projectors should be close enough for their cones to intersect

### Viewing Overlap Information

When a projector is detected as overlapping with another:

1. Select the projector
2. Check the "Overlaps with: [projector name]" information in the projector parameters
3. Adjust the "Edge Blend" slider to control the blending

## Edge Blending

Edge blending allows for smooth transitions between overlapping projection areas.

### Edge Blend Controls

For projectors with detected overlaps:

1. The "Edge Blend" slider appears in the projector parameters
2. Values range from 0.0 (no blending) to 1.0 (full blending)
3. Adjust the value to control how much the projectors blend in the overlap area

### Edge Blend Properties

Edge blending is controlled by:

- `pj_edge_blend_amount`: Float property (0.0-1.0) controlling blend amount
- `pj_overlaps_with`: String property referencing the overlapping projector

## Projector Alignment

The alignment tools help you position multiple projectors in organized arrangements.

### Aligning Projector Groups

To align projectors in a collection:

1. Select a collection in the Multi-Projector panel
2. Click the "Align Projectors" button
3. Adjust the spacing parameter if needed
4. The projectors will be arranged in a horizontal row

### Alignment Options

The alignment tool provides:

- **Spacing**: Distance between adjacent projectors in the aligned group

### Alignment Behavior

The alignment:

1. Uses the leftmost projector's position as the starting point
2. Sorts projectors by X position
3. Aligns all projectors to the same Y and Z coordinates
4. Spaces them evenly along the X axis
5. Sets all projectors to the same rotation

## Multi-Projector Statistics

The Multi-Projector panel includes statistics about your projector setup:

- **Total Projectors**: Number of projectors in the scene
- **Collections**: Number of projector collections
- **Overlapping Projectors**: Number of projectors with detected overlaps

## Advanced Usage

### Multi-projector Workflows

Effective multi-projector workflows typically follow this pattern:

1. Create and position your first projector
2. Duplicate it to create additional projectors
3. Organize related projectors into collections
4. Use the alignment tools to arrange projectors
5. Detect overlapping areas
6. Adjust edge blending for smooth transitions
7. Fine-tune individual projector parameters

### Working with Complex Projector Arrays

For complex arrangements with many projectors:

1. Create separate collections for different logical groups
2. Use parent objects or empties for additional organization
3. Consider scripting for very large arrays (10+ projectors)

## Technical Reference

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `pj_collection` | String | Collection name this projector belongs to |
| `pj_overlaps_with` | String | Name of projector this one overlaps with |
| `pj_edge_blend_amount` | Float (0.0-1.0) | Amount of edge blending for overlaps |
| `pj_is_active_projector` | Boolean | Whether this projector is active |

### Operators

| Operator | ID | Description |
|----------|----------|-------------|
| Duplicate Projector | `projection.duplicate_projector` | Creates a copy of selected projector |
| Create Collection | `projection.create_projector_collection` | Creates a new projector collection |
| Add to Collection | `projection.add_to_collection` | Adds selected projectors to active collection |
| Remove from Collection | `projection.remove_from_collection` | Removes projectors from their collection |
| Delete Collection | `projection.delete_collection` | Deletes the active collection |
| Detect Overlapping | `projection.detect_overlapping` | Finds overlapping projection areas |
| Align Projector Group | `projection.align_group` | Aligns projectors in a row |
| Set Active Collection | `projection.set_active_collection` | Sets the active collection | 