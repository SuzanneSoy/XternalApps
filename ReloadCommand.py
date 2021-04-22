import os
import FreeCAD
import FreeCADGui as Gui
import PySide
from PySide import QtGui
from importlib import reload

# This command is inserted into each workbench by AppCommand.py

def R():
    # Clear the report view:
    Gui.getMainWindow().findChild(QtGui.QTextEdit, "Report view").clear()
    # Reload modules:
    import XternalAppsParametricTool
    import ReloadCommand
    mods = [XternalAppsParametricTool, ReloadCommand]
    for m in mods:
        reload(m)
    print(str(len(mods)) + "modules reloaded")


class ReloadCommand():
    def __init__(self, appName):
        pass

    def GetResources(self):
        return {
            'Pixmap':   os.path.dirname(__file__) + '/icons/' + "reload.svg",
            'Accel':    "Shit+R", # R for Reload
            'MenuText': "Reload XternalApps (developper tool)",
            'ToolTip':  "Reload some modules of the XternalApps workbenches, needed for development only.",
        }

    def Activated(self):
        R()

    def IsActive(self):
        # return false to grey out the command in the menus, toolbars etc.
        return True

def createCommands(appName):
    Gui.addCommand('XternalAppsReload' + appName + 'Command', ReloadCommand(appName))