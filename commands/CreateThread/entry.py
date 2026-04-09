"""CreateThread command — Outer, Inner, or Matched Pair with tolerance control."""

from __future__ import annotations

import os

import adsk.core
import adsk.fusion

from ... import config
from ...lib import fusionAddInUtils as futil
from ...lib.thread.params import ThreadParameters
from ...lib.thread import generator

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Create Thread"
CMD_ID = f"{config.COMPANY_NAME}_{config.ADDIN_NAME}_CreateThread"
CMD_DESCRIPTION = "Create multi-start threads optimized for FDM 3D printing."
IS_PROMOTED = True

WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name
PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

local_handlers = []

MODE_OUTER = "Outer (Male)"
MODE_INNER = "Inner (Female)"
MODE_PAIR = "Matched Pair"


def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_DESCRIPTION, ICON_FOLDER)
    futil.add_handler(cmd_def.commandCreated, command_created)
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    tab = workspace.toolbarTabs.itemById(TAB_ID) or workspace.toolbarTabs.add(TAB_ID, TAB_NAME)
    panel = tab.toolbarPanels.itemById(PANEL_ID) or tab.toolbarPanels.add(PANEL_ID, PANEL_NAME, PANEL_AFTER, False)
    panel.controls.addCommand(cmd_def).isPromoted = IS_PROMOTED


def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    if panel:
        ctrl = panel.controls.itemById(CMD_ID)
        if ctrl: ctrl.deleteMe()
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def: cmd_def.deleteMe()
    if panel and panel.controls.count == 0: panel.deleteMe()
    tab = workspace.toolbarTabs.itemById(TAB_ID)
    if tab and tab.toolbarPanels.count == 0: tab.deleteMe()


