import FreeCAD
import FreeCADGui as Gui
import PySide
from PySide import QtGui
from PySide import QtCore

import Embed

class GIMPCommand():
    def __init__(self, appName):
        self.appName = appName

    def GetResources(self):
        return {
            'Pixmap':   ':/icons/GIMP.svg',
            'Accel':    "Shit+E", # E for Embed
            'MenuText': "Start " + self.appName,
            'ToolTip':  "Start " + self.appName,
        }

    def Activated(self):
        p = Embed.ExternalAppInstance(self.appName)
        p.waitForWindow()

    def IsActive(self):
        # return false to grey out the command in the menus, toolbars etc.
        return True

Gui.addCommand('MousepadCommand', GIMPCommand('Mousepad'))
Gui.addCommand('InkscapeCommand', GIMPCommand('Inkscape'))
Gui.addCommand('GIMPCommand', GIMPCommand('GIMP'))
