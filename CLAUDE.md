# ThreadMaker — Fusion 360 Add-In

"Threads for the 3D print makers"

## Project

Fusion 360 add-in for creating multi-start threads optimized for FDM 3D printing.
Supports 1-N starts, custom profiles (V, trapezoidal, buttress), inner/outer threads,
fit clearances, and GPI/SPI bottle closure presets.

## Stack

- Python (Fusion 360 embedded runtime, 3.14)
- Fusion 360 API (`adsk.core`, `adsk.fusion`)
- No external dependencies

## Critical API Knowledge

**CoilFeatures is READ-ONLY** — cannot create coils via API. Use instead:
- `TemporaryBRepManager.createHelixWire()` for helix geometry
- `SweepFeatures` to sweep thread profile along helix path
- `CircularPatternFeatures` or rotated start points for multi-start

**Key methods:**
```python
tmpBRepMgr = adsk.fusion.TemporaryBRepManager.get()
helixWire = tmpBRepMgr.createHelixWire(axisPoint, axisVector, startPoint, pitch, turns, taperAngle)
```

**From TongueGroove lessons:**
- SWIG requires plain Python `list` for `participantBodies`, not ObjectCollection
- `distanceOne` does NOT work for Cut sweeps
- `app.log('')` crashes — use `app.log(' ')` for blank lines
- `AllExtentDefinition.create()` doesn't exist — use `ThroughAllExtentDefinition.create()`
- Chamfer must run before trim cuts (sweep faces go stale)
- Diagnostic scripts first, then implement

## Development Methodology (lessons from TongueGroove)

### You cannot interpret 3D screenshots
Do not say "I can see in the image that..." about geometry. Ask for measurements,
log output, or descriptions in words. You can read UI text and error messages.

### Diagnostic scripts before guessing
When unsure if an API method works as documented, write a standalone Script that
creates test geometry, performs the operation, and measures with `boundingBox` and
`pointContainment`. Deploy to `~/Library/.../API/Scripts/<Name>/`. Numbers don't lie.

### Never iterate by changing the add-in and asking the user to test
If you've tried the same fix twice and it doesn't work, write a diagnostic script
to understand what's actually happening. The user's time is expensive.

### Verify every API method against the Python stubs
Grep the stubs — they are the single source of truth:
```bash
grep -A 15 "def methodName" "~/Library/.../Autodesk Fusion.app/Contents/Api/Python/packages/adsk/fusion.py"
```

### Operation order matters
Feature face references become stale after the body is modified. Plan the sequence:
- Chamfer/fillet BEFORE trim cuts (sweep faces go stale after cuts)
- Log face counts and edge counts to detect stale references
- The groove fillet works after fill-back because fills are Join (additive), not Cut

### Full sweep + trim/fill pattern
For controlling feature extent along a path:
- `distanceOne` does NOT work for Cut sweeps (verified)
- Instead: full sweep, then trim (Cut) or fill-back (Join) at each end
- Trim/fill uses construction plane at gap position + DistanceExtentDefinition
- Add 0.05mm margin to trim distances to catch curve slivers

### Log everything from the start
Every operation should log values in mm: distances, fractions, face counts, edge counts,
feature health states. When something fails, the log tells you exactly where and why.

### Tooltips, icons, help from the start
Include Resources/ folder with 16x16, 32x32, 64x64 icons, 300x200 toolclip,
help.html, and tooltips on every command input. Makes the add-in feel native.

### Update docs when you learn something
Add findings to `verified-findings.md` in the fusion360-scripting skill immediately.
Future sessions benefit from past pain.

## Key Files

- `PLAN.md` — comprehensive design plan with UI layout, features, API approach
- `ThreadMaker.py` — add-in source (to be written)
- `Resources/` — icons, toolclip, help.html

## Deployment

```bash
bash deploy.sh
```

Add-in directory: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/ThreadMaker/`
