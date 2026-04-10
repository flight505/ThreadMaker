"""ThreadMaker add-in configuration."""

COMPANY_NAME = "flight505"
ADDIN_NAME = "ThreadMaker"

# Fusion workspace / panel placement
# All flight505 3D print add-ins share a single "3D Print Tools" panel
design_workspace = "FusionSolidEnvironment"
tools_tab_id = "SolidTab"
my_tab_name = "SolidTab"  # main Solid tab, not a custom tab

my_panel_id = "flight505_3DPrintTools_panel"  # shared across all add-ins
my_panel_name = "3D Print Tools"
my_panel_after = "SolidModifyPanel"

DEBUG = False
