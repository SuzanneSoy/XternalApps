import FreeCAD
import FreeCADGui as Gui
import PySide
from PySide import QtGui
from PySide import QtCore

import Embed

class GIMPCommand():
    def GetResources(self):
        return {
            'Pixmap':   ':/icons/GIMP.svg',
            'Accel':    "Shit+G",
            'MenuText': "Menu text",
            'ToolTip':  "Tooltip",
        }

    def Activated(self):
        print("Command activated")
        p = Embed.ExternalAppInstance('GIMP')
        p.waitForWindow()

    def IsActive(self):
        # return false to grey out the command in the menus, toolbars etc.
        return True

Gui.addCommand('GIMPCommand', GIMPCommand())
