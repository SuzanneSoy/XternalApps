import FreeCAD as App
import FreeCADGui
#from xml.etree import ElementTree
from lxml import etree
import ExternalAppsList
from ToolXML import *
from collections import namedtuple
import re

XFormsInput = namedtuple('XFormsInput', ['input', 'modelElement', 'type', 'maybeEnum'])
XFormsEnum = namedtuple('XFormsEnum', ['labels', 'values'])

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

def typeToFreeCADType(type, maybeEnum):
    if maybeEnum is not None:
        return 'App::PropertyEnumeration'
    elif type.startswith('mime:'):
        return MIMETypeToFreeCADType(MIMEType[5:])
    elif type in typeToFreeCADTypeDict:
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

    def interpretFormElement(self, xmlXFormsElement, xml, instanceDocument, types):
        # TODO: is it safe to pass input unprotected here?
        modelElement = instanceDocument.find(xmlXFormsElement.attrib['ref'],
                                             namespaces=xmlXFormsElement.nsmap)
        if modelElement is None:
            raise Exception('Could not find ' + xmlXFormsElement.attrib['ref'] \
                            + ' in instance document with namespaces=' + repr(xmlXFormsElement.nsmap))
        type = types.get(instanceDocument.getpath(modelElement))
        if type is None:
            raise Exception('Could not find type for ' + instanceDocument.getpath(modelElement))
        path = xml.getpath(xmlXFormsElement)
        return (path, xmlXFormsElement, modelElement, type)

    def interpretXML(self):
        """Parse the self.Tool.XForms document, and return
        * the parsed xml,
        * a dictionary types[path] = "type"
        * a dictionary inputs[path] = (xml_input_element, xml_model_element, type)."""
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
                path, xmlXFormsElement, modelElement, type = self.interpretFormElement(input, xml, instanceDocument, types)
                inputs[path] = XFormsInput(input=xmlXFormsElement, modelElement=modelElement, type=type, maybeEnum=None)
            for select1 in group.findall('./xforms:select1', ns):
                path, xmlXFormsElement, modelElement, type = self.interpretFormElement(select1, xml, instanceDocument, types)
                # Gather the allowed elements for the enum
                enum = {}
                for item in select1.findall('./xforms:item', ns):
                  enum[item.attrib['label']] = item.attrib['value']
                inputs[path] = XFormsInput(input=xmlXFormsElement, modelElement=modelElement, type=type, maybeEnum=enum)
        return (xml, types, modelInstance, inputs)

    def toSimpleName(self, name):
        return re.sub(r'( |[^-a-zA-Z0-9])+', ' ', name).title().replace(' ', '')

    def createPropertiesFromXML(self, obj):
        xml, types, modelInstance, inputs = self.interpretXML()
        for (input, modelElement, type, maybeEnum) in inputs.values():
            simpleName = self.toSimpleName(input.attrib['label'])
            group = "/".join(input.xpath('ancestor-or-self::xforms:group/xforms:label/text()', namespaces=ns)) or None
            print((simpleName, typeToFreeCADType(type, maybeEnum), maybeEnum))
            obj.addProperty(typeToFreeCADType(type, maybeEnum),
                            simpleName,
                            group,
                            input.attrib['label'] + '\nA value of type ' + type)
            if maybeEnum is not None:
                setattr(obj, simpleName, [self.toSimpleName(k) for k in maybeEnum.keys()])
                # TODO: have a converter from the labels to the values

    @property
    def Tool(self):
        return ExternalAppsList.apps[self.AppName].Tools[self.ToolName]

def execute(self, obj):
        """This is called when the object is recomputed"""
