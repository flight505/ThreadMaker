"""ThreadMaker — Fusion 360 add-in for multi-start threads optimized for FDM 3D printing."""

from . import commands
from .lib import fusionAddInUtils as futil
import adsk.core


def run(context):
    try:
        if not context['IsApplicationStartup']:
            app = adsk.core.Application.get()
            ui = app.userInterface
            ui.messageBox(
                'ThreadMaker loaded. Find it under the Tools tab.',
                'ThreadMaker',
            )
        commands.start()
    except:
        futil.handle_error('run')


def stop(context):
    try:
        futil.clear_handlers()
        commands.stop()
    except:
        futil.handle_error('stop')
