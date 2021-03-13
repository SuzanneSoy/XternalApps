import FreeCAD as App
import FreeCADGui
from lxml import etree
import ExternalAppsList
from ToolXML import *
from collections import namedtuple
import re
from copy import deepcopy
from collections import defaultdict

XFormsInput = namedtuple('XFormsInput', ['input', 'modelElementPath', 'type', 'maybeEnum', 'InputValueToModelValue', 'ModelValueToInputValue'])
XFormsEnum = namedtuple('XFormsEnum', ['labels', 'values'])
InterpretedXML = namedtuple('InterpretedXML', ['xml', 'types', 'inputs']) # Parsed XML, dictionary(modelElementPath) -> type, dictionary(formElementPath) -> XFormsInput

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

def encode_bytes(bytestring):
    try:
        return ("utf-8", bytestring.decode('utf-8', errors='strict'))
    except ValueError:
        from base64 import b64encode
        return ("base64", b64encode(bytestring))

def decode_bytes(encoding_and_string):
    encoding, string = encoding_and_string
    if encoding == "utf-8":
        return string.encode('utf-8')
    elif encoding == "base64":
        from base64 import b64decode
        return b64decode(string)
    else:
        raise ValueError("invalid encoding: expected utf-8 or base64")

class XternalAppsParametricTool():
    def __init__(self, obj, appName, toolName):
        self.Type = "XternalAppsParametricTool"
        self.AppName = appName
        self.ToolName = toolName
        obj.Proxy = self
        self.ModelInstance = self.getDefaultModelInstance(obj)
        self.ModelToProperties = {}
        self.ModelOnChanged = defaultdict(set)
        self.createPropertiesFromXML(obj)

    def __getstate__(self):
        copied = self.__dict__.copy()
        copied['ModelInstance'] = encode_bytes(etree.tostring(copied['ModelInstance']))
        return copied

    def __setstate__(self, state):
        if state:
            state['ModelInstance'] = etree.fromstring(decode_bytes(state['ModelInstance']))
            self.__dict__ = state
            
    def getDefaultModelInstance(self, obj):
        xml = etree.parse(self.Tool.XForms)
        model = xml.find('./xforms:model', ns)
        instanceDocument = etree.ElementTree(model.find('./xforms:instance/*', ns))
        return deepcopy(instanceDocument)

    def typecheckModelInstance(self, types, instance):
        """TODO"""

    def updateModelInstance(self, instance, ref, value):
        """TODO"""

    def onChanged(self, obj, prop):
        if hasattr(self, 'SimpleInputNameToInput'):
            inputPath = self.SimpleInputNameToInput.get(prop, None)
            if inputPath is not None:
                modelElementPath = self.Inputs[inputPath].modelElementPath
                modelElement = self.ModelInstance.find(modelElementPath)
                newText = self.Inputs[inputPath].InputValueToModelValue(getattr(obj, prop))
                print((prop, getattr(obj, prop), modelElement.text, newText))
                if modelElement.text != newText:
                    modelElement.text = newText
                    for inputPathToUpdate in self.ModelOnChanged[modelElementPath]:
                        if inputPathToUpdate != inputPath:
                            # TODO: this is terrible and will lead to infinite update loops
                            setattr(obj, self.InputToSimpleInputName[inputPathToUpdate], self.Inputs[inputPathToUpdate].ModelValueToInputValue(newText))

    def interpretFormElement(self, xmlXFormsElement, xml, instanceDocument, types):
        # TODO: is it safe to pass input unprotected here?
        modelElement = instanceDocument.find(xmlXFormsElement.attrib['ref'],
                                             namespaces=xmlXFormsElement.nsmap)
        if modelElement is None:
            raise Exception('Could not find ' + xmlXFormsElement.attrib['ref'] \
                            + ' in instance document with namespaces=' + repr(xmlXFormsElement.nsmap))
        modelElementPath = instanceDocument.getelementpath(modelElement)
        type = types.get(modelElementPath)
        if type is None:
            raise Exception('Could not find type for ' + modelElementPath)
        path = xml.getelementpath(xmlXFormsElement)
        return (path, xmlXFormsElement, modelElementPath, type)

    def interpretXML(self):
        """Parse the self.Tool.XForms document, and return
        * the parsed xml,
        * a dictionary types[path] = "type"
        * a dictionary inputs[path] = (xml_input_element, xml_model_element, type)."""
        types = {}
        #modelInstance = {}
        inputs = {}

        xml = etree.parse(self.Tool.XForms)
        model = xml.find('./xforms:model', ns)
        instanceDocument = etree.ElementTree(model.find('./xforms:instance/*', ns))

        # register all xform:bind to types[pathToTargetElement]
        for bind in model.findall('xforms:bind', ns):
            for bound in instanceDocument.findall(bind.attrib['ref'], namespaces=bind.nsmap):
                path = instanceDocument.getelementpath(bound)
                # TODO: if has attrib type then …
                type = bind.attrib['type']
                # TODO: I guess XForms implicitly allows intersection types by using several bind statements?
                types[path] = type
                # TODO: "required" field

        # register all inputs to inputs[pathToElement]
        for group in xml.findall('./xforms:group', ns):
            for input in group.findall('./xforms:input', ns):
                path, xmlXFormsElement, modelElementPath, type = self.interpretFormElement(input, xml, instanceDocument, types)
                inputs[path] = XFormsInput(input=xmlXFormsElement, modelElementPath=modelElementPath, type=type, maybeEnum=None, InputValueToModelValue = None, ModelValueToInputValue = None)
            for select1 in group.findall('./xforms:select1', ns):
                path, xmlXFormsElement, modelElementPath, type = self.interpretFormElement(select1, xml, instanceDocument, types)
                # Gather the allowed elements for the enum
                enum = {}
                for item in select1.findall('./xforms:item', ns):
                  enum[item.attrib['label']] = item.attrib['value']
                inputs[path] = XFormsInput(input=xmlXFormsElement, modelElementPath=modelElementPath, type=type, maybeEnum=enum, InputValueToModelValue = None, ModelValueToInputValue = None)
        return InterpretedXML(xml=xml, types=types, inputs=inputs) # modelInstance, 

    def toSimpleName(self, name):
        return re.sub(r'( |[^-a-zA-Z0-9])+', ' ', name).title().replace(' ', '')

    def toUniqueSimpleName(self, name, mutableNextUnique):
        m = re.match(r'^((.*[^0-9])?)([0-9]*)$', name)
        base = m.group(1)
        counter = m.group(3)
        if counter == '' and mutableNextUnique[base] == 0:
            mutableNextUnique[name] = 1
        elif counter == '':
            counter = str(mutableNextUnique[name])
            mutableNextUnique[name] = mutableNextUnique[name] + 1
        elif int(counter) > mutableNextUnique[name]:
            mutableNextUnique[name] = str(int(counter)+1)
        else:
            counter = str(mutableNextUnique[name])
            mutableNextUnique[name] = mutableNextUnique[name] + 1
        return base + counter

    def createPropertiesFromXML(self, obj):
        xml, types, inputs = self.interpretXML() # modelInstance,
        simpleInputNameToInput = {}
        inputToSimpleInputName = {}
        nextUniqueSimpleName = defaultdict(lambda: 0)
        inputs2 = {}
        for inputPath, (input, modelElementPath, type, maybeEnum, _1, _2) in inputs.items():
            simpleName = self.toUniqueSimpleName(self.toSimpleName(input.attrib['label']), nextUniqueSimpleName)
            simpleInputNameToInput[simpleName] = inputPath
            inputToSimpleInputName[inputPath] = simpleName
        
            group = "/".join(input.xpath('ancestor-or-self::xforms:group/xforms:label/text()', namespaces=ns)) or None

            loadedValue = self.ModelInstance.find(modelElementPath).text

            obj.addProperty(typeToFreeCADType(type, maybeEnum),
                            simpleName,
                            group,
                            input.attrib['label'] + '\nA value of type ' + type)

            inputValueToModelValue = str
            modelValueToInputValue = lambda x: x
            if maybeEnum is not None:
                enumWithSimpleNames = { self.toSimpleName(k): v for k, v in maybeEnum.items() }
                setattr(obj, simpleName, list(enumWithSimpleNames.keys()))
                inputValueToModelValue = enumWithSimpleNames.get
                modelValueToInputValue = {v: l for l, v in enumWithSimpleNames.items()}.get

            if loadedValue is not None:
                print("setting " + simpleName + "(full label = " + input.attrib['label'] + ") to " + str(loadedValue))
                setattr(obj, simpleName, modelValueToInputValue(loadedValue))
            
            # TODO: refactor this!
            inputs2[inputPath] = XFormsInput(
                input=input,
                modelElementPath=modelElementPath,
                type=type,
                maybeEnum=maybeEnum,
                InputValueToModelValue = inputValueToModelValue,
                ModelValueToInputValue = modelValueToInputValue)
            
            self.ModelOnChanged[modelElementPath].add(inputPath)
        self.Types = types
        self.Inputs = inputs2
        self.SimpleInputNameToInput = simpleInputNameToInput
        self.InputToSimpleInputName = inputToSimpleInputName

    @property
    def Tool(self):
        return ExternalAppsList.apps[self.AppName].Tools[self.ToolName]

    def execute(self, obj):
        """This is called when the object is recomputed"""
