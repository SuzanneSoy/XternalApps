#!/usr/bin/env python

# Does not work with inkscape 1.1
#extension_directory="$(inkscape --extension-directory)"

appImage = '/home/suzanne/perso/dl/software/dessin/Inkscape-16c8184-x86_64.AppImage'

import sys, os, subprocess, signal, tempfile, re
mountProcess = subprocess.Popen([appImage, '--appimage-mount'], stdout=subprocess.PIPE)

# os.path.join, but forbit .. and other tricks that would get out of the base directory.
def joinNoDotDot(base, rel):
    rel = os.fsencode(rel)
    absBase = os.path.abspath(base)
    relRequested = os.path.relpath(os.path.join(absBase, rel), start=absBase)
    absRequested = os.path.abspath(os.path.join(absBase, relRequested))
    commonPrefix = os.path.commonprefix([absRequested, absBase])
    if relRequested.startswith(os.fsencode(os.pardir)):
        raise ValueError("security check failed: requested inkscape extension is outside of inkscape extension directory 1" + repr(relRequested))
    elif commonPrefix != absBase:
        raise ValueError("security check failed: requested inkscape extension is outside of inkscape extension directory 2")
    else:
        return absRequested

tempfiles=[]
tempdirs=[]
try:
    d = tempfile.mkdtemp()
    tempdirs += [d]
    pathfile = os.path.join(d, "as_path.svg")
    tempfiles += [pathfile]

    # Convert all objects (incl. circles) to paths and extract the IDs (not all FreeCAD objects in the SVG have an ID, converting to paths seems to assign them an ID)
    processAsPath = subprocess.Popen([appImage, sys.argv[-1], '--actions=select-all;object-to-path;select-list', '--export-type=svg', '--export-filename=' + pathfile], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    asPath = processAsPath.communicate()
    if processAsPath.returncode != 0:
        # TODO: forward the stderr and use subprocess.CalledProcessError
        raise ValueError("Child process failed: could not execute Inkscape to convert SVG objects to paths")
    lines = asPath[0].split(b'\n')
    if lines[0] == b'Run experimental bundle that bundles everything':
        lines = lines[1:]
    ids = [line.split(b' ')[0] for line in lines]

    try:
        if mountProcess.poll() is None:
            mountPoint = mountProcess.stdout.readline().rstrip(b'\r\n') # TODO: this is slightly wrong (removes multiple occurrences)
        else:
            raise "Could not mount AppImage"
    
        apprun = os.path.join(mountPoint, b'AppRun')
        extensionDirectory = os.path.join(mountPoint, b'usr/share/inkscape/extensions')
        e = os.environb.copy()
        e['PYTHONPATH'] = e.get('PYTHONPATH', b'') + os.path.pathsep.encode('utf-8') + os.path.join(mountPoint, b'usr/lib/python3/dist-packages/')
        extensionPy = joinNoDotDot(extensionDirectory, sys.argv[1])
        cmd = [apprun, 'python3.8', extensionPy] + [b'--id='+id for id in ids] + sys.argv[2:-1] + [pathfile]
        process = subprocess.Popen(cmd, env=e, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        result = process.communicate()[0]
        if process.returncode != 0:
            # TODO: forward the stderr and use subprocess.CalledProcessError
            raise ValueError("Child process failed: could not execute Inkscape extension with the given parameters")
        lines = result.split(b'\n')
        if lines[0] == b'Run experimental bundle that bundles everything':
            lines = lines[1:]
        # TODO: use lxml instead
        with open('/tmp/fooaaa', 'w') as debug:
            debug.write('trollollo')
            debug.write('1' + str(lines[0])+'\n\n')
            lines[0] = re.sub(rb' version="([.0-9]*)"', rb' version="\1" inkscape:version="\1"', lines[0])
            debug.write('2' + str(lines[0])+'\n\n')
        #sed -i -e '1 s/ version="1.1"/ inkscape:version="1.1"&/'
        sys.stdout.buffer.write(b'\n'.join(lines))
    # --id=rect815 --subdivs 6 --smooth 4.0 /tmp/a.svg 2>/dev/null | sed -e '/Run experimental bundle that bundles everything/,1 d'
    
    finally:
        mountProcess.send_signal(signal.SIGINT)
    
    #LD_LIBRARY_PATH= PYTHONPATH="$extension_directory:$PYTHONPATH" python2 "$extension_directory"/fractalize.py "$@"
    #/nix/store/zr4xihxd720pq3n0a58ixrqa243hx7an-python-2.7.17-env/bin/python2.7
    
    #./perso/dl/software/dessin/Inkscape-3bc2e81-x86_64.AppImage --appimage-mount
finally:
    for tempfile in tempfiles:
        try:
            os.remove(tempfile)
        except:
            pass
    for tempdir in tempdirs:
        try:
            os.rmdir(tempdir)
        except:
            pass
