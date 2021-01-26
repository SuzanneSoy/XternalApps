import os
import FreeCAD
import FreeCADGui as Gui
import PySide
from PySide import QtGui
from PySide import QtCore

import ExternalAppsList
import Embed

class AppCommand():
    def __init__(self, appName):
        self.appName = appName

    def GetResources(self):
        return {
            'Pixmap':   ExternalAppsList.apps[self.appName].Icon,
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

def createCommands(appName):
    Gui.addCommand('ExternalAppsOpen' + appName + 'Command', AppCommand(appName))