def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)

    inp = args.command.commandInputs

    # ── Mode ──
    d = inp.addDropDownCommandInput("thread_type", "Thread Type", adsk.core.DropDownStyles.TextListDropDownStyle)
    d.tooltip = "Outer: thread bumps on a cylinder. Inner: thread ridges inside a bore. Matched Pair: select both faces and create matching threads with automatic tolerance."
    d.listItems.add(MODE_OUTER, True)
    d.listItems.add(MODE_INNER, False)
    d.listItems.add(MODE_PAIR, False)

    # ── Face selections ──
    d = inp.addSelectionInput("target_face", "Apply To", "Select a cylindrical face")
    d.addSelectionFilter("CylindricalFaces"); d.setSelectionLimits(0, 1)
    d.tooltip = "Click the cylindrical face to thread. Diameter auto-detected."

    d = inp.addSelectionInput("male_face", "Male Face (Outer)", "Select jar neck outer face")
    d.addSelectionFilter("CylindricalFaces"); d.setSelectionLimits(0, 1)
    d.tooltip = "The OUTSIDE surface of the neck. Thread bumps protrude outward."; d.isVisible = False

    d = inp.addSelectionInput("female_face", "Female Face (Inner)", "Select lid inner face")
    d.addSelectionFilter("CylindricalFaces"); d.setSelectionLimits(0, 1)
    d.tooltip = "The INSIDE surface of the lid. Thread ridges protrude inward."; d.isVisible = False

    # ── Female Style (Matched Pair only) ──
    style_group = inp.addGroupCommandInput("style_group", "Female Style")
    style_group.isExpanded = True; style_group.isVisible = False
    sg = style_group.children

    d = sg.addDropDownCommandInput("female_style", "Style", adsk.core.DropDownStyles.TextListDropDownStyle)
    d.tooltip = "Full Thread: helical ridges inside lid (same as male). Lug Tabs: simple rectangular tabs at the lid opening — easier to print, more tolerant."
    d.listItems.add("Full Thread", True)
    d.listItems.add("Lug Tabs", False)

    d = sg.addIntegerSpinnerCommandInput("tab_count", "Tab Count", 2, 8, 1, 4)
    d.tooltip = "Number of lug tabs evenly spaced inside the lid opening. 4 is standard for jars up to 80mm."
    d.isVisible = False

    d = sg.addValueInput("tab_height", "Tab Height", "mm", adsk.core.ValueInput.createByString("0.8 mm"))
    d.tooltip = "Axial height of each tab. Must be smaller than the gap between thread ridges (pitch - thread thickness). Too tall = won't fit between ridges."
    d.isVisible = False

    d = sg.addValueInput("tab_depth", "Tab Depth", "mm", adsk.core.ValueInput.createByString("1.0 mm"))
    d.tooltip = "How far each tab protrudes inward from the bore wall. Should match or slightly exceed the thread protrusion for solid engagement."
    d.isVisible = False

    d = sg.addFloatSpinnerCommandInput("tab_width", "Tab Width (deg)", "", 5.0, 45.0, 1.0, 15.0)
    d.tooltip = "Angular span of each tab in degrees. Wider tabs = more contact area but harder to engage. 10-20° typical."
    d.isVisible = False

    d = sg.addValueInput("tab_offset", "Tab Offset", "mm", adsk.core.ValueInput.createByString("0 mm"))
    d.tooltip = "Distance from the lid opening edge before tabs begin. 0 = flush with the lip. Independent from the male thread offset."
    d.isVisible = False

    # ── Info (Matched Pair) ──
    info_group = inp.addGroupCommandInput("info_group", "Calculated")
    info_group.isExpanded = True; info_group.isVisible = False
    ig = info_group.children
    ig.addTextBoxCommandInput("info_gap", "Gap per Side", "-", 2, True)
    ig.addTextBoxCommandInput("info_protrusion", "Thread Protrusion", "-", 2, True)
    ig.addTextBoxCommandInput("info_engagement", "Engagement", "-", 2, True)
    ig.addTextBoxCommandInput("info_height", "Active Height / Lead", "-", 2, True)

    # ── Thread ──
    tg = inp.addGroupCommandInput("thread_group", "Thread")
    tg.isExpanded = True; t = tg.children

    d = t.addValueInput("diameter", "Diameter", "mm", adsk.core.ValueInput.createByString("34 mm"))
    d.tooltip = "Face diameter. Auto-detected from face selection."

    d = t.addValueInput("pitch", "Pitch", "mm", adsk.core.ValueInput.createByString("3 mm"))
    d.tooltip = "Distance between adjacent crests along the axis. Lead = pitch × starts."

    d = t.addIntegerSpinnerCommandInput("num_starts", "Starts", 1, 8, 1, 3)
    d.tooltip = "Independent thread helixes. 3 = quick-turn jar lid (closes in ~120°)."

    d = t.addValueInput("section_size", "Thread Thickness", "mm", adsk.core.ValueInput.createByString("2 mm"))
    d.tooltip = "Cross-section diameter of each thread ridge. Controls how thick the thread is. For FDM: 1.5–2.5mm."

    d = t.addFloatSpinnerCommandInput("revolutions", "Revolutions", "", 0.25, 1.5, 0.05, 0.5)
    d.tooltip = "How far each segment wraps (in turns). 0.5 = 180° per segment. Active height = revolutions × lead."

    # ── Tolerance ──
    tol_group = inp.addGroupCommandInput("tol_group", "Tolerance")
    tol_group.isExpanded = True; tol = tol_group.children

    d = tol.addValueInput("radial_tolerance", "Helix Offset", "mm", adsk.core.ValueInput.createByString("0.1 mm"))
    d.tooltip = "How far the thread helix center is inset from the face surface. This is a small manufacturing offset (0.05-0.15mm). NOTE: This does NOT create a gap between parts — you must build your geometry with a gap between the neck and lid bore. Recommended gap: 0.5-1.0mm per side."

    # ── Placement ──
    pg = inp.addGroupCommandInput("place_group", "Placement")
    pg.isExpanded = False; p = pg.children

    d = p.addDropDownCommandInput("start_from", "Start From", adsk.core.DropDownStyles.TextListDropDownStyle)
    d.tooltip = "Which end of the face the thread starts from. For lug tabs: this is the lid opening edge where tabs are placed."
    d.listItems.add("Top", True); d.listItems.add("Bottom", False)

    d = p.addValueInput("offset", "Offset from Edge", "mm", adsk.core.ValueInput.createByString("1.5 mm"))
    d.tooltip = "Distance from the starting edge before thread begins. 1–2mm recommended."

    # ── Options ──
    og = inp.addGroupCommandInput("opt_group", "Options")
    og.isExpanded = False; o = og.children

    d = o.addDropDownCommandInput("profile", "Profile", adsk.core.DropDownStyles.TextListDropDownStyle)
    d.tooltip = "Thread cross-section. Circular=easy FDM. V-Thread=ISO standard. Trapezoidal=strongest."
    d.listItems.add("Circular", True); d.listItems.add("V-Thread 60°", False); d.listItems.add("Trapezoidal 30°", False)

    d = o.addBoolValueInput("chamfer", "Lead-in Chamfer", True, "", True)
    d.tooltip = "Taper thread ends for smooth engagement."

    d = o.addBoolValueInput("preview", "Preview", True, "", True)
    d.tooltip = "Live preview before committing."

    d = o.addDropDownCommandInput("preview_scope", "Preview Scope", adsk.core.DropDownStyles.TextListDropDownStyle)
    d.tooltip = "Which threads to preview."; d.isVisible = False
    d.listItems.add("Both", True); d.listItems.add("Male Only", False); d.listItems.add("Female Only", False)

    d = o.addDropDownCommandInput("direction", "Direction", adsk.core.DropDownStyles.TextListDropDownStyle)
    d.tooltip = "Right-hand tightens clockwise (standard)."
    d.listItems.add("Right-hand", True); d.listItems.add("Left-hand", False)


