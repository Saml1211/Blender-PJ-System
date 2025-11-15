# Projection Calculation Specification

## Overview

This document defines the canonical mathematical formulas used for projection calculations in the Blender Projection System. Both the Python (Blender add-on) and TypeScript (web application) implementations must produce identical results for identical inputs.

## Core Formulas

### 1. Throw Ratio Calculation

**Formula**: `TR = D / W`

Where:
- `TR` = Throw Ratio (dimensionless)
- `D` = Throw Distance (meters)
- `W` = Image Width (meters)

**Implementation Requirements**:
- If `W ≤ 0`, return `infinity`
- Result should be precise to at least 3 decimal places

**Example**:
```
D = 6.0m, W = 3.0m → TR = 2.0
D = 4.0m, W = 2.0m → TR = 2.0
D = 3.0m, W = 2.0m → TR = 1.5
```

### 2. Image Width Calculation

**Formula**: `W = D / TR`

Where:
- `W` = Image Width (meters)
- `D` = Throw Distance (meters)
- `TR` = Throw Ratio (dimensionless)

**Implementation Requirements**:
- If `TR ≤ 0`, return `infinity`
- Result should be precise to at least 3 decimal places

**Example**:
```
D = 6.0m, TR = 2.0 → W = 3.0m
D = 4.0m, TR = 2.0 → W = 2.0m
D = 10.0m, TR = 2.5 → W = 4.0m
```

### 3. Throw Distance Calculation

**Formula**: `D = W × TR`

Where:
- `D` = Throw Distance (meters)
- `W` = Image Width (meters)
- `TR` = Throw Ratio (dimensionless)

**Implementation Requirements**:
- No special edge cases (multiplication is always valid)
- Result should be precise to at least 3 decimal places

**Example**:
```
W = 3.0m, TR = 2.0 → D = 6.0m
W = 2.0m, TR = 2.0 → D = 4.0m
W = 4.0m, TR = 2.5 → D = 10.0m
```

### 4. Image Height Calculation

**Formula**: `H = W × (AR_h / AR_w)`

Where:
- `H` = Image Height (meters)
- `W` = Image Width (meters)
- `AR_w` = Aspect Ratio Width component (e.g., 16 for 16:9)
- `AR_h` = Aspect Ratio Height component (e.g., 9 for 16:9)

**Implementation Requirements**:
- If `AR_w ≤ 0`, return `0`
- Result should be precise to at least 3 decimal places

**Example**:
```
W = 16.0m, AR = 16:9 → H = 9.0m
W = 3.2m, AR = 16:9 → H = 1.8m
W = 4.0m, AR = 4:3 → H = 3.0m
```

## Edge Cases

### Division by Zero
- **Throw Ratio**: If image width is zero or negative, return `infinity`
- **Image Width**: If throw ratio is zero or negative, return `infinity`
- **Image Height**: If aspect ratio width is zero or negative, return `0`

### Negative Values
- Distance, width, and height should never be negative in valid projector setups
- If negative values are encountered:
  - For division operations: treat as zero (return `infinity`)
  - For multiplication operations: allow calculation but result will be negative

### Very Small Values
- Values less than 1mm (0.001m) should be handled carefully
- Floating point precision should maintain at least 3 decimal places

## Bidirectional Consistency

The formulas must maintain mathematical consistency in both directions:

```
Given D and W:
  TR = D / W
  W_calculated = D / TR
  D_calculated = W × TR

  Assert: W_calculated ≈ W (within 0.001m)
  Assert: D_calculated ≈ D (within 0.001m)
```

## Common Projector Types

Reference values for validation testing:

| Projector Type | Throw Ratio | Example Setup |
|---------------|-------------|---------------|
| Ultra Short Throw | 0.3 - 0.5 | 1.5m distance → 3.0-5.0m width |
| Short Throw | 0.5 - 1.0 | 2.0m distance → 2.0-4.0m width |
| Standard Throw | 1.5 - 2.0 | 6.0m distance → 3.0-4.0m width |
| Long Throw | 2.0 - 3.0 | 10.0m distance → 3.3-5.0m width |
| Ultra Long Throw | 3.0+ | 15.0m distance → 3.0-5.0m width |

## Implementation Locations

### Python Implementation
**File**: `blender_projection_system/properties.py`

**Functions**:
- `update_throw_distance()` - Lines 7-17: Calculates TR when D changes
- `update_image_width()` - Lines 19-29: Calculates TR when W changes
- `update_throw_ratio()` - Lines 31-41: Calculates W when TR changes

**Note**: Image height is calculated implicitly through aspect ratio properties.

### TypeScript Implementation
**File**: `web-projection-system/src/utils/projectionCalculations.ts`

**Functions**:
- `calculateThrowRatio(distance, width)` - Lines 9-12
- `calculateImageWidth(distance, throwRatio)` - Lines 18-21
- `calculateThrowDistance(width, throwRatio)` - Lines 27-29
- `calculateImageHeight(width, aspectRatioWidth, aspectRatioHeight)` - Lines 35-38

## Validation Requirements

Both implementations must pass the following validation tests:

### Test Case 1: Standard Throw
```
Input: D = 6.0m, W = 3.0m
Expected: TR = 2.0
```

### Test Case 2: Short Throw
```
Input: D = 2.0m, TR = 0.5
Expected: W = 4.0m
```

### Test Case 3: Aspect Ratio
```
Input: W = 3.2m, AR = 16:9
Expected: H = 1.8m
```

### Test Case 4: Bidirectional Consistency
```
Input: D = 6.0m, W = 3.0m
Step 1: TR = D / W = 2.0
Step 2: W_calc = D / TR = 3.0m
Step 3: D_calc = W × TR = 6.0m
Assert: W_calc = W AND D_calc = D
```

### Test Case 5: Edge Case - Zero Width
```
Input: D = 5.0m, W = 0.0m
Expected: TR = infinity
```

## Update Protocol

When modifying calculation logic:

1. **Update this specification first** - Document the change
2. **Update Python implementation** - Modify `properties.py`
3. **Update TypeScript implementation** - Modify `projectionCalculations.ts`
4. **Update tests** - Add test cases in both `test_calculations.py` and future TypeScript tests
5. **Validate consistency** - Manually verify both implementations produce identical results

## Version History

- **v1.0** (2025-01-15) - Initial specification based on MVP implementation
- Current implementations verified to match specification as of MVP completion

## References

- Blender Add-on: `blender_projection_system/properties.py`
- Web Application: `web-projection-system/src/utils/projectionCalculations.ts`
- Unit Tests: `tests/test_calculations.py`
- This specification supersedes any comments or documentation in the code files
