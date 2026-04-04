# ThreadMaker — Design Plan

**"Threads for the 3D print makers"**

A Fusion 360 add-in for creating multi-start threads optimized for FDM 3D printing.
Supports inner and outer threads, configurable profiles, fit clearances, and
standard bottle/jar closure presets.

## Target Users

- 3D printing hobbyists designing threaded closures
- Product designers creating bottle/jar prototypes
- Engineers needing quick-turn multi-start threads
- Anyone who finds Fusion's built-in Thread tool insufficient for multi-start or custom profiles

## Core Features

### 1. Thread Types
- **Outer (male)** — protrusion on a cylindrical surface
- **Inner (female)** — channel cut into a cylindrical bore
- **Both** — create matching male and female from one operation

### 2. Multi-Start Support
- 1 to 8 starts (default: 1)
- Starts evenly spaced: 360° / N
- Lead = Pitch × Starts (calculated and displayed)
- Turns-to-close calculated and shown (helps user understand quick-turn benefit)

### 3. Thread Profiles (optimized for FDM)
- **V-Thread 60°** (default) — ISO metric compatible, prints well at 30° from vertical
- **Trapezoidal 30°** — flat crest/root, strong shear resistance
- **ACME 29°** — similar to trapezoidal, US standard
- **Buttress 45°/7°** — asymmetric, best for containers/compression
- **Custom** — user-defined flank angles, crest/root widths

### 4. Fit Clearance (3D printing specific)
- **Radial clearance** per side (default 0.3mm for 0.4mm nozzle)
- **Axial clearance** (thread depth reduction)
- Presets: Tight (0.15mm), Standard (0.3mm), Loose (0.4mm), Custom
- Nozzle size input to auto-calculate minimum features

### 5. Thread Geometry
- **Nominal diameter** (outer for male, inner for female)
- **Pitch** (distance between threads on same start)
- **Thread depth** (default: 0.65 × pitch)
- **Thread length** (along axis)
- **Lead-in chamfer** (45° × 0.5mm default) at both ends
- **Thread fade** (gradual depth ramp over 1.5 × pitch at start/end)

### 6. Presets
- **Metric** — M6, M8, M10, M12, M16, M20 (single-start)
- **Bottle GPI/SPI** — 24-400, 28-400, 28-410, 33-400, 38-400, 53-400
- **Custom** — save and recall user-defined thread specs

### 7. Smart Calculations
- Auto-calculate lead from pitch × starts
- Auto-calculate turns-to-close from thread length / lead
- Auto-calculate min wall thickness warning
- Auto-calculate recommended engagement length (1.5 × diameter)
- Show overhang angle warning if profile exceeds 45°
- Validate thread depth vs wall thickness

### 8. Visual Aide
- Section view diagram in the command dialog showing thread profile
- Labels for pitch, depth, crest, root, flank angle
- Updates live as user changes parameters
- Different diagram for inner vs outer thread

## UI Layout

```
── THREADMAKER ──

Thread Type          [Outer ▾]        Outer / Inner / Both
Apply To             [1 selected]     Select cylindrical face or edge

── Dimensions ──
Nominal Diameter     20 mm            (auto-detected from selection)
Pitch                2.0 mm
Number of Starts     3
Thread Length         15 mm
Lead (calculated)    6.0 mm           (read-only: pitch × starts)
Turns to Close       2.5              (read-only: length / lead)

── Profile ──
Profile Type         [V-Thread 60° ▾]
Thread Depth         1.3 mm           (default: 0.65 × pitch)
Crest Width          0.25 mm          (default: 0.125 × pitch)
Root Width           0.35 mm          (default: 0.175 × pitch)

── Fit (3D Printing) ──
Clearance Preset     [Standard ▾]     Tight / Standard / Loose / Custom
Radial Clearance     0.3 mm/side
Nozzle Diameter      0.4 mm           (for validation)

── Options ──
Lead-in Chamfer      ☑  0.5 mm
Thread Fade          ☑  3.0 mm        (default: 1.5 × pitch)
Direction            [Right-hand ▾]    Right-hand / Left-hand

── Presets ──
Load Preset          [None ▾]         Metric / GPI Bottle / Custom...

                     [OK]  [Cancel]
```

