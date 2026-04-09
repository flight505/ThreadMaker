"""Thread profile sketch generators.

Each function draws a closed profile on a sketch that's already been created
on a construction plane perpendicular to the helix path at its start.

CRITICAL: The sketch coordinate system does NOT align with world axes.
Must query sketch.xDirection / yDirection and project radial/axial vectors
to draw in the correct orientation.
"""

from __future__ import annotations

import math

import adsk.core
import adsk.fusion


def draw_circular(sketch: adsk.fusion.Sketch, radius_cm: float) -> None:
    """Draw a circular thread cross-section centered at sketch origin."""
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(0, 0, 0), radius_cm
    )


def draw_v_thread(
    sketch: adsk.fusion.Sketch,
    params,
    thread_type: str,
) -> None:
    """Draw ISO V-thread 60° trapezoidal profile.

    Profile is a trapezoid with:
    - Root (on cylinder surface): width = 3P/4
    - Crest (at tip): width = P/8
    - Depth = 5H/8 where H = P × sqrt(3)/2
    """
    pitch_cm = params.pitch_cm
    H = pitch_cm * math.sqrt(3) / 2
    depth_cm = 5 / 8 * H
    overlap_cm = min(0.05, depth_cm * 0.1)  # scale with thread size, max 0.5mm

    root_half_cm = 3 * pitch_cm / 8
    crest_half_cm = pitch_cm / 16

    if thread_type == "inner":
        depth_cm = -depth_cm
        overlap_cm = -overlap_cm

    _draw_trapezoid(sketch, -overlap_cm, depth_cm, root_half_cm, crest_half_cm)


def draw_trapezoidal(
    sketch: adsk.fusion.Sketch,
    params,
    thread_type: str,
) -> None:
    """Draw trapezoidal 30° thread profile (ACME-like).

    Equal-width trapezoid: root and crest flats are the same width.
    """
    pitch_cm = params.pitch_cm
    depth_cm = pitch_cm / 2
    overlap_cm = min(0.05, depth_cm * 0.1)

    flat_half_cm = pitch_cm * 0.366  # equal root and crest width

    if thread_type == "inner":
        depth_cm = -depth_cm
        overlap_cm = -overlap_cm

    _draw_trapezoid(sketch, -overlap_cm, depth_cm, flat_half_cm, flat_half_cm)


def _draw_trapezoid(
    sketch: adsk.fusion.Sketch,
    root_radial_cm: float,
    crest_radial_cm: float,
    root_half_axial_cm: float,
    crest_half_axial_cm: float,
) -> None:
    """Draw a trapezoidal profile using sketch-space coordinate mapping.

    Parameters are in (radial, axial) space — this function projects them
    into the sketch's actual X/Y coordinate system.

    Assumes the cylinder is centered at world origin with Z-axis alignment.
    """
    x_dir = sketch.xDirection
    y_dir = sketch.yDirection
    origin = sketch.origin

    # Radial = outward from cylinder center toward sketch origin
    radial_world = adsk.core.Vector3D.create(origin.x, origin.y, 0)
    if radial_world.length < 1e-6:
        radial_world = adsk.core.Vector3D.create(1, 0, 0)
    radial_world.normalize()

    axial_world = adsk.core.Vector3D.create(0, 0, 1)

    rsx = radial_world.dotProduct(x_dir)
    rsy = radial_world.dotProduct(y_dir)
    asx = axial_world.dotProduct(x_dir)
    asy = axial_world.dotProduct(y_dir)

    def to_sketch(radial: float, axial: float):
        return (radial * rsx + axial * asx, radial * rsy + axial * asy)

    rb = to_sketch(root_radial_cm, -root_half_axial_cm)
    cb = to_sketch(crest_radial_cm, -crest_half_axial_cm)
    ct = to_sketch(crest_radial_cm, crest_half_axial_cm)
    rt = to_sketch(root_radial_cm, root_half_axial_cm)

    lines = sketch.sketchCurves.sketchLines
    points = [
        adsk.core.Point3D.create(rb[0], rb[1], 0),
        adsk.core.Point3D.create(cb[0], cb[1], 0),
        adsk.core.Point3D.create(ct[0], ct[1], 0),
        adsk.core.Point3D.create(rt[0], rt[1], 0),
    ]

    for i in range(4):
        lines.addByTwoPoints(points[i], points[(i + 1) % 4])
