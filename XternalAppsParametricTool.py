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
import Part

parser = etree.XMLParser(resolve_entities=False)

FreeCADType = namedtuple('FreeCADType', ['type', 'defaultForType', 'maybeEnumValues', 'maybeMIMEType', 'fromString'])

XFormsInput = namedtuple('XFormsInput', ['modelElementPath', 'label', 'simpleName', 'maybeEnum', 'groupName', 'relevance']) #'type', 'input', 'InputValueToModelValue', 'ModelValueToInputValue'
XFormsEnum = namedtuple('XFormsEnum', ['labels', 'values'])
InterpretedXML = namedtuple('InterpretedXML', ['xml', 'types', 'inputs']) # Parsed XML, dictionary(modelElementPath) -> type, dictionary(formElementPath) -> XFormsInput

# Safe printing of unknown strings
# This does not aim to have an exact representation of the string, just enough to display in error messages
def safeErr(s):
    s = str(s)
    result = ''
    for c in s:
        if c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 :_-':
            result += c
        else:
            result += ('\\u%04x' % + ord(c))
    return result

def CreateCommand(appName, toolName):
    App.ActiveDocument.openTransaction('Create parametric %s from %s'%(toolName, appName))
    FreeCADGui.addModule("XternalAppsParametricTool")
    FreeCADGui.doCommand("XternalAppsParametricTool.create(%s, %s)"%(repr(appName), repr(toolName)))
    App.ActiveDocument.commitTransaction()

def create(appName, toolName):
    sel = FreeCADGui.Selection.getSelection()
    name = appName + toolName
    #obj = App.ActiveDocument.addObject("App::DocumentObjectGroupPython", name)
    obj = App.ActiveDocument.addObject("Part::FeaturePython", name)
    XternalAppsParametricTool(obj, appName, toolName, sel)
    return obj

