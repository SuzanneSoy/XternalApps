import FreeCAD
import FreeCADGui as Gui
import subprocess
import PySide
import re
from PySide import QtGui
from PySide import QtCore

import XternalAppsList

def x11stillAlive(windowId):
    try:
        subprocess.check_output(['xprop', '-id', str(windowId), '_NET_WM_PID'])
        return True
    except:
        return False

def x11prop(windowId, prop, type):
    try:
        process_output = subprocess.check_output(['xprop', '-id', str(windowId), prop])
        # use decode('utf-8', 'ignore') to use strings instead of
        # byte strings and discard ill-formed unicode in case this
        # tool doesn't sanitize their output
        output = process_output.decode('utf-8', 'ignore').split('\n')
    except subprocess.CalledProcessError as e:
        output = []
    xprop_re = re.compile(r'^' + re.escape(prop) + r'\(' + re.escape(type) + r'\)((:)| =(.*))$')
    for line in output:
        trymatch = xprop_re.match(line)
        if trymatch:
            return trymatch.group(2) or trymatch.group(3)
    return None
