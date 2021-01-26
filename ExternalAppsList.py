import os
import FreeCAD
import FreeCADGui as Gui
import subprocess
import PySide
import re
from PySide import QtGui
from PySide import QtCore

from MyX11Utils import *

class Tool():
    def __init__(self, *, appName, toolName, xForms, toolTip, icon, extendedDescription, openHelpFile):
        self.AppName = appName
        self.ToolName = toolName
        self.XForms = xForms
        self.ToolTip = toolTip
        self.Icon = icon
        self.ExtendedDescription = extendedDescription
        self.OpenHelpFile = openHelpFile

    @staticmethod
    def fromXForms(*, appName, xForms):
        # TODO: implement a tool cache which avoids parsing the XML and memorizes the name and icon
        return Tool(appName=appName,
                    toolName = "from XForms … TODO",
                    xForms = xForms,
                    toolTip = "from XForms … TODO",
                    # TODO: get the icon from the XForms file
                    icon = os.path.dirname(__file__) + '/icons/' + appName + '.svg',
                    extendedDescription = "from XForms … TODO",
                    openHelpFile = None)

class ToolsClass():
    def __init__(self, tools):
        # TODO: make this private
        self.AllTools = {tool.ToolName: tool for tool in tools}
    def __getitem__(self, k):
        return self.AllTools[k]
    def __iter__(self):
        return self.AllTools.__iter__()

class App():
    def __init__(self, name, *, start_command_and_args, xwininfo_filter_re, extra_xprop_filter, tools):
        self.name = name
        self.Icon = os.path.dirname(__file__) + '/icons/' + self.name + '.svg'
        self.start_command_and_args = start_command_and_args
        self.xwininfo_filter_re = re.compile(xwininfo_filter_re)
        self.extra_xprop_filter = extra_xprop_filter
        self.Tools = ToolsClass([Tool.fromXForms(appName=self.name, xForms=t) for t in tools])

class Apps():
    def __init__(self, *apps):
        # TODO: make this private
        self.AllApps = {app.name: app for app in apps}
    def __getitem__(self, k):
        return self.AllApps[k]
    def __iter__(self):
        return self.AllApps.__iter__()

# app-specific infos:
apps = Apps(
    App('Mousepad',
        start_command_and_args = ['mousepad', '--disable-server'],
        xwininfo_filter_re = r'mousepad',
        extra_xprop_filter = lambda processId, windowId, i: True,
        tools = []),
    App('Inkscape',
        start_command_and_args = ['inkscape'],
        xwininfo_filter_re = r'inkscape',
        extra_xprop_filter = lambda processId, windowId, i: x11prop(windowId, 'WM_STATE',  'WM_STATE') is not None,
        tools = [
            "myTool.xforms"
        ]),
    App('GIMP',
        start_command_and_args = ['env', '-i', 'DISPLAY=:0', '/home/suzanne/perso/dotfiles/nix/result/bin/gimp', '--new-instance'],
        xwininfo_filter_re = r'gimp',
        extra_xprop_filter = lambda processId, windowId, i: x11prop(windowId, 'WM_STATE',  'WM_STATE') is not None,
        tools = []))
