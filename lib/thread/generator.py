"""Core thread generation: helix wire → sweep → chamfer → pattern.

Both outer and inner threads use JoinFeatureOperation:
  - Outer: bumps protrude outward from cylinder surface
  - Inner: ridges protrude inward from bore wall

Lug tab mode creates simple rectangular tabs instead of helical ridges.
"""

from __future__ import annotations

import math
from typing import Optional

import adsk.core
import adsk.fusion

from .params import ThreadParameters
from . import profiles


def create_thread(
    params: ThreadParameters,
    target_face: adsk.fusion.BRepFace,
    design: adsk.fusion.Design,
) -> str:
    """Main entry point. Returns status message."""
    errors = params.validate()
    if errors:
        return "Validation:\n- " + "\n- ".join(errors)

    component = design.activeComponent
    if component is None:
        return "No active component."

    frame = _frame_from_face(target_face)
    if frame is None:
        return "Selected face must be cylindrical."

    # Lug tabs for inner threads when requested
    if params.thread_type == "inner" and params.female_style == "lug_tabs":
        return _build_lug_tabs(params, frame, component, target_face)

    return _build_helical_thread(params, frame, component, target_face)


# ── Face frame ──

class _FaceFrame:
    __slots__ = ('origin', 'axis', 'radius_cm', 'top_point', 'bottom_point', 'face_height_cm')

    def __init__(self, origin, axis, radius_cm, top_point, bottom_point, face_height_cm):
        self.origin = origin
        self.axis = axis
        self.radius_cm = radius_cm
        self.top_point = top_point
        self.bottom_point = bottom_point
        self.face_height_cm = face_height_cm


def _frame_from_face(face: adsk.fusion.BRepFace) -> Optional[_FaceFrame]:
    geom = face.geometry
    if not isinstance(geom, adsk.core.Cylinder):
        return None

    origin = adsk.core.Point3D.create(geom.origin.x, geom.origin.y, geom.origin.z)
    axis = adsk.core.Vector3D.create(geom.axis.x, geom.axis.y, geom.axis.z)
    axis.normalize()

    min_param = float('inf')
    max_param = float('-inf')

    for ei in range(face.edges.count):
        edge = face.edges.item(ei)
        for vertex in [edge.startVertex, edge.endVertex]:
            if vertex is None:
                continue
            pt = vertex.geometry
            vec = adsk.core.Vector3D.create(pt.x - origin.x, pt.y - origin.y, pt.z - origin.z)
            param = vec.dotProduct(axis)
            min_param = min(min_param, param)
            max_param = max(max_param, param)

    if min_param == float('inf'):
        bb = face.boundingBox
        for pt in [bb.minPoint, bb.maxPoint]:
            vec = adsk.core.Vector3D.create(pt.x - origin.x, pt.y - origin.y, pt.z - origin.z)
            param = vec.dotProduct(axis)
            min_param = min(min_param, param)
            max_param = max(max_param, param)

    top = adsk.core.Point3D.create(origin.x + axis.x * max_param, origin.y + axis.y * max_param, origin.z + axis.z * max_param)
    bot = adsk.core.Point3D.create(origin.x + axis.x * min_param, origin.y + axis.y * min_param, origin.z + axis.z * min_param)
    return _FaceFrame(origin, axis, geom.radius, top, bot, max_param - min_param)


# ── Helical thread ──

