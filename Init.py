import os
import FreeCAD
import XternalAppsDummy
# The __file__ special variable isn't available in the Init.py file, so we load a dummy module located in the same directory to get its path.
FreeCAD.ConfigSet('SplashScreen', os.path.join(os.path.dirname(XternalAppsDummy.__file__),'splash.png'))

# See https://github.com/FreeCAD/FreeCAD/blob/eb6167ff89bc2b287c83d726dfcd52b775d1757e/src/Gui/MainWindow.cpp#L1512
# for all the ways to set a splashscreen and their precedence order. I couldn't make the ~/.FreeCAD/splash_image.png work

