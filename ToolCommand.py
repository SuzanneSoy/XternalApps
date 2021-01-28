import os
import FreeCAD
import FreeCADGui as Gui
import PySide
from PySide import QtGui
from PySide import QtCore

import ExternalAppsList
import Embed
import XternalAppsParametricTool

class ToolCommand():
    def __init__(self, appName, toolName):
        self.Tool = ExternalAppsList.apps[appName].Tools[toolName]

    def GetResources(self):
        return {
            'Pixmap':   self.Tool.Icon,
            #'Accel':    "Shit+T",
            'MenuText': self.Tool.ToolName,
            'ToolTip':  "Runs the " + self.Tool.ToolName + " tool from " + self.Tool.AppName + "\n\n" + self.Tool.ToolTip,
        }

    def Activated(self):
        XternalAppsParametricTool.create(self.Tool.AppName, self.Tool.ToolName)

    def IsActive(self):
        # return false to grey out the command in the menus, toolbars etc.
        return App.ActiveDocument is not None

def createCommands(appName):
    for toolName in ExternalAppsList.apps[appName].Tools:
        Gui.addCommand('ExternalAppsTool' + appName + toolName + 'Command', ToolCommand(appName, toolName))
