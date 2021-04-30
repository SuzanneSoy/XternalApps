import FreeCAD as App
import FreeCADGui
from lxml import etree
import XternalAppsList
from ToolXML import *
from collections import namedtuple
import re
from copy import deepcopy
from collections import defaultdict
import pprint

parser = etree.XMLParser(resolve_entities=False)

FreeCADType = namedtuple('FreeCADType', ['type', 'defaultForType', 'maybeEnumValues'])

XFormsInput = namedtuple('XFormsInput', ['modelElementPath', 'label', 'simpleName', 'maybeEnum', 'groupName']) #'type', 'input', 'InputValueToModelValue', 'ModelValueToInputValue'
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
    'xsd:decimal': FreeCADType(type='App::PropertyFloat', defaultForType=0.0, maybeEnumValues=None),
    'xsd:string': FreeCADType(type='App::PropertyString', defaultForType='', maybeEnumValues=None),
}

def getShortPath(root, elem, root_needs_dot = True):
    if isinstance(root, etree._ElementTree):
        root = root.getroot()
    if root == elem:
        return '.'
    else:
        parent = elem.getparent()
        parentChildren = list(parent) # convert to list of children
        index = parentChildren.index(elem)
        return getShortPath(root, parent) + '/*[' + str(index) + ']'

def typeToFreeCADType(type, namespacesAtTypeElement, maybeSchema):
    def escape(str): return 
    if type.startswith('mime:'):
        return MIMETypeToFreeCADType(type[5:])
    elif type in typeToFreeCADTypeDict:
        return typeToFreeCADTypeDict[type]
    elif maybeSchema is not None and ':' in type:
        # TODO: should the type be looked up using the namespaces on the 'type="xxx"' side or on the 'schema' side?
        nameNs, name = type.split(':', 1)
        if '"' in name or '&' in name:
            raise ValueError("invaid character in type name")
        if nameNs not in namespacesAtTypeElement.keys() or namespacesAtTypeElement[nameNs] != maybeSchema.attrib['targetNamespace']:
            raise ValueError('namespace of type reference must match the targetNamespace of the schema')
        schemaTypes = maybeSchema.findall('.//*[@name="'+name+'"]', namespaces=namespacesAtTypeElement)
        if len(schemaTypes) != 1:
            raise ValueError('Could not find definition for XForms type.')
        else:
            schemaType = schemaTypes[0];
            return schemaTypeToFreeCADType(schemaType)
    else:
        raise ValueError('Unsupported XForms type')

def schemaTypeToFreeCADType(schemaType):
    if schemaType.tag == "{http://www.w3.org/2001/XMLSchema}simpleType":
        restriction = schemaType.find('./xsd:restriction', ns)
        base = restriction.attrib['base']
        if ':' not in base:
            raise ValueError('only restrictions of xsd:string (a.k.a. enums) are supported')
        baseNs, baseName = base.split(':', 1)
        if baseName != 'string' or baseNs not in restriction.nsmap.keys() or restriction.nsmap[baseNs] != ns['xsd']:
            raise ValueError('only restrictions of xsd:string (a.k.a. enums) are supported')
        enumCases = restriction.findall('./xsd:enumeration', ns)
        enumValues = [enumCase.attrib['value'] for enumCase in enumCases]
        return FreeCADType(type = 'App::PropertyEnumeration', maybeEnumValues = enumValues, defaultForType = (enumValues[0] if len(enumValues) > 0 else None))
    elif schemaType.tag == "{http://www.w3.org/2001/XMLSchema}complexType":
        return ValueError("Complex XML chema types are not supported")
    
def MIMETypeToFreeCADType(MIMEType):
    if MIMEType == 'image/svg+xml':
        return FreeCADType(type='App::PropertyLink', defaultForType=None, maybeEnumValues=None)
    else:
        raise ValueError('Unsupported MIME type')

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

def toSimpleName(name):
    return re.sub(r'( |[^-a-zA-Z0-9])+', ' ', name).title().replace(' ', '')

def toUniqueSimpleName(name, mutableNextUnique):
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