## Technical Approach

### CRITICAL: CoilFeatures API is READ-ONLY

The Fusion 360 `CoilFeatures` collection has NO `createInput()` or `add()` method.
Coils are a "primitive" feature — UI only, cannot be created via the API.
(Same limitation as BoxFeatures, CylinderFeatures, SphereFeatures.)

Also: no start angle offset, no custom profile. Only 4 built-in section types
(circle, square, triangular external/internal).

### Primary Approach: HelixWire + Sweep

`TemporaryBRepManager.createHelixWire()` creates a helix wire body with full control:

```python
tmpBRepMgr = adsk.fusion.TemporaryBRepManager.get()
helixWire = tmpBRepMgr.createHelixWire(
    axisPoint,    # Point3D — point on helix axis
    axisVector,   # Vector3D — axis direction
    startPoint,   # Point3D — start point (distance to axis = radius)
    pitch,        # float — pitch in cm
    turns,        # float — number of turns
    taperAngle    # float — taper angle in radians (0 for straight)
)
```

For multi-start (N starts):
1. Calculate startPoint for each start: rotate by `i × 360°/N` around axis
2. Create N helix wires with `createHelixWire()`
3. Add each wire to a BaseFeature to persist it
4. Create Path from each wire's edge
5. Draw thread profile sketch perpendicular to helix at start
6. Sweep profile along each helix path

Angular offset for start points:
```python
matrix = adsk.core.Matrix3D.create()
matrix.setToRotation(i * 2 * math.pi / N, axisVector, axisPoint)
startPt = startPoint.copy()
startPt.transformBy(matrix)
```

### Alternative: Single start + CircularPattern

1. Create one thread start (helix wire + sweep)
2. Use `CircularPatternFeatures` to replicate N times at 360°
3. `quantity = N` (includes original), `totalAngle = 2π`
4. This works because rotating a coil around its central axis offsets the start angle

### For inner (female) threads:
- Sweep with `CutFeatureOperation` directly into the bore body
- OR: create as NewBody, then Boolean subtract

### For matching male+female pair:
- Create male thread geometry
- Create female = male dimensions + 2 × radial clearance on diameter
- Female thread depth = male depth + axial clearance

