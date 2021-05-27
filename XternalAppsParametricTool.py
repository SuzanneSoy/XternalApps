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

FreeCADType = namedtuple('FreeCADType', ['type', 'defaultForType', 'maybeEnumValues', 'maybeMIMEType'])

XFormsInput = namedtuple('XFormsInput', ['modelElementPath', 'label', 'simpleName', 'maybeEnum', 'groupName', 'relevance']) #'type', 'input', 'InputValueToModelValue', 'ModelValueToInputValue'
XFormsEnum = namedtuple('XFormsEnum', ['labels', 'values'])
InterpretedXML = namedtuple('InterpretedXML', ['xml', 'types', 'inputs']) # Parsed XML, dictionary(modelElementPath) -> type, dictionary(formElementPath) -> XFormsInput

def CreateCommand(appName, toolName):
    App.ActiveDocument.openTransaction('Create parametric %s from %s'%(toolName, appName))
    FreeCADGui.addModule("XternalAppsParametricTool")
    FreeCADGui.doCommand("XternalAppsParametricTool.create(%s, %s)"%(repr(appName), repr(toolName)))
    App.ActiveDocument.commitTransaction()

def create(appName, toolName):
    sel = FreeCADGui.Selection.getSelection()
    name = appName + toolName
    obj = App.ActiveDocument.addObject("App::DocumentObjectGroupPython", name)
    XternalAppsParametricTool(obj, appName, toolName, sel)
    return obj