# ── Helpers ──

def _mode(inp):
    dd = adsk.core.DropDownCommandInput.cast(inp.itemById("thread_type"))
    return dd.selectedItem.name if dd else MODE_OUTER

def _is_pair(inp): return _mode(inp) == MODE_PAIR

def _face(inp, fid):
    s = adsk.core.SelectionCommandInput.cast(inp.itemById(fid))
    return adsk.fusion.BRepFace.cast(s.selection(0).entity) if s and s.selectionCount > 0 else None

def _val(inp, fid):
    v = adsk.core.ValueCommandInput.cast(inp.itemById(fid))
    return v.value if v else 0.0

def _dd_name(inp, fid):
    dd = adsk.core.DropDownCommandInput.cast(inp.itemById(fid))
    return dd.selectedItem.name if dd else ""

def _shared(inp):
    prof_map = {"Circular": "circular", "V-Thread 60°": "v60", "Trapezoidal 30°": "trapezoidal"}
    starts = adsk.core.IntegerSpinnerCommandInput.cast(inp.itemById("num_starts"))
    rev = adsk.core.FloatSpinnerCommandInput.cast(inp.itemById("revolutions"))
    chamfer = adsk.core.BoolValueCommandInput.cast(inp.itemById("chamfer"))
    tabs = adsk.core.IntegerSpinnerCommandInput.cast(inp.itemById("tab_count"))

    female_style = "full_thread"
    if _dd_name(inp, "female_style") == "Lug Tabs":
        female_style = "lug_tabs"

    tab_width_inp = adsk.core.FloatSpinnerCommandInput.cast(inp.itemById("tab_width"))

    return dict(
        pitch_cm=_val(inp, "pitch"),
        num_starts=starts.value if starts else 3,
        revolutions=rev.value if rev else 0.5,
        profile=prof_map.get(_dd_name(inp, "profile"), "circular"),
        section_size_cm=_val(inp, "section_size"),
        radial_tolerance_cm=_val(inp, "radial_tolerance"),
        chamfer=chamfer.value if chamfer else True,
        right_hand=_dd_name(inp, "direction") != "Left-hand",
        offset_cm=_val(inp, "offset"),
        female_style=female_style,
        tab_count=tabs.value if tabs else 4,
        tab_height_cm=_val(inp, "tab_height"),
        tab_depth_cm=_val(inp, "tab_depth"),
        tab_width_deg=tab_width_inp.value if tab_width_inp else 15.0,
        tab_offset_cm=_val(inp, "tab_offset"),
    )