def _build_helical_thread(params, frame, component, target_face):
    """Create helical thread segments via helix wire → sweep → chamfer → pattern."""

    if params.thread_type == "outer":
        helix_radius = frame.radius_cm - params.helix_offset_cm
        op_label = "outer"
    else:
        helix_radius = frame.radius_cm + params.helix_offset_cm
        op_label = "inner"

    # Helix direction
    if params.start_from == "top":
        anchor = frame.top_point
        helix_axis = adsk.core.Vector3D.create(-frame.axis.x, -frame.axis.y, -frame.axis.z)
        offset_dir = -1.0
    else:
        anchor = frame.bottom_point
        helix_axis = adsk.core.Vector3D.create(frame.axis.x, frame.axis.y, frame.axis.z)
        offset_dir = 1.0

    if not params.right_hand:
        helix_axis.scaleBy(-1)

    helix_origin = adsk.core.Point3D.create(
        anchor.x + frame.axis.x * offset_dir * params.offset_cm,
        anchor.y + frame.axis.y * offset_dir * params.offset_cm,
        anchor.z + frame.axis.z * offset_dir * params.offset_cm,
    )

    radial = _perpendicular_to(frame.axis)
    radial.normalize()
    start_point = adsk.core.Point3D.create(
        helix_origin.x + radial.x * helix_radius,
        helix_origin.y + radial.y * helix_radius,
        helix_origin.z + radial.z * helix_radius,
    )

    # Cap revolutions so the thread respects end_position_cm (far-edge margin).
    # Available axial length = face_height - offset - end_position. If the
    # requested helix would overrun, truncate to fit. Minimum 0.1 turns.
    available_length = frame.face_height_cm - params.offset_cm - params.end_position_cm
    desired_length = params.helix_pitch_cm * params.helix_turns
    if available_length > 0 and desired_length > available_length:
        effective_turns = max(0.1, available_length / params.helix_pitch_cm)
    else:
        effective_turns = params.helix_turns

    # Create helix wire
    tmpBRep = adsk.fusion.TemporaryBRepManager.get()
    helix_wire = tmpBRep.createHelixWire(
        helix_origin, helix_axis, start_point,
        params.helix_pitch_cm, effective_turns, 0.0,
    )
    if helix_wire is None:
        return f"{op_label}: helix creation failed"

    # Persist wire
    base_feat = component.features.baseFeatures.add()
    base_feat.startEdit()
    component.bRepBodies.add(helix_wire, base_feat)
    base_feat.finishEdit()

    if base_feat.bodies.count == 0 or base_feat.bodies.item(0).edges.count == 0:
        return f"{op_label}: helix wire has no edges"

    helix_edge = base_feat.bodies.item(0).edges.item(0)
    path = adsk.fusion.Path.create(helix_edge, adsk.fusion.ChainedCurveOptions.noChainedCurves)

    # Profile plane + sketch
    plane_input = component.constructionPlanes.createInput()
    plane_input.setByDistanceOnPath(path, adsk.core.ValueInput.createByReal(0))
    profile_plane = component.constructionPlanes.add(plane_input)

    sketch = component.sketches.add(profile_plane)
    if params.profile == "circular":
        profiles.draw_circular(sketch, params.section_radius_cm)
    elif params.profile == "v60":
        profiles.draw_v_thread(sketch, params, params.thread_type)
    elif params.profile == "trapezoidal":
        profiles.draw_trapezoidal(sketch, params, params.thread_type)

    if sketch.profiles.count == 0:
        return f"{op_label}: no closed profile"

    # Sweep as Join
    operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
    sweeps = component.features.sweepFeatures
    sweep_input = sweeps.createInput(sketch.profiles.item(0), path, operation)
    sweep_input.orientation = adsk.fusion.SweepOrientationTypes.PerpendicularOrientationType
    target_body = target_face.body
    if target_body:
        sweep_input.participantBodies = [target_body]

    try:
        sweep_feat = sweeps.add(sweep_input)
    except Exception as e:
        return f"{op_label}: sweep failed — {e}"

    # Chamfer thread ends BEFORE pattern
    chamfer_feats = []
    if params.chamfer:
        chamfer_feats = _chamfer_ends(component, sweep_feat, params)

    # Circular pattern
    if params.num_starts > 1:
        try:
            _pattern(component, sweep_feat, chamfer_feats, frame, params.num_starts)
        except Exception as e:
            return f"{op_label}: pattern failed — {e}"

    # Hide wire
    if base_feat.bodies.count > 0 and base_feat.bodies.item(0).isValid:
        base_feat.bodies.item(0).isVisible = False

    return f"{op_label}: {params.num_starts}-start thread created"


# ── Lug tabs ──

