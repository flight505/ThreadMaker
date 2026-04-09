"""Thread parameter definitions and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True, slots=True)
class ThreadParameters:
    """All dimensions in Fusion internal units (cm).

    Key relationships:
      lead = pitch × num_starts
      active_height = revolutions × lead
      protrusion = section_radius - radial_tolerance
      ridge_gap = pitch - section_size (space between ridges for tabs)
    """

    thread_type: str              # "outer" or "inner"
    major_diameter_cm: float      # face diameter
    pitch_cm: float               # distance between adjacent crests
    num_starts: int               # 1–8
    revolutions: float            # turns per segment (0.25–1.5)
    profile: str                  # "circular", "v60", "trapezoidal"
    section_size_cm: float        # thread cross-section diameter
    radial_tolerance_cm: float    # helix inset from face surface
    chamfer: bool                 # lead-in taper on thread ends
    right_hand: bool              # right-hand = clockwise tighten
    start_from: str               # "top" or "bottom"
    offset_cm: float              # distance from edge before thread starts

    # Female style
    female_style: str = "full_thread"  # "full_thread" or "lug_tabs"

    # Lug tab specific (independent from helical thread params)
    tab_count: int = 4            # number of tabs
    tab_height_cm: float = 0.08   # axial height (0.8mm default)
    tab_depth_cm: float = 0.1     # radial protrusion inward (1mm default)
    tab_width_deg: float = 15.0   # angular span of each tab
    tab_offset_cm: float = 0.0    # distance from opening edge (independent from thread offset)

    @property
    def lead_cm(self) -> float:
        return self.pitch_cm * self.num_starts

    @property
    def helix_pitch_cm(self) -> float:
        return self.lead_cm

    @property
    def helix_turns(self) -> float:
        return self.revolutions

    @property
    def active_height_cm(self) -> float:
        return self.helix_pitch_cm * self.revolutions

    @property
    def section_radius_cm(self) -> float:
        return self.section_size_cm / 2.0

    @property
    def helix_offset_cm(self) -> float:
        return self.radial_tolerance_cm

    @property
    def ridge_gap_cm(self) -> float:
        """Axial gap between thread ridges where tabs must fit."""
        return self.pitch_cm - self.section_size_cm

    def protrusion_cm(self) -> float:
        return self.section_radius_cm - self.radial_tolerance_cm

    def engagement_with_gap_cm(self, gap_cm: float) -> float:
        return 2 * self.protrusion_cm() - gap_cm

    def validate(self) -> List[str]:
        errors: List[str] = []
        if self.thread_type not in ("outer", "inner"):
            errors.append("Thread type must be 'outer' or 'inner'.")
        if self.major_diameter_cm <= 0:
            errors.append("Diameter must be positive.")
        if self.pitch_cm <= 0:
            errors.append("Pitch must be positive.")
        if not 1 <= self.num_starts <= 8:
            errors.append("Starts must be 1–8.")
        if not 0.1 <= self.revolutions <= 2.0:
            errors.append("Revolutions must be 0.1–2.0.")
        if self.profile not in ("circular", "v60", "trapezoidal"):
            errors.append("Invalid profile.")
        if self.section_size_cm <= 0:
            errors.append("Thread thickness must be positive.")
        if self.radial_tolerance_cm < 0:
            errors.append("Helix offset cannot be negative.")
        if self.protrusion_cm() <= 0:
            errors.append("Thread thickness must be larger than 2× helix offset.")
        if self.start_from not in ("top", "bottom"):
            errors.append("Start from must be 'top' or 'bottom'.")
        if self.offset_cm < 0:
            errors.append("Offset cannot be negative.")
        if self.female_style not in ("full_thread", "lug_tabs"):
            errors.append("Female style must be 'full_thread' or 'lug_tabs'.")
        if self.female_style == "lug_tabs":
            if not 2 <= self.tab_count <= 8:
                errors.append("Tab count must be 2–8.")
            if self.tab_height_cm <= 0:
                errors.append("Tab height must be positive.")
            if self.tab_depth_cm <= 0:
                errors.append("Tab depth must be positive.")
            if self.tab_height_cm > self.ridge_gap_cm and self.ridge_gap_cm > 0:
                errors.append(f"Tab height ({self.tab_height_cm*10:.1f}mm) exceeds gap between ridges ({self.ridge_gap_cm*10:.1f}mm). Reduce tab height or increase pitch.")
        return errors
