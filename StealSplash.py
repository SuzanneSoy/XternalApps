class Foo():
    def __del__(self):
        def catchSplash():
            import PySide
            from PySide import QtGui, QtCore
            import pprint
            print(QtGui.QApplication.topLevelWidgets())
            sps = [w for w in QtGui.QApplication.topLevelWidgets() if 'PySide2.QtWidgets.QWidget' in str(w)]
            if len(sps) == 1:
              sps[0].hide()
            print("toplevel=")
            pprint.pprint(QtGui.QApplication.topLevelWidgets())
            print("children=")
            pprint.pprint([x.children() for x in sps])

        print("del")
        catchSplash()

        import PySide
        from PySide import QtGui, QtCore
        tm = QtCore.QTimer()
        tm.timeout.connect(lambda: print(catchSplash))
        tm.start(100)

        #import FreeCAD
        #setattr(FreeCAD, "stealsplash", tm)

#foo = Foo()
print("IN stealsplash")

Splash = None

def isDeleted(obj):
    try:
        str(obj)
        return False
    except:
        return True

def steal():
    def checkSplashStillHere(official, splash, tm):
        print("check")
        if isDeleted(official):
            print("delete extra splash")
            tm.stop()
            splash.hide()
            # TODO: properly de-allocate on the FreeCAD object
            Splash = None
    def catchSplash():
        global Splash
        import PySide
        from PySide import QtGui, QtCore
        import pprint
        print(QtGui.QApplication.topLevelWidgets())
        sps = [w for w in QtGui.QApplication.topLevelWidgets() if 'PySide2.QtWidgets.QWidget' in str(w)]
        if len(sps) == 1:
            # This does not work
            try:
                QtGui.QSplashScreen.setPixmap(sps[0], '/tmp/splash.png')
            except:
                pass
            # this works, it's then possible to replace with a new splash but the progress text won't be displayed on the new splash
            # the official splash screen also doesn't have any children, so it's not possible to get the text from there
            # I could steal the info from the log, but unless FreeCAD was started with -l, I don't know how to access that log in Python.
            #sps[0].hide()
            
            # Solution: put a transparent background on this splash, make a new one and raise this one above.
            
            splash = QtGui.QSplashScreen('/tmp/splash.png')
            splash.show()
            sps[0].raise_()

            tm = QtCore.QTimer()
            tm.timeout.connect(lambda *, official=sps[0], splash=splash, tm=tm: checkSplashStillHere(official, splash, tm))
            tm.start(100)

            import FreeCAD
            setattr(FreeCAD, "Splash", (sps[0], splash, tm))

        #print("toplevel=")
        #pprint.pprint(QtGui.QApplication.topLevelWidgets())
        #print("children=")
        #pprint.pprint([x.children() for x in sps])

    print("del")
    catchSplash()