### Thread fade (gradual start/end):
- Use `SweepFeatureInput.distanceOne` to control sweep extent? 
  (WARNING: distanceOne doesn't work for Cut sweeps — verified in TongueGroove)
- Better: scale the profile over the fade zone using a guide rail
- Or: create the helix wire with extra turns, sweep full, then trim the ends
  (same trim-cut approach proven in TongueGroove)

### Helix Wire → Persistent Edge

The wire from `createHelixWire()` is temporary. To use as sweep path:
```python
baseFeat = comp.features.baseFeatures.add()
baseFeat.startEdit()
comp.bRepBodies.add(helixWire, baseFeat)
baseFeat.finishEdit()
# Now get the edge from the persistent body
edge = baseFeat.bodies.item(0).edges.item(0)
path = adsk.fusion.Path.create(edge, ChainedCurveOptions.connectedChainedCurves)
```

## Operation Sequence

1. **Read inputs** — diameter, pitch, starts, length, profile, clearances
2. **Validate** — wall thickness, overhang angles, minimum features for nozzle
3. **Create thread profile sketch** — on a plane perpendicular to the axis at the thread start
4. **For each start (i = 0 to N-1)**:
   a. Rotate the profile sketch by `i × 360°/N`
   b. Create a coil or sweep along helical path
   c. Join (outer) or Cut (inner) to the target body
5. **Add lead-in chamfer** at both ends
6. **Create matching thread** if "Both" selected (with clearance applied)

## Error Handling

- **Diameter too small for pitch**: "Thread depth exceeds available wall. Reduce pitch or increase diameter."
- **Chamfer too large**: auto-reduce like TongueGroove
- **Overhang warning**: "Flank angle exceeds 45°. Thread may require supports when printing."
- **Feature creation failure**: log face/edge details for debugging
- **No cylindrical face selected**: clear message about what to select

## Logging

All operations log values in mm:
- Thread parameters (diameter, pitch, starts, lead, depth)
- Profile dimensions (crest, root, flank angles)
- Clearances applied
- Each coil/sweep creation: success/failure + health state
- Chamfer/fade operations
- Total feature count and timeline impact

## Testing Plan

### Diagnostic scripts (before add-in):
1. **Single coil on a cylinder** — verify Coil API works, measure result
2. **Multi-start offset** — verify angular offset approach (pattern or multiple coils)
3. **Custom profile sweep** — verify sweep along helical path with trapezoidal profile
4. **Inner thread cut** — verify CutFeatureOperation on a bore

### Manual tests (with add-in):
1. Simple outer M10 thread on a cylinder
2. Inner M10 thread in a bore
3. Triple-start bottle thread (28-400 style)
4. Matching male + female pair → test fit
5. Various profiles (V, trapezoidal, buttress)
6. Edge cases: very fine pitch, very coarse pitch, many starts

## Default Values

```python
DEFAULTS = {
    'pitch_mm': 2.0,
    'starts': 1,
    'thread_length_mm': 15.0,
    'depth_factor': 0.65,        # depth = factor × pitch
    'crest_factor': 0.125,       # crest width = factor × pitch
    'root_factor': 0.175,        # root width = factor × pitch
    'clearance_mm': 0.3,         # per side radial clearance
    'nozzle_mm': 0.4,
    'chamfer_mm': 0.5,
    'chamfer_angle_deg': 45,
    'fade_factor': 1.5,          # fade length = factor × pitch
    'min_wall_mm': 2.0,
    'engagement_factor': 1.5,    # engagement = factor × diameter
    'profile': 'v60',            # v60, trap30, acme29, buttress, custom
    'direction': 'right',        # right or left hand
}
```

## File Structure

```
ThreadMaker/
├── ThreadMaker.py           # Add-in entry point
├── ThreadMaker.manifest     # type: addin
├── Resources/
│   ├── 16x16.png
│   ├── 32x32.png
│   ├── 64x64.png
│   ├── toolclip.png         # 300×200px
│   └── help.html
├── ARCHITECTURE.md          # Operation scratchpad
├── CLAUDE.md                # Project context
└── README.md                # User documentation
```

## Competitive Landscape

**No existing public add-in creates multi-start threads via the API.**

| Project | Stars | What it does | Limitation |
|---|---|---|---|
| CustomThreads | 380 | Thread XML definitions for 3D printing | Single-start only, uses threadFeatures API |
| ThreadKeeper | 86 | Restores thread XMLs after Fusion updates | Not a thread creator |
| HelixGenerator | 49 | Creates helical sketch splines | No thread profile, no sweep |
| CustomScrews | 42 | Parametric screws | Single-start standard threads only |
| Bolt (Autodesk) | 4 | Bolt with hex head + thread | Standard threads only |
| Bottle (Autodesk) | 3 | Bottle with cap thread | Single-start, basic |

ThreadMaker fills the gap: multi-start + custom profiles + 3D printing clearances.

## Key API Facts (Verified)

- `CoilFeatures` has NO createInput/add — cannot create coils via API
- `TemporaryBRepManager.createHelixWire()` — creates helix with full control
- `Matrix3D.setToRotation()` — rotates start points for multi-start offset
- `CircularPatternFeatures` — can pattern a thread body N times around axis
- `threadFeatures` API — only single-start standard threads, not useful for us
- No `addHelix()` on sketch curves — cannot create helix in sketch programmatically
- BaseFeature required to persist temporary BRep wire bodies

## Research Status

- [x] 3D print thread design (profiles, tolerances, GPI standards)
- [x] Fusion 360 Coil API — **READ-ONLY, cannot create coils**
- [x] HelixWire API — **WORKS, full control over helix geometry**
- [x] GitHub existing add-ins — **no multi-start competition**
- [ ] Diagnostic script: createHelixWire + sweep on a cylinder
- [ ] Diagnostic script: multi-start with rotated start points
- [ ] Diagnostic script: CircularPattern vs N individual sweeps
