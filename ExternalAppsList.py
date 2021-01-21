import FreeCAD
import FreeCADGui as Gui
import subprocess
import PySide
import re
from PySide import QtGui
from PySide import QtCore

from MyX11Utils import *

class App():
    def __init__(self, name, *, start_command_and_args, xwininfo_filter_re, extra_xprop_filter):
        self.name = name
        self.start_command_and_args = start_command_and_args
        self.xwininfo_filter_re = re.compile(xwininfo_filter_re)
        self.extra_xprop_filter = extra_xprop_filter

class Apps():
    def __init__(self, *apps):
        # TODO: make this private
        self.apps = {app.name: app for app in apps}
    def __getitem__(self, k):
        return self.apps[k]
    def __iter__(self):
        return self.apps.__iter__()

# app-specific infos:
apps = Apps(
    App('Mousepad',
        start_command_and_args = ['mousepad', '--disable-server'],
        xwininfo_filter_re = r'mousepad',
        extra_xprop_filter = lambda processId, windowId, i: True),
    App('Inkscape',
        start_command_and_args = ['inkscape'],
        xwininfo_filter_re = r'inkscape',
        extra_xprop_filter = lambda processId, windowId, i: x11prop(windowId, 'WM_STATE',  'WM_STATE') is not None),
    App('GIMP',
        start_command_and_args = ['env', '-i', 'DISPLAY=:0', '/home/suzanne/perso/dotfiles/nix/result/bin/gimp', '--new-instance'],
        xwininfo_filter_re = r'gimp',
        extra_xprop_filter = lambda processId, windowId, i: x11prop(windowId, 'WM_STATE',  'WM_STATE') is not None))
