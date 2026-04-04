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

## Before Writing Code

1. Use the `fusion360-scripting` skill — check `verified-findings.md` first
2. Write diagnostic scripts to test uncertain API behaviour
3. Grep Python stubs for exact method signatures
4. Never trust training data for Fusion 360 API

## Key Files

- `PLAN.md` — comprehensive design plan with UI layout, features, API approach
- `ThreadMaker.py` — add-in source (to be written)
- `Resources/` — icons, toolclip, help.html

## Deployment

```bash
bash deploy.sh
```

Add-in directory: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/ThreadMaker/`