def _build_lug_tabs(params, frame, component, target_face):
    """Create curved inward-protruding tabs on a bore via revolve.

    Approach: draw tab cross-section on a radial plane, revolve around
    the cylinder axis by tab_width degrees. This creates a curved tab
    that conforms to the bore wall.

    Tab-specific params (independent from helical thread params):
    - tab_height_cm: axial height (must fit between thread ridges)
    - tab_depth_cm: radial protrusion inward
    - tab_width_deg: angular span (revolve angle)
    - tab_offset_cm: distance from opening edge
    """
    radius_cm = frame.radius_cm
    tab_count = params.tab_count
    tab_height = params.tab_height_cm
    tab_depth = params.tab_depth_cm
    tab_width = params.tab_width_deg

    # Tab Z position at the opening edge
    if params.start_from == "bottom":
        tab_bottom_z = frame.bottom_point.z + params.tab_offset_cm
        tab_top_z = tab_bottom_z + tab_height
    else:
        tab_top_z = frame.top_point.z - params.tab_offset_cm
        tab_bottom_z = tab_top_z - tab_height

    target_body = target_face.body

    # Step 1: Create tab profile sketch on a RADIAL plane (contains the axis)
    # Use the XZ construction plane — this is a plane through the axis
    sketch = component.sketches.add(component.xZConstructionPlane)
    lines = sketch.sketchCurves.sketchLines

    # In XZ plane: X = radial distance from axis, sketch_Y = Z axis (height)
    # Tab profile: rectangle at the bore radius, protruding inward
    inner_r = radius_cm - tab_depth   # tab inner edge
    outer_r = radius_cm + 0.02        # slight overlap into wall

    # XZ plane maps: sketch X → world X, sketch Y → world -Z (negated!)
    # So for world Z positions, use negative sketch Y
    # tab_bottom_z in world → -tab_bottom_z in sketch Y
    # But actually in Fusion XZ plane: sketch X = world X, sketch Y = world Z?
    # Let me use the actual sketch coordinate system
    # For XZ plane: sketch (x, y) → world (x, 0, -y) based on f360mcp coordinate mapping
    # But we need to draw at the correct Z... let me use a construction plane instead

    # Actually, use an offset plane from YZ at angle 0 (the XZ plane through the axis)
    # The sketch on XZ plane has: sketch X = world X, sketch Y = world -Z

    # Profile corners (in sketch coords on XZ plane)
    # World X = radial distance, World Z = tab_bottom_z to tab_top_z
    # Sketch X = world X, Sketch Y = -world Z
    p1 = adsk.core.Point3D.create(inner_r, -tab_bottom_z, 0)  # inner bottom
    p2 = adsk.core.Point3D.create(outer_r, -tab_bottom_z, 0)  # outer bottom
    p3 = adsk.core.Point3D.create(outer_r, -tab_top_z, 0)     # outer top
    p4 = adsk.core.Point3D.create(inner_r, -tab_top_z, 0)     # inner top

    lines.addByTwoPoints(p1, p2)
    lines.addByTwoPoints(p2, p3)
    lines.addByTwoPoints(p3, p4)
    lines.addByTwoPoints(p4, p1)

    if sketch.profiles.count == 0:
        return "lug_tabs: no profile created on radial plane"

    # Step 2: Revolve around the Z axis by tab_width degrees (symmetric)
    revolves = component.features.revolveFeatures
    revolve_axis = _best_construction_axis(component, frame.axis)
    rev_input = revolves.createInput(
        sketch.profiles.item(0),
        revolve_axis,
        adsk.fusion.FeatureOperations.JoinFeatureOperation,
    )
    rev_input.setAngleExtent(False, adsk.core.ValueInput.createByString(f'{tab_width} deg'))
    if target_body:
        rev_input.participantBodies = [target_body]

    try:
        first_feature = revolves.add(rev_input)
    except Exception as e:
        return f"lug_tabs: revolve failed — {e}"

    # Step 3: Pattern tabs around the axis
    if tab_count > 1:
        try:
            patterns = component.features.circularPatternFeatures
            entities = adsk.core.ObjectCollection.create()
            entities.add(first_feature)
            pat_axis = _best_construction_axis(component, frame.axis)
            pat_input = patterns.createInput(entities, pat_axis)
            pat_input.quantity = adsk.core.ValueInput.createByReal(tab_count)
            pat_input.totalAngle = adsk.core.ValueInput.createByString('360 deg')
            pat_input.isSymmetric = False
            patterns.add(pat_input)
        except Exception as e:
            return f"lug_tabs: pattern failed — {e}"

    return f"lug_tabs: {tab_count} tabs ({tab_height*10:.1f}×{tab_depth*10:.1f}mm, {tab_width:.0f}°)"


# ── Compression rim ──

