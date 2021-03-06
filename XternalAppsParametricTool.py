import FreeCAD as App
import FreeCADGui
#from xml.etree import ElementTree
from lxml import etree
import ExternalAppsList
from ToolXML import *
import re

def CreateCommand(appName, toolName):
    App.ActiveDocument.openTransaction('Create parametric %s from %s'%(toolName, appName))
    FreeCADGui.addModule("XternalAppsParametricTool")
    FreeCADGui.doCommand("XternalAppsParametricTool.create(%s, %s)"%(repr(appName), repr(toolName)))
    App.ActiveDocument.commitTransaction()

def create(appName, toolName):
    name = appName + toolName
    obj = App.ActiveDocument.addObject("App::DocumentObjectGroupPython", name)
    XternalAppsParametricTool(obj, appName, toolName)
    return obj

# TODO: read-only/immutable
typeToFreeCADTypeDict = {
    # TODO:do an XML namespace lookup instead of comparing a constant.
    'xsd:decimal': 'App::PropertyFloat',
    'xsd:string': 'App::PropertyString',
}

def typeToFreeCADType(type):
    if type.startswith('mime:'):
        return MIMETypeToFreeCADType(MIMEType[5:])
    if type in typeToFreeCADTypeDict:
        return typeToFreeCADTypeDict[type]
    else:
        raise ArgumentException('Unsupported XForms type')

def MIMETypeToFreeCADType(MIMEType):
    if MIMEType == 'image/svg+xml':
        return 'App::PropertyLink'
    else:
        raise ArgumentException('Unsupported MIME type')

class XternalAppsParametricTool():
    def __init__(self, obj, appName, toolName):
        self.Type = "XternalAppsParametricTool"
        self.AppName = appName
        self.ToolName = toolName
        obj.Proxy = self
        self.createPropertiesFromXML(obj)

    def interpretXML(self):
        types = {}
        modelInstance = {}
        inputs = {}

        xml = etree.parse(self.Tool.XForms)
        model = xml.find('./xforms:model', ns)
        instanceDocument = etree.ElementTree(model.find('./xforms:instance/*', ns))

        # Traverse the XForms instance and register all elements in modelInstance[pathToElement]
        for element in instanceDocument.findall('.//*'):
            path = instanceDocument.getpath(element)
            modelInstance[path] = element.text

        # register all xform:bind to types[pathToTargetElement]
        for bind in model.findall('xforms:bind', ns):
            for bound in instanceDocument.findall(bind.attrib['ref'], namespaces=bind.nsmap):
                path = instanceDocument.getpath(bound)
                # TODO: if has attrib type then …
                type = bind.attrib['type']
                # TODO: I guess XForms implicitly allows intersection types by using several bind statements?
                types[path] = type
                # TODO: "required" field

        # register all inputs to inputs[pathToElement]
        for group in xml.findall('./xforms:group', ns):
            for input in group.findall('./xforms:input', ns):
                # TODO: is it safe to pass input unprotected here?
                modelElement = instanceDocument.find(input.attrib['ref'], namespaces=input.nsmap)
                if modelElement is None:
                    raise Exception('Could not find ' + input.attrib['ref'] + ' in instance document with namespaces=' + repr(input.nsmap))
                type = types[instanceDocument.getpath(modelElement)]
                inputs[xml.getpath(input)] = (input, modelElement, type)
        return (xml, types, modelInstance, inputs)

    def createPropertiesFromXML(self, obj):
        xml, types, modelInstance, inputs = self.interpretXML()
        for (input, modelElement, type) in inputs.values():
            simpleName = re.sub(r'( |[^-a-zA-Z0-9])+', ' ', input.attrib['label']).title().replace(' ', '')
            input.xpath('ancestor-or-self::group')
            obj.addProperty(typeToFreeCADType(type),
                            simpleName,
                            "/".join(input.xpath('ancestor-or-self::xforms:group/xforms:label/text()', namespaces=ns)) or None,
                            input.attrib['label'] + '\nA value of type ' + type)

    @property
    def Tool(self):
        return ExternalAppsList.apps[self.AppName].Tools[self.ToolName]

def execute(self, obj):
        """This is called when the object is recomputed"""