class XternalAppsParametricTool():
    def __init__(self, obj, appName, toolName):
        self.Type = "XternalAppsParametricTool"
        self.AppName = appName
        self.ToolName = toolName        
        self.MonitorChanges = False;
        obj.Proxy = self
        
        self.types    = self.xmlTypesToPython(self.Tool.XForms)
        self.defaults = self.xmlDefaultsToPython(self.Tool.XForms, self.types)
        self.form     = self.xmlFormToPython(self.Tool.XForms, self.types)
        
        self.ModelInstance = self.defaults
        self.createProperties(obj, self.types, self.ModelInstance, self.form)

        self.MonitorChanges = True;
        return

    def __getstate__(self):
        copied = self.__dict__.copy()
        copied['ModelInstance'] = list(copied['ModelInstance'].items())
        del copied['types']
        del copied['defaults']
        del copied['form']
        return copied

    def __setstate__(self, state):
        if state:
            state['ModelInstance'] = dict(state['ModelInstance'])
            self.__dict__ = state
            self.types    = self.xmlTypesToPython(self.Tool.XForms)
            self.defaults = self.xmlDefaultsToPython(self.Tool.XForms, self.types)
            self.form     = self.xmlFormToPython(self.Tool.XForms, self.types)
            
    def getDefaultModelInstance(self, obj):
        xml = etree.parse(self.Tool.XForms, parser=parser)
        model = xml.find('./xforms:model', ns)
        instanceDocument = etree.ElementTree(model.find('./xforms:instance/*', ns))
        return deepcopy(instanceDocument)

    def typecheckModelInstance(self, types, instance):
        """TODO"""

    def updateModelInstance(self, instance, ref, value):
        """TODO"""

    def onChanged(self, obj, prop):
        if self.MonitorChanges:
            try:
                self.MonitorChanges = False
                inputs = [input for input in self.form.values() if input.simpleName == prop]
                if len(inputs) == 1:
                    input = inputs[0]
                    newModelValue = getattr(obj, prop)
                    if input.maybeEnum:
                        newModelValue = input.maybeEnum[newModelValue]
                    self.ModelInstance[input.modelElementPath] = newModelValue
                    for other in self.form.values():
                        if other.modelElementPath == input.modelElementPath and other.simpleName != input.simpleName:
                            newFormValue = newModelValue
                            if other.maybeEnum:
                                newFormValue = [f for f, m in other.maybeEnum.items() if m == newModelValue][0]
                            setattr(obj, other.simpleName, newFormValue)
                            obj.setExpression(other.simpleName, None)
            finally:
                self.MonitorChanges = True
        return
        
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
        path = getShortPath(xml, xmlXFormsElement) # YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY
        return (path, xmlXFormsElement, modelElementPath, type)

    def xmlFormToPython(self, form_xml, types):
        """Parse the …-form.xml document, and return
        a dictionary form[form_path] = ("model_path", "label", enum_labels?)"""

        xml = etree.parse(form_xml, parser=parser) # self.Tool.XForms
        model_root = xml.find('./xforms:model', ns)
        instanceDocument = etree.ElementTree(model_root.find('./xforms:instance/*', ns))
        inputs = {}
        nextUniqueSimpleName = defaultdict(lambda: 0)

        # register all inputs to inputs[pathToElement]
        for group in xml.findall('./xforms:group', ns):
            for input in group.findall('./xforms:input', ns):
                path, xmlXFormsElement, modelElementPath, _type = self.interpretFormElement(input, xml, instanceDocument, types)

                label = input.attrib['label']
                simpleName = toUniqueSimpleName(toSimpleName(label), nextUniqueSimpleName)
                groupName = "/".join(input.xpath('ancestor-or-self::xforms:group/xforms:label/text()', namespaces=ns)) or None

                # input=xmlXFormsElement,
                inputs[path] = XFormsInput(modelElementPath=modelElementPath, label=label, simpleName=simpleName, maybeEnum=None, groupName=groupName) # type=type,
            for select1 in group.findall('./xforms:select1', ns):
                path, xmlXFormsElement, modelElementPath, _type = self.interpretFormElement(select1, xml, instanceDocument, types)
                
                label = select1.attrib['label']
                simpleName = toUniqueSimpleName(toSimpleName(label), nextUniqueSimpleName)
                groupName = "/".join(select1.xpath('ancestor-or-self::xforms:group/xforms:label/text()', namespaces=ns)) or None

                # Gather the allowed elements for the enum
                enum = {}
                for item in select1.findall('./xforms:item', ns):
                  enum[item.attrib['label']] = item.attrib['value']
                # input=xmlXFormsElement,
                inputs[path] = XFormsInput(modelElementPath=modelElementPath, label=label, simpleName=simpleName, maybeEnum=enum, groupName=groupName) # type=type,
        
        return inputs

    def xmlTypesToPython(self, model_xml):
        """Parse the …-model.xml document, and return
        a dictionary model[model_path] = ("FreeCAD type", FreeCADValue)."""

        xml = etree.parse(model_xml, parser=parser) # self.Tool.XForms
        model_root = xml.find('./xforms:model', ns)
        instanceDocument = etree.ElementTree(model_root.find('./xforms:instance/*', ns))
        maybeSchema = model_root.findall('./xsd:schema', ns)
        maybeSchema = None if len(maybeSchema) != 1 else maybeSchema[0];

        types = {}
        for bind in model_root.findall('xforms:bind', ns):
            for bound in instanceDocument.findall(bind.attrib['ref'], namespaces=bind.nsmap):
                path = instanceDocument.getelementpath(bound)
                # TODO: if has attrib type then …
                type = bind.attrib['type']
                type = typeToFreeCADType(type, bind.nsmap, maybeSchema)
                # TODO: I guess XForms implicitly allows intersection types by using several bind statements?
                types[path] = type
                # TODO: "required" field
        return types

    def xmlDefaultsToPython(self, model_xml, types):
        xml = etree.parse(model_xml, parser=parser) # self.Tool.XForms
        model_root = xml.find('./xforms:model', ns)
        instanceDocument = etree.ElementTree(model_root.find('./xforms:instance/*', ns))

        defaults = {}
        for modelElement in instanceDocument.findall('//*', ns):
            path = instanceDocument.getelementpath(modelElement)
            default = modelElement.text
            if default is None:
                default = types[path].defaultForType
            defaults[path] = default
        return defaults

    def createProperties(self, obj, types, defaults, form):
        for key, (modelElementPath, label, simpleName, maybeEnum, groupName) in form.items():
            obj.addProperty(types[modelElementPath].type,
                            simpleName,
                            groupName,
                            label + '\nA value of type ' + types[modelElementPath].type)
            default = defaults[modelElementPath]
            if maybeEnum is not None:
                setattr(obj, simpleName, list(maybeEnum.keys()))
                print(default, maybeEnum)
                # TODO: use a bidirectional dict
                default = [k for k, v in maybeEnum.items() if v == default][0]
            setattr(obj, simpleName, default)

    @property
    def Tool(self):
        return XternalAppsList.apps[self.AppName].Tools[self.ToolName]

    def execute(self, obj):
        """This is called when the object is recomputed"""