def create_compression_rim(
    target_face: adsk.fusion.BRepFace,
    design: adsk.fusion.Design,
    rim_height_cm: float,
    rim_width_cm: float,
    rim_offset_cm: float,
    from_top: bool,
    thread_type: str,
) -> str:
    """Create an axisymmetric compression rim on the opening of a cylindrical face.

    Geometry:
      - Rectangular profile on the XZ radial plane
      - Revolved 360° around the cylinder axis as JoinFeatureOperation
      - Outer (male) rim protrudes outward from the cylinder surface
      - Inner (female) rim protrudes inward from the bore wall

    Parameters are in cm. ``from_top`` matches the thread's ``start_from``.
    """
    component = design.activeComponent
    if component is None:
        return "rim: no active component"

    frame = _frame_from_face(target_face)
    if frame is None:
        return "rim: face must be cylindrical"

    radius_cm = frame.radius_cm
    if thread_type == "outer":
        inner_r = radius_cm - 0.02          # slight overlap into body
        outer_r = radius_cm + rim_width_cm  # protrudes outward
    else:
        inner_r = radius_cm - rim_width_cm  # protrudes inward
        outer_r = radius_cm + 0.02

    # Rim axial band at the opening edge
    if from_top:
        rim_top_z = frame.top_point.z - rim_offset_cm
        rim_bot_z = rim_top_z - rim_height_cm
    else:
        rim_bot_z = frame.bottom_point.z + rim_offset_cm
        rim_top_z = rim_bot_z + rim_height_cm

    target_body = target_face.body
    sketch = component.sketches.add(component.xZConstructionPlane)
    lines = sketch.sketchCurves.sketchLines

    # XZ plane maps: sketch X → world X, sketch Y → world -Z (same as lug tabs)
    p1 = adsk.core.Point3D.create(inner_r, -rim_bot_z, 0)
    p2 = adsk.core.Point3D.create(outer_r, -rim_bot_z, 0)
    p3 = adsk.core.Point3D.create(outer_r, -rim_top_z, 0)
    p4 = adsk.core.Point3D.create(inner_r, -rim_top_z, 0)

    lines.addByTwoPoints(p1, p2)
    lines.addByTwoPoints(p2, p3)
    lines.addByTwoPoints(p3, p4)
    lines.addByTwoPoints(p4, p1)

    if sketch.profiles.count == 0:
        return "rim: no profile created"

    revolves = component.features.revolveFeatures
    revolve_axis = _best_construction_axis(component, frame.axis)
    rev_input = revolves.createInput(
        sketch.profiles.item(0),
        revolve_axis,
        adsk.fusion.FeatureOperations.JoinFeatureOperation,
    )
    rev_input.setAngleExtent(False, adsk.core.ValueInput.createByString("360 deg"))
    if target_body:
        rev_input.participantBodies = [target_body]

    try:
        revolves.add(rev_input)
    except Exception as e:
        return f"rim: revolve failed — {e}"

    return f"rim: {rim_height_cm*10:.2f}×{rim_width_cm*10:.2f}mm"


# ── Chamfer ──

def _chamfer_ends(component, sweep_feat, params):
    """Chamfer thread ends. Tries progressively smaller sizes."""
    chamfers = component.features.chamferFeatures
    results = []

    sizes = [
        (params.section_size_cm * 0.4, params.section_size_cm * 0.2),
        (params.section_size_cm * 0.3, params.section_size_cm * 0.15),
        (params.section_size_cm * 0.2, params.section_size_cm * 0.1),
    ]

    for faces in [sweep_feat.startFaces, sweep_feat.endFaces]:
        if faces.count == 0:
            continue
        cap_edge = _longest_edge(faces.item(0))
        if cap_edge is None:
            continue

        done = False
        for d1, d2 in sizes:
            if done:
                break
            for flipped in [False, True]:
                edges = adsk.core.ObjectCollection.create()
                edges.add(cap_edge)
                ci = chamfers.createInput2()
                ci.chamferEdgeSets.addTwoDistancesChamferEdgeSet(
                    edges,
                    adsk.core.ValueInput.createByReal(d1),
                    adsk.core.ValueInput.createByReal(d2),
                    flipped, True,
                )
                try:
                    results.append(chamfers.add(ci))
                    done = True
                    break
                except Exception:
                    pass

    return results


# ── Pattern ──

def _pattern(component, sweep_feat, chamfer_feats, frame, count):
    patterns = component.features.circularPatternFeatures
    entities = adsk.core.ObjectCollection.create()
    entities.add(sweep_feat)
    for cf in chamfer_feats:
        entities.add(cf)

    pat_axis = _best_construction_axis(component, frame.axis)
    pat_input = patterns.createInput(entities, pat_axis)
    pat_input.quantity = adsk.core.ValueInput.createByReal(count)
    pat_input.totalAngle = adsk.core.ValueInput.createByString('360 deg')
    pat_input.isSymmetric = False
    patterns.add(pat_input)


# ── Utilities ──

def _longest_edge(face):
    best = None
    best_len = 0
    for ei in range(face.edges.count):
        e = face.edges.item(ei)
        if e.length > best_len:
            best_len = e.length
            best = e
    return best


def _best_construction_axis(component, axis):
    candidates = [
        (component.xConstructionAxis, abs(axis.x)),
        (component.yConstructionAxis, abs(axis.y)),
        (component.zConstructionAxis, abs(axis.z)),
    ]
    return max(candidates, key=lambda c: c[1])[0]


def _perpendicular_to(v):
    trial = adsk.core.Vector3D.create(1, 0, 0)
    result = v.crossProduct(trial)
    if result.length < 1e-6:
        trial = adsk.core.Vector3D.create(0, 1, 0)
        result = v.crossProduct(trial)
    result.normalize()
    return result
