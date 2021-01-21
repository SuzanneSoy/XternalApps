import sys

class XternalAppsWorkbench(Workbench):
    MenuText = "XternalApps"
    ToolTip = "Embeds external Applications in FreeCAD"
    Icon = """
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

    def __init__(self):
        super(self.__class__, self).__init__()

    def Initialize(self):
        print('Initialize')
        if sys.version_info[0] == 2:
            import Resources2
        else:
            import Resources3
        import GIMPCommand
        import Embed
        Embed.ExternalApps()
        self.list = ['GIMPCommand']
        self.appendMenu("ExternalApplications", self.list)
        self.appendToolbar("ExternalApplications", self.list)

    def Activated(self):
        print('Activated')
        pass

    def Deactivated(self):
        print('Deactivated')
        pass

    def ContextMenu(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"

Gui.addWorkbench(XternalAppsWorkbench())