def _single_params(inp):
    type_map = {MODE_OUTER: "outer", MODE_INNER: "inner"}
    return ThreadParameters(
        thread_type=type_map.get(_mode(inp), "outer"),
        major_diameter_cm=_val(inp, "diameter"),
        start_from="top" if _dd_name(inp, "start_from") == "Top" else "bottom",
        **_shared(inp),
    )


def _pair_params(inp, mf, ff):
    s = _shared(inp)
    sf = "top" if _dd_name(inp, "start_from") == "Top" else "bottom"
    male = ThreadParameters(thread_type="outer", major_diameter_cm=mf.geometry.radius * 2, start_from=sf, **s)
    # Female: use lug_tabs style if selected, opposite start direction
    female = ThreadParameters(thread_type="inner", major_diameter_cm=ff.geometry.radius * 2,
                              start_from="bottom" if sf == "top" else "top", **s)
    return male, female


# ── Execute ──

def command_execute(args: adsk.core.CommandEventArgs):
    try:
        inp = args.command.commandInputs
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox("Open a design first.", CMD_NAME); return

        if _is_pair(inp):
            mf, ff = _face(inp, "male_face"), _face(inp, "female_face")
            if not mf or not ff:
                ui.messageBox("Select both faces.", CMD_NAME); return
            if mf.body == ff.body:
                ui.messageBox("Faces must be on different bodies.", CMD_NAME); return
            male, female = _pair_params(inp, mf, ff)
            for p in [male, female]:
                e = p.validate()
                if e: ui.messageBox("\n".join(e), CMD_NAME); return
            s1 = generator.create_thread(male, mf, design)
            s2 = generator.create_thread(female, ff, design)
            futil.log(f"Pair: {s1} | {s2}")
            if "failed" in (s1 + s2).lower():
                ui.messageBox(f"Male: {s1}\nFemale: {s2}", CMD_NAME)
        else:
            p = _single_params(inp)
            e = p.validate()
            if e: ui.messageBox("\n".join(e), CMD_NAME); return
            f = _face(inp, "target_face")
            if not f: ui.messageBox("Select a face.", CMD_NAME); return
            s = generator.create_thread(p, f, design)
            futil.log(f"Single: {s}")
            if "failed" in s.lower(): ui.messageBox(s, CMD_NAME)
    except Exception:
        import traceback; ui.messageBox(traceback.format_exc(), CMD_NAME)


def command_preview(args: adsk.core.CommandEventArgs):
    try:
        inp = args.command.commandInputs
        prev = adsk.core.BoolValueCommandInput.cast(inp.itemById("preview"))
        if prev and not prev.value: return
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design: return

        if _is_pair(inp):
            mf, ff = _face(inp, "male_face"), _face(inp, "female_face")
            if not mf or not ff: return
            scope = _dd_name(inp, "preview_scope") or "Both"
            male, female = _pair_params(inp, mf, ff)
            if scope in ("Both", "Male Only") and not male.validate():
                generator.create_thread(male, mf, design)
            if scope in ("Both", "Female Only") and not female.validate():
                generator.create_thread(female, ff, design)
        else:
            f = _face(inp, "target_face")
            if not f: return
            p = _single_params(inp)
            if not p.validate():
                generator.create_thread(p, f, design)
        args.isValidResult = True
    except Exception:
        import traceback; app.log(f'Preview: {traceback.format_exc()}')


# ── Input Changed ──

