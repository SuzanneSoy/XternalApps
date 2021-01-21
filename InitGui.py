import sys

import ExternalAppsList

myIcon = """
        /* XPM */
        static char * icon_xpm[] = {
        "16 16 15 1",
        " 	c None",
        ".	c #FFFFFF",
        "+	c #E8E5E5",
        "@	c #897578",
        "#	c #9B8B8D",
        "$	c #75575C",
        "%	c #C9C3C4",
        "&	c #FF89DA",
        "*	c #FF96DA",
        "=	c #FFA2DA",
        "-	c #FFACDA",
        ";	c #FFB2DA",
        ">	c #FFEAF3",
        ",	c #FFB9DA",
        "'	c #FF9DDA",
        "................",
        "..........+@....",
        ".........#$%....",
        "........$$$.....",
        ".......%$$%.....",
        ".......&%.......",
        "......*&........",
        ".....=&.........",
        "....-&.....&....",
        "...;&>....&&....",
        "..,'&.....&&....",
        "..&&.....&..&...",
        ".........&&&&...",
        "........&...&...",
        ".......&.....&..",
        "................"};
        """

class XternalAppsWorkbench(Workbench):
    """Subclasses must implement the appName attribute"""
    global myIcon
    global XternalAppsWorkbench

    Icon = myIcon

    def __init__(self):
        self.MenuText = "XternalApps: " + self.appName
        self.ToolTip = "Embeds " + self.appName + " in FreeCAD"
        super(XternalAppsWorkbench, self).__init__()

    def Initialize(self):
        if sys.version_info[0] == 2:
            import Resources2
        else:
            import Resources3
        import GIMPCommand
        import Embed
        Embed.ExternalApps()
        self.list = [self.appName + 'Command']
        self.appendMenu("ExternalApplications", self.list)
        self.appendToolbar("ExternalApplications", self.list)

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    #def ContextMenu(self):
    #    pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"

def addAppWorkbench(appName):
    workbenchClass = type(
        "XternalApps" + appName + "Workbench",
        (XternalAppsWorkbench,), { 'appName': appName })
    Gui.addWorkbench(workbenchClass())

for app in ExternalAppsList.apps:
    addAppWorkbench(app)