# TODO: read-only/immutable
typeToFreeCADTypeDict = {
    # TODO:do an XML namespace lookup instead of comparing a constant.
    'xsd:decimal': FreeCADType(type='App::PropertyFloat', defaultForType=0.0, maybeEnumValues=None, maybeMIMEType=None),
    'xsd:string': FreeCADType(type='App::PropertyString', defaultForType='', maybeEnumValues=None, maybeMIMEType=None),
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
        return FreeCADType(type = 'App::PropertyEnumeration', defaultForType = (enumValues[0] if len(enumValues) > 0 else None), maybeEnumValues = enumValues, maybeMIMEType=None)
    elif schemaType.tag == "{http://www.w3.org/2001/XMLSchema}complexType":
        return ValueError("Complex XML chema types are not supported")
    
def MIMETypeToFreeCADType(MIMEType):
    if MIMEType == 'image/svg+xml':
        return FreeCADType(type='App::PropertyLink', defaultForType=None, maybeEnumValues=None, maybeMIMEType = MIMEType)
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


class XternalAppsParametricTool():
    def __init__(self, obj, appName, toolName, sel=[]):
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

        self.oldExpressionEngine = obj.ExpressionEngine

        self.MonitorChanges = True

        #pprint.pprint(self.types)
        #pprint.pprint(self.form)

        # Special treatment for the "primary" form field
        primary = [input for input in self.form.values() if input.relevance == 'primary']
        if len(primary) == 1:
            primary = primary[0]
            type = self.types[primary.modelElementPath].type

            # Display the contents of the primary form element as children in the tree view
            if type in ['App::PropertyLink', 'App::PropertyLinkList']:
                self.form['FreeCADGroup'] = XFormsInput(modelElementPath=primary.modelElementPath, label='Group', simpleName='Group', maybeEnum=primary.maybeEnum, groupName='Base', relevance='primary')

            if type == 'App::PropertyLink' and len(sel) >= 1:
                setattr(obj, primary.simpleName, sel[0])
            elif type == 'App::PropertyLinkList':
                setattr(obj, primary.simpleName, sel)

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
            finally:
                #print('MonitorChanges = ' + str(restoreMonitorChanges))
                self.MonitorChanges = restoreMonitorChanges

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
            defaults[path] = default
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
            setattr(obj, simpleName, default)

    @property
    def Tool(self):
        return XternalAppsList.apps[self.AppName].Tools[self.ToolName]

    def xmlCommandToPython(self, document):
        """Parse the .xml document, and return
        a pair of dictionaries accepts[model_path] = style and returns[model_path] = style."""

        xml = etree.parse(self.Tool.XForms, parser=parser)

        model_root = xml.find('./xforms:model', ns)
        instanceDocument = etree.ElementTree(model_root.find('./xforms:instance/*', ns))

        command = xml.find('./XternalApps:command', ns)
        method = command.attrib['method']
        commandName = command.attrib['name']

        accepts = command.find('./XternalApps:accepts', ns)
        returns = command.find('./XternalApps:returns', ns)

        maybeDefault = accepts.findall('./XternalApps:default', ns)
        if len(maybeDefault) == 1:
            default_style = maybeDefault[0].attrib['style']
        elif len(maybeDefault) > 1:
            raise ValueError('The accepts tag should contain at most one default tag')
        else:
            default_style = None
        
        styles = {}
        optionNames = {}
        # Put all the model fields in accepts[path]
        for modelElement in instanceDocument.findall('//*', ns):
            path = instanceDocument.getelementpath(modelElement)
            styles[path] = default_style
            optionNames[path] = etree.QName(modelElement).localname
        
        style_is_default = {k: True for k in styles.keys()}
        for exception in accepts.findall('./XternalApps:exception', ns):
            ref = exception.attrib['ref']
            style = exception.attrib['style']
            for modelElement in instanceDocument.findall(ref, exception.nsmap):
                path = instanceDocument.getelementpath(modelElement)
                if style_is_default[path]:
                    style_is_default[path] = False
                    styles[path] = style
                else:
                    ValueError('overlapping exceptions in command/accepts/exception')
        
        pipe_in = None
        positionalArguments = {}
        namedArguments = []
        tempfiles = []
        tempdirs = []
        for modelElementPath, value in self.ModelInstance.items():
            style = styles[modelElementPath]
            type = self.types[modelElementPath]
            
            # Convert to the type expected by the tool
            if type.type == 'App::PropertyLink' and type.maybeMIMEType == 'image/svg+xml':
                import tempfile, os
                d = tempfile.mkdtemp()
                svgfile = os.path.join(d, "sketch.svg")
                tempfiles += [svgfile]
                tempdirs += [d]
                exportSVG(value, svgfile)
                value = svgfile
            else:
                # TODO ################# convert the value from FreeCAD to what the program supports ###################
                value = str(value)

            if style == 'double-dash':
                namedArguments += ['--' + optionNames[modelElementPath], value]
            elif style == 'pipe':
                if pipe_in != None:
                    raise ValueError('more then one option uses a "pipe" style')
                pipe_in = value
            elif style == 'positional':
                pos = unknown_todo() ######################################### TODO ############################
                positionalArguments[pos] = value
            elif style == 'exitcode':
                raise ValueError('exitcode is supported only for the output of the command, not for its input')
            else:
                raise ValueError('unsupported argument-passing style')
        
        positionalArguments = [v for i, vs in sorted(positionalArguments.items()) for v in vs]
        if pipe_in is not None:
            pipe_in_handle = open(pipe_in)

        # TODO: use the XML for this
        d = tempfile.mkdtemp()
        result_filename = os.path.join(d, "result.svg")
        pipe_out = result_filename
        tempfiles += [pipe_out]
        tempdirs += [d]
        pipe_out_handle = open(pipe_out, 'w')

        import subprocess
        print([commandName] + positionalArguments + namedArguments + ['stdin=' + pipe_in, 'stdout=' + pipe_out])
        proc = subprocess.Popen([commandName] + positionalArguments + namedArguments, stdin=pipe_in_handle, stdout=pipe_out_handle)
        proc.communicate()
        exitcode = proc.returncode

        pipe_in_handle.close()
        with open(result_filename, 'rb') as result_file:
            result = result_file.read()
        pipe_out_handle.close()

        # Circumvent bug which leaves App.ActiveDocument to an incorrect value after the newDocument + closeDocument
        oldActiveDocumentName = App.ActiveDocument.Name
        tempDocument = App.newDocument('load_svg', hidden=True)
        import importSVG
        importSVG.insert(pipe_out,'load_svg')
        solids = []
        for o in tempDocument.Objects:
            shape = o.Shape
            wire = Part.Wire(shape.Edges)
            #face = Part.Face(wire)
            solids += [wire] #face
        p = Part.makeCompound(solids)
        for obj in tempDocument.Objects:
            print("remove:" + obj.Name)
            tempDocument.removeObject(obj.Name)
        Part.show(p)
        for o in tempDocument.Objects:
            o2 = document.copyObject(o, False, False)
        App.closeDocument('load_svg')
        App.setActiveDocument(oldActiveDocumentName)

        for tempfile in tempfiles:
            os.remove(tempfile)
        for tempdir in tempdirs:
            os.rmdir(tempdir)

        print(exitcode, result)

    def execute(self, obj):
        print("""This is called when the object is recomputed""")
        self.xmlCommandToPython(obj.Document)

    #<XternalApps:accepts>
    #  <XternalApps:default ref=".//*" style="double-dash">
    #  <XternalApps:exception ref="my:svgfile" style="pipe" />
    #</XternalApps:accepts>

    #<XternalApps:returns>
    #  <XternalApps:exception ref="my:output-svgfile" style="pipe" />
    #  <XternalApps:exception ref="my:output-exitcode" style="exitcode" />
    #</XternalApps:returns>


