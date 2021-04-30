import os
import FreeCAD
import FreeCADGui as Gui
import PySide
from PySide import QtGui
from PySide import QtCore

import XternalAppsList
import Embed
import XternalAppsParametricTool

class ToolCommand():
    def __init__(self, appName, toolName):
        self.Tool = XternalAppsList.apps[appName].Tools[toolName]

    def GetResources(self):
        return {
            'Pixmap':   self.Tool.Icon,
            #'Accel':    "Shit+T",
            'MenuText': self.Tool.ToolName,
            'ToolTip':  "Runs the " + self.Tool.ToolName + " tool from " + self.Tool.AppName + "\n\n" + self.Tool.ToolTip,
        }

    def Activated(self):
        XternalAppsParametricTool.CreateCommand(self.Tool.AppName, self.Tool.ToolName)

    def IsActive(self):
        # return false to grey out the command in the menus, toolbars etc.
        return FreeCAD.ActiveDocument is not None

def createCommands(appName):
    for toolName in XternalAppsList.apps[appName].Tools:
        Gui.addCommand('XternalAppsTool' + appName + toolName + 'Command', ToolCommand(appName, toolName))
