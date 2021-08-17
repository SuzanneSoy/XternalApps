import os
import FreeCAD
import FreeCADGui as Gui
import PySide
from PySide import QtGui
from PySide import QtCore

import XternalAppsList
import Embed

class AppCommand():
    def __init__(self, appName):
        self.appName = appName

    def GetResources(self):
        return {
            'Pixmap':   XternalAppsList.apps[self.appName].Icon,
            'Accel':    "Shit+E", # E for Embed
            'MenuText': "Start " + self.appName,
            'ToolTip':  "Start " + self.appName,
        }

    def Activated(self):
        p = Embed.XternalAppInstance(self.appName)
        p.waitForWindow()

    def IsActive(self):
        # return false to grey out the command in the menus, toolbars etc.
        return True

def createCommands(appName):
    Gui.addCommand('XternalAppsOpen' + appName + 'Command', AppCommand(appName))

