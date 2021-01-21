import FreeCAD
import FreeCADGui as Gui
import subprocess
import PySide
import re
from PySide import QtGui
from PySide import QtCore

class Tool():
    def __init__(self, name, *, start_command_and_args, xwininfo_filter_re, extra_xprop_filter):
        self.name = name
        self.start_command_and_args = start_command_and_args
        self.xwininfo_filter_re = re.compile(xwininfo_filter_re)
        self.extra_xprop_filter = extra_xprop_filter

class Tools():
    def __init__(self, *tools):
        self.__dict__ = {tool.name: tool for tool in tools}
    def __getitem__(self, k): return self.__dict__[k]

# tool-specific infos:
tools = Tools(
    Tool('Mousepad',
        start_command_and_args = ['mousepad', '--disable-server'],
        xwininfo_filter_re = r'mousepad',
        extra_xprop_filter = lambda processId, windowId, i: True),
    Tool('Inkscape',
        start_command_and_args = ['inkscape'],
        xwininfo_filter_re = r'inkscape',
        extra_xprop_filter = lambda processId, windowId, i: x11prop(windowId, 'WM_STATE',  'WM_STATE') is not None),
    Tool('GIMP',
        start_command_and_args = ['env', '-i', 'DISPLAY=:0', '/home/suzanne/perso/dotfiles/nix/result/bin/gimp', '--new-instance'],
        xwininfo_filter_re = r'gimp',
        extra_xprop_filter = lambda processId, windowId, i: x11prop(windowId, 'WM_STATE',  'WM_STATE') is not None))

class EmbeddedWindow(QtCore.QObject):
    def __init__(self, tool, externalAppInstance, processId, windowId):
        super(EmbeddedWindow, self).__init__()
        self.tool = tool
        self.externalAppInstance = externalAppInstance
        self.processId = processId
        self.windowId = windowId
        self.mdi = Gui.getMainWindow().findChild(QtGui.QMdiArea)
        self.xw = QtGui.QWindow.fromWinId(self.windowId)
        self.xw.setFlags(QtGui.Qt.FramelessWindowHint)
        self.xwd = QtGui.QWidget.createWindowContainer(self.xw)
        self.mwx = QtGui.QMainWindow()
        self.mwx.layout().addWidget(self.xwd)
        self.mdiSub = self.mdi.addSubWindow(self.xwd)
        self.xwd.setBaseSize(640,480)
        self.mwx.setBaseSize(640,480)
        self.mdiSub.setBaseSize(640,480)
        self.mdiSub.setWindowTitle(tool.name)
        self.mdiSub.show()
        #self.xw.installEventFilter(self)
    def eventFilter(self, obj, event):
        # This doesn't seem to work, some events occur but no the close one.
        if event.type() == QtCore.QEvent.Close:
            mdiSub.close()
        return False


# <optional spaces> <digits (captured in group 1)> <optional spaces> "<quoted string>"  <optional spaces> : <anything>
xwininfo_re = re.compile(r'^\s*([0-9]+)\s*"[^"]*"\s*:.*$')

def x11stillAlive(windowId):
    try:
        subprocess.check_output(['xprop', '-id', str(windowId), '_NET_WM_PID'])
        return True
    except:
        return False

def x11prop(windowId, prop, type):
    try:
        output = subprocess.check_output(['xprop', '-id', str(windowId), prop]).decode('utf-8', 'ignore').split('\n')
    except subprocess.CalledProcessError as e:
        output = []
    xprop_re = re.compile(r'^' + re.escape(prop) + r'\(' + re.escape(type) + r'\)((:)| =(.*))$')
    for line in output:
        trymatch = xprop_re.match(line)
        if trymatch:
            return trymatch.group(2) or trymatch.group(3)
    return None

def try_pipe_lines(commandAndArguments):
    try:
        return subprocess.check_output(commandAndArguments).decode('utf-8', 'ignore').split('\n')
    except:
        return []

class ExternalApps():
    def __init__(self):
        setattr(FreeCAD, 'ExternalApps', self)

def deleted(widget):
    """Detect RuntimeError: Internal C++ object (PySide2.QtGui.QWindow) already deleted."""
    try:
        str(widget) # str fails on already-deleted Qt wrappers.
        return False
    except:
        return True

class ExternalAppInstance(QtCore.QObject):
    def __init__(self, toolName):
        super(ExternalAppInstance, self).__init__()
        self.tool = tools[toolName]
        # Start the application
        # TODO: popen_process shouldn't be exposed to in-document scripts, it would allow them to redirect output etc.
        print('Starting ' + ' '.join(self.tool.start_command_and_args))
        self.popen_process = subprocess.Popen(self.tool.start_command_and_args)
        self.toolProcessIds = [self.popen_process.pid]
        self.initWaitForWindow()
        self.foundWindows = dict()
        setattr(FreeCAD.ExternalApps, self.tool.name, self)

    def initWaitForWindow(self):
        self.TimeoutHasOccurred  = False # for other scritps to know the status
        self.startupTimeout = 10000
        self.elapsed = QtCore.QElapsedTimer()
        self.elapsed.start()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.attemptToFindWindow)

    def waitForWindow(self):
        self.timer.start(50)

    @QtCore.Slot()
    def attemptToFindWindow(self):
        try:
            self.attemptToFindWindowWrapped()
        except:
            self.timer.stop()
            raise

    def attemptToFindWindowWrapped(self):
        # use decode('utf-8', 'ignore') to use strings instead of byte strings and discard ill-formed unicode in case these tool doesn't sanitize their output
        for line in try_pipe_lines(['xwininfo', '-root', '-tree', '-int']):
            if self.tool.xwininfo_filter_re.search(line):
                windowId = int(xwininfo_re.match(line).group(1))
                # use decode('utf-8', 'ignore') to use strings instead of byte strings and discard ill-formed unicode in case this tool doesn't sanitize their output
                xprop_try_process_id = x11prop(windowId, '_NET_WM_PID', 'CARDINAL')
                if xprop_try_process_id:
                    processId = int(xprop_try_process_id) # TODO try parse int and catch failure
                    if processId in self.toolProcessIds:
                        if self.tool.extra_xprop_filter(processId, windowId, len(self.foundWindows)):
                            self.foundWindow(processId, windowId)

        if self.elapsed.elapsed() > self.startupTimeout:
            self.timer.stop()
            self.TimeoutHasOccurred = True

    def foundWindow(self, processId, windowId):
        if windowId not in self.foundWindows.keys():
            self.foundWindows[windowId] = EmbeddedWindow(self.tool, self, processId, windowId)
            # TODO: find an event instead of polling
            for w in self.foundWindows.values():
                #if not deleted(xw) and not xw.isActive():
                if not x11stillAlive(w.windowId):
                    w.mdiSub.close()

# prevent_garbage_collect by binding to a variable???
#p = ExternalAppInstance('Mousepad')
#p = ExternalAppInstance('Inkscape')
ExternalApps()

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
        p = ExternalAppInstance('GIMP')
        p.waitForWindow()

    def IsActive(self):
        # return false to grey out the command in the menus, toolbars etc.
        return True

Gui.addCommand('GIMPCommand', GIMPCommand())
