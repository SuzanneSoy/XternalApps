def getSingletonFromXML(xml, path):
    # TODO: error-checking and a proper message here if there is no matching element or more than one.
    elem = xml.find(path, ns)
    if elem is None:
        raise Exception('Error: could not find ' + path + ' in tool xforms')
    else:
        return elem

ns={
  'my':"http://github.com/jsmaniac/XternalApps/myTool",
  'XternalApps':"http://github.com/jsmaniac/XternalApps/v1",
  'xforms':"http://www.w3.org/2002/xforms",
  'xsd':"http://www.w3.org/2001/XMLSchema",
}