# TODO: read-only/immutable
typeToFreeCADTypeDict = {
    # TODO:do an XML namespace lookup instead of comparing a constant.
    'xsd:decimal': FreeCADType(type='App::PropertyFloat', defaultForType=0.0, maybeEnumValues=None, maybeMIMEType=None, fromString=float),
    'xsd:string':  FreeCADType(type='App::PropertyString', defaultForType='', maybeEnumValues=None, maybeMIMEType=None, fromString=lambda x: x),
    'xsd:integer': FreeCADType(type='App::PropertyInteger', defaultForType=0, maybeEnumValues=None, maybeMIMEType=None, fromString=int),
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
        raise ValueError('Unsupported XForms type ' + safeErr(type))

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
        return FreeCADType(type = 'App::PropertyEnumeration', defaultForType = (enumValues[0] if len(enumValues) > 0 else None), maybeEnumValues = enumValues, maybeMIMEType=None, fromString=lambda x: x)
    elif schemaType.tag == "{http://www.w3.org/2001/XMLSchema}complexType":
        return ValueError("Complex XML chema types are not supported")
    
def MIMETypeToFreeCADType(MIMEType):
    if MIMEType == 'image/svg+xml':
        return FreeCADType(type='App::PropertyLink', defaultForType=None, maybeEnumValues=None, maybeMIMEType = MIMEType, fromString=lambda x: x)
    else:
        raise ValueError('Unsupported MIME type')

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

def lookup(dict, part, value):
    kvs = [(k, v) for k, v in dict.items() if part(v) == value]
    if len(kvs) == 1:
        return kvs[0]
    return (None, None)

def exportSVG(obj, svgfile):
    import importSVG
    p=App.ParamGet("User parameter:BaseApp/Preferences/Mod/Draft")
    old_svg_export_style = p.GetInt('svg_export_style')
    try:
        p.SetInt('svg_export_style', 1)
        importSVG.export([obj], svgfile)
    finally:
        p.SetInt('svg_export_style', old_svg_export_style)
    
    # TODO: modify the SVG to set a fake Inkscape version, to avoid the pop-up dialog.

class XternalAppsParametricToolViewProvider():
    def __init__(self, vobj):
        """
        Set this object to the proxy object of the actual view provider
        """

        vobj.Proxy = self

    def attach(self, vobj):
        """
        Setup the scene sub-graph of the view provider, this method is mandatory
        """
        self.ViewObject = vobj
        self.Object = vobj.Object

    def updateData(self, fp, prop):
        """
        If a property of the handled feature has changed we have the chance to handle this here
        """
        print('VVVVVVVVVVVVVVVVVV', repr(fp), repr(prop))
        return

    def getDisplayModes(self,vobj):
        """
        Return a list of display modes.
        """
        return []

    def getDefaultDisplayMode(self):
        """
        Return the name of the default display mode. It must be defined in getDisplayModes.
        """
        return "Shaded"

    def setDisplayMode(self,mode):
        """
        Map the display mode defined in attach with those defined in getDisplayModes.
        Since they have the same names nothing needs to be done.
        This method is optional.
        """
        return mode

    def onChanged(self, vp, prop):
        """
        Print the name of the property that has changed
        """
        App.Console.PrintMessage("Change property: " + str(prop) + "\n")

    def getIcon(self):
        """
        Return the icon in XMP format which will appear in the tree view. This method is optional and if not defined a default icon is shown.
        """

        return """
            /* XPM */
            static const char * ViewProviderBox_xpm[] = {
            "16 16 6 1",
            "    c None",
            ".   c #141010",
            "+   c #615BD2",
            "@   c #C39D55",
            "#   c #000000",
            "$   c #57C355",
            "        ........",
            "   ......++..+..",
            "   .@@@@.++..++.",
            "   .@@@@.++..++.",
            "   .@@  .++++++.",
            "  ..@@  .++..++.",
            "###@@@@ .++..++.",
            "##$.@@$#.++++++.",
            "#$#$.$$$........",
            "#$$#######      ",
            "#$$#$$$$$#      ",
            "#$$#$$$$$#      ",
            "#$$#$$$$$#      ",
            " #$#$$$$$#      ",
            "  ##$$$$$#      ",
            "   #######      "};
            """

    def claimChildren(self):
        return self.Object.Proxy.getChildren(self.Object)

    def __getstate__(self):
        """
        Called during document saving.
        """
        return None

    def __setstate__(self,state):
        """
        Called during document restore.
        """
        print('AAAAAAAAAAAAAAAAAAAYYYYYYYYYYYYYYYYYYYYYYYYY', repr(self), repr(state))
        return None

    def onDocumentRestored(self, obj):
        print('AAAAAAAAAAAAAAAAAAAXXXXXXXXXXXXXXXXXXXXXXXXX', repr(self), repr(obj))

class XternalAppsParametricTool():
    def init1(self, appName, toolName):
        self.Type = "XternalAppsParametricTool"
        self.AppName = appName
        self.ToolName = toolName        
        self.MonitorChanges = False

    def init2(self, obj):
        self.Object = obj
        obj.Proxy = self

        self.types    = self.xmlTypesToPython(self.Tool.XForms)
        self.defaults = self.xmlDefaultsToPython(self.Tool.XForms, self.types)
        self.form     = self.xmlFormToPython(self.Tool.XForms, self.types)

        # TODO: on restore, reload the model instance from obj (or recompute it on the fly)
        self.ModelInstance = self.defaults

        self.oldExpressionEngine = obj.ExpressionEngine

    def init3(self, obj):
        self.MonitorChanges = True

    def __init__(self, obj, appName, toolName, sel=[]):
        self.init1(appName, toolName)
        self.init2(obj)
        self.createProperties(obj, self.types, self.ModelInstance, self.form)
        self.init3(obj)

        # Special treatment for the "primary" form field
        primary = [input for input in self.form.values() if input.relevance == 'primary']
        if len(primary) == 1:
            primary = primary[0]
            type = self.types[primary.modelElementPath].type

            # Display the contents of the primary form element as children in the tree view
            if type in ['App::PropertyLink', 'App::PropertyLinkList']:
                #self.form['FreeCADGroup'] = XFormsInput(modelElementPath=primary.modelElementPath, label='Group', simpleName='Group', maybeEnum=primary.maybeEnum, groupName='Base', relevance='primary')
                pass

            if type == 'App::PropertyLink' and len(sel) >= 1:
                setattr(obj, primary.simpleName, sel[0])
            elif type == 'App::PropertyLinkList':
                setattr(obj, primary.simpleName, sel)

        XternalAppsParametricToolViewProvider(obj.ViewObject)
        self.execute(obj)

    def getChildren(self, obj):
        primary = [input for input in self.form.values() if input.relevance == 'primary']
        if len(primary) == 1:
            primary = primary[0]
            type = self.types[primary.modelElementPath].type
            if type == 'App::PropertyLink':
                return [getattr(obj, primary.simpleName)]
            elif type == 'App::PropertyLinkList':
                return getattr(obj, primary.simpleName)
        return []

    def __getstate__(self):
        return { "AppName": self.AppName, "ToolName": self.ToolName }

        print('XXX_GET_STATE')
        print('self', repr(self))
        copied = self.__dict__.copy()
        copied['ModelInstance'] = list(copied['ModelInstance'].items())
        del copied['types']
        del copied['defaults']
        del copied['form']
        print('copied', repr(copied))
        return copied

    def __setstate__(self, state):
        print('XXX_SET_STATE')
        print(repr(self), repr(state))
        if state:
            # TODO: always sanitize data that is restored, for security reasons.
            #self.AppName = str(state['AppName'])
            #self.ToolName = str(state['ToolName'])
            #self.__init__(obj, self.AppName, self.ToolName, sel=[])
            self.init1(str(state['AppName']), str(state['ToolName']))
            #state['ModelInstance'] = dict(state['ModelInstance'])
            #self.__dict__ = state
            #self.types    = self.xmlTypesToPython(self.Tool.XForms)
            #self.defaults = self.xmlDefaultsToPython(self.Tool.XForms, self.types)
            #self.form     = self.xmlFormToPython(self.Tool.XForms, self.types)
    
    def onDocumentRestored(self, obj):
        print('XXX_ON_DOCUMENT_RESTORED')
        self.init2(obj)
        self.reloadProperties(obj, self.form)
        self.init3(obj)
        #self.__init__(obj, self.AppName, self.ToolName, sel=[])
            
    def onChanged(self, obj, prop):
        import sys
        #print ('onChanged' + str(prop), file=sys.stderr)
        
        restoreMonitorChanges = self.MonitorChanges
        if self.MonitorChanges:
            try:
                #print('MonitorChanges = False')
                self.MonitorChanges = False
                # clear expressions attached to the same part of the model
                if (prop == 'ExpressionEngine'):
                    # compare with oldExpressionEngine
                    added = []
                    removed = []
                    for (k, _) in obj.ExpressionEngine:
                        if k not in self.oldExpressionEngine:
                            added = added + [k]
                    #for k in self.oldExpressionEngine:
                    #    if k not in self.oldExpressionEngine:
                    #        removed = removed + [k]
                    # Clear expressions for properties linked to the one that was added.
                    for a in added:
                        _, input = lookup(self.form, lambda input: input.simpleName, a)
                        if input:
                            for other in self.form.values():
                                if other.modelElementPath == input.modelElementPath and other.simpleName != input.simpleName:
                                    # clear other.simpleName
                                    obj.setExpression(other.simpleName, None)
                self.oldExpressionEngine = set([k for k, v in obj.ExpressionEngine])
        
                #######################################
                self.setModelFromInput(obj, prop)
                #######################################
            finally:
                #print('MonitorChanges = ' + str(restoreMonitorChanges))
                self.MonitorChanges = restoreMonitorChanges
    
    def setModelFromInput(self, obj, prop):
        _, input = lookup(self.form, lambda input: input.simpleName, prop)
        if input:
            newModelValue = getattr(obj, prop)
            if input.maybeEnum:
                newModelValue = input.maybeEnum[newModelValue]
            # The Group property always contains a list, but we may use it to represent a link to a single element.
            if prop == 'Group' and self.types[input.modelElementPath].type == 'App::PropertyLink':
                if len(newModelValue) > 0:
                    newModelValue = newModelValue[0]
                else:
                    newModelValue = None
            print(self.ModelInstance, input.modelElementPath, newModelValue)
            self.ModelInstance[input.modelElementPath] = newModelValue
            for other in self.form.values():
                if other.modelElementPath == input.modelElementPath and other.simpleName != input.simpleName:
                    newFormValue = newModelValue
                    #print('newModelValue', newModelValue)
                    if other.maybeEnum:
                        newFormValue = [f for f, m in other.maybeEnum.items() if m == newModelValue][0]
                    #print(prop, newFormValue, other.simpleName, dict(obj.ExpressionEngine).get(prop), dict(obj.ExpressionEngine).get(other.simpleName))
                    #obj.setExpression(other.simpleName, dict(obj.ExpressionEngine).get(prop))
                    #print(obj, other.simpleName, newFormValue)
                    setattr(obj, other.simpleName, newFormValue)

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
        path = getShortPath(xml, xmlXFormsElement) # TODO !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        
        relevance = xmlXFormsElement.xpath('./@XternalApps:relevance', namespaces=ns)
        if len(relevance):
            relevance = relevance[0]
        else:
            relevance = None
        
        return (path, xmlXFormsElement, modelElementPath, type, relevance)

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
                path, xmlXFormsElement, modelElementPath, _type, relevance = self.interpretFormElement(input, xml, instanceDocument, types)

                label = input.attrib['label']
                simpleName = toUniqueSimpleName(toSimpleName(label), nextUniqueSimpleName)
                groupName = "/".join(input.xpath('ancestor-or-self::xforms:group/xforms:label/text()', namespaces=ns)) or None

                inputs[path] = XFormsInput(modelElementPath=modelElementPath, label=label, simpleName=simpleName, maybeEnum=None, groupName=groupName, relevance=relevance) # type=type,
            
            for upload in group.findall("./xforms:upload", ns):
                path, xmlXFormsElement, modelElementPath, _type, relevance = self.interpretFormElement(upload, xml, instanceDocument, types)

                label = upload.xpath('./xforms:label/text()', namespaces=ns)
                if len(label) != 1:
                    raise ValueError("An xforms:upload element should contain exactly one xforms:label element")
                label = label[0]
                if upload.xpath('./xforms:filename/@ref', namespaces=ns) != ['@filename']:
                    raise ValueError("The ref attribute of an xforms:filename should always be the string '@filename' (this is a limitation of the XternalApps format).")

                simpleName = toUniqueSimpleName(toSimpleName(label), nextUniqueSimpleName)
                groupName = "/".join(upload.xpath('ancestor-or-self::xforms:group/xforms:label/text()', namespaces=ns)) or None

                inputs[path] = XFormsInput(modelElementPath=modelElementPath, label=label, simpleName=simpleName, maybeEnum=None, groupName=groupName, relevance=relevance) # type=type,

            for select1 in group.findall('./xforms:select1', ns):
                path, xmlXFormsElement, modelElementPath, _type, relevance = self.interpretFormElement(select1, xml, instanceDocument, types)
                
                label = select1.attrib['label']
                simpleName = toUniqueSimpleName(toSimpleName(label), nextUniqueSimpleName)
                groupName = "/".join(select1.xpath('ancestor-or-self::xforms:group/xforms:label/text()', namespaces=ns)) or None

                # Gather the allowed elements for the enum
                enum = {}
                for item in select1.findall('./xforms:item', ns):
                  enum[item.attrib['label']] = item.attrib['value']
                # input=xmlXFormsElement,
                inputs[path] = XFormsInput(modelElementPath=modelElementPath, label=label, simpleName=simpleName, maybeEnum=enum, groupName=groupName, relevance=relevance) # type=type,
        
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
            defaults[path] = types[path].fromString(default)
        return defaults

    def createProperties(self, obj, types, defaults, form):
        for key, (modelElementPath, label, simpleName, maybeEnum, groupName, relevance) in form.items():
            obj.addProperty(types[modelElementPath].type,
                            simpleName,
                            groupName,
                            label + '\nA value of type ' + types[modelElementPath].type)
            default = defaults[modelElementPath]
            if maybeEnum is not None:
                setattr(obj, simpleName, list(maybeEnum.keys()))
                # TODO: use a bidirectional dict
                default = [k for k, v in maybeEnum.items() if v == default][0]
            try:
                setattr(obj, simpleName, default)
            except:
                raise ValueError('Could not set ' + safeErr(obj) + "." + safeErr(simpleName) + " = " + safeErr(repr(default)))

    def reloadProperties(self, obj, form):
        for key, (modelElementPath, label, simpleName, maybeEnum, groupName, relevance) in form.items():
            self.setModelFromInput(obj, simpleName)

    @property
    def Tool(self):
        return XternalAppsList.apps[self.AppName].Tools[self.ToolName]

    def xmlCommandToPython(self, obj, document):
        """Parse the .xml document, and return
        a pair of dictionaries accepts[model_path] = style and returns[model_path] = style."""

        print('A')

        xml = etree.parse(self.Tool.XForms, parser=parser)

        model_root = xml.find('./xforms:model', ns)
        instanceDocument = etree.ElementTree(model_root.find('./xforms:instance/*', ns))

        print('B')
        command = xml.find('./XternalApps:command', ns)
        method = command.attrib['method']
        commandName = command.attrib['name']

        print('C')
        # Step 1: get the list of all fields
        optionNames = {}
        for modelElement in instanceDocument.findall('//*', ns):
            # Put all the model fields in optionNames[path] = optionName
            modelElementPath = instanceDocument.getelementpath(modelElement)
            optionNames[modelElementPath] = etree.QName(modelElement).localname

        print('D')
        tempfiles = []
        tempdirs = []
        try:
            commandLine = [commandName]
            default = None
            pipeIn = None
            # Step 2: generate most of the command-line, leaving a placeholder for the fields that use the default behaviour
            print('E')
            def formatTemplateElement(isInput, style, key, type, value, tempdirs, tempfiles):
                print('K3X')
                # Convert to the type expected by the tool
                if type.type == 'App::PropertyLink' and type.maybeMIMEType == 'image/svg+xml':
                    print('K31')
                    import tempfile, os
                    d = tempfile.mkdtemp()
                    tempdirs += [d]
                    svgfile = os.path.join(d, "sketch.svg")
                    tempfiles += [svgfile]
                    print("exportSVG", repr(value), repr(svgfile))
                    exportSVG(value, svgfile)
                    value = svgfile
                else:
                    print('K32')
                    # TODO ################# convert the value from FreeCAD to what the program supports ###################
                    value = str(value)

                if style == 'value':
                    if isInput:
                        return [value]
                    else:
                        pass # TODO: e.g. ['temporary_output_file']
                elif style == 'double-dash':
                    if isInput:
                        return ['--' + key, value]
                    else:
                        pass # TODO: e.g. ['-o', 'temporary_output_file']
                elif style == 'pipe':
                    if isInput:
                        if pipeIn is not None:
                            raise ValueError('Only one parameter can be passed as a pipe')
                        pipeIn = value
                    else:
                        pass # TODO: output
                    return []
                elif style == 'exitcode':
                    if isInput:
                        raise ValueError('the exitcode style can only be used for the output direction')
                    else:
                        pass # TODO: output
                else:
                    raise ValueError('Unsupported argument-passing or value-returning style')
            print('F')
            for templateElement in command.findall('./*', ns):
                print('G')
                direction = templateElement.attrib['direction']
                style     = templateElement.attrib['style']
                tag       = templateElement.tag

                print('H')
                tagPrefix = '{'+ns['XternalApps']+'}'
                if not tag.startswith(tagPrefix):
                    continue
                tag = tag[len(tagPrefix):]

                print('I')
                if direction == 'input':
                    isInput = True
                elif direction == 'output':
                    isInput = False
                else:
                    raise ValueError('Invalid value for direction attribute')

                print('J')
                if tag == 'constant':
                    print('K1')
                    if isInput:
                        key = templateElement.attrib.get('key', None)
                        type = typeToFreeCADTypeDict['xsd:string']
                        value = templateElement.attrib['value']
                        commandLine += formatTemplateElement(isInput, style, key, type, value, tempdirs, tempfiles)
                    else:
                        raise ValueError('constant elements of a command-line input can only be part of the input, not of the output')
                elif tag == 'default':
                    print('K2')
                    if isInput:
                        if default is not None:
                            raise ValueError('Only one default tag can be specified for a given direction')
                        default = {'style':style, 'position':len(commandLine)}
                    else:
                        pass # TODO: output
                elif tag == 'exception':
                    print('K3')
                    ref = templateElement.attrib['ref']
                    found = False
                    if isInput:
                        for modelElement in instanceDocument.findall(ref, templateElement.nsmap):
                            found = True
                            modelElementPath = instanceDocument.getelementpath(modelElement)
                            key   = optionNames[modelElementPath]
                            value = self.ModelInstance[modelElementPath]
                            type  = self.types[modelElementPath]
                            commandLine += formatTemplateElement(isInput, style, key, type, value, tempdirs, tempfiles)
                            if modelElementPath in optionNames:
                                del(optionNames[modelElementPath])
                            else:
                                raise ValueError('In command-line template, the same field is referenced by two tags (e.g. exception and ignore)')
                    else:
                        found = True
                        # TODO: output
                        pass
                    if not found:
                        raise ValueError('Could not resolve reference in command-line template: ' + safeErr(ref))
                elif tag == 'ignore':
                    print('K4')
                    ref = templateElement.attrib['ref']
                    found = False
                    if isInput:
                        for modelElement in instanceDocument.findall(ref, templateElement.nsmap):
                            found = True
                            modelElementPath = instanceDocument.getelementpath(modelElement)
                            if modelElementPath in optionNames:
                                del(optionNames[modelElementPath])
                            else:
                                raise ValueError('In command-line template, the same field is referenced by two tags (e.g. exception and ignore)')
                    else:
                        found = True
                        # TODO: output
                        pass
                    if not found:
                        raise ValueError('Could not resolve reference in command-line template')
                else:
                    print('K5')
                    raise ValueError('Unexpected tag in command-line template:' + safeErr(tag)) 
            
            # Step 3: replace the placeholder with the remaining input fields
            print('L')
            commandLineDefault = []
            for modelElementPath, key in optionNames.items():
                value = self.ModelInstance[modelElementPath]
                type  = self.types[modelElementPath]
                if default is None:
                    raise ValueError('Some fields are not included in the command-line template, and no default is present. To ignore a field, use the ignore tag.')
                style = default['style']
                commandLineDefault += formatTemplateElement(True, style, key, type, value, tempdirs, tempfiles)
            if default is not None:
                position = default['position']
                commandLine[position:position] = commandLineDefault
            
            # Step 4: call the command
            #for modelElementPath, value in self.ModelInstance.items():
            #    style = styles[modelElementPath]
            #    type = self.types[modelElementPath]
            
            pipeInHandle = None
            if pipeIn is not None:
                pipeInHandle = open(pipeIn)

            # TODO: use the XML for this
            import tempfile, os
            d = tempfile.mkdtemp()
            resultFilename = os.path.join(d, "result.svg")
            pipeOut = resultFilename
            tempfiles += [pipeOut]
            tempdirs += [d]
            pipeOutHandle = open(pipeOut, 'w')

            import subprocess
            #print(commandLine + ['stdin=' + str(pipeIn), 'stdout=' + str(pipeOut)])
            proc = subprocess.Popen(commandLine, stdin=pipeInHandle, stdout=pipeOutHandle)
            proc.communicate()
            exitcode = proc.returncode

            if pipeInHandle is not None:
                pipeInHandle.close()
            with open(resultFilename, 'rb') as resultFile:
                result = resultFile.read()
            pipeOutHandle.close()

            # Circumvent bug which leaves App.ActiveDocument to an incorrect value after the newDocument + closeDocument
            oldActiveDocumentName = App.ActiveDocument.Name
            tempDocument = App.newDocument('load_svg', hidden=True)
            import importSVG
            importSVG.insert(pipeOut,'load_svg')
            solids = []
            for o in tempDocument.Objects:
                shape = o.Shape
                wire = Part.Wire(shape.Edges)
                #face = Part.Face(wire)
                solids += [wire] #face
            p = Part.makeCompound(solids)
            for o in tempDocument.Objects:
                print("remove:" + o.Name)
                tempDocument.removeObject(o.Name)
            Part.show(p)
            print("===============================================================")
            for o in tempDocument.Objects:
                #o2 = document.copyObject(o, False, False)
                #print(o2.Name)
                obj.Shape = o.Shape
                obj.ViewObject.DisplayMode = o.ViewObject.DisplayMode
                break
                #document.removeObject(o2.Name)
            print("===============================================================!!")
            App.closeDocument('load_svg')
            App.setActiveDocument(oldActiveDocumentName)
        finally:
            pass
            #for tempfile in tempfiles:
            #    try:
            #        os.remove(tempfile)
            #    except:
            #        pass
            #for tempdir in tempdirs:
            #    try:
            #        os.rmdir(tempdir)
            #    except:
            #        pass

        print(exitcode, result)

    def execute(self, obj):
        print("""This is called when the object is recomputed""")
        self.xmlCommandToPython(obj, obj.Document)