def command_input_changed(args: adsk.core.InputChangedEventArgs):
    try:
        changed = args.input; inp = args.inputs
        pair = _is_pair(inp)

        if changed.id == "thread_type":
            inp.itemById("target_face").isVisible = not pair
            inp.itemById("male_face").isVisible = pair
            inp.itemById("female_face").isVisible = pair
            inp.itemById("info_group").isVisible = pair
            inp.itemById("style_group").isVisible = pair
            inp.itemById("preview_scope").isVisible = pair
            inp.itemById("diameter").isVisible = not pair

        if changed.id == "female_style":
            is_lug = _dd_name(inp, "female_style") == "Lug Tabs"
            for fid in ("tab_count", "tab_height", "tab_depth", "tab_width", "tab_offset"):
                ctrl = inp.itemById(fid)
                if ctrl:
                    ctrl.isVisible = is_lug

        if changed.id == "target_face":
            f = _face(inp, "target_face")
            if f and isinstance(f.geometry, adsk.core.Cylinder):
                v = adsk.core.ValueCommandInput.cast(inp.itemById("diameter"))
                if v: v.value = f.geometry.radius * 2.0

        if pair and changed.id in ("male_face", "female_face", "section_size", "pitch",
                                    "num_starts", "radial_tolerance", "revolutions",
                                    "female_style", "tab_height", "tab_depth", "tab_width"):
            _update_info(inp)
    except Exception:
        import traceback; app.log(f'InputChanged: {traceback.format_exc()}')


def _update_info(inp):
    mf, ff = _face(inp, "male_face"), _face(inp, "female_face")
    gap_b = adsk.core.TextBoxCommandInput.cast(inp.itemById("info_gap"))
    prot_b = adsk.core.TextBoxCommandInput.cast(inp.itemById("info_protrusion"))
    eng_b = adsk.core.TextBoxCommandInput.cast(inp.itemById("info_engagement"))
    ht_b = adsk.core.TextBoxCommandInput.cast(inp.itemById("info_height"))

    if not mf or not ff:
        for b in [gap_b, prot_b, eng_b, ht_b]:
            if b: b.text = "Select both faces"
        return

    mr = mf.geometry.radius * 10 if isinstance(mf.geometry, adsk.core.Cylinder) else 0
    fr = ff.geometry.radius * 10 if isinstance(ff.geometry, adsk.core.Cylinder) else 0
    gap = fr - mr
    sec = _val(inp, "section_size") * 10
    tol = _val(inp, "radial_tolerance") * 10
    prot = sec / 2 - tol
    eng = 2 * prot - gap

    pitch = _val(inp, "pitch") * 10
    starts_i = adsk.core.IntegerSpinnerCommandInput.cast(inp.itemById("num_starts"))
    rev_i = adsk.core.FloatSpinnerCommandInput.cast(inp.itemById("revolutions"))
    starts = starts_i.value if starts_i else 3
    rev = rev_i.value if rev_i else 0.5
    lead = pitch * starts
    active = rev * lead

    if gap_b:
        if gap < 0:
            gap_b.text = "ERROR: Female face must be larger than male face"
        elif gap < 0.3:
            gap_b.text = f"{gap:.2f} mm — TOO SMALL! Build geometry with 0.5-1.0mm gap per side"
        else:
            gap_b.text = f"{gap:.2f} mm"
    is_lug = _dd_name(inp, "female_style") == "Lug Tabs"
    ridge_gap = pitch - sec  # gap between thread ridges

    if prot_b:
        prot_b.text = f"{prot:.2f} mm each side"
    if eng_b:
        if is_lug:
            tab_h = _val(inp, "tab_height") * 10
            tab_d = _val(inp, "tab_depth") * 10
            if tab_h > ridge_gap and ridge_gap > 0:
                eng_b.text = f"Tab {tab_h:.1f}mm > ridge gap {ridge_gap:.1f}mm — WON'T FIT! Reduce tab height"
            else:
                eng_b.text = f"Tab: {tab_h:.1f}mm h × {tab_d:.1f}mm deep (ridge gap: {ridge_gap:.1f}mm)"
        else:
            if eng <= 0:
                eng_b.text = f"{eng:.2f} mm — WON'T ENGAGE! Increase thickness or gap"
            elif eng > gap * 1.8 and gap > 0.01:
                eng_b.text = f"{eng:.2f} mm — VERY TIGHT, may not screw"
            elif eng > 0.5:
                eng_b.text = f"{eng:.2f} mm — GOOD"
            else:
                eng_b.text = f"{eng:.2f} mm — marginal"
    if ht_b:
        ht_b.text = f"{active:.1f} mm (lead: {lead:.0f} mm, ridge gap: {ridge_gap:.1f} mm)"


def command_destroy(_args):
    global local_handlers
    local_handlers = []
