# -*- coding: utf-8 -*-
#
# (C) Copyright 2018 InovaDevelopment.com
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Karl  Schopmeyer <inovadevelopment.com>
#

"""
Test of pywbem_mock package.  This tests the implementation of pywbem_mock
using a set of local mock qualifiers, classes, and instances.

"""
from __future__ import absolute_import, print_function

import os
import shutil
import re
from datetime import datetime
try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict  # pylint: disable=import-error
import six
import pytest
from testfixtures import OutputCapture

from ...utils import skip_if_moftab_regenerated
from ..utils.dmtf_mof_schema_def import TOTAL_QUALIFIERS, TOTAL_CLASSES, \
    install_test_dmtf_schema, DMTF_TEST_SCHEMA_VER

# pylint: disable=wrong-import-position, wrong-import-order, invalid-name
from ...utils import import_installed
pywbem = import_installed('pywbem')
from pywbem import CIMClass, CIMProperty, CIMInstance, CIMMethod, \
    CIMParameter, Uint32, MOFCompileError, MOFRepositoryError, \
    CIMInstanceName, CIMClassName, CIMQualifier, CIMQualifierDeclaration, \
    CIMError, DEFAULT_NAMESPACE, CIM_ERR_INVALID_CLASS, \
    CIM_ERR_INVALID_NAMESPACE, CIM_ERR_NOT_FOUND, CIM_ERR_INVALID_PARAMETER, \
    CIM_ERR_ALREADY_EXISTS, CIM_ERR_INVALID_ENUMERATION_CONTEXT, \
    CIM_ERR_NAMESPACE_NOT_EMPTY, CIM_ERR_INVALID_SUPERCLASS, \
    CIM_ERR_NOT_SUPPORTED, CIM_ERR_METHOD_NOT_AVAILABLE  # noqa: E402
from pywbem._nocasedict import NocaseDict  # noqa: E402
from pywbem._utils import _format  # noqa: E402
from pywbem._cim_operations import pull_path_result_tuple  # noqa: E402
pywbem_mock = import_installed('pywbem_mock')
from pywbem_mock import FakedWBEMConnection, DMTFCIMSchema, \
    InstanceWriteProvider, MethodProvider  # noqa: E402
# pylint: enable=wrong-import-position, wrong-import-order, invalid-name


VERBOSE = False

# test variables to allow selectively executing tests.
OK = True
RUN = True
FAIL = False


# location of testsuite/schema dir used by all tests as test DMTF CIM Schema
# This directory is permanent and should not be removed.
TEST_DIR = os.path.dirname(__file__)

# Location of DMTF schema directory used by all tests.
# This directory is permanent and should not be removed.
TESTSUITE_SCHEMA_DIR = os.path.join('tests', 'schema')

# List of initially existing namespaces in the mock repository
INITIAL_NAMESPACES = [DEFAULT_NAMESPACE]


# Expand the set of namespaces to include one that is not the default
# namespace.  This should be used with the methods to add NOT_DEFAULT_NS
# to the mock before compiling into the mock or adding cim objects.
# There are methods to accomplish this.
NOT_DEFAULT_NS = 'root/notdefaultns'
EXPANDED_NAMESPACES = [DEFAULT_NAMESPACE, NOT_DEFAULT_NS]


# Temporarily set this because all of the fixtures generate this warning
# for every use.  One alternative may be to prefix each fixture name with
# an underscore
# pylint: disable=redefined-outer-name


def model_path(inst_path):
    """
    Create just the model path for a CIMInstanceName. That is the CIMInstance
    Name with host and namespace removed.
    """
    model_path = inst_path.copy()
    model_path.host = None
    model_path.namespace = None
    return(model_path)


def equal_model_path(p1, p2):
    """
    Compare the model path component of CIMInstanceNames for equality. The model
    path is the classname and keybindings components of CIMInstanceName

    Return True if equal, otherwise return False
    """
    if p1.keybindings == p2.keybindings \
            and p1.classname.lower() == p2.classname.lower():
        return True
    if p1.classname.lower() != p2.classname.lower():
        print(_format('ModelPathCompare. classnames %s and %s not equal.',
                      p1.classname, p2.classname))
    else:
        print(_format('ModelPathCompare. keybinding difference:\np1:\n%s'
                      '\np2\n%s', p1.keybindings, p2.keybindings))
    return False


def fix_instname_namespace_keys(inst_name, ns):
    """
    Set the namespace component of any keys  in the instance
    to the value defined by ns.  This is used to fix the keybindings in
    association CIMInstanceNames to match the repository which includes the
    namespace as part of the keys.
    """
    assert isinstance(inst_name, CIMInstanceName)
    inst_name = inst_name.copy()  # copy so we do not change original
    # iterate through the keybindings for any that are CIMInstanceName
    # If the namespace component is None, modify to the value of ns
    for value in six.itervalues(inst_name.keybindings):
        if isinstance(value, CIMInstanceName):
            if value.namespace is None:
                value.namespace = ns
    return inst_name


def assert_equal_ciminstancenames(l1, l2, model=False):
    """
    Assert if the two iterables of CIMInstanceNames are not equal except
    for order
    """
    def set_model_path(cin):
        """Return model path component of CIMInstanceName"""
        assert isinstance(cin, CIMInstanceName)
        mp = cin.copy()
        mp.host = None
        mp.namespace = None
        return mp

    if model:
        l1 = [set_model_path(cin) for cin in l1]
        l2 = [set_model_path(cin) for cin in l2]

    assert set(l1) == set(l2)


def assert_equal_ciminstances(l1, l2):
    """
    Test if instances in two iterables equal. For now just test paths
    """

    def _rtn_paths(insts):
        """Return the list of paths of a list of instances"""
        return [inst.path for inst in insts]

    assert_equal_ciminstancenames(_rtn_paths(l1), _rtn_paths(l2))


def objs_equal(objdict1, objdict2, obj_type, parent_obj_name):
    """
    Equality test and display for objects that are a part of a class or
    instance, i.e. methods, properties, parameters and qualifiers

    Returns True  if equal  or False if not equal

    """
    if objdict1 == objdict2:
        return True

    print('Mismatch: Obj type=%s parent name %s' % (obj_type, parent_obj_name))

    if len(objdict1) != len(objdict2):
        print('Number of %s(s):%s differ\n  p1(len=%s)=%s\n  p2(len=%s)=%s' %
              (obj_type, parent_obj_name,
               len(objdict1), sorted(objdict1.keys()),
               len(objdict2), sorted(objdict2.keys())))
        return False

    for name, value in objdict1.items():
        if name not in objdict2:
            print('%s:%s %s in %s not in %s' % (obj_type, parent_obj_name,
                                                name,
                                                objdict1.keys().sort(),
                                                objdict2.keys().sort()))

        if value != objdict2[name]:
            print('%s:%s mismatch \np1=%r\np2=%r' %
                  (obj_type, parent_obj_name, value, objdict2[name]), )
        if getattr(value, "qualifiers", None):
            objs_equal(value.qualifiers, objdict2[name].qualifiers,
                       'qualifiers', parent_obj_name + ':' + name)
        if getattr(value, "parameters", None):
            objs_equal(value.parameters, objdict2[name].parameters,
                       'parameter', parent_obj_name + ':' + name)

    return False


def insts_equal(inst1, inst2):
    """
    Compare the properties, qualifiers and model paths of two instances
    for equality.

    Returns True if equal or False if not equal
    """
    if equal_model_path(inst1.path, inst2.path) and \
            inst1.classname == inst2.classname and \
            inst1.qualifiers == inst2.qualifiers and \
            inst1.properties == inst2.properties:
        return True

    if inst1.properties != inst2.properties:
        if len(inst1.properties) != len(inst2.properties):
            print('Number of properties differ p1(%s)=%s, p2(%s)=%s' %
                  (len(inst1.properties), inst1.properties.keys(),
                   len(inst2.properties), inst2.properties.keys()))
        else:
            for prop1, pvalue1 in inst1.properties.items():
                if pvalue1 != inst2.properties[prop1]:
                    print('Inst mismatch property \np1=%r\np2=%r' %
                          (inst1.properties[prop1], inst2.properties[prop1]))

    objs_equal(inst1.qualifiers, inst2.qualifiers, 'qualifiers',
               'instance  %s' % inst1.classname)

    return False


def classes_equal(cls1, cls2):
    """
    Detailed test of classes for equality. Displays component found not
    equal.

    Returns True if equal, else False
    """

    if cls1 == cls2:
        return True
    if cls1.classname != cls2.classname:
        print("Classname mismatch %s != %s" % (cls1.classname, cls2.classname))
        return False
    if cls1.superclass and cls1.superclass != cls2.superclass:
        print("Class %s superclass mismatch %s != %s" % (cls1. classname,
                                                         cls1.superclass,
                                                         cls2.superclass))
        return False

    objs_equal(cls1.qualifiers, cls2.qualifiers, 'qualifier', cls1.classname)

    objs_equal(cls1.properties, cls2.properties, 'Property', cls1.classname)

    objs_equal(cls1.methods, cls2.methods, 'Method', cls1.classname)

    return False


def assert_classes_equal(cls1, cls2):
    """
    Test for classes equal and assert. Rather than just use == this code
    tests the components and displays info on the differences if the classes
    are not equal.  This is useful because just outputing the repl for a
    class generates data that is difficult to debug.
    """
    classes_equal(cls1, cls2)
    assert cls1 == cls2

###################################################################
#
#  Fixtures for testing pywbem_mock
#
###################################################################


@ pytest.fixture
def tst_qualifiers():
    """
    CIM_Qualifierdecl definition of qualifiers used by tst_classes
    """
    scopesp = NocaseDict([
        ('CLASS', False),
        ('ASSOCIATION', False),
        ('INDICATION', False),
        ('PROPERTY', True),
        ('REFERENCE', True),
        ('METHOD', False),
        ('PARAMETER', False),
        ('ANY', False),
    ])
    scopesd = NocaseDict([
        ('CLASS', True),
        ('ASSOCIATION', True),
        ('INDICATION', True),
        ('PROPERTY', True),
        ('REFERENCE', True),
        ('METHOD', True),
        ('PARAMETER', True),
        ('ANY', True),
    ])
    q1 = CIMQualifierDeclaration('Key', 'boolean', is_array=False,
                                 scopes=scopesp,
                                 overridable=False, tosubclass=True,
                                 toinstance=False, translatable=None)
    q2 = CIMQualifierDeclaration('Description', 'string', is_array=False,
                                 scopes=scopesd,
                                 overridable=True, tosubclass=True,
                                 toinstance=False, translatable=None)
    return [q1, q2]


@pytest.fixture
def tst_class():
    """
    Builds and returns a single class: CIM_Foo that to be used as a
    test class for the mock class tests.
    This assumes that add_cimobjects resolves classes. so things line
    scoping, etc. on qualifiers and class origin are not included
    """
    kkey = {'Key': CIMQualifier('Key', True)}
    dkey = {'Description': CIMQualifier('Description', 'CIM_Foo description')}
    qkey = {'Description': CIMQualifier('Description', 'qualifier description')}

    c = CIMClass(
        'CIM_Foo', qualifiers=dkey,
        properties={'InstanceID':
                    CIMProperty('InstanceID', None, qualifiers=kkey,
                                type='string')},
        methods={'Delete': CIMMethod('Delete', 'uint32', qualifiers=qkey),
                 'Fuzzy': CIMMethod('Fuzzy', 'string', qualifiers=qkey)})
    return c


@pytest.fixture
def tst_classwqualifiers(tst_qualifiers, tst_class):
    """
    Returns the tst class CIM_Foo with its qualifierdeclarations.
    """
    return tst_qualifiers + [tst_class]


@pytest.fixture
def tst_classes(tst_class):
    """
    Builds and returns a list of 5 classes
        CIM_Foo - top level in hierarchy
        CIM_Foo_sub - Subclass to CIMFoo
        CIM_Foo_sub2 - Subclass to CIMFoo
        CIM_Foo_sub_sub - Subclass to CIMFoo_sub
        CIM_Foo_nokey - top level in hierarchy
    This assumes that add_cimobjects resolves classes. so things line
    scoping, etc. on qualifiers and class origin are not included
    """
    ckey = {'Description': CIMQualifier('Description', 'Subclass Description')}
    pkey = {'Description': CIMQualifier('Description', 'property description')}
    qkey = {'Description': CIMQualifier('Description', 'qualifier description')}

    c2 = CIMClass(
        'CIM_Foo_sub', superclass='CIM_Foo', qualifiers=ckey,
        properties={'cimfoo_sub':
                    CIMProperty('cimfoo_sub', None, type='string',
                                qualifiers=qkey)})

    c3 = CIMClass(
        'CIM_Foo_sub2', superclass='CIM_Foo', qualifiers=ckey,
        properties={'cimfoo_sub2':
                    CIMProperty('cimfoo_sub2', None, type='string',
                                qualifiers=pkey)})

    c4 = CIMClass(
        'CIM_Foo_sub_sub', superclass='CIM_Foo_sub', qualifiers=ckey,
        properties={'cimfoo_sub_sub':
                    CIMProperty('cimfoo_sub_sub', None, type='string',
                                qualifiers=pkey)})

    c5 = CIMClass(
        'CIM_Foo_nokey', qualifiers=ckey,
        properties=[
            CIMProperty('InstanceID', None, qualifiers=qkey, type='string'),
            CIMProperty('cimfoo', None, qualifiers=qkey, type='string',),
        ])

    return [tst_class, c2, c3, c4, c5]


@pytest.fixture
def tst_classeswqualifiers(tst_qualifiers, tst_classes):
    """
    Append the test qualifiers to the test classes and return both
    """
    return tst_qualifiers + tst_classes


@pytest.fixture
def tst_pg_namespace_class():
    """
    Builds and returns a PG_Namespace class.
    """
    qkey = CIMQualifier('Key', True, overridable=False, tosubclass=True)
    c = CIMClass(
        'PG_Namespace', superclass=None,
        properties=[
            CIMProperty('Name', None, type='string',
                        qualifiers=[qkey]),
            CIMProperty('CreationClassName', None, type='string',
                        qualifiers=[qkey]),
            CIMProperty('ObjectManagerName', None, type='string',
                        qualifiers=[qkey]),
            CIMProperty('ObjectManagerCreationClassName', None, type='string',
                        qualifiers=[qkey]),
            CIMProperty('SystemName', None, type='string',
                        qualifiers=[qkey]),
            CIMProperty('SystemCreationClassName', None, type='string',
                        qualifiers=[qkey]),
        ]
    )
    return c


def build_cimfoo_instance(id_):
    """
    Build a single instance of an instance of CIM_Foo where id is
    used to create the unique identity. The input parameter id_ is used
    to create the value for the key property InstanceID.
    """
    iname = 'CIM_Foo%s' % id_
    return CIMInstance('CIM_Foo',
                       properties={'InstanceID': iname},
                       path=CIMInstanceName('CIM_Foo', {'InstanceID': iname}))


def build_cimfoosub_instance(id_):
    """
    Build a single instance of an instance of CIM_Foo where id is
    used to create the unique identity.
    """
    inst_id = 'CIM_Foo_sub%s' % id_
    inst = CIMInstance('CIM_Foo_sub',
                       properties={
                           'InstanceID': inst_id,
                           'cimfoo_sub': 'cimfoo_sub prop  for %s' % inst_id},
                       path=CIMInstanceName('CIM_Foo_sub',
                                            {'InstanceID': inst_id}))
    return inst


def build_cimfoosub2_instance(id_):
    """
    Build a single instance of an instance of CIM_Foo_sub2 where id is
    used to create the unique identity.
    """
    inst_id = 'CIM_Foo_sub2%s' % id_
    inst = CIMInstance('CIM_Foo_sub2',
                       properties={
                           'InstanceID': inst_id,
                           'cimfoo_sub2': 'cimfoo_sub2 prop for %s' % inst_id},
                       path=CIMInstanceName('CIM_Foo_sub2',
                                            {'InstanceID': inst_id}))
    return inst


def build_cimfoosub_sub_instance(id_):
    """
    Build a single instance of an instance of CIM_Foo_sub2 where id is
    used to create the unique identity.
    """
    inst_id = 'CIM_Foo_sub_sub%s' % id_
    inst = CIMInstance('CIM_Foo_sub_sub',
                       properties={
                           'InstanceID': inst_id,
                           'cimfoo_sub': 'cimfoo_sub prop:  %s' % inst_id,
                           'cimfoo_sub_sub': 'cimfoo_sub_sub: %s' % inst_id},
                       path=CIMInstanceName('CIM_Foo_sub_sub',
                                            {'InstanceID': inst_id}))
    return inst


def build_cimfoo_nokey_instance():
    """
    Build a single instance of an instance of CIM_Foo_nokey.
    """
    return CIMInstance('CIM_Foo_nokey',
                       properties={'cimfoo': 'none'},
                       path=CIMInstanceName('CIM_Foo_nokey'))


@pytest.fixture
def tst_instances():
    """
    Build instances of CIM_foo and 2 instances of CIM_Foo_sub and
    return them
    """
    rtn = []

    for i in six.moves.range(1, 3):
        rtn.append(build_cimfoo_instance(i))
    for i in six.moves.range(4, 6):
        rtn.append(build_cimfoosub_instance(i))
    for i in six.moves.range(7, 9):
        rtn.append(build_cimfoosub2_instance(i))
    for i in six.moves.range(10, 12):
        rtn.append(build_cimfoosub_sub_instance(i))
    rtn.append(build_cimfoo_nokey_instance())
    return rtn


@pytest.fixture
def tst_classeswqualifiersandinsts(tst_classeswqualifiers, tst_instances):
    """
    Append tst_instances to tst_classeswqualifiers. This builds a simple
    package of qualifiers, classes and instances that can be added to
    repository.
    """
    return tst_classeswqualifiers + tst_instances


@pytest.fixture
def tst_insts_big():
    """
    Create Instances of cimfoo for the ide 3 to what is in list_size.  This
    does not include instances that were created in the tst_instances
    fixture.
    """
    list_size = 100
    big_list = []

    for i in six.moves.range(3, list_size + 1):
        big_list.append(build_cimfoo_instance(i))
    return big_list


@pytest.fixture
def tst_classes_mof(tst_qualifiers_mof):
    """
    Test classes to be compiled as part of tests. This is the same
    classes as the tst_classes fixture. This merges the tst_compile_qualifiers
    str and the classes string into a single string and returns it.
    The qualifiers are merged because they are required to resolve classes
    within the repository.
    """

    cl_str = """
             [Description ("blah blah")]
        class CIM_Foo {
                [Key, Description ("This is key prop")]
            string InstanceID;

                [Description ("This is a method with in and out parameters")]
            uint32 Fuzzy(
                [IN, Description("FuzzyMethod Param")]
              string FuzzyParameter,

                [IN, OUT, Description ( "Test of ref in/out parameter")]
              CIM_Foo REF Foo,

                [IN ( false ), OUT, Description("TestMethod Param")]
              string OutputParam);

                [ Description("Method with no Parameters") ]
            uint32 DeleteNothing();
        };

            [Description ("Subclass of CIM_Foo")]
        class CIM_Foo_sub : CIM_Foo {
            string cimfoo_sub;
        };

        class CIM_Foo_sub2 : CIM_Foo {
            string cimfoo_sub2;
        };

        class CIM_Foo_sub_sub : CIM_Foo_sub {
            string cimfoo_sub_sub;
                [Description("Sample method with input and output parameters")]
            uint32 Method1(
                [IN, Description("Input Param1")]
              string InputParam1,
                [IN, Description("Input Param2")]
              string InputParam2,
                [IN ( false), OUT, Description("Response param 1")]
              string OutputParam1,
                [IN ( false), OUT, Description("Response param 2")]
              string OutputParam2);
            uint32 Method2(
                [IN, Description("Input Param1")]
              Uint32 InputParam1,
                [IN, Description("Input Param2")]
              string InputParam2,
                [IN, Description("Generate Exception if this exists")]
              string TestCIMErrorException,
                [IN ( false), OUT, Description("Response param 1")]
              string OutputParam1,
                [IN ( false), OUT, Description("Response param 2")]
              Uint64 OutputParam2[]);
        };

             [Description ("blah blah")]
        class CIM_Foo_nokey {
                [Key, Description ("This is key prop")]
            string InstanceID;

            string cimfoo;
        };
    """
    return tst_qualifiers_mof + '\n\n' + cl_str + '\n\n'


@pytest.fixture
def tst_instances_mof(tst_classes_mof):
    """
    Adds the same instances as defined in tst_instances to
    test_classes_mof
    """
    inst_str = """
        instance of CIM_Foo as $foo1 { InstanceID = "CIM_Foo1"; };
        instance of CIM_Foo as $foo2 { InstanceID = "CIM_Foo2"; };
        instance of CIM_Foo_sub as $foosub4 { InstanceID = "CIM_Foo_sub4";
                                              cimfoo_sub = "data sub 4";};
        instance of CIM_Foo_sub as $foosub5 { InstanceID = "CIM_Foo_sub5";
                                              cimfoo_sub = "data sub5";};
        instance of CIM_Foo_sub2 as $foosub21 { InstanceID = "CIM_Foo_sub21";
                                                cimfoo_sub2 = "data sub 21";};
        instance of CIM_Foo_sub2 as $foosub22 { InstanceID = "CIM_Foo_sub22";
                                                cimfoo_sub2 = "data sub22";};

        instance of CIM_Foo_sub_sub as $foosub21 {
            InstanceID = "CIM_Foo_sub_sub21";
            cimfoo_sub = "data sub 10";
            cimfoo_sub_sub = "data sub 21";};
        instance of CIM_Foo_sub_sub as $foosub22 {
            InstanceID = "CIM_Foo_sub_sub22";
            cimfoo_sub = "data sub 11";
            cimfoo_sub_sub = "data sub_sub22";};
    """
    return tst_classes_mof + '\n\n' + inst_str + '\n\n'


@pytest.fixture
def tst_person_instance_names():
    """Defines the instance names for the instances in tst_assoc_mof below"""
    return ['Mike', 'Saara', 'Sofi', 'Gabi']


@pytest.fixture
def tst_assoc_qualdecl_mof():
    """
    Set of qualifier declarations used in definition of a set of
    classes to test associations
    """
    return """
        Qualifier Association : boolean = false,
            Scope(association),
            Flavor(DisableOverride, ToSubclass);

        Qualifier Description : string = null,
            Scope(any),
            Flavor(EnableOverride, ToSubclass, Translatable);

        Qualifier In : boolean = true,
            Scope(parameter),
            Flavor(DisableOverride, ToSubclass);

        Qualifier Key : boolean = false,
            Scope(property, reference),
            Flavor(DisableOverride, ToSubclass);

        Qualifier Out : boolean = false,
            Scope(parameter),
            Flavor(DisableOverride, ToSubclass);
    """


@pytest.fixture
def tst_assoc_class_mof():
    """
    Target, destination, and association classes used to define an
    association test model. This fixture assumes that qualifier declarations
    consistent with tst_assoc_qualdelc fixture above.
    """
    return """
        class TST_Person{
                [Key, Description ("This is key prop")]
            string name;
            string extraProperty = "defaultvalue";
        };

        class TST_Personsub : TST_Person{
            string secondProperty = "empty";
            uint32 counter;
        };

        [Association, Description(" Lineage defines the relationship "
            "between parents and children.") ]
        class TST_Lineage {
            [key] string InstanceID;
            TST_Person ref parent;
            TST_Person ref child;
        };

        [Association, Description(" Family gathers person to family.") ]
        class TST_MemberOfFamilyCollection {
           [key] TST_Person ref family;
           [key] TST_Person ref member;
        };

        [ Description("Collection of Persons into a Family") ]
        class TST_FamilyCollection {
                [Key, Description ("This is key prop and family name")]
            string name;
        };
    """


@pytest.fixture
def tst_assoc_mof(tst_assoc_qualdecl_mof, tst_assoc_class_mof):
    """
    Complete MOF definition of a simple set of classes and association class
    to test associations and references. Includes qualifiers, classes,
    and instances.
    """
    instances = """
        instance of TST_Person as $Mike { name = "Mike"; };
        instance of TST_Person as $Saara { name = "Saara"; };
        instance of TST_Person as $Sofi { name = "Sofi"; };
        instance of TST_Person as $Gabi{ name = "Gabi"; };

        instance of TST_PersonSub as $Mikesub{ name = "Mikesub";
                                    secondProperty = "one" ;
                                    counter = 1; };

        instance of TST_PersonSub as $Saarasub { name = "Saarasub";
                                    secondProperty = "two" ;
                                    counter = 2; };

        instance of TST_PersonSub as $Sofisub{ name = "Sofisub";
                                    secondProperty = "three" ;
                                    counter = 3; };

        instance of TST_PersonSub as $Gabisub{ name = "Gabisub";
                                    secondProperty = "four" ;
                                    counter = 4; };

        instance of TST_Lineage as $MikeSofi
        {
            InstanceID = "MikeSofi";
            parent = $Mike;
            child = $Sofi;
        };

        instance of TST_Lineage as $MikeGabi
        {
            InstanceID = "MikeGabi";
            parent = $Mike;
            child = $Gabi;
        };

        instance of TST_Lineage  as $SaaraSofi
        {
            InstanceID = "SaaraSofi";
            parent = $Saara;
            child = $Sofi;
        };

        instance of TST_FamilyCollection as $Family1
        {
            name = "family1";
        };

        instance of TST_FamilyCollection as $Family2
        {
            name = "Family2";
        };


        instance of TST_MemberOfFamilyCollection as $SofiMember
        {
            family = $Family1;
            member = $Sofi;
        };

        instance of TST_MemberOfFamilyCollection as $GabiMember
        {
            family = $Family1;
            member = $Gabi;
        };

        instance of TST_MemberOfFamilyCollection as $MikeMember
        {
            family = $Family2;
            member = $Mike;
        };
    """
    return tst_assoc_qualdecl_mof + tst_assoc_class_mof + instances


# Counts of instances for tests of tst_assoc_mof fixture.
TST_PERSON_INST_COUNT = 4                                 # num TST_PERSON
TST_PERSON_SUB_INST_COUNT = 4                             # num SUB
TST_PERSONWITH_SUB_INST_COUNT = TST_PERSON_INST_COUNT + \
    TST_PERSON_SUB_INST_COUNT                             # num both


def add_objects_to_repo(conn, namespace, objects_list):
    """
    Test setup.  Conditionally adds namespace to mock repository and adds
    the lists of objects to the repo.  Each object in the objects_list may
    be  list of CIM objects that will be added using self.add_cimObject
    or a string that is MOF that will be compiled.
    """
    if namespace and namespace != conn.default_namespace:
        conn.add_namespace(namespace)
    assert isinstance(objects_list, (list, tuple))

    for obj in objects_list:
        if isinstance(obj, six.string_types):
            conn.compile_mof_string(obj, namespace=namespace)
        else:
            conn.add_cimobjects(obj, namespace=namespace)


#########################################################################
#
#            Pytest Test Classes
#
#########################################################################


class TestFakedWBEMConnection(object):
    """
    Test the basic characteristics of the FakedWBEMConnection including
    init parameters.
    """

    @pytest.mark.parametrize(
        "set_on_init", [False, True])
    @pytest.mark.parametrize(
        "delay", [.5, 1])
    def test_response_delay(self, tst_qualifiers, tst_class, set_on_init,
                            delay):
        # pylint: disable=no-self-use
        """
        Test the response delay attribute set both in init parameter and with
        attribute.
        """

        # pylint: disable=protected-access
        FakedWBEMConnection._reset_logging_config()
        if set_on_init:
            conn = FakedWBEMConnection(response_delay=delay)
        else:
            conn = FakedWBEMConnection()
            conn.response_delay = delay

        assert conn.response_delay == delay
        conn.add_cimobjects(tst_qualifiers)
        conn.add_cimobjects(tst_class)

        start_time = datetime.now()
        conn.GetClass('CIM_Foo')
        exec_time = (datetime.now() - start_time).total_seconds()

        if delay:
            assert exec_time > delay * .8
            assert exec_time < delay * 2.5
        else:
            assert exec_time < 0.1

    @pytest.mark.parametrize(
        "set_on_init", [False, True])
    @pytest.mark.parametrize(
        "disable", [False, None, True])
    def test_disable_pull(self, tst_classeswqualifiers, tst_instances,
                          set_on_init, disable):
        # pylint: disable=no-self-use
        """
        Test the disable_pull_operations property set both in init
        and with property.
        """
        def operation_fail(fn, *pargs, **kwargs):
            """Confirm the operation fn fails with CIM_ERR_NOT_SUPPORTED"""
            with pytest.raises(CIMError) as exec_info:
                fn(*pargs, **kwargs)
            exc = exec_info.value
            assert exc.status_code == CIM_ERR_NOT_SUPPORTED

        # pylint: disable=protected-access
        FakedWBEMConnection._reset_logging_config()

        if set_on_init:
            conn = FakedWBEMConnection(disable_pull_operations=disable)
        else:
            conn = FakedWBEMConnection()
            assert conn.disable_pull_operations is False
            conn.disable_pull_operations = disable

        # Test if the attribute correctly set in conn
        if disable:
            assert conn.disable_pull_operations is True
        elif disable is False:
            assert conn.disable_pull_operations is False
        else:
            assert disable is None
            assert conn.disable_pull_operations is False

        # Test if the attribute correctly set in conn.mainprovider
        if disable:
            assert conn.mainprovider.disable_pull_operations is True
        elif disable is False:
            assert conn.mainprovider.disable_pull_operations is False
        else:
            assert disable is None
            assert conn.mainprovider.disable_pull_operations is False

        conn.add_cimobjects(tst_classeswqualifiers)
        conn.add_cimobjects(tst_instances)
        tst_class = 'CIM_Foo'
        paths = conn.EnumerateInstanceNames(tst_class)
        path = paths[0]

        if conn.disable_pull_operations is True:
            operation_fail(conn.OpenEnumerateInstances, tst_class)
            operation_fail(conn.OpenEnumerateInstancePaths, tst_class)
            operation_fail(conn.OpenReferenceInstances, path)
            operation_fail(conn.OpenReferenceInstancePaths, path)
            operation_fail(conn.OpenAssociatorInstancePaths, path)
            operation_fail(conn.OpenAssociatorInstancePaths, path)
            # TODO Future add this tfail(conn.OpenQueryInstances,
            #                     tst_class, 'WQL', "SELECT FROM CIM_Foo" )

        else:
            conn.OpenEnumerateInstances(tst_class)
            conn.OpenEnumerateInstancePaths(tst_class)
            conn.OpenReferenceInstances(path)
            conn.OpenReferenceInstancePaths(path)
            conn.OpenAssociatorInstancePaths(path)
            conn.OpenAssociatorInstancePaths(path)
            # TODO: Future conn.OpenQueryInstances
            #       (tst_class, 'WQL', "SELECT FROM CIM_Foo" )

    def test_repr(self):
        # pylint: disable=no-self-use
        """ Test output of repr"""
        # pylint: disable=protected-access
        FakedWBEMConnection._reset_logging_config()
        conn = FakedWBEMConnection(response_delay=3)
        repr_ = '%r' % conn
        assert repr_.startswith('FakedWBEMConnection(response_delay=3,')

    def test_attr(self):
        # pylint: disable=no-self-use
        """
        Test initial FadedWBEMConnection attributes
        """
        # pylint: disable=protected-access
        FakedWBEMConnection._reset_logging_config()
        conn = FakedWBEMConnection()
        assert conn.scheme == 'http'
        assert conn.host == 'FakedUrl:5988'
        assert conn.url == 'http://FakedUrl:5988'
        assert conn.use_pull_operations is False
        assert conn.stats_enabled is False
        assert conn.default_namespace == DEFAULT_NAMESPACE
        assert conn.operation_recorder_enabled is False
        # TODO/ks: Future this becomes part of provider
        assert isinstance(conn.methods, NocaseDict)


class TestRepoMethods(object):
    """
    Test the repository support methods including the ability to add objects
    to the repository, _get_subclass_names, _get_superclass_names, _get_class,
    _get_instance, display_repository, etc.
    """

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES)
    @pytest.mark.parametrize(
        "mof", [False, True])
    @pytest.mark.parametrize(
        "cln, exp_rtn", [
            ['CIM_Foo', True],
            ['CIM_FooX', False],
        ]
    )
    def test_class_exists(self, conn, tst_classeswqualifiers, tst_classes_mof,
                          ns, mof, cln, exp_rtn):
        # pylint: disable=no-self-use
        """ Test the _class_exists() method"""
        if mof:
            skip_if_moftab_regenerated()
            conn.compile_mof_string(tst_classes_mof, namespace=ns)
        else:
            conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)
        # pylint: disable=protected-access
        assert conn.mainprovider.class_exists(ns, cln) == exp_rtn

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES)
    @pytest.mark.parametrize(
        "mof", [False, True])
    @pytest.mark.parametrize(
        "cln, di, exp_clns", [
            [None, True, ['CIM_Foo', 'CIM_Foo_sub', 'CIM_Foo_sub2',
                          'CIM_Foo_sub_sub', 'CIM_Foo_nokey']],
            [None, False, ['CIM_Foo', 'CIM_Foo_nokey']],
            ['CIM_Foo', True, ['CIM_Foo_sub', 'CIM_Foo_sub2',
                               'CIM_Foo_sub_sub']],
            ['cim_foo', True, ['CIM_Foo_sub', 'CIM_Foo_sub2',
                               'CIM_Foo_sub_sub']],  # test case insensitivity
            ['CIM_Foo', False, ['CIM_Foo_sub', 'CIM_Foo_sub2']],
            ['CIM_Foo_sub', True, ['CIM_Foo_sub_sub']],
            ['CIM_Foo_sub', False, ['CIM_Foo_sub_sub']],
        ]
    )
    def test_get_subclassnames(self, conn, tst_classeswqualifiers,
                               tst_classes_mof, ns, cln, mof, di, exp_clns):
        # pylint: disable=no-self-use
        """
        Test the _internal _get_subclass_names method. Tests against both
        add_cimobjects and compiled objects
        """
        if mof:
            skip_if_moftab_regenerated()
            conn.compile_mof_string(tst_classes_mof, namespace=ns)
        else:
            conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)

        # pylint: disable=protected-access
        class_store = conn._get_class_store(ns)

        assert set(conn.mainprovider._get_subclass_names(cln,
                                                         class_store,
                                                         di)) == \
            set(exp_clns)

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES)
    @pytest.mark.parametrize(
        "mof", [False, True])
    @pytest.mark.parametrize(
        # cln - classname where search for superclassnames begins
        # exp_cln - Expected superclasses of cln
        "cln, exp_cln", [
            ['CIM_Foo', []],
            ['CIM_Foo_sub', ['CIM_Foo']],
            ['cim_foo_sub', ['CIM_Foo']],      # test case independence
            ['CIM_Foo_sub_sub', ['CIM_Foo', 'CIM_Foo_sub']],
        ]
    )
    def test_get_superclass_names(self, conn, tst_classeswqualifiers,
                                  tst_classes_mof, ns, mof, cln, exp_cln):
        # pylint: disable=no-self-use
        """
            Test the _get_superclass_names method
        """
        if mof:
            skip_if_moftab_regenerated()
            conn.compile_mof_string(tst_classes_mof, namespace=ns)
        else:
            conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)

        # pylint: disable=protected-access
        class_store = conn._get_class_store(ns)
        clns = conn.mainprovider._get_superclass_names(cln, class_store)
        assert clns == exp_cln

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES)
    @pytest.mark.parametrize(
        "mof", [False, True])
    @pytest.mark.parametrize(
        "cln, lo, iq, ico, pl, exp_prop", [
            # classname     lo     iq    ico   pl     exp_prop
            ['CIM_Foo_sub', False, True, True, None, ['InstanceID',
                                                      'cimfoo_sub']],
            ['CIM_Foo_sub', False, False, True, None, ['InstanceID',
                                                       'cimfoo_sub']],
            ['CIM_Foo_sub', False, True, False, None, ['InstanceID',
                                                       'cimfoo_sub']],
            ['CIM_Foo_sub', False, True, True, ['cimfoo_sub'], ['cimfoo_sub']],
            ['CIM_Foo_sub', False, True, True, ['InstanceID'], ['InstanceID']],
            ['CIM_Foo_sub', False, True, True, [''], []],
            ['CIM_Foo_sub', True, True, True, None, ['cimfoo_sub']],
            ['CIM_Foo_sub', True, False, True, None, ['cimfoo_sub']],
            ['CIM_Foo_sub', True, True, False, None, ['cimfoo_sub']],
            ['CIM_Foo_sub', True, True, False, ['InstanceID'], []],
            ['CIM_Foo_sub', True, True, False, ['cimfoo_sub'], ['cimfoo_sub']],
            ['cim_foo_sub', True, True, False, ['cimfoo_sub'], ['cimfoo_sub']],
        ]
    )
    def test_get_class(self, conn, tst_classeswqualifiers, tst_classes_mof,
                       ns, mof, cln, lo, iq, ico, pl, exp_prop):
        # pylint: disable=no-self-use
        """
        Test variations on the _get_class method that gets a class
        from the repository, creates a copy  and filters it.
        """
        if mof:
            skip_if_moftab_regenerated()
            conn.compile_mof_string(tst_classes_mof, namespace=ns)
        else:
            conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)

        # _get_class gets a copy of the class filtered by the parameters
        # pylint: disable=protected-access
        cl = conn.mainprovider.get_class(ns, cln, local_only=lo,
                                         include_qualifiers=iq,
                                         include_classorigin=ico,
                                         property_list=pl)

        cl_props = [p.name for p in six.itervalues(cl.properties)]

        class_store = conn._get_class_store(ns)
        tst_class = class_store.get(cln)

        if ico:
            for prop in six.itervalues(cl.properties):
                assert prop.class_origin
            for method in six.itervalues(cl.methods):
                assert method.class_origin
        else:
            for prop in six.itervalues(cl.properties):
                assert not prop.class_origin
            for method in six.itervalues(cl.methods):
                assert not method.class_origin

        if not iq:
            assert not cl.qualifiers
            for prop in six.itervalues(cl.properties):
                assert not prop.qualifiers
            for method in six.itervalues(cl.methods):
                for param in six.itervalues(method.parameters):
                    assert not param.qualifiers
        else:
            assert cl.qualifiers == tst_class.qualifiers

        if pl:
            # special test for empty property list
            if len(pl) == 1 and pl[0] == '':
                assert not cl_props
            else:
                # Cover case where pl is for property not in class
                tst_lst = [p for p in pl if p in cl_props]
                if tst_lst != pl:
                    assert set(cl_props) == set(tst_lst)
                else:
                    assert set(cl_props) == set(pl)
        else:
            assert set(cl_props) == set(exp_prop)

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES)
    @pytest.mark.parametrize(
        "mof", [False, True])
    @pytest.mark.parametrize(
        "cln, key, iq, ico, pl, exp_props, exp_exc",
        [
            # cln         key      iq     ico   pl      exp_props   exp_exc
            ['CIM_Foo', 'CIM_Foo1', None, None, None, ['InstanceID'], None],
            ['cim_foo', 'CIM_Foo1', None, None, None, ['InstanceID'], None],
            ['CIM_Foo', 'CIM_Foo1', None, None, ['InstanceID'], ['InstanceID'],
             None],
            ['CIM_Foo', 'CIM_Foo1', None, None, ['Instx'], [], None],
            ['CIM_Foo', 'CIM_Foo1', True, None, None, ['InstanceID'], None],
            ['CIM_Foo', 'CIM_Foo1', None, True, None, ['InstanceID'], None],
            ['CIM_Foo', 'CIM_Foo1', None, None, "", [], None],
            ['CIM_Foo', 'CIM_Foo2', None, None, None, ['InstanceID'], None],
            ['CIM_Foo_sub', 'CIM_Foo_sub4', None, None, None, ['InstanceID',
                                                               'cimfoo_sub'],
             None],

            ['CIM_Foo_sub', 'CIM_Foo_sub99', None, None, None, None,
             CIMError(CIM_ERR_NOT_FOUND)],
        ]
    )
    def test_get_instance(self, conn, tst_classeswqualifiers, tst_instances,
                          tst_instances_mof, ns, mof, cln, key, iq, ico, pl,
                          exp_props, exp_exc):
        # pylint: disable=no-self-use
        """
        Test the internal _get_instance method.  Test for getting correct and
        error responses for both compiled and added objects including parameters
        of propertylist, include qualifiers, include class origin.
        """
        if mof:
            skip_if_moftab_regenerated()
            conn.compile_mof_string(tst_instances_mof, namespace=ns)
        else:
            conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)
            conn.add_cimobjects(tst_instances, namespace=ns)

        lo = False   # TODO expand test to use lo parameterized.
        # since lo is deprecated we might just drop it and always
        # go false.

        assert ns is not None

        iname = CIMInstanceName(cln,
                                keybindings={'InstanceID': key},
                                namespace=ns)
        if exp_exc is None:
            # pylint: disable=protected-access
            instance_store = conn._get_instance_store(ns)
            inst = conn.mainprovider._get_instance(iname, instance_store,
                                                   lo, ico, iq, pl)
            assert isinstance(inst, CIMInstance)
            assert inst.path.classname.lower() == cln.lower()
            assert iname == inst.path
            assert inst.classname.lower() == cln.lower()
            assert inst.path.host is None

            if pl == "":
                assert not inst.properties
            else:
                assert set(inst.keys()) == set(exp_props)

        else:
            with pytest.raises(exp_exc.__class__) as exec_info:
                # pylint: disable=protected-access
                instance_store = conn._get_instance_store(ns)
                conn.mainprovider._get_instance(iname,
                                                instance_store, lo,
                                                ico, iq, pl)
            exc = exec_info.value
            if isinstance(exp_exc, CIMError):
                assert exc.status_code == exp_exc.status_code

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES)
    @pytest.mark.parametrize(
        "mof", [False, True])
    @pytest.mark.parametrize(
        "cln, key, exp_ok",
        [
            ['CIM_Foo', 'CIM_Foo1', True],
            ['CIM_Foo', 'CIM_Foo2', True],
            ['cim_foo', 'CIM_Foo2', True],
            ['CIM_Foo_sub', 'CIM_Foo_sub4', True],
            ['CIM_Foo_sub', 'CIM_Foo_sub99', False],
        ]
    )
    def test_find_instance(self, conn, tst_classeswqualifiers, tst_instances,
                           tst_instances_mof, ns, mof,
                           cln, key, exp_ok):
        # pylint: disable=no-self-use
        """
        Test the find instance repo method with both compiled and add
        creation of the repo.
        """
        if mof:
            skip_if_moftab_regenerated()
            conn.compile_mof_string(tst_instances_mof, namespace=ns)
        else:
            conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)
            conn.add_cimobjects(tst_instances, namespace=ns)

        instance_store = conn.mainprovider.get_instance_store(ns)

        iname = CIMInstanceName(cln,
                                keybindings={'InstanceID': key},
                                namespace=ns)

        # pylint: disable=protected-access
        inst = conn.mainprovider.find_instance(iname, instance_store)

        if exp_ok:
            assert isinstance(inst, CIMInstance)
            assert equal_model_path(iname, inst.path)
        else:
            assert inst is None

    @staticmethod
    def method2_callback(conn, methodname, object_name, **params):
        """Test callback function for ethod2. Not really used but
           installed to define function
        """
        pass

    @staticmethod
    def method1_callback(conn, methodname, object_name, **params):
        """Test callback function for method1. Not really used but
           installed to define function
        """
        pass

    @staticmethod
    def fuzzy_callback(conn, methodname, object_name, **params):
        """Test callback function for fuzzy method. Not really used but
           installed to define function
        """
        pass

    @pytest.mark.skip(reason="Used only to display repo so not real test.")
    def test_disp_repo_tostdout(self, conn, tst_instances_mof):
        """
        Test method used only for manual tests.
        TODO: This test can be removed before we finalize mock
        """
        skip_if_moftab_regenerated()
        namespaces = ['interop']
        for ns in namespaces:
            conn.compile_mof_string(tst_instances_mof, namespace=ns)

            conn.add_method_callback('CIM_Foo', 'Fuzzy',
                                     self.fuzzy_callback,
                                     namespace=ns)

            inst_id = 'CIM_foo_sub_sub_test_unicode'

            str_data = u'\u212b \u0420 \u043e \u0441 \u0441\u0438 \u044f \u00e0'
            inst = CIMInstance(
                'CIM_Foo_sub_sub',
                properties={
                    'InstanceID': inst_id,
                    'cimfoo_sub': 'cimfoo_sub prop:  %s' % str_data,
                    'cimfoo_sub_sub': 'cimfoo_sub_sub: %s' % str_data},
                path=CIMInstanceName('CIM_Foo_sub_sub',
                                     {'InstanceID': inst_id}))
            conn.add_cimobjects(inst, namespace=ns)

            # The following will not compile.  Gets compiler error
            # str = u'instance of CIM_Foo_sub2 as $foosub22 {' \
            # u'InstanceID = "CIM_Foo_unicode";\n' \
            # u'cimfoo_sub2 = \u212b \u0420 \u043e \u0441 \u0441' \
            # u' \u0438 \u044f \u00e0;};'
            # conn.compile_mof_string(str, namespace=ns)

        # Test basic display repo output
        conn.display_repository()
        tst_file_name = 'tmp_testfrom_test_dr.txt'
        tst_file = os.path.join(TEST_DIR, tst_file_name)
        conn.display_repository(dest=tst_file)

    def test_display_repository(self, conn, tst_instances_mof, capsys):
        """
        Test the display of the repository with it various options.
        This is done in a single test method for simplicity
        """
        skip_if_moftab_regenerated()
        # Create the objects in all namespaces
        namespaces = INITIAL_NAMESPACES
        for ns in namespaces:
            conn.compile_mof_string(tst_instances_mof, namespace=ns)

            conn.add_method_callback('CIM_Foo', 'Fuzzy',
                                     self.fuzzy_callback,
                                     namespace=ns)

        # Test basic display repo output
        conn.display_repository()
        captured = capsys.readouterr()

        result = captured.out
        print('RESULT\n%s' % result)

        assert result.startswith(
            "// ========Mock Repo Display fmt=mof namespaces=all")
        assert "class CIM_Foo_sub_sub : CIM_Foo_sub {" in result
        assert "instance of CIM_Foo {" in result
        for ns in namespaces:
            assert _format("// Namespace {0!A}: contains 9 Qualifier "
                           "Declarations", ns) \
                in result
            assert _format("// Namespace {0!A}: contains 5 Classes", ns) \
                in result
            assert _format("// Namespace {0!A}: contains 8 Instances", ns) \
                in result
        assert "Qualifier Abstract : boolean = false," in result

        # Confirm that the display formats work
        for param in ('xml', 'mof', 'repr'):
            conn.display_repository(output_format=param)
            captured = capsys.readouterr()
            assert captured.out

        # confirm that the two repositories exist
        conn.display_repository(namespaces=namespaces)
        captured = capsys.readouterr()
        assert captured.out

        # test with a defined namespace
        ns = namespaces[0]
        conn.display_repository(namespaces=[ns])
        captured = capsys.readouterr()
        assert captured.out

        conn.display_repository(namespaces=ns)
        captured = capsys.readouterr()
        assert captured.out

        # test for invalid output_format
        with pytest.raises(ValueError):
            conn.display_repository(output_format='blah')
            captured = capsys.readouterr()
            assert captured.out

    def test_display_repo_tofile(self, conn, tst_instances_mof):
        # pylint: disable=no-self-use
        """
        Test output of the display_repository method to a file.
        """
        skip_if_moftab_regenerated()
        conn.compile_mof_string(tst_instances_mof, namespace=DEFAULT_NAMESPACE)

        tst_file_name = 'test_wbemconnection_mock_repo.txt'
        tst_file = os.path.join(TEST_DIR, tst_file_name)
        conn.display_repository(dest=tst_file)
        assert os.path.isfile(tst_file)
        with open(tst_file, 'r') as f:
            data = f.read()
        assert data.startswith(
            "// ========Mock Repo Display fmt=mof namespaces=all")
        assert 'class CIM_Foo_sub_sub : CIM_Foo_sub {' in data
        assert 'instance of CIM_Foo {' in data
        assert 'Qualifier Abstract : boolean = false,' in data
        os.remove(tst_file)

    # TODO: Add test of format of the repo output with a very simple schema
    #       to keep the comparison small.

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    def test_addcimobject(self, conn, ns, tst_classeswqualifiers, tst_instances,
                          tst_insts_big, tst_classes):
        # pylint: disable=no-self-use
        """
        Test inserting all of the object definitions in the fixtures into
        the repository
        """
        conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)
        conn.add_cimobjects(tst_instances, namespace=ns)
        conn.add_cimobjects(tst_insts_big, namespace=ns)

        exp_ns = ns or conn.default_namespace

        # pylint: disable=protected-access
        class_store = conn._get_class_store(exp_ns)
        assert class_store.len() == len(tst_classes)

        instance_store = conn._get_instance_store(exp_ns)
        assert instance_store.len() == len(tst_instances) + len(tst_insts_big)

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    def test_addcimobject_err(self, conn, ns, tst_classeswqualifiers,
                              tst_instances):
        # pylint: disable=no-self-use
        """Test error if duplicate instance inserted"""
        conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)
        conn.add_cimobjects(tst_instances, namespace=ns)
        with pytest.raises(ValueError):
            conn.add_cimobjects(tst_instances, namespace=ns)

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    def test_addcimobject_err1(self, conn, ns, tst_classeswqualifiers):
        # pylint: disable=no-self-use
        """Test error if class with no superclass"""
        conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)
        c = CIMClass('CIM_BadClass', superclass='CIM_NotExist')
        with pytest.raises(ValueError):
            conn.add_cimobjects(c, namespace=ns)

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    def test_compile_qualifiers(self, conn, ns, tst_qualifiers_mof):
        # pylint: disable=no-self-use
        """
        Test compile qualifiers with namespace from mof
        """
        skip_if_moftab_regenerated()
        conn.compile_mof_string(tst_qualifiers_mof, ns)

        assert conn.GetQualifier(
            'Association', namespace=ns).name == 'Association'
        assert conn.GetQualifier(
            'Indication', namespace=ns).name == 'Indication'
        assert conn.GetQualifier('Abstract', namespace=ns).name == 'Abstract'
        assert conn.GetQualifier('Aggregate', namespace=ns).name == 'Aggregate'
        assert conn.GetQualifier('Key', namespace=ns).name == 'Key'

        quals = conn.EnumerateQualifiers(namespace=ns)
        assert len(quals) == 9

    @pytest.mark.parametrize(
        "default_ns, additional_ns, test_ns, exp_ns, exp_exc",
        [
            ('root/def', [], 'root/blah', 'root/blah', None),
            ('root/def', [], '//root/blah//', 'root/blah', None),
            ('root/def', ['root/foo'], 'root/blah', 'root/blah', None),
            ('root/def', ['root/blah'], 'root/blah', None,
             CIMError(CIM_ERR_ALREADY_EXISTS)),
            ('root/def', [], None, None, ValueError()),
        ]
    )
    def test_add_namespace(self, default_ns, additional_ns, test_ns, exp_ns,
                           exp_exc):
        # pylint: disable=no-self-use
        """
        Test add_namespace(). This tests the methods for managing namespaces
        in the FakedWBEMConnection class
        """
        conn = FakedWBEMConnection()
        conn.add_namespace(default_ns)
        for ns in additional_ns:
            conn.add_namespace(ns)
        if not exp_exc:

            # The code to be tested
            conn.add_namespace(test_ns)

            assert exp_ns in conn.namespaces
        else:
            with pytest.raises(exp_exc.__class__) as exec_info:

                # The code to be tested
                conn.add_namespace(test_ns)

            exc = exec_info.value
            if isinstance(exp_exc, CIMError):
                assert exc.status_code == exp_exc.status_code

    @pytest.mark.parametrize(
        "default_ns, additional_ns, test_ns, exp_ns, exp_exc",
        [
            ('root/def', ['root/blah'], 'root/blah', 'root/blah', None),
            ('root/def', ['root/blah'], '//root/blah//', 'root/blah', None),
            ('root/def', ['root/blah', 'root/foo'], 'root/blah', 'root/blah',
             None),
            ('root/def', [], 'root/blah', None, CIMError(CIM_ERR_NOT_FOUND)),
            ('root/def', [], None, None, ValueError()),
        ]
    )
    def test_remove_namespace(self, default_ns, additional_ns, test_ns, exp_ns,
                              exp_exc):
        # pylint: disable=no-self-use
        """
        Test _remove_namespace()
        """
        # TODO: This test goes back and forth between the methods in
        # wbemconnectionfake, mainprovider, and datastore. Make consistent

        conn = FakedWBEMConnection()
        conn.add_namespace(default_ns)
        for ns in additional_ns:
            conn.add_namespace(ns)

        if not exp_exc:
            # The code to be tested
            # pylint: disable=protected-access
            conn.remove_namespace(test_ns)

            assert exp_ns not in conn.namespaces
        else:
            with pytest.raises(exp_exc.__class__) as exec_info:

                # The code to be tested
                # pylint: disable=protected-access
                conn.remove_namespace(test_ns)

            exc = exec_info.value
            if isinstance(exp_exc, CIMError):
                assert exc.status_code == exp_exc.status_code

    def test_unicode(self, conn):
        # pylint: disable=no-self-use
        """
        Test compile and display repository with unicode in MOF string
        """
        ns = DEFAULT_NAMESPACE

        qmof = """
        Qualifier Description : string = null,
            Scope(any),
            Flavor(EnableOverride, ToSubclass, Translatable);

        Qualifier Key : boolean = false,
            Scope(property, reference),
            Flavor(DisableOverride, ToSubclass);
        """

        # TODO: KS need to allow set of existing qualifier.
        # Qualifier Description : string = null,
        #    Scope(any),
        #    Flavor(EnableOverride, ToSubclass, Translatable);

        cmof = u"""
        class CIM_Foo {
                [Key,
                 Description ("\u212b \u0420\u043e\u0441\u0441\u0438"
                              "\u044f\u00E0 voil\u00e0")]
            string InstanceID;
        };
        """
        skip_if_moftab_regenerated()

        conn.compile_mof_string(qmof, ns)
        conn.compile_mof_string(cmof, ns)

        with OutputCapture():
            conn.display_repository()
        tst_file_name = 'test_wbemconnection_mock_repo_unicode.txt'
        tst_file = os.path.join(TEST_DIR, tst_file_name)

        conn.display_repository(dest=tst_file)
        assert os.path.isfile(tst_file)
        os.remove(tst_file)

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    def test_compile_mult(self, conn, ns):
        # pylint: disable=no-self-use
        """
        Test compile of multiple separate compile units including qualifiers,
        classes and instances.
        """

        exp_ns = ns or conn.default_namespace

        q1 = """
        Qualifier Association : boolean = false,
            Scope(association),
            Flavor(DisableOverride, ToSubclass);
        """
        q2 = """
        Qualifier Description : string = null,
            Scope(any),
            Flavor(EnableOverride, ToSubclass, Translatable);

        Qualifier Key : boolean = false,
            Scope(property, reference),
            Flavor(DisableOverride, ToSubclass);
        """

        c1 = """
             [Description ("blah blah")]
        class CIM_Foo {
                [Key, Description ("This is key prop")]
            string InstanceID;
        };
        """
        c2 = """
            [Description ("Subclass of CIM_Foo")]
        class CIM_Foo_sub : CIM_Foo {
            string cimfoo_sub;
        };
        """
        i1 = """
        instance of CIM_Foo as $foo1 { InstanceID = "CIM_Foo1"; };
        """
        i2 = """
        instance of CIM_Foo as $foo2 { InstanceID = "CIM_Foo2"; };
        """
        i3 = """
        instance of CIM_Foo as $foo3 { InstanceID = "CIM_Foo3"; };
        """
        # TODO: Remove alias once inst without alias properly generates path
        # IN MOF compiler
        i4 = """
        instance of CIM_Foo as $foo4 { InstanceID = "CIM_Foo4"; };
        """
        skip_if_moftab_regenerated()

        conn.compile_mof_string(q1, ns)
        # pylint: disable=protected-access
        qual_repo = conn._get_qualifier_store(exp_ns)

        assert qual_repo.object_exists('Association')
        conn.compile_mof_string(q2, ns)

        qual_repo = conn._get_qualifier_store(exp_ns)
        # pylint: enable=protected-access

        assert qual_repo.object_exists('Association')
        assert qual_repo.object_exists('Description')
        assert qual_repo.object_exists('Key')

        assert conn.GetQualifier('Association', namespace=ns)
        assert conn.GetQualifier('Description', namespace=ns)

        conn.compile_mof_string(c1, ns)
        assert conn.GetClass('CIM_Foo', namespace=ns, LocalOnly=False,
                             IncludeQualifiers=True, IncludeClassOrigin=True)

        conn.compile_mof_string(c2, ns)
        assert conn.GetClass('CIM_Foo_sub', namespace=ns)

        conn.compile_mof_string(i1, ns)
        rtn_names = conn.EnumerateInstanceNames('CIM_Foo', namespace=ns)
        assert len(rtn_names) == 1
        conn.compile_mof_string(i2, ns)
        rtn_names = conn.EnumerateInstanceNames('CIM_Foo', namespace=ns)
        assert len(rtn_names) == 2
        conn.compile_mof_string(i3, ns)
        rtn_names = conn.EnumerateInstanceNames('CIM_Foo', namespace=ns)
        assert len(rtn_names) == 3
        conn.compile_mof_string(i4, ns)
        rtn_names = conn.EnumerateInstanceNames('CIM_Foo', namespace=ns)
        assert len(rtn_names) == 4
        for name in rtn_names:
            inst = conn.GetInstance(name)
            assert inst.classname == 'CIM_Foo'

        for id_ in ['CIM_Foo4', 'CIM_Foo3', 'CIM_Foo2', 'CIM_Foo1']:
            iname = CIMInstanceName('CIM_Foo',
                                    keybindings={'InstanceID': id_},
                                    namespace=exp_ns)
            assert iname in rtn_names

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    def test_compile_classes(self, conn, tst_classes_mof, ns):
        # pylint: disable=no-self-use
        """
        Test compile of classes into the repository
        """
        skip_if_moftab_regenerated()

        conn.compile_mof_string(tst_classes_mof, namespace=ns)

        assert conn.GetClass('CIM_Foo', namespace=ns).classname == 'CIM_Foo'
        assert conn.GetClass('CIM_Foo_sub',
                             namespace=ns).classname == 'CIM_Foo_sub'
        assert conn.GetClass('CIM_Foo_sub2',
                             namespace=ns).classname == 'CIM_Foo_sub2'
        assert conn.GetClass('CIM_Foo_sub_sub',
                             namespace=ns).classname == 'CIM_Foo_sub_sub'

        clns = conn.EnumerateClassNames(namespace=ns)
        assert len(clns) == 2
        clns = conn.EnumerateClassNames(namespace=ns, DeepInheritance=True)
        assert len(clns) == 5
        cls = conn.EnumerateClasses(namespace=ns, DeepInheritance=True)
        assert len(cls) == 5
        assert set(clns) == set([cl.classname for cl in cls])

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    def test_compile_instances(self, conn, ns, tst_classes_mof):
        # pylint: disable=no-self-use
        """
        Test compile of instance MOF into the repository in single file with
        classes.
        """

        skip_if_moftab_regenerated()

        tst_ns = ns or conn.default_namespace
        insts_mof = """
            instance of CIM_Foo as $Alice {
            InstanceID = "Alice";
            };
            instance of CIM_Foo as $Bob {
                InstanceID = "Bob";
            };
            """
        # compile as single unit by combining classes and instances
        # The compiler builds the instance paths.
        all_mof = '%s\n\n%s' % (tst_classes_mof, insts_mof)

        conn.compile_mof_string(all_mof, namespace=ns)
        rtn_names = conn.EnumerateInstanceNames('CIM_Foo', namespace=ns)
        assert len(rtn_names) == 2

        for name in rtn_names:
            inst = conn.GetInstance(name)
            assert inst.classname == 'CIM_Foo'

        for id_ in ['Alice', 'Bob']:
            iname = CIMInstanceName('CIM_Foo',
                                    keybindings={'InstanceID': id_},
                                    namespace=tst_ns)
            assert iname in rtn_names

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    def test_compile_assoc_mof(self, conn, tst_assoc_mof, ns,
                               tst_person_instance_names):
        # pylint: disable=no-self-use
        """
        Test the  tst_assoc_mof compiled MOF to confirm compiled correct
        classes and instances.
        """

        skip_if_moftab_regenerated()

        conn.compile_mof_string(tst_assoc_mof, namespace=ns)

        clns = conn.EnumerateClassNames(namespace=ns, DeepInheritance=True)

        assert 'TST_Person' in clns
        assert 'TST_Lineage' in clns
        assert 'TST_Personsub' in clns
        assert 'TST_MemberOfFamilyCollection' in clns
        assert 'TST_FamilyCollection' in clns
        assert len(clns) == 5

        inst_names = conn.EnumerateInstanceNames('TST_Person', namespace=ns)
        assert len(inst_names) == TST_PERSONWITH_SUB_INST_COUNT
        insts = conn.EnumerateInstances('TST_Person', namespace=ns)
        assert len(inst_names) == TST_PERSONWITH_SUB_INST_COUNT

        # Test for particular instances in the enum response
        for name in tst_person_instance_names:
            result = [inst for inst in insts
                      if inst.classname == 'TST_Person' and
                      inst['name'] == name]
            assert len(result) == 1

        # test GetInstance
        for name in tst_person_instance_names:
            kb = {'name': name}
            inst_name = CIMInstanceName('TST_Person', kb, namespace=ns)
            conn.GetInstance(inst_name)

        inst_names = conn.EnumerateInstanceNames('TST_Lineage', namespace=ns)
        assert len(inst_names) == 3
        insts = conn.EnumerateInstances('TST_Lineage', namespace=ns)
        assert len(inst_names) == 3

        for inst_name in inst_names:
            conn.GetInstance(inst_name)

        # TODO test returned instance for match with what was created

    def test_compile_complete_dmtf_schema(self, conn):
        # pylint: disable=no-self-use
        """
        Test Compiling the complete DMTF CIM schema. This test compiles all
        classes of  the DMTF schema that is defined in the test suite.
        """
        skip_if_moftab_regenerated()

        ns = 'root/cimv2'
        # install the schema if necessary.
        dmtf_schema = install_test_dmtf_schema()

        conn.compile_mof_file(dmtf_schema.schema_mof_file, namespace=ns,
                              search_paths=[dmtf_schema.schema_mof_dir])

        # pylint: disable=protected-access
        assert conn._get_class_store(ns).len() == TOTAL_CLASSES
        assert conn._get_qualifier_store(ns).len() == TOTAL_QUALIFIERS

    @ pytest.mark.parametrize(
        # Test use of both compile_dmtf_schema and compile_schema_classes
        "use_compile_dmtf_schema", [True, False])
    @pytest.mark.parametrize(
        # Description - Description of the test
        # classnames - List of classnames to compile
        # extra_exp_classnames - Dependent classnames that will be compiled in
        #              addition to the classes in classnames
        # exp_class - CIMClass defining expected class as compiled (optional)
        #             If this exists the compiled class must match this
        # run_test - If True, execute the test
        "description, classnames, extra_exp_classnames, exp_class, run_tst",
        [
            ["Test with several classes. ",
             ['CIM_RegisteredProfile', 'CIM_Namespace', 'CIM_ObjectManager',
              'CIM_ElementConformsToProfile', 'CIM_ReferencedProfile'],
             ['CIM_EnabledLogicalElement', 'CIM_Job',
              'CIM_LogicalElement', 'CIM_ManagedSystemElement',
              'CIM_Service', 'CIM_Service', 'CIM_ConcreteJob',
              'CIM_Dependency', 'CIM_ManagedElement', 'CIM_ManagedElement',
              'CIM_Error', 'CIM_RegisteredSpecification',
              'CIM_ReferencedSpecification', 'CIM_WBEMService'],
             None,
             True],

            ["Test with single classes. Broken",
             ['CIM_ObjectManager'],
             ['CIM_EnabledLogicalElement', 'CIM_Error', 'CIM_LogicalElement',
              'CIM_ConcreteJob', 'CIM_WBEMService',
              'CIM_ManagedSystemElement', 'CIM_Service',
              'CIM_ManagedElement', 'CIM_Job'],
             None,
             True],

            ["Test with simple group of classes",
             ['CIM_ElementConformsToProfile'],
             ['CIM_ManagedElement',
              'CIM_RegisteredSpecification', 'CIM_RegisteredProfile'],
             None,
             True],

            ["Test with single class",
             ['CIM_RegisteredProfile'],
             ['CIM_ManagedElement', 'CIM_RegisteredSpecification'],
             None,
             True],

            ["Test with single association. Confirms assoc dependents",
             ['CIM_ProductComponent'],
             ['CIM_Component', 'CIM_ManagedElement', 'CIM_ProductComponent',
              'CIM_Product'],
             None,
             True],

            ["Test with class that passes Caption",
             ['CIM_FileServerCapabilities'],
             ['CIM_ManagedElement', 'CIM_Capabilities', 'CIM_SettingData'],
             None,
             True],

            ["Test with class that has embeddedinstance (CIM_SettingData",
             ['CIM_Capabilities'],
             ['CIM_ManagedElement', 'CIM_SettingData'],
             None,
             True],

            ["Test compile of Association subclass",
             ['CIM_HostedDependency'],
             ['CIM_Dependency', 'CIM_ManagedElement', ],
             CIMClass(
                 classname='CIM_HostedDependency',
                 superclass='CIM_Dependency',
                 properties=NocaseDict({
                     'Antecedent': CIMProperty(
                         name='Antecedent', value=None, type='reference',
                         reference_class='CIM_ManagedElement',
                         embedded_object=None, is_array=False, array_size=None,
                         class_origin='CIM_Dependency',
                         propagated=True,
                         qualifiers=NocaseDict({
                             'Override': CIMQualifier(
                                 name='Override', value='Antecedent',
                                 type='string', tosubclass=False,
                                 overridable=True,
                                 translatable=None, toinstance=None,
                                 propagated=False),
                             'Max': CIMQualifier(
                                 name='Max', value=1,
                                 type='uint32',
                                 tosubclass=True, overridable=True,
                                 translatable=None,
                                 toinstance=None, propagated=False),
                             'Description': CIMQualifier(
                                 name='Description',
                                 value='The scoping ManagedElement.',
                                 type='string',
                                 tosubclass=True, overridable=True,
                                 translatable=True,
                                 toinstance=None, propagated=False),
                             'Key': CIMQualifier(
                                 name='Key',
                                 value=True, type='boolean',
                                 tosubclass=True, overridable=False,
                                 translatable=None,
                                 toinstance=None, propagated=True)})),
                     'Dependent': CIMProperty(
                         name='Dependent', value=None, type='reference',
                         reference_class='CIM_ManagedElement',
                         embedded_object=None, is_array=False,
                         array_size=None,
                         class_origin='CIM_Dependency',
                         propagated=True,
                         qualifiers=NocaseDict({
                             'Override': CIMQualifier(
                                 name='Override', value='Dependent',
                                 type='string', tosubclass=False,
                                 overridable=True,
                                 translatable=None, toinstance=None,
                                 propagated=False),
                             'Description': CIMQualifier(
                                 name='Description',
                                 value='The hosted ManagedElement.',
                                 type='string',
                                 tosubclass=True, overridable=True,
                                 translatable=True,
                                 toinstance=None, propagated=False),
                             'Key': CIMQualifier(
                                 name='Key',
                                 value=True, type='boolean',
                                 tosubclass=True, overridable=False,
                                 translatable=None,
                                 toinstance=None, propagated=True)}))}),
                 methods=NocaseDict({}),
                 qualifiers=NocaseDict({
                     'Association': CIMQualifier(
                         name='Association', value=True,
                         type='boolean', tosubclass=True,
                         overridable=False,
                         translatable=None, toinstance=None,
                         propagated=False),
                     'Version': CIMQualifier(
                         name='Version', value='2.8.0',
                         type='string', tosubclass=False,
                         overridable=True,
                         translatable=True, toinstance=None,
                         propagated=False),
                     'UMLPackagePath': CIMQualifier(
                         name='UMLPackagePath',
                         value='CIM::Core::CoreElements',
                         type='string',
                         tosubclass=True, overridable=True,
                         translatable=None,
                         toinstance=None, propagated=False),
                     'Description': CIMQualifier(
                         name='Description',
                         value='HostedDependency defines a '
                               'ManagedElement in the '
                               'context of another '
                               'ManagedElement in which it '
                               'resides.',
                         type='string', tosubclass=True,
                         overridable=True,
                         translatable=True, toinstance=None,
                         propagated=False)}),
                 path=CIMClassName(classname='CIM_HostedDependency',
                                   namespace='root/cimv2',
                                   host='FakedUrl:5988')),
             True],
        ]
    )
    def test_compile_partial_dmtf_schema(self, conn, use_compile_dmtf_schema,
                                         description, classnames,
                                         extra_exp_classnames, exp_class,
                                         run_tst):
        # pylint: disable=no-self-use,unused-argument
        """
        Test Compiling DMTF CIM schema using the compile_dmtf_schema method.
        Optionally compare one of the returned classes against the
        class defined in exp_class.  This test is specifically to assure
        that things like propagated, etc. are correct as compiled and
        installed in the repo.
        """
        if not run_tst:
            pytest.skip("This test marked to be skipped")

        skip_if_moftab_regenerated()

        ns = 'root/cimv2'
        if use_compile_dmtf_schema:
            conn.compile_dmtf_schema(DMTF_TEST_SCHEMA_VER, TESTSUITE_SCHEMA_DIR,
                                     class_names=classnames,
                                     verbose=True)

        else:  # use compile_schema_classes
            schema = DMTFCIMSchema(DMTF_TEST_SCHEMA_VER, TESTSUITE_SCHEMA_DIR,
                                   verbose=True)

            conn.compile_schema_classes(classnames,
                                        schema.schema_pragma_file,
                                        verbose=True)

        # Test the set of created classnames for match to exp_classnames
        exp_classnames = classnames
        exp_classnames.extend(extra_exp_classnames)
        rslt_classnames = conn.EnumerateClassNames(DeepInheritance=True,
                                                   namespace=ns)
        assert set(exp_classnames) == set(rslt_classnames)

        # If exp_class exists compare the exp_class to the created class
        if exp_class:
            rtn_cls = conn.GetClass(exp_class.classname, namespace=ns,
                                    IncludeQualifiers=True,
                                    IncludeClassOrigin=True,
                                    LocalOnly=False)
            assert rtn_cls == exp_class

    def test_compile_err(self, conn):
        # pylint: disable=no-self-use
        """
        Test compile that has an error
        """
        q1 = """
            Qualifier Association : boolean = false,
                Scope(associations),
                Flavor(DisableOverride, ToSubclass);
        """
        skip_if_moftab_regenerated()

        with pytest.raises(MOFCompileError) as exec_info:
            conn.compile_mof_string(q1)

        exc = exec_info.value
        assert re.search(r"MOF grammar error", exc.msg, re.IGNORECASE)

    @pytest.mark.skip(reason="Fails because does not allow dup")
    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    def test_compile_instances_dup(self, conn, ns, tst_classes_mof):
        # pylint: disable=no-self-use
        """
        Test compile of instance MOF  with duplicate keys into the repository
        fails
        """

        skip_if_moftab_regenerated()

        tst_ns = ns or conn.default_namespace
        insts_mof = """
            instance of CIM_Foo_sub as $Alice {
                InstanceID = "Alice";
                cimfoo_sub = "one";
            };
            instance of CIM_Foo_sub as $Alice1 {
                InstanceID = "Alice";
                cimfoo_sub = "two";
            };
            """

        # compile as single unit by combining classes and instances
        # The compiler builds the instance paths.
        conn.compile_mof_string(tst_classes_mof, namespace=tst_ns)
        conn.compile_mof_string(insts_mof, namespace=tst_ns)
        insts = conn.EnumerateInstances('CIM_Foo_sub')

        # test replacement occurred.
        assert len(insts) == 1
        assert insts[0].get('cimfoo_sub') == 'two'
        conn.GetInstance(CIMInstanceName('CIM_Foo_sub',
                                         {'InstanceID': 'Alice'},
                                         namespace=tst_ns))


class UserProviderTest(InstanceWriteProvider):
    """
    Basic user provider implements CreateInstance and DeleteInstance
    """

    def __init__(self, cimrepository):
        """
        Init of test provider
        """
        super(UserProviderTest, self).__init__(cimrepository)

    def CreateInstance(self, namespace, NewInstance):
        """Test Create instance just calls super class method"""
        # pylint: disable=useless-super-delegation
        return super(UserProviderTest, self).CreateInstance(
            namespace, NewInstance)

    def DeleteInstance(self, InstanceName):
        """Test Create instance just calls super class method"""
        # pylint: disable=useless-super-delegation
        return super(UserProviderTest, self).DeleteInstance(
            InstanceName)


class UserMethodProviderTest(MethodProvider):
    """
    Basic user provider implements CreateInstance and DeleteInstance
    """

    def __init__(self, cimrepository):
        """
        Init of test provider
        """
        super(UserMethodProviderTest, self).__init__(cimrepository)

    def InvokeMethod(self, namespace, methodname, objectname, Params):
        """Test InvokeMethod provider with InvokeMethod"""
        # return return-value 0 and no output parameters
        return (0, None)


class TestProviderRegisterMethods(object):
    """
    Test the repository support for use of user providers that are
    registered and substituted for the default provider.
    """

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None]
    )
    @pytest.mark.parametrize(
        # desc - description of the test
        # input - list of lists where the inner lists contain the parameters
        #         of a single request(testnamespaces, lclassnames
        #         provider_type, provider)
        #         * testnamespaces - Namespace or list of namespaces in which
        #           provider is to be registered
        #         * classnames - classname or list of classnames to register
        #           for provider
        #         * provider_type - String defining provider type
        #           ('instance', etc.)
        #         * provider - Class that contains the user provider.
        # exp_exec - Exception if one is expected
        # condition - test condition (True, False, 'pdb')
        "desc, inputs, exp_exec, condition",
        [
            ["validate ns='root/cimv2', etc.",
             [
                 ["root/cimv2", "CIM_Foo", 'instance', UserProviderTest],
             ],
             None, True],

            ["validate  ns='root/cimv2', etc.",
             [
                 ["root/cimv2", "CIM_Foo_sub_sub", 'instance',
                  UserProviderTest],
             ],
             None, True],

            ["validate  ns='root/cimv2', etc.",
             [["root/cimv2", ["CIM_Foo", "CIM_Foo_sub_sub"], 'instance',
               UserProviderTest]],
             None, True],

            ["validate  ns='root/cimv2' invalid classname fails",
             [["root/cimv2", "CIM_Foox", 'instance', UserProviderTest]],
             ValueError, True],

            ["validate  Namespace empty list invalid classname works",
             [["root/cimv2", "CIM_Foo", 'instance', UserProviderTest]],
             None, True],
        ]
    )
    def test_register_provider(self, conn, ns, desc, inputs,
                               exp_exec, condition, tst_classeswqualifiers,
                               tst_instances):
        # pylint: disable=no-self-use
        """
        Test register_provider method.
        """
        if not condition:
            pytest.skip("This test marked to be skipped")
        skip_if_moftab_regenerated()

        if condition == "pdb":
            import pdb  # pylint: disable=import-outside-toplevel
            pdb.set_trace()  # pylint: disable=no-member

        add_objects_to_repo(conn, ns, [tst_classeswqualifiers, tst_instances])

        if exp_exec is None:
            for item in inputs:
                tst_ns = item[0]
                clns = item[1]
                provider_type = item[2]
                provider = item[3]
                conn.register_provider(tst_ns, clns, provider_type, provider)

            pr = conn.provider_registry
            if not isinstance(clns, (list, tuple)):
                clns = [clns]
            for cln in clns:
                assert cln in pr, desc
                pr_cln = pr[cln]
                if isinstance(tst_ns, six.string_types):
                    tst_ns = [tst_ns]
                for lns in tst_ns:
                    assert lns in pr_cln, desc
                    assert provider_type in pr_cln[lns], desc

        else:
            with pytest.raises(exp_exec):
                for item in inputs:
                    tst_ns = item[0]
                    clns = item[1]
                    provider_type = item[2]
                    provider = item[3]

                    conn.register_provider(tst_ns, clns, provider_type,
                                           provider)

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None]
    )
    @pytest.mark.parametrize(
        # desc - description of the test
        # input - list of lists where the inner lists contain the parameters
        #         of a single request(testnamespaces, lclassnames
        #         provider_type, provider)
        #         * testnamespaces - Namespace or list of namespaces in which
        #           provider is to be registered
        #         * classnames - classname or list of classnames to register
        #           for provider
        #         * provider_type - String defining provider type
        #           ('instance', etc.)
        #         * provider - Class that contains the user provider.
        # get_ns - namespace parameter for get_registered_provider
        # get_cln - classname parameter for get_registered_provider
        # get_pt - provider_type parameter for get_registered_provider
        # exp_rslt - get_registered_provider expected return (True, None)
        # condition - test condition (True, False, 'pdb')
        "desc, inputs, get_ns, get_cln, get_pt, exp_rslt, condition",
        [
            ["Verify registry empty returns nothing",
             [
             ],
             'root/cimv2', 'CIM_Foo', 'instance',
             None, True],
            ["register single good instance provider and test good result",
             [
                 ["root/cimv2", "CIM_Foo", 'instance', UserProviderTest],
             ],
             'root/cimv2', 'CIM_Foo', 'instance',
             True, True],

            ["Verify get returns None namespace not found",
             [
                 ["root/cimv2", "CIM_Foo", 'instance', UserProviderTest],
             ],
             'root/cimv2x', 'CIM_Foo', 'instance',
             None, True],

            ["Verify get returns None classname  not found",
             [
                 ["root/cimv2", "CIM_Foo", 'instance', UserProviderTest],
             ],
             'root/cimv2', 'CIM_Foo_sub_sub', 'instance',
             None, True],

            ["Verify get v provider type does not match",
             [
                 ["root/cimv2", "CIM_Foo", 'method', UserMethodProviderTest],
             ],
             'root/cimv2', 'CIM_Foo', 'method',
             None, FAIL],

            ["Verify returns provider, with different class",
             [
                 ["root/cimv2", "CIM_Foo_sub_sub", 'instance',
                  UserProviderTest],
             ],
             'root/cimv2', 'CIM_Foo_sub_sub', 'instance',
             True, True],

            ["Verify multiple providers registered, returns OK",
             [["root/cimv2", ["CIM_Foo", "CIM_Foo_sub_sub"], 'instance',
               UserProviderTest]],
             'root/cimv2', 'CIM_Foo', 'instance',
             True, True],

            ["Verify test, multiple providers registered, returns OK",
             [["root/cimv2", ["CIM_Foo", "CIM_Foo_sub_sub"], 'instance',
               UserProviderTest]],
             'root/cimv2', 'CIM_Foo_sub_sub', 'instance',
             True, True],

            ["Verify test, register with None as namespace, returns OK",
             [[None, ["CIM_Foo"], 'instance',
               UserProviderTest]],
             'root/cimv2', 'CIM_Foo_sub_sub', 'instance',
             True, FAIL],

        ]
    )
    def test_get_registered_provider(self, conn, ns, desc, inputs, get_ns,
                                     get_cln, get_pt, exp_rslt, condition,
                                     tst_classeswqualifiers, tst_instances):
        # pylint: disable=no-self-use,unused-argument
        """
        Creates a set of valid provider registrations and tests the
        get_provider_registration for multiple inputs
        """
        if not condition:
            pytest.skip("This test marked to be skipped")
        skip_if_moftab_regenerated()

        if condition == "pdb":
            import pdb  # pylint: disable=import-outside-toplevel
            pdb.set_trace()  # pylint: disable=no-member

        add_objects_to_repo(conn, ns, [tst_classeswqualifiers, tst_instances])

        # Register multiple providers.  All registrations are must be
        # accepted
        for item in inputs:
            tst_ns = item[0]
            clns = item[1]
            provider_type = item[2]
            provider = item[3]

            conn.register_provider(tst_ns, clns, provider_type, provider)

        # Test provider registration with get_registered_provider
        if not exp_rslt or exp_rslt is True:
            rtn = conn.providerdispatcher.get_registered_provider(
                get_ns, get_pt, get_cln)
            if exp_rslt is None:
                assert rtn is None
            if exp_rslt is True:
                assert rtn
                assert issubclass(rtn, InstanceWriteProvider)

        else:
            with pytest.raises(exp_rslt):
                conn.providerdispatcher.get_registered_provider(
                    get_ns, get_pt, get_cln)

    def test_user_provider1(self, conn, tst_classeswqualifiers,
                            tst_instances):
        """
        Test execution with a user provider and CreateInstance.
        """

        class CIM_FooUserProvider(InstanceWriteProvider):
            """
            Define the user provider with only CreateInstance supported
            """

            def __init__(self, cimrepository):
                """
                Init of test provider
                """
                super(CIM_FooUserProvider, self).__init__(cimrepository)

            def CreateInstance(self, namespace, NewInstance):
                """
                My user CreateInstance.  Will change the InstanceID and
                use the default to commit the NewInstance to the repository.
                """

                # modify the InstanceID property
                NewInstance.properties["InstanceID"].value = "MyModifiedID"

                # send back to the superclass to complete insertion into
                # the repository.
                return super(CIM_FooUserProvider, self).CreateInstance(
                    namespace, NewInstance)

        skip_if_moftab_regenerated()

        ns = conn.default_namespace

        add_objects_to_repo(conn, ns, [tst_classeswqualifiers, tst_instances])

        conn.register_provider(ns, 'CIM_Foo', 'instance', CIM_FooUserProvider)

        new_instance = CIMInstance("CIM_Foo",
                                   properties={'InstanceID': 'origid'})

        rtnd_path = conn.CreateInstance(new_instance)

        rtnd_instance = conn.GetInstance(rtnd_path)

        assert rtnd_path.keybindings["InstanceId"] == "MyModifiedID"
        assert rtnd_instance.path == rtnd_path

        conn.DeleteInstance(rtnd_path)

    def test_user_provider2(self, conn, tst_classeswqualifiers,
                            tst_instances):
        """
        Test with a single user defined provider using CIM_Foo_sub as the
        class and handles ModifyInstance only
        """

        class CIM_FooSubUserProvider(InstanceWriteProvider):
            """
            Define the user provider
            """

            def __init__(self, cimrepository):
                """
                Init of test provider
                """
                super(CIM_FooSubUserProvider, self).__init__(cimrepository)

            def ModifyInstance(self, ModifiedInstance,
                               IncludeQualifiers=None, PropertyList=None):
                """
                My user CreateInstance.  Will change the InstanceID and
                use the default to commit the NewInstance to the repository.
                """

                # modify a None key property.
                ModifiedInstance.properties["cimfoo_sub"].value = "ModProperty"

                # send back to the superclass to complete insertion into
                # the repository.
                return super(CIM_FooSubUserProvider, self).ModifyInstance(
                    ModifiedInstance)

        skip_if_moftab_regenerated()

        ns = conn.default_namespace

        add_objects_to_repo(conn, ns, [tst_classeswqualifiers, tst_instances])

        conn.register_provider(ns, 'CIM_Foo_sub', 'instance',
                               CIM_FooSubUserProvider)

        new_instance = CIMInstance(
            "CIM_Foo_sub",
            properties={'InstanceID': 'origid',
                        'cimfoo_sub': "ModProperty"})

        rtnd_path = conn.CreateInstance(new_instance)

        rtnd_instance = conn.GetInstance(rtnd_path)

        conn.ModifyInstance(rtnd_instance)

        rtnd_modified_instance = conn.GetInstance(rtnd_path)

        assert rtnd_modified_instance.properties["cimfoo_sub"].value == \
            "ModProperty"

        assert rtnd_instance.path == rtnd_path


def resolve_class(conn, cls, ns):
    """
    Execute the _resolve_class method on the cls to create a class that
    is resolved (i.e. the inherited characteristics are inserted into the
    class).
    """
    ns = ns or conn.default_namespace
    # pylint: disable=protected-access
    qualifier_store = conn._get_qualifier_store(ns)
    # pylint: disable=protected-access
    rslvd_cls = conn.mainprovider._resolve_class(cls, ns, qualifier_store)
    return rslvd_cls


def assert_resolved_classes_equal(conn, ns, exp_class, tst_class):
    """
    Test two pywbem classes for equality. The exp_class is resolved before the
    test.
    """
    ns = ns or conn.default_namespace
    exp_resolved = resolve_class(conn, exp_class, ns)
    assert_classes_equal(exp_resolved, tst_class)


class TestClassOperations(object):
    """
    Test mocking of Class level operations including classname operations
    """
    @pytest.mark.parametrize(
        "ns, cln, tst_ns, exp_status", [
            [DEFAULT_NAMESPACE, 'CIM_Foo', None, None],
            [DEFAULT_NAMESPACE, 'cim_foo', None, None],
            [DEFAULT_NAMESPACE, 'CIM_Foo', 'BadNamespace',
             CIM_ERR_INVALID_NAMESPACE],
            [DEFAULT_NAMESPACE, 'CIM_Foo', DEFAULT_NAMESPACE, None],
            [DEFAULT_NAMESPACE, 'CIM_Foox', None, CIM_ERR_NOT_FOUND],
            # test with non-default namespace
            [NOT_DEFAULT_NS, 'CIM_Foo', NOT_DEFAULT_NS, None],
        ]
    )
    def test_getclass(self, conn, tst_qualifiers, tst_class, ns, cln,
                      tst_ns, exp_status):
        # pylint: disable=no-self-use
        """
        Test returns from get class including;
          Good return
          Invalid namespace
          Class Not found
        """
        add_objects_to_repo(conn, ns, [tst_qualifiers, tst_class])

        if exp_status is None:
            cl = conn.GetClass(cln, namespace=tst_ns,
                               IncludeQualifiers=True,
                               IncludeClassOrigin=True)
            cl.path = None
            assert_resolved_classes_equal(conn, ns, tst_class, cl)
        else:
            with pytest.raises(CIMError) as exec_info:
                conn.GetClass(cln, namespace=tst_ns)
            exc = exec_info.value
            assert exc.status_code == exp_status

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "cn, iq, ico",
        [
            ['CIM_Foo', False, False],
            ['cim_foo', False, False],
            ['CIM_Foo', True, False],
            ['CIM_Foo', True, True],
            ['CIM_Foo_sub', False, False],
            ['CIM_Foo_sub', True, False],
            ['CIM_Foo_sub', True, True],
        ]
    )
    def test_getclass_iqico(self, conn, tst_classeswqualifiers, ns, cn, iq,
                            ico, tst_classes):
        # pylint: disable=no-self-use
        """
        Test mocking wbemconnection getClass
        test using Mock directly and returning a class.
        """

        # Verify test valid in that cn exists in repo

        for cls in tst_classes:
            if cls.classname.lower() == cn.lower():
                tst_class = cls
        assert tst_class is not None

        conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)

        cl = conn.GetClass(cn, namespace=ns, IncludeQualifiers=iq,
                           LocalOnly=False, IncludeClassOrigin=ico)

        # resolve the  test class before we manipulate it per iq and ico
        tst_class = resolve_class(conn, tst_class, ns)

        # remove all qualifiers and class_origins and test for equality
        if not iq:
            tst_class.qualifiers = NocaseDict()
            for prop in cl.properties:
                tst_class.properties[prop].qualifiers = NocaseDict()
            for method in cl.methods:
                tst_class.methods[method].qualifiers = NocaseDict()
                for param in cl.methods[method].parameters:
                    tst_class.methods[method].parameters[param].qualifiers = \
                        NocaseDict()

        # remove class origin if ico = None. Else test
        if not ico:
            for prop in tst_class.properties:
                tst_class.properties[prop].class_origin = None
            for method in tst_class.methods:
                tst_class.methods[method].class_origin = None

        # Test the modified tst_class against the returned class
        tst_ns = ns or conn.default_namespace
        tst_class.path = CIMClassName(cn, host='FakedUrl:5988',
                                      namespace=tst_ns)

        assert cl == tst_class

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        # parameters are classname(cn), LocalOnly(lo),
        # pl_exp(expected properties)
        "cn, lo, pl_exp", [
            ['CIM_Foo_sub', None, ['cimfoo_sub']],
            ['CIM_Foo_sub', True, ['cimfoo_sub']],
            ['cim_foo_sub', True, ['cimfoo_sub']],
            ['CIM_Foo_sub', False, ['cimfoo_sub', 'InstanceID']],
            ['CIM_Foo_sub_sub', None, ['cimfoo_sub_sub']],
            ['CIM_Foo_sub_sub', True, ['cimfoo_sub_sub']],
            ['CIM_Foo_sub_sub', False, ['cimfoo_sub_sub', 'cimfoo_sub',
                                        'InstanceID']],
        ]
    )
    def test_getclass_lo(self, conn, ns, tst_qualifiers, tst_classes, cn, lo,
                         pl_exp):
        # pylint: disable=no-self-use
        """
        Test mocking wbemconnection GetClass to test LocalOnly parameter.
        NOTE: This is the mock implementation.  The DMTF specification leaves
        this as ambiguous.
        """
        conn.add_cimobjects(tst_qualifiers, namespace=ns)
        conn.add_cimobjects(tst_classes, namespace=ns)

        cl = conn.GetClass(cn, namespace=ns, LocalOnly=lo,
                           IncludeQualifiers=True,
                           IncludeClassOrigin=True)

        assert cl.classname.lower() == cn.lower()
        assert len(cl.properties) == len(pl_exp)
        rtn_props = cl.properties.keys()
        assert set(rtn_props) == set(pl_exp)

        tst_cls_dict = dict()
        for cl in tst_classes:
            tst_cls_dict[cl.classname] = resolve_class(conn, cl, ns)

        # test for qualifiers
        for pname, prop in cl.properties.items():
            prop_class_origin = prop.class_origin
            class_prop_qualifiers = \
                tst_cls_dict[prop_class_origin].properties[pname].qualifiers
            assert prop.qualifiers == class_prop_qualifiers

    @pytest.mark.parametrize(
        "ns", EXPANDED_NAMESPACES + [None])
    # property list, expected properties in response
    @pytest.mark.parametrize(
        "pl, p_exp", [
            [None, ['InstanceID', 'cimfoo_sub', 'cimfoo_sub_sub']],
            ['', []],
            ['InstanceID', ['InstanceID']],
            [['InstanceID'], ['InstanceID']],
            [['InstanceID', 'InstanceID'], ['InstanceID']],
            [['InstanceID', 'cimfoo_sub'], ['InstanceID', 'cimfoo_sub']]
        ]
    )
    def test_getclass_pl(self, conn, ns, tst_classeswqualifiers, pl, p_exp):
        # pylint: disable=no-self-use
        """
        Test get_class property list filtering
        """
        add_objects_to_repo(conn, ns, [tst_classeswqualifiers])
        cn = 'CIM_Foo_sub_sub'

        cl = conn.GetClass(cn, namespace=ns, PropertyList=pl,
                           LocalOnly=False,
                           IncludeQualifiers=True,
                           IncludeClassOrigin=True)

        assert len(cl.properties) == len(p_exp)
        rtn_props = cl.properties.keys()
        assert set(rtn_props) == set(p_exp)

    @pytest.mark.parametrize(
        "ns", EXPANDED_NAMESPACES + [None])
    @pytest.mark.parametrize(
        # cn - Classname for request (May be None)
        # di - Boolean defines DeepInheritance value for request
        # exp_rslt - List of expected classnames on response or CIMError object
        "cn, di, exp_rslt,", [
            [None, None, ['CIM_Foo', 'CIM_Foo_nokey']],
            [None, False, ['CIM_Foo', 'CIM_Foo_nokey']],
            [None, True, ['CIM_Foo', 'CIM_Foo_sub', 'CIM_Foo_sub2',
                          'CIM_Foo_sub_sub', 'CIM_Foo_nokey']],
            ['CIM_Foo', None, ['CIM_Foo_sub', 'CIM_Foo_sub2']],
            ['cim_foo', None, ['CIM_Foo_sub', 'CIM_Foo_sub2']],
            [CIMClassName('CIM_Foo'), None, ['CIM_Foo_sub', 'CIM_Foo_sub2']],
            ['CIM_Foo', True, ['CIM_Foo_sub', 'CIM_Foo_sub2',
                               'CIM_Foo_sub_sub']],
            [CIMClassName('CIM_Foo'), True, ['CIM_Foo_sub', 'CIM_Foo_sub2',
                                             'CIM_Foo_sub_sub']],
            ['CIM_Foo_sub_sub', None, []],
            ['CIM_Foo_sub_subxx', None, CIMError(CIM_ERR_INVALID_CLASS)],
        ]
    )
    def test_enumerateclassnames(self, conn, ns, cn, di, exp_rslt,
                                 tst_classeswqualifiers):
        # pylint: disable=no-self-use
        """
        Test EnumerateClassNames mock with parameters for namespace,
        classname, DeepInheritance
        """

        add_objects_to_repo(conn, ns, tst_classeswqualifiers)

        if isinstance(exp_rslt, CIMError):
            with pytest.raises(CIMError) as exec_info:
                conn.EnumerateClassNames(ClassName=cn, namespace=ns,
                                         DeepInheritance=di)
            exc = exec_info.value
            assert exc.status_code == exp_rslt.status_code
            return

        if cn is None:
            rtn_clns = conn.EnumerateClassNames(namespace=ns,
                                                DeepInheritance=di)
        else:
            rtn_clns = conn.EnumerateClassNames(ClassName=cn,
                                                namespace=ns,
                                                DeepInheritance=di)

        for cn_ in rtn_clns:
            assert isinstance(cn_, six.string_types)
        assert len(rtn_clns) == len(exp_rslt)
        assert set(rtn_clns) == set(exp_rslt)

    @pytest.mark.parametrize(
        "ns", EXPANDED_NAMESPACES + [None])
    @pytest.mark.parametrize(
        # iq: includequalifiers input parameter
        "iq", [None, False, True])
    @pytest.mark.parametrize(
        # ico: includeclassorigin input parameter
        "ico", [None, False, True])
    @pytest.mark.parametrize(
        # cn_param: classname input parameter
        # di: deepinheritance input parameter
        # pl_exp: Properties expected in response
        # len_exp: number of classes expected in response
        # exp_rslt: If integer, expected number of class in respons. If
        #           failed, CIMError exception object with expected status code
        "cn_param, lo, di, pl_exp, exp_rslt", [
            [None, None, None, ['InstanceID', 'cimfoo'], 2],
            [None, None, True, ['InstanceID', 'cimfoo_sub', 'cimfoo_sub2',
                                'cimfoo_sub_sub', 'cimfoo'], 5],
            ['CIM_Foo', None, None, ['InstanceID', 'cimfoo_sub',
                                     'cimfoo_sub2'], 2],
            ['CIM_Foo', None, True, ['InstanceID', 'cimfoo_sub',
                                     'cimfoo_sub2', 'cimfoo_sub_sub'], 3],
            ['CIM_Foo_sub_sub', None, None, [], 0],
            ['CIM_Foo_sub_sub', None, True, [], 0],

            [None, True, None, ['InstanceID', 'cimfoo_sub', 'cimfoo_sub2',
                                'cimfoo_sub_sub', 'cimfoo'], 2],
            [None, True, True, ['InstanceID', 'cimfoo'], 5],
            ['CIM_Foo', True, None, ['InstanceID'], 2],
            ['CIM_Foo', True, True, ['InstanceID'], 3],
            ['CIM_Foo_sub_sub', True, None, [], 0],
            ['CIM_Foo_sub_sub', True, True, [], 0],

            [None, False, None, ['InstanceID', 'cimfoo_sub', 'cimfoo_sub2',
                                 'cimfoo_sub_sub', 'cimfoo'], 2],
            [None, False, True, ['InstanceID', 'cimfoo_sub', 'cimfoo_sub2',
                                 'cimfoo_sub_sub', 'cimfoo'], 5],
            ['CIM_Foo', False, None, ['InstanceID', 'cimfoo_sub',
                                      'cimfoo_sub2'], 2],
            ['CIM_Foo', False, True, ['InstanceID', 'cimfoo_sub',
                                      'cimfoo_sub2', 'cimfoo_sub_sub'], 3],
            ['CIM_Foo_sub_sub', False, None, [], 0],
            ['CIM_Foo_sub_sub', False, True, [], 0],
            ['CIM_Foo_sub_subxx', False, True, [],
             CIMError(CIM_ERR_INVALID_CLASS)],

        ]
    )
    def test_enumerateclasses(self, conn, iq, ico, ns, cn_param, lo, di,
                              pl_exp, exp_rslt, tst_qualifiers, tst_classes):
        # pylint: disable=no-self-use
        """
        Test EnumerateClasses for proper processing of input parameters.
        All tests in this test method pass and there should be no exceptions.
        Tests for correct properties, methods, and qualifiers, returned for
        lo and di and correct number of classes returned
        """
        add_objects_to_repo(conn, ns, [tst_qualifiers, tst_classes])

        if isinstance(exp_rslt, CIMError):
            exp_exc = exp_rslt
            with pytest.raises(CIMError) as exec_info:
                conn.EnumerateClassNames(ClassName=cn_param, namespace=ns,
                                         DeepInheritance=di)
            exc = exec_info.value
            assert exc.status_code == exp_exc.status_code
            return

        if cn_param is None:
            rtn_classes = conn.EnumerateClasses(DeepInheritance=di,
                                                namespace=ns,
                                                LocalOnly=lo,
                                                IncludeQualifiers=iq,
                                                IncludeClassOrigin=ico)
        else:
            rtn_classes = conn.EnumerateClasses(ClassName=cn_param,
                                                namespace=ns,
                                                DeepInheritance=di,
                                                LocalOnly=lo,
                                                IncludeQualifiers=iq,
                                                IncludeClassOrigin=ico)

        assert isinstance(exp_rslt, six.integer_types)
        assert len(rtn_classes) == exp_rslt

        for rtn_class in rtn_classes:
            assert isinstance(rtn_class, CIMClass)

            if lo:
                # get the corresponding test input class
                tst_class = None
                for tst_cl in tst_classes:
                    if tst_cl.classname == rtn_class.classname:
                        tst_class = tst_cl
                        break
                assert tst_class

                assert set(rtn_class.properties.keys()) == \
                    set(tst_class.properties.keys())
            else:
                # not lo, returns all properties from superclasses.
                # test for return as subset of pl_exp
                rtn_set = set(rtn_class.properties.keys())
                assert rtn_set.issubset(set(pl_exp))

            # Confirm get_class returns the same set of properties
            rtn_getclass = conn.GetClass(rtn_class.classname, namespace=ns,
                                         LocalOnly=lo,
                                         IncludeQualifiers=iq,
                                         IncludeClassOrigin=ico)

            assert set(rtn_getclass.properties.keys()) == \
                set(rtn_class.properties.keys())

            assert set(rtn_getclass.methods.keys()) == \
                set(rtn_class.methods.keys())

            if ico:
                for prop in six.itervalues(rtn_getclass.properties):
                    assert prop.class_origin is not None

                for method in six.itervalues(rtn_getclass.methods):
                    assert method.class_origin is not None
            else:
                for prop in six.itervalues(rtn_getclass.properties):
                    assert prop.class_origin is None

                for method in six.itervalues(rtn_getclass.methods):
                    assert method.class_origin is None

            if iq is True or iq is None:
                if rtn_getclass.qualifiers:
                    assert rtn_class.qualifiers
                for prop in six.itervalues(rtn_getclass.properties):
                    if rtn_getclass.properties[prop.name].qualifiers:
                        assert prop.qualifiers is not None

                for method in six.itervalues(rtn_getclass.methods):
                    if rtn_getclass.methods[method.name].qualifiers:
                        assert method.qualifiers is not None
            else:
                assert not rtn_class.qualifiers
                for prop in six.itervalues(rtn_getclass.properties):
                    assert not prop.qualifiers

                for method in six.itervalues(rtn_getclass.methods):
                    assert not method.qualifiers

    def process_pretcl(self, conn, pre_tst_classes, ns, tst_classes):
        """Support method for createclass. Executes createclass on the
           pre_tst_classes parameter. Compiles all classes found in the
           parameter
        """
        if pre_tst_classes:
            if isinstance(pre_tst_classes, list):
                for cls in pre_tst_classes:
                    self.process_pretcl(conn, cls, ns, tst_classes)
            elif isinstance(pre_tst_classes, six.string_types):
                for cls in tst_classes:
                    if cls.classname == pre_tst_classes:
                        conn.CreateClass(cls, namespace=ns)
            elif isinstance(pre_tst_classes, CIMClass):
                conn.CreateClass(pre_tst_classes, namespace=ns)

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "desc, pre_tst_classes, tstcl, exp_rtn_cl, exp_exc, run_tst", [
            # desc: Description of test
            # pre_tst_classes: Create the defined class or classes before the
            #                  test. These are the superclasses for the new
            #                  class to be created
            #                  May be:
            #                   * pywbem CIMClass definition,
            #                   * string defining name of class in tst_classes
            #                   * list of class/classnames
            # tstcl: Either string defining test class name in tst_classes or
            #      CIMClass to be passed to CreateClass
            # exp_rtn_cl: None or expected CIMClass returned from get_instance
            # exp_exc: None or expected exception object
            # run_tst: If False, skip this test

            ['Create simple class correctly',
             None, 'CIM_Foo',
             CIMClass(
                 'CIM_Foo', superclass=None,
                 qualifiers={
                     'Description': CIMQualifier(
                         'Description', "CIM_Foo description",
                         overridable=True,
                         tosubclass=True,
                         translatable=True,
                         propagated=False)},
                 properties={
                     'InstanceID': CIMProperty(
                         'InstanceID', None,  # noqa: E121
                         qualifiers={
                             'Key': CIMQualifier(
                                 'Key', True, type='boolean',
                                 overridable=False,
                                 tosubclass=True,
                                 propagated=False), },
                         type='string', class_origin='CIM_Foo',
                         propagated=False), },
                 methods={
                     'Delete': CIMMethod(
                         'Delete', 'uint32',
                         qualifiers={
                             'Description': CIMQualifier(
                                 'Description', "qualifier description",
                                 overridable=True,
                                 tosubclass=True,
                                 translatable=True,
                                 propagated=False)},
                         class_origin='CIM_Foo',
                         propagated=False),
                     'Fuzzy': CIMMethod(
                         'Fuzzy', 'string',
                         qualifiers={
                             'Description': CIMQualifier(
                                 'Description', "qualifier description",
                                 overridable=True,
                                 tosubclass=True,
                                 translatable=True,
                                 propagated=False)},
                         class_origin='CIM_Foo',
                         propagated=False), },
             ),
             None, OK],

            ['Validate CreateClass creates valid subclass from 2 superclasses',
             'CIM_Foo',
             'CIM_Foo_sub',
             CIMClass(
                 'CIM_Foo_sub', superclass='CIM_Foo',
                 qualifiers={'Description': CIMQualifier(
                     'Description', "Subclass Description",
                     overridable=True,
                     tosubclass=True,
                     translatable=True,
                     propagated=False)},
                 properties={
                     'cimfoo_sub': CIMProperty(
                         'cimfoo_sub', None,  # noqa: E121
                         qualifiers={'Description': CIMQualifier(
                             'Description', "qualifier description",
                             overridable=True,
                             tosubclass=True,
                             translatable=True,
                             propagated=False)},
                         type='string', class_origin='CIM_Foo_sub',
                         propagated=False),
                     'InstanceID': CIMProperty(
                         'InstanceID', None,  # noqa: E121
                         qualifiers={
                             'Key': CIMQualifier(
                                 'Key', True, type='boolean',
                                 overridable=False,
                                 tosubclass=True,
                                 propagated=True), },
                         type='string', class_origin='CIM_Foo',
                         propagated=True), },
                 methods={
                     'Delete': CIMMethod(
                         'Delete', 'uint32',
                         qualifiers={
                             'Description': CIMQualifier(
                                 'Description', "qualifier description",
                                 overridable=True,
                                 tosubclass=True,
                                 translatable=True,
                                 propagated=True)},
                         class_origin='CIM_Foo',
                         propagated=True),
                     'Fuzzy': CIMMethod(
                         'Fuzzy', 'string',
                         qualifiers={'Description': CIMQualifier(
                             'Description', "qualifier description",
                             overridable=True,
                             tosubclass=True,
                             translatable=True,
                             propagated=True)},
                         class_origin='CIM_Foo',
                         propagated=True), },
             ),
             None, OK],

            ["Create valid 2nd level subclass from fixture defined classes.",
             ['CIM_Foo', 'CIM_Foo_sub'],
             'CIM_Foo_sub_sub',
             'CIM_Foo_sub_sub', None, True, ],

            ["Create valid 2nd level subclass from class with extra data.",
             ['CIM_Foo', 'CIM_Foo_sub'],
             'CIM_Foo_sub_sub',
             CIMClass(
                 'CIM_Foo_sub_sub', superclass='CIM_Foo_sub',
                 qualifiers={'Description': CIMQualifier(
                     'Description', 'Subclass Description',
                     overridable=True,
                     tosubclass=True,
                     translatable=True,
                     propagated=False)},
                 properties={
                     'InstanceID':
                         CIMProperty('InstanceID', None, type='string',
                                     class_origin='CIM_Foo', propagated=True,
                                     is_array=False, array_size=None,
                                     qualifiers={
                                         'key': CIMQualifier(
                                             'Key', True, propagated=True,
                                             tosubclass=True,
                                             overridable=False)}),
                     'cimfoo_sub': CIMProperty(
                         'cimfoo_sub', None,
                         qualifiers={
                             'Description': CIMQualifier(
                                 'Description', "qualifier description",
                                 overridable=True,
                                 tosubclass=True,
                                 translatable=True,
                                 propagated=True)},
                         type='string', class_origin='CIM_Foo_sub',
                         propagated=True),
                     'cimfoo_sub_sub': CIMProperty(
                         'cimfoo_sub_sub', None,
                         qualifiers={
                             'Description': CIMQualifier(
                                 'Description', "property description",
                                 overridable=True,
                                 tosubclass=True,
                                 translatable=True,
                                 propagated=False)},
                         type='string', class_origin='CIM_Foo_sub_sub',
                         propagated=False),
                 },
                 methods={
                     'Delete': CIMMethod(
                         'Delete', 'uint32',
                         class_origin='CIM_Foo', propagated=True,
                         qualifiers={
                             'Description': CIMQualifier(
                                 'Description', 'qualifier description',
                                 propagated=True,
                                 tosubclass=True,
                                 overridable=True,
                                 translatable=True)}),
                     'Fuzzy': CIMMethod('Fuzzy', 'string',
                                        class_origin='CIM_Foo', propagated=True,
                                        qualifiers={
                                            'Description': CIMQualifier(
                                                'Description',
                                                'qualifier description',
                                                propagated=True,
                                                tosubclass=True,
                                                overridable=True,
                                                translatable=True)}),
                 },
             ),
             None, OK],

            [
                'Create valid 2nd level subclass with key override. '
                ' Confirms key is set.',
                ['CIM_Foo'],
                CIMClass(
                    'CIM_Foo_testOverride', superclass='CIM_Foo',
                    properties={
                        'InstanceID':
                            CIMProperty(
                                'InstanceID', None,
                                qualifiers={
                                    'Override': CIMQualifier(
                                        'Override', 'InstanceID'),
                                    'Description': CIMQualifier(
                                        'Description', "blah Blah Blah")
                                },
                                type='string'),
                    }
                ),
                # exp_rtn class definition
                CIMClass(
                    'CIM_Foo_testOverride', superclass='CIM_Foo',
                    properties={
                        'InstanceID':
                            CIMProperty(
                                'InstanceID', None, type='string',
                                class_origin='CIM_Foo', propagated=True,
                                is_array=False, array_size=None,
                                qualifiers={
                                    'key': CIMQualifier('Key', True,
                                                        propagated=True,
                                                        tosubclass=True,
                                                        overridable=False),
                                    'Override': CIMQualifier(
                                        'Override', 'InstanceID',
                                        propagated=False,
                                        tosubclass=False,
                                        overridable=True),
                                    'Description': CIMQualifier(
                                        'Description', "blah Blah Blah",
                                        propagated=False,
                                        tosubclass=True,
                                        overridable=True,
                                        translatable=True)})
                    },
                    methods={
                        'Delete': CIMMethod(
                            'Delete', 'uint32',
                            class_origin='CIM_Foo', propagated=True,
                            qualifiers={
                                'Description': CIMQualifier(
                                    'Description', 'qualifier description',
                                    propagated=True,
                                    tosubclass=True,
                                    overridable=True,
                                    translatable=True)}),
                        'Fuzzy': CIMMethod(
                            'Fuzzy', 'string',
                            class_origin='CIM_Foo', propagated=True,
                            qualifiers={
                                'Description': CIMQualifier(
                                    'Description', 'qualifier description',
                                    propagated=True,
                                    tosubclass=True,
                                    overridable=True,
                                    translatable=True)}),
                    },
                ),
                None, OK
            ],

            [
                'Fail create invalid subclass, dup property with no override',
                ['CIM_Foo', 'CIM_Foo_sub'],
                CIMClass(
                    'CIM_Foo_sub_sub', superclass='CIM_Foo_sub',
                    properties={
                        'cimfoo_sub': CIMProperty(
                            'cimfoo_sub', "blah",  # noqa: E121
                            type='string',
                            class_origin='CIM_Foo_sub_sub', propagated=False)
                    }
                ),
                None, CIMError(CIM_ERR_INVALID_PARAMETER), OK
            ],

            ['Fail because superclass does not exist in namespace',
             None, 'CIM_Foo_sub', None, CIMError(CIM_ERR_INVALID_SUPERCLASS),
             OK],

            ['Fail because trying to create incorrect type',
             None, CIMQualifierDeclaration('blah', 'string'), None,
             CIMError(CIM_ERR_INVALID_PARAMETER), OK],

            # No invalid namespace test defined because createclass creates
            # namespace
        ],
    )
    def test_createclass(self, conn, desc, pre_tst_classes, tstcl, exp_rtn_cl,
                         exp_exc, tst_qualifiers_mof, tst_classes, ns, run_tst):
        # pylint: disable=no-self-use,protected-access,unused-argument
        """
            Test create class. Tests for namespace variable,
            correctly adding, and invalid add where class has superclass
            No way to do bad namespace error because this  method creates
            namespace if it does not exist.
        """
        if not run_tst:
            pytest.skip("This test marked to be skipped")
        skip_if_moftab_regenerated()

        # preinstall required qualifiers
        conn.compile_mof_string(tst_qualifiers_mof, namespace=ns)

        # if pretcl, create/install the pre test class.  Installs the
        # prerequisite classes into the repository.
        self.process_pretcl(conn, pre_tst_classes, ns, tst_classes)

        # Create the new_class to send to CreateClass from the
        # existing tst_classes or class defined for this test
        if isinstance(tstcl, six.string_types):
            for cl in tst_classes:
                if cl.classname == tstcl:
                    new_class = cl
        else:
            new_class = tstcl

        if exp_exc is not None:
            with pytest.raises(exp_exc.__class__) as exec_info:
                conn.CreateClass(new_class, namespace=ns)

            exc = exec_info.value
            if isinstance(exp_exc, CIMError):
                assert exc.status_code == exp_exc.status_code

        else:
            conn.CreateClass(new_class, namespace=ns)

            # Get class with localonly set and confirm against the
            # test class.
            rtn_class = conn.GetClass(new_class.classname,
                                      namespace=ns,
                                      IncludeQualifiers=True,
                                      IncludeClassOrigin=True,
                                      LocalOnly=False)
            rtn_class.path = None

            # test for propagated set
            for pname, pvalue in rtn_class.properties.items():
                assert pvalue.propagated is not None
                if new_class.superclass is None:
                    assert pvalue.class_origin == new_class.classname
            for mname, mvalue in rtn_class.methods.items():
                assert mvalue.propagated is not None
                if new_class.superclass is None:
                    assert mvalue.class_origin == new_class.classname

            # if expected rtn is a CIMClass, compare the classes
            if isinstance(exp_rtn_cl, CIMClass):
                assert_classes_equal(rtn_class, exp_rtn_cl)

            elif isinstance(exp_rtn_cl, six.string_types):
                for cls in tst_classes:
                    if cls.classname == exp_rtn_cl:
                        clsr = resolve_class(conn, cls, ns)
                        assert_classes_equal(clsr, rtn_class)

            else:
                if isinstance(tstcl, CIMClass):
                    assert_classes_equal(tstcl, rtn_class)

                    # tstcl does not have propagated False on override qualifier
                    tstclr = resolve_class(conn, tstcl, ns)
                    assert_classes_equal(tstclr, rtn_class)
                else:
                    assert set(rtn_class.properties) == \
                        set(new_class.properties)
                    assert set(rtn_class.methods) == set(new_class.methods)
                    assert set(rtn_class.qualifiers) == \
                        set(new_class.qualifiers)

            # Get the class with local only false. and test for valid
            # ico, lo and non-lo properties/methods.

            rtn_class = conn.GetClass(new_class.classname,
                                      namespace=ns,
                                      IncludeQualifiers=True,
                                      IncludeClassOrigin=True,
                                      LocalOnly=False)
            ns = ns or conn.default_namespace
            class_store = conn._get_class_store(ns)
            superclasses = conn.mainprovider._get_superclass_names(
                new_class.classname, class_store)

            if new_class.superclass is None:
                superclass = None
            else:
                superclass = conn.GetClass(new_class.superclass, namespace=ns,
                                           IncludeQualifiers=True,
                                           IncludeClassOrigin=True,
                                           LocalOnly=False)
            # TODO most of the following is generic and just retests what
            # we defined for resolve.  Need to do it with each testcase, not
            # in general.
            if superclass:
                for prop in superclass.properties:
                    assert prop in rtn_class.properties
                for method in superclass.methods:
                    assert method in rtn_class.methods

            # Test for correct qualifier attributes in create class
            for pname, pvalue in rtn_class.properties.items():
                if superclass:
                    # If there is a superclass
                    if 'Override' in pvalue.qualifiers:
                        ov_qual = pvalue.qualifiers['Override']
                        sc_pname = ov_qual.value
                        if sc_pname in superclass.properties:
                            assert pvalue.propagated is True
                            assert pvalue.class_origin in superclasses
                            if pvalue.type != 'reference':
                                spvalue = superclass.properties[pname]
                                assert spvalue.type == pvalue.type
                            else:  # property type ref with override
                                spvalue = superclass.properties[sc_pname]
                                assert spvalue.type == pvalue.type
                        else:
                            assert False, "Override %s without property %s " \
                                          "in superclass" % (pname, sc_pname)
                    else:   # superclass but no override
                        if pname in superclass.properties:
                            assert pvalue.propagated is True
                            assert pvalue.class_origin in superclasses
                            assert pvalue.type == \
                                superclass.properties[pname].type
                        else:  # pname not in superclass properties
                            assert pvalue.propagated is False
                            assert pvalue.class_origin == rtn_class.classname
                else:  # No superclass
                    assert pvalue.propagated is False
                    assert pvalue.class_origin == rtn_class.classname

            for mname, mvalue in rtn_class.methods.items():
                if superclass:
                    if 'Override' in mvalue.qualifiers:
                        sc_mname = mvalue.qualifiers['Override']
                        if sc_mname in superclass.methods:
                            assert mvalue.propagated is True
                            assert mvalue.class_origin == superclass.classname
                            if mvalue.type != 'reference':
                                assert superclass.pname == mname
                                smvalue = superclass.methods[mname]
                                assert smvalue.type == mvalue.type
                            else:  # property type ref with override
                                smvalue = superclass.methods[sc_mname]
                                assert smvalue.type == mvalue.type
                        else:
                            assert False, "Override %s without property %s " \
                                          "in superclass" % (pname, sc_mname)
                    else:   # superclass but no override
                        if mname in superclass.methods:
                            assert mvalue.propagated is True
                            assert mvalue.class_origin in superclasses
                            assert mvalue.return_type == \
                                superclass.methods[mname].return_type
                        else:
                            assert mvalue.propagated is False
                            assert mvalue.class_origin == rtn_class.classname
                # TODO test each parameter also. Currently we stop at methods

    # Issue # 2210, implement a specifc test for ModifyClass

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "cn, exp_status", [
            ['CIM_Foo', None],
            ['CIM_Foo', None],
            ['CIM_Foox', CIM_ERR_NOT_FOUND],
            ['CIM_Foox', CIM_ERR_NOT_FOUND],
        ]
    )
    def test_deleteclass(self, conn, tst_qualifiers, tst_classes, cn, ns,
                         exp_status):
        # pylint: disable=no-self-use
        """
            Test create class. Tests for namespace variable,
            correctly adding, and invalid add where class has superclass
        """
        conn.add_cimobjects(tst_qualifiers, namespace=ns)
        conn.add_cimobjects(tst_classes, namespace=ns)
        if not exp_status:
            conn.DeleteClass(cn, namespace=ns)
            with pytest.raises(CIMError) as exec_info:
                conn.GetClass(cn, namespace=ns)
                exc = exec_info.value
                assert exc.status_code == CIM_ERR_NOT_FOUND
        else:
            with pytest.raises(CIMError) as exec_info:
                conn.DeleteClass(cn, namespace=ns)
            exc = exec_info.value
            assert exc.status_code == exp_status


class TestInstanceOperations(object):
    """
    Test the Instance mock operations including get, enumerate, create
    delete, modify, execquery, and invoke method on instance
    """

    @pytest.mark.parametrize(
        "ns, cln, inst_id, tst_ns, exp_status", [
            # verify class and instance in default, use default
            [DEFAULT_NAMESPACE, 'CIM_Foo', 'CIM_Foo1', None, None],
            # verify works with explicit tst_ns
            [DEFAULT_NAMESPACE, 'CIM_Foo', 'CIM_Foo1', DEFAULT_NAMESPACE, None],
            [DEFAULT_NAMESPACE, 'CIM_Foo', 'badid', DEFAULT_NAMESPACE,
             CIM_ERR_NOT_FOUND],
            [DEFAULT_NAMESPACE, 'CIM_Foo', 'CIM_Foo1', 'BadNamespace',
             CIM_ERR_INVALID_NAMESPACE],
            [DEFAULT_NAMESPACE, 'CIM_Foox', 'CIM_Foo1', None,
             CIM_ERR_INVALID_CLASS],
            # class and instance in ns. test different tst_ns fails
            [NOT_DEFAULT_NS, 'CIM_Foo', 'CIM_Foo1', DEFAULT_NAMESPACE,
             CIM_ERR_INVALID_CLASS],
        ]
    )
    def test_getinstance(self, conn, ns, cln, inst_id, tst_ns, exp_status,
                         tst_classeswqualifiers, tst_instances):
        # pylint: disable=no-self-use
        """
        Test with multiple namespaces for successful GetInstance and with
        error for namespace and instance name
        """
        if ns != DEFAULT_NAMESPACE:
            conn.add_namespace(ns)
        conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)
        conn.add_cimobjects(tst_instances, namespace=ns)

        req_inst_path = CIMInstanceName(cln, {'InstanceID': inst_id},
                                        namespace=tst_ns)
        if not exp_status:
            inst = conn.GetInstance(req_inst_path)
            req_inst_path.namespace = ns
            assert inst.path == req_inst_path
            # TODO test returned instance. Right now only comparing
            # the paths

        else:
            with pytest.raises(CIMError) as exec_info:
                conn.GetInstance(req_inst_path)
            exc = exec_info.value
            assert exc.status_code == exp_status

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None]
    )
    @pytest.mark.parametrize(
        "lo, iq, ico", [
            [None, None, None],
            [None, True, None],
            [None, True, True],
        ]
    )
    def test_getinstance_opts(self, conn, ns, lo, iq, ico,
                              tst_classeswqualifiers, tst_instances):
        # pylint: disable=no-self-use
        """
        Test getting an instance from the repository with GetInstance and
        the options set
        """
        # TODO extend to test lo and iq
        conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)
        conn.add_cimobjects(tst_instances, namespace=ns)

        request_inst_path = CIMInstanceName(
            'CIM_Foo', {'InstanceID': 'CIM_Foo1'}, namespace=ns)

        inst = conn.GetInstance(request_inst_path, LocalOnly=lo,
                                IncludeClassOrigin=ico, IncludeQualifiers=iq)

        inst.path.namespace = ns
        assert inst.path == request_inst_path
        # TODO test complete instances returned. Now only testing paths

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None]
    )
    @pytest.mark.parametrize(
        "cln, inst_id, pl, props_exp",
        [
            #   cln        inst_id   pl      props_exp
            ['CIM_Foo', 'CIM_Foo1', None, ['InstanceID']],
            ['CIM_Foo', 'CIM_Foo1', "", []],
            ['CIM_Foo', 'CIM_Foo1', "blah", []],
            ['CIM_Foo', 'CIM_Foo1', 'InstanceID', ['InstanceID']],
            ['CIM_Foo', 'CIM_Foo1', ['InstanceID'], ['InstanceID']],
            ['CIM_Foo', 'CIM_Foo1', ['INSTANCEID'], ['InstanceID']],
            ['CIM_Foo_sub', 'CIM_Foo_sub4', None, ['InstanceID', 'cimfoo_sub']],
            ['CIM_Foo_sub', 'CIM_Foo_sub4', "", []],
            ['CIM_Foo_sub', 'CIM_Foo_sub4', 'cimfoo_sub', ['cimfoo_sub']],
            ['CIM_Foo_sub', 'CIM_Foo_sub4', "blah", []],
            ['CIM_Foo_sub', 'CIM_Foo_sub4', 'InstanceID', ['InstanceID']],
            ['CIM_Foo_sub', 'CIM_Foo_sub4', ['INSTANCEID'], ['InstanceID']],
            ['CIM_Foo_sub', 'CIM_Foo_sub4', ['instanceid'], ['InstanceID']],
            ['CIM_Foo_sub', 'CIM_Foo_sub4', ['InstanceID', 'cimfoo_sub'],
             ['InstanceID', 'cimfoo_sub']],
        ]
    )
    def test_getinstance_pl(self, conn, ns, cln, inst_id, pl, props_exp,
                            tst_classeswqualifiers, tst_instances):
        # pylint: disable=no-self-use
        """
        Test the variations of property list against what is returned by
        GetInstance.
        """

        conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)
        conn.add_cimobjects(tst_instances, namespace=ns)
        request_inst_path = CIMInstanceName(
            cln, {'InstanceID': inst_id}, namespace=ns)

        inst = conn.GetInstance(request_inst_path, PropertyList=pl)

        inst.path.namespace = ns
        assert inst.path == request_inst_path

        # Assert p_exp(expected returned properties) matches returned
        # properties.
        assert set([x.lower() for x in props_exp]) ==  \
            set([x.lower() for x in inst.keys()])

    # TODO KS add error test to this group. cln, exp_cond  and test for
    # bad class, no class should pull in at least test below.
    @pytest.mark.parametrize(
        "ns", EXPANDED_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "cln", ['cim_foo', 'CIM_Foo'])
    def test_enumerateinstancenames(self, conn, ns, cln,
                                    tst_classeswqualifiers, tst_instances):
        # pylint: disable=no-self-use
        """
        Test mock EnumerateInstanceNames against instances in tst_instances
        fixture with both classes and instances in the repo.
        """

        add_objects_to_repo(conn, ns, [tst_classeswqualifiers, tst_instances])

        rtn_inst_names = conn.EnumerateInstanceNames(cln, ns)

        namespace = conn.default_namespace if ns is None else ns

        # pylint: disable=protected-access
        class_store = conn._get_class_store(namespace)
        exp_subclasses = conn.mainprovider._get_subclass_names(cln,
                                                               class_store,
                                                               True)
        exp_subclasses.append(cln)
        sub_class_dict = NocaseDict()
        for name in exp_subclasses:
            sub_class_dict[name] = name

        instance_store = conn._get_instance_store(namespace)
        request_inst_names = [i.path for i in instance_store.iter_values()
                              if i.classname in sub_class_dict]

        assert len(rtn_inst_names) == len(request_inst_names)

        for inst_name in rtn_inst_names:
            assert isinstance(inst_name, CIMInstanceName)
            assert inst_name in request_inst_names
            assert inst_name.classname in sub_class_dict

    @pytest.mark.parametrize(
        "ns, cln, tst_ns, exp_exc", [  # TODO integrate this into normal test
            # ns: repo namespace
            # cln: target classname
            # tst_ns: namespace for enumerateinstances
            # exp_exc: None or expected exception object
            [DEFAULT_NAMESPACE, None, DEFAULT_NAMESPACE, None],
            [DEFAULT_NAMESPACE, None, None, None],
            [DEFAULT_NAMESPACE, 'CIM_Foo', 'BadNamespace',
             CIMError(CIM_ERR_INVALID_NAMESPACE)],
            [DEFAULT_NAMESPACE, 'CIM_Foox', None,
             CIMError(CIM_ERR_INVALID_CLASS)],
        ]
    )
    def test_enumerateinstancenames_ns_er(self, conn, tst_classeswqualifiers,
                                          tst_instances, ns, cln, tst_ns,
                                          exp_exc):
        # pylint: disable=no-self-use
        """
        Test basic successful operation with namespaces and test for
        namespace and classname errors.
        """
        conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)
        conn.add_cimobjects(tst_instances, namespace=ns)
        enum_classname = 'CIM_Foo'

        namespace = ns or conn.default_namespace

        # pylint: disable=protected-access
        instance_store = conn._get_instance_store(namespace)
        # pylint: enable=protected-access

        if not exp_exc:
            # since we do not have classes in the repository, we get back only
            # instances of the defined class
            rtn_inst_names = conn.EnumerateInstanceNames(enum_classname, ns)

            exp_clns = [enum_classname, 'CIM_Foo_sub', 'CIM_Foo_sub2',
                        'CIM_Foo_sub_sub']

            # pylint: disable=protected-access
            request_inst_names = [i.path for i in instance_store.iter_values()
                                  if i.classname in exp_clns]

            assert len(rtn_inst_names) == len(request_inst_names)

            for inst_name in rtn_inst_names:
                assert isinstance(inst_name, CIMInstanceName)
                assert inst_name in request_inst_names
                # TODO: use algorithm to get list of possible
                # classes. Right now just fixed list
                assert inst_name.classname in exp_clns

        else:
            with pytest.raises(CIMError) as exec_info:
                conn.EnumerateInstanceNames(cln, tst_ns)
            exc = exec_info.value
            assert exc.status_code == exp_exc.status_code

    @pytest.mark.parametrize(
        "ns", EXPANDED_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "cln, di, exp_cln, exp_prop", [
            # di True, expect all subprops
            ['CIM_Foo', True,
             ['CIM_Foo', 'CIM_Foo_sub', 'CIM_Foo_sub2', 'CIM_Foo_sub_sub'],
             ['InstanceID', 'cimfoo_sub', 'cimfoo_sub2', 'cimfoo_sub_sub']],

            # di false, expect only one property.
            ['CIM_Foo', False,
             ['CIM_Foo', 'CIM_Foo_sub', 'CIM_Foo_sub2', 'CIM_Foo_sub_sub'],
             ['InstanceID']],
        ]
    )
    def test_enumerateinstances(self, conn, tst_classeswqualifiers,
                                tst_instances, ns, cln, di, exp_cln, exp_prop):
        # pylint: disable=no-self-use
        """
        Test mock EnumerateInstances. Returns instances
        of defined class and subclasses
        """

        add_objects_to_repo(conn, ns, (tst_classeswqualifiers, tst_instances))

        rtn_insts = conn.EnumerateInstances(cln, namespace=ns,
                                            DeepInheritance=di)

        tst_inst_dict = {}
        for inst in tst_instances:
            tst_inst_dict[str(model_path(inst.path))] = inst

        # TODO: Future compute number should be returned. Right now fixed number
        assert len(rtn_insts) == 8
        rtn_cln = []
        for inst in rtn_insts:
            assert isinstance(inst, CIMInstance)
            assert inst.classname in exp_cln   # don't need this
            rtn_cln.append(inst.classname)

            mp = str(model_path(inst.path))
            assert mp in tst_inst_dict
            tst_inst = tst_inst_dict[mp]
            assert tst_inst is not None
            # if not di it reports fixed set of properties based parameterize
            if not di:
                assert set(inst.keys()) == set(exp_prop)
            else:
                # di so properties differ instances of each different class.
                # TODO improve algorithm so we define exactly what properties
                # we should receive.
                assert set(inst.keys()).issubset(exp_prop)

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "cln, di, pl, props_exp",
        # props_exp - list of properties or dict of properties per class exp
        [
            #  cln      di    pl      props_exp
            ['CIM_Foo', False, None, ['InstanceID']],
            ['CIM_Foo', False, "", []],
            ['CIM_Foo', False, "blah", []],
            ['CIM_Foo', False, 'InstanceID', ['InstanceID']],
            ['CIM_Foo', False, ['InstanceID'], ['InstanceID']],
            ['CIM_Foo', False, ['INSTANCEID'], ['InstanceID']],
            ['CIM_Foo', False, ['instanceid'], ['InstanceID']],
            ['CIM_Foo_sub', False, None, ['InstanceID', 'cimfoo_sub']],
            ['CIM_Foo_sub', False, "", []],
            ['CIM_Foo_sub', False, 'cimfoo_sub', ['cimfoo_sub']],
            ['CIM_Foo_sub', False, "blah", []],
            ['CIM_Foo_sub', False, 'InstanceID', ['InstanceID']],
            ['CIM_Foo_sub', False, ['INSTANCEID'], ['InstanceID']],
            ['CIM_Foo_sub', False, ['instanceid'], ['InstanceID']],
            ['CIM_Foo_sub', False, ['InstanceID', 'cimfoo_sub'],
             ['InstanceID', 'cimfoo_sub']],
            ['CIM_Foo', True, None, {'CIM_Foo': ['InstanceID'],
                                     'CIM_Foo_sub': ['InstanceID',
                                                     'cimfoo_sub'],
                                     'CIM_Foo_sub2': ['InstanceID',
                                                      'cimfoo_sub2'],
                                     'CIM_Foo_sub_sub': ['InstanceID',
                                                         'cimfoo_sub',
                                                         'cimfoo_sub_sub']}],
            ['CIM_Foo', True, "", []],
            ['CIM_Foo', True, "blah", []],
            ['CIM_Foo', True, 'InstanceID', ['InstanceID']],
            ['CIM_Foo', True, ['InstanceID'], ['InstanceID']],
            ['CIM_Foo', True, ['INSTANCEID'], ['InstanceID']],
            ['CIM_Foo', True, ['instanceid'], ['InstanceID']],
            ['CIM_Foo', True, ['cimfoo_sub2'],
             {'CIM_Foo': [],
              'CIM_Foo_sub': [],
              'CIM_Foo_sub2': ['cimfoo_sub2'],
              'CIM_Foo_sub_sub': []}],
            ['CIM_Foo_sub', True, None,
             {'CIM_Foo_sub': ['InstanceID', 'cimfoo_sub'],
              'CIM_Foo_sub_sub': ['InstanceID',
                                  'cimfoo_sub',
                                  'cimfoo_sub_sub']}],
            ['CIM_Foo_sub', True, "", []],
            ['CIM_Foo_sub', True, 'cimfoo_sub', ['cimfoo_sub']],
            ['CIM_Foo_sub', True, "blah", []],
            ['CIM_Foo_sub', True, 'InstanceID', ['InstanceID']],
            ['CIM_Foo_sub', True, ['INSTANCEID'], ['InstanceID']],
            ['CIM_Foo_sub', True, ['instanceid'], ['InstanceID']],
            ['CIM_Foo_sub', True, ['InstanceID', 'cimfoo_sub'],
             ['InstanceID', 'cimfoo_sub']],
        ]
    )
    def test_enumerateinstances_pl_di(self, conn, ns, cln, di, pl, props_exp,
                                      tst_classeswqualifiers, tst_instances):
        # pylint: disable=no-self-use
        """
        Test mock EnumerateInstances with namespace as an input
        optional parameter and a defined property list.

        """
        conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)
        conn.add_cimobjects(tst_instances, namespace=ns)

        rtn_insts = conn.EnumerateInstances(cln, namespace=ns,
                                            DeepInheritance=di,
                                            PropertyList=pl)

        # If props_exp is dict, test for returned properties by class in
        # dict.  All rtnd classes must be in dict
        for inst in rtn_insts:
            assert isinstance(inst, CIMInstance)
            if isinstance(props_exp, dict):
                props_expi = props_exp[inst.classname]
            else:
                props_expi = props_exp
            props_expi = [x.lower() for x in props_expi]
            props_act = [x.lower() for x in inst.keys()]
            assert set(props_expi) == set(props_act)

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "di, pl, exp_p, exp_inst", [
            # [None, None, ['InstanceID', 'cimfoo_sub'], 8],
            [False, None, ['InstanceID'], 8],
        ]
    )
    def test_enumerateinstances_di(self, conn, tst_classeswqualifiers,
                                   tst_instances, ns,
                                   di, pl, exp_p, exp_inst):
        # pylint: disable=no-self-use,unused-argument
        """
        Test EnumerateInstances with DeepInheritance and propertylist opetions.
        """
        conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)
        conn.add_cimobjects(tst_instances, namespace=ns)

        cln = 'CIM_Foo'
        rtn_insts = conn.EnumerateInstances(cln, namespace=ns,
                                            DeepInheritance=di,
                                            PropertyList=pl)

        assert len(rtn_insts) == exp_inst

        target_class = conn.GetClass(cln, namespace=ns, LocalOnly=False)
        cl_props = sorted(list(target_class.properties.keys()))

        tst_class_names = conn.EnumerateClassNames(ns, DeepInheritance=True)

        for inst in rtn_insts:
            assert isinstance(inst, CIMInstance)
            assert inst.classname in tst_class_names

            # Test property names
            inst_props = sorted(list(inst.properties.keys()))
            if di is not True:
                # inst_props should match cl_props
                if len(inst_props) != len(cl_props):
                    # TODO: Still have issue with one test. and am therefore
                    # displaying the following as a reminder
                    print("TODO: test_enumerateinstances_di(): "
                          "inst prop and class prop names should match:\n"
                          "  inst  prop names ({}): {!r}\n"
                          "  class prop names ({}): {!r}".
                          format(len(inst_props), inst_props,
                                 len(cl_props), cl_props))
                assert inst_props == cl_props
            else:
                di_class = conn.GetClass(inst.classname, namespace=ns,
                                         LocalOnly=False)
                cl_props = sorted(list(di_class.properties.keys()))
                assert inst_props == cl_props

            # TODO Test actual instance returned

    # TODO test for ico and iq
    # TODO test for pl where repository contains classes
    # TODO test for instances do not exist.

    @pytest.mark.parametrize(
        "ns, cln, tst_ns, exp_status", [  # TODO integrate this into normal test
            # [DEFAULT_NAMESPACE, None, DEFAULT_NAMESPACE, None],
            [DEFAULT_NAMESPACE, 'CIM_Foo', 'BadNamespace',
             CIM_ERR_INVALID_NAMESPACE],
            # [DEFAULT_NAMESPACE, 'CIM_Foox', DEFAULT_NAMESPACE,
            #  CIM_ERR_INVALID_CLASS],
        ]
    )
    def test_enumerateinstances_er(self, conn, ns, cln, tst_ns,
                                   exp_status, tst_classeswqualifiers,
                                   tst_instances):
        # pylint: disable=no-self-use
        """
        Test the various error cases for Enumerate.  Errors include:
        Invalid namespace, instance not_found and if a class is specified
        on input, shou
        """
        conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)
        conn.add_cimobjects(tst_instances, namespace=ns)

        if not exp_status:
            # since we do not have classes in the repository, we get back only
            # instances of the defined class
            rtn_inst_names = conn.EnumerateInstanceNames(cln, ns)

            # pylint: disable=protected-access
            request_inst_names = [i.path for i in conn._get_instance_store(ns)
                                  if i.classname == cln]

            assert len(rtn_inst_names) == len(request_inst_names)

            for inst_name in rtn_inst_names:
                assert isinstance(inst_name, CIMInstanceName)
                assert inst_name in request_inst_names
                assert inst_name.classname == cln

        else:
            with pytest.raises(CIMError) as exec_info:
                conn.EnumerateInstances(cln, tst_ns)
            exc = exec_info.value
            assert exc.status_code == exp_status

    @pytest.mark.parametrize(
        "ns", EXPANDED_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "tst, new_inst, exp_rslt", [
            # TODO: This is a badly designed set of test parameters.
            # TODO: it only allows testing against tst_classeswqualifiers
            # tst: integer that defines special modification within test
            #      execution. 0. Use new_instance as defined,
            #                 1. Set namespace to bad namespace,
            #                 2. Use the tst_instances list index defined in
            #                    new_inst parameter for new_instance param
            #                    with CreateInstance
            # new_inst: New instance to be passed to CreateInstance
            #           Integer: index into tst_instances.
            #           CIMInstance: CIMInstance to be passed to CreateInstance.
            # exp_rslt:    None: Compare based on tst parameter
            #                    CIMInstance expected to be created. Tested by
            #                    doing GetInstance on the instance returned from
            #                    CreateInstance
            #              CIMError: status code expected

            # The following test new_instance against specific instances
            # in exp_rslt using tst definition # 2 and expecting good return
            # I.e. They compare the results to previously defined tests.
            [2, 0, None],
            [2, 1, None],
            [2, 4, None],
            [2, 5, None],
            [2, 7, None],

            # test simple new instance against predefined instance.
            [0, CIMInstance('CIM_Foo_sub',
                            properties={'InstanceID': 'inst1',
                                        'cimfoo_sub': 'blah'}),
             CIMInstance('CIM_Foo_sub',
                         properties={'InstanceID': 'inst1',
                                     'cimfoo_sub': 'blah'})],

            # test new instance has correct case on property names.
            # TODO: Broken for some reason
            [0, CIMInstance('CIM_Foo_sub',
                            properties={'instanceid': 'inst1',
                                        'CIMFOO_SUB': 'blah'}),
             CIMInstance('CIM_Foo_sub',
                         properties={'InstanceID': 'inst1',
                                     'cimfoo_sub': 'blah'})],

            # test invalid namespace
            [1, CIMInstance('CIM_Foo_sub',
                            properties={'InstanceID': 'inst1',
                                        'cimfoo_sub': 'data1'}),
             CIMError(CIM_ERR_INVALID_NAMESPACE)],

            # No key property in new instance
            [0, CIMInstance('CIM_Foo_sub',
                            properties={'cimfoo_sub': 'data2'}),
             CIMError(CIM_ERR_INVALID_PARAMETER)],

            # Test instance class not in repository
            [0, CIMInstance('CIM_Foo_subx',
                            properties={'InstanceID': 'inst1',
                                        'cimfoo_sub': 'data3'}),
             CIMError(CIM_ERR_INVALID_CLASS)],

            # Test invalid property. Property not in class
            [0, CIMInstance('CIM_Foo_sub',
                            properties={'InstanceID': 'inst1',
                                        'cimfoo_subx': 'wrong prop name'}),
             CIMError(CIM_ERR_INVALID_PARAMETER)],

            # Test invalid property in new instance, type not same as class
            [0, CIMInstance('CIM_Foo_sub',
                            properties={'InstanceID': 'inst1',
                                        'cimfoo_sub': Uint32(6)}),
             CIMError(CIM_ERR_INVALID_PARAMETER)],

            # test array type mismatch
            [0, CIMInstance('CIM_Foo_sub',
                            properties={'InstanceID': 'inst1',
                                        'cimfoo_sub': ['blah', 'blah']}),
             CIMError(CIM_ERR_INVALID_PARAMETER)],

            # NewInstance is not an instance
            [0, CIMClass('CIM_Foo_sub'), TypeError()],
        ]
    )
    def test_createinstance(self, conn, ns, tst, new_inst, exp_rslt,
                            tst_classeswqualifiers, tst_instances):
        # pylint: disable=no-self-use
        """
        Test creating an instance.  Tests by creating an
        instance and then getting that instance. This also includes error
        tests if exp_exc is not None.
        """

        add_objects_to_repo(conn, ns, tst_classeswqualifiers)

        # copy input instance to avoid poluting test
        if isinstance(new_inst, CIMInstance):
            new_inst = new_inst.copy()

        # modify input in accord with the tst parameter
        if tst == 0:   # pass on the new_inst defined in the parameter
            new_insts = [new_inst]
        elif tst == 1:   # invalid namespace test
            ns = 'BadNamespace'
            new_insts = [tst_instances[0]]
        elif tst == 2:  # Create one entry from the tst_instances list
            assert isinstance(new_inst, int)
            new_insts = [tst_instances[new_inst]]
        elif tst == 3:   # create everything in tst_instances
            new_insts = tst_instances
        else:  # Error. Test not defined.
            assert False, "The tst parameter %s not defined" % tst
        if exp_rslt is None:   # exp_status is None
            for inst in new_insts:
                rtn_inst_name = conn.CreateInstance(inst, ns)
                rtn_inst = conn.GetInstance(rtn_inst_name)
                cls = conn.GetClass(inst.classname,
                                    namespace=ns,
                                    LocalOnly=False,
                                    IncludeQualifiers=True)
                inst.path.namespace = rtn_inst.path.namespace
                assert rtn_inst.path == inst.path
                assert rtn_inst == inst
                # Execute case sensitive equality test on all properties in
                # returned instance against class properties
                for prop_name in rtn_inst:
                    c_prop_name = cls.properties[prop_name].name
                    assert c_prop_name == prop_name
        elif isinstance(exp_rslt, CIMInstance):
            inst = new_insts[0]   # assumes only a single instance to test.
            exp_inst = exp_rslt
            rtn_inst_name = conn.CreateInstance(inst, ns)
            rtn_inst = conn.GetInstance(rtn_inst_name)
            inst.path = rtn_inst.path
            assert rtn_inst.path == inst.path
            assert rtn_inst == inst
            for prop_name in inst:
                exp_prop = exp_inst.properties[prop_name]
                rtn_prop = rtn_inst.properties[prop_name]
                # assert case-sensitive match
                assert rtn_prop.name == exp_prop.name

        else:
            with pytest.raises(exp_rslt.__class__) as exec_info:
                conn.CreateInstance(new_insts[0], ns)
            exc = exec_info.value
            if isinstance(exp_rslt, CIMError):
                assert exc.status_code == exp_rslt.status_code

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    def test_createinstance_dup(self, conn, tst_classeswqualifiers,
                                tst_instances, ns):
        # pylint: disable=no-self-use
        """
        Test duplicate instance cannot be created.
        """
        conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)

        new_inst = tst_instances[0]

        rtn_inst_name = conn.CreateInstance(new_inst, ns)
        rtn_inst = conn.GetInstance(rtn_inst_name)

        new_inst.path.namespace = rtn_inst.path.namespace
        assert rtn_inst.path == new_inst.path
        assert rtn_inst == new_inst

        # test add again
        with pytest.raises(CIMError) as exec_info:
            conn.CreateInstance(new_inst)
        exc = exec_info.value
        assert exc.status_code == CIM_ERR_ALREADY_EXISTS

    @pytest.mark.parametrize(
        "interop_ns",
        ['interop', 'root/interop', 'root/PG_InterOp']
    )
    @pytest.mark.parametrize(
        "desc, additional_ns, new_inst, exp_ns, exp_exc",
        [
            (
                "Create namespace that does not exist yet, with already "
                "normalized name",
                [],
                CIMInstance('PG_Namespace',
                            properties=dict(Name='root/blah')),
                'root/blah', None
            ),
            (
                "Create namespace that does not exist yet, with not yet "
                "normalized name",
                [],
                CIMInstance('PG_Namespace',
                            properties=dict(Name='//root/blah//')),
                'root/blah', None
            ),
            (
                "Create namespace that already exists",
                ['root/blah'],
                CIMInstance('PG_Namespace',
                            properties=dict(Name='root/blah')),
                None, CIMError(CIM_ERR_ALREADY_EXISTS)
            ),
            (
                "Create namespace with missing Name property in instance",
                ['root/blah'],
                CIMInstance('PG_Namespace', properties=dict()),
                None, CIMError(CIM_ERR_INVALID_PARAMETER)
            ),
        ]
    )
    def test_createinstance_namespace(
            self, conn, tst_pg_namespace_class, tst_qualifiers,
            desc, interop_ns, additional_ns, new_inst, exp_ns, exp_exc):
        # pylint: disable=no-self-use,unused-argument
        """
        Test the faked CreateInstance with a namespace instance to create ns.
        """

        conn.add_namespace(interop_ns)
        conn.add_cimobjects(tst_qualifiers, namespace=interop_ns)
        conn.add_cimobjects(tst_pg_namespace_class, namespace=interop_ns)
        for ns in additional_ns:
            conn.add_namespace(ns)

        if not exp_exc:
            # The code to be tested
            new_path = conn.CreateInstance(new_inst, namespace=interop_ns)

            act_ns = new_path.keybindings['Name']
            assert act_ns == exp_ns
            assert act_ns in conn.namespaces
        else:
            with pytest.raises(exp_exc.__class__) as exec_info:

                # The code to be tested
                conn.CreateInstance(new_inst, namespace=interop_ns)

            exc = exec_info.value
            if isinstance(exp_exc, CIMError):
                assert exc.status_code == exp_exc.status_code

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "tst_mof, exp_rtn, exp_excp",
        [
            # Compiler builds path
            ['instance of TST_Person as $Mike { name = "Mike"; };',
             ('TST_Person', {'name': "Mike"}), None],
            # Mocker builds path
            ['instance of TST_Person { name = "Mike"; };',
             ('TST_Person', {'name': "Mike"}), None],

            # Fails, because key property not in new instance
            ['instance of TST_Person {extraProperty = "Blah"; };',
             ('TST_Person', {}),
             MOFRepositoryError(
                 r"Cannot compile instance .* CreateInstance", None,
                 CIMError(CIM_ERR_INVALID_PARAMETER))],

            # Test assoc class with ref props as keys, mocker builds path
            ['instance of TST_Person as $Sofi { name = "Sofi"; };\n'
             'instance of TST_FamilyCollection as $Family1 '
             '{ name = "family1"; };\n'
             'instance of TST_MemberOfFamilyCollection '
             '{ family = $Family1; member = $Sofi; };\n',
             ('TST_MemberOfFamilyCollection',
              {'family': CIMInstanceName('TST_FamilyCollection',
                                         {'name': 'family1'}),
               'member': CIMInstanceName('TST_Person', {'name': "Sofi"})}),
             None],

            # Test assoc class withref props as keys, compiler builds path
            ['instance of TST_Person as $Sofi { name = "Sofi"; };\n'
             'instance of TST_FamilyCollection as $Family1 '
             '{ name = "family1"; };\n'
             'instance of TST_MemberOfFamilyCollection as $Family1Sofi'
             '{ family = $Family1; member = $Sofi; };\n',
             ('TST_MemberOfFamilyCollection',
              {'family': CIMInstanceName('TST_FamilyCollection',
                                         {'name': 'family1'}),
               'member': CIMInstanceName('TST_Person', {'name': "Sofi"})}),
             None],

            # Test assoc with one key reference property missing
            ['instance of TST_Person as $Sofi { name = "Sofi"; };\n'
             'instance of TST_FamilyCollection as $Family1 '
             '{ name = "family1"; };\n'
             'instance of TST_MemberOfFamilyCollection as $Family1Sofi'
             '{ family = $Family1; };\n',
             ('TST_MemberOfFamilyCollection',
              {'family': CIMInstanceName('TST_FamilyCollection',
                                         {'name': 'family1'}),
               'member': CIMInstanceName('TST_Person', {'name': "Sofi"})}),
             MOFRepositoryError(
                 r"Cannot compile instance .* CreateInstance", None,
                 CIMError(CIM_ERR_INVALID_PARAMETER))],
        ]
    )
    def test_compile_instances_path(self, conn, ns, tst_assoc_qualdecl_mof,
                                    tst_assoc_class_mof,
                                    tst_mof, exp_rtn, exp_excp):
        # pylint: disable=no-self-use
        """
        Test variations of compile of CIMInstances to validate the
        implementation of setting path. Both the compiler and mocker allow
        setting the path on CreateInstance.  This tests both
        good compile and errors
        """

        classes_mof = tst_assoc_qualdecl_mof + tst_assoc_class_mof

        skip_if_moftab_regenerated()

        # Test with instance that does not include
        if exp_excp is None:
            conn.compile_mof_string(classes_mof + tst_mof, namespace=ns)

            exp_ns = ns or conn.default_namespace
            # Add namespace to any keybinding that is a CIMInstanceName
            kbs = exp_rtn[1]
            for kb, kbv in kbs.items():
                if isinstance(kbv, CIMInstanceName):
                    kbv.namespace = exp_ns
                    kbs[kb] = kbv
            exp_path = CIMInstanceName(exp_rtn[0], keybindings=exp_rtn[1],
                                       namespace=exp_ns)

            inst = conn.GetInstance(exp_path)
            assert inst.path == exp_path

        else:
            with pytest.raises(exp_excp.__class__) as exec_info:
                # The code to be tested
                conn.compile_mof_string(classes_mof + tst_mof, namespace=ns)

            exc = exec_info.value
            if isinstance(exp_excp, CIMError):
                assert exc.status_code == exp_excp.status_code
            elif isinstance(exp_excp, MOFCompileError):
                assert re.search(exp_excp.msg, exc.msg, re.IGNORECASE)

    @pytest.mark.parametrize(
        "ns", EXPANDED_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "sp, nv, pl, exp_resp, condition", [
            # sp: Special test. integer. 0 means No special test.
            #     other positive integers demand instance mod before modify
            # nv: (new value) single list containing a property name/value or
            #   iterable where each entry contains a propertyname/value
            # pl: property list for ModifyInstanceor None. May be empty
            #   property list
            # exp_resp: True if change expected. False if none expected.
            #   CIMError exception object if expected
            # condition: Condition. False, skip test, True, Run test,
            #                       'pdb'-debug

            # change any property that is different
            [0, ['cimfoo_sub', 'newval'], None, True, OK],
            # change any property that is different with prop case different
            [0, ['CIMFOO_SUB', 'newval'], None, True, OK],
            # change this property only
            [0, ['cimfoo_sub', 'newval'], ['cimfoo_sub'], True, OK],
            # Duplicate in property list
            [0, ['cimfoo_sub', 'newval'], ['cimfoo_sub', 'cimfoo_sub'], True,
             OK],
            # empty prop list, no change
            [0, ['cimfoo_sub', 'newval'], [], False, OK],
            # pl for prop that does not change
            [0, ['cimfoo_sub', 'newval'], ['cimfoo_sub_sub'], False, OK],
            # change any property that is different
            [0, ['cimfoo_sub_sub', 'newval'], None, True, OK],
            # change this property
            [0, ['cimfoo_sub_sub', 'newval'], ['cimfoo_sub_sub'], True, OK],
            # empty prop list, no change
            [0, ['cimfoo_sub_sub', 'newval'], [], False, OK],
            # pl for prop that does not change
            [0, ['cimfoo_sub_sub', 'newval'], ['cimfoo_sub'], False, OK],
            # Prop name not in class but in Property list
            [0, ['cimfoo_sub', 'newval'], ['cimfoo_sub', 'not_in_class'],
             CIMError(CIM_ERR_INVALID_PARAMETER), OK],
            # change any property that is different, no prop list
            [0, [('cimfoo_sub', 'newval'),
                 ('cimfoo_sub_sub', 'newval2'), ], None, True, OK],
            # change any property that is different, no prop list, p case diff
            [0, [('CIMFOO_SUB', 'newvalx'),
                 ('CIMFOO_SUB_sub', 'newval2x'), ], None, True, OK],
            # Invalid change, Key property
            [0, ['InstanceID', 'newval'], None, CIMError(CIM_ERR_NOT_FOUND),
             OK],
            # Bad namespace. Depends on special code in path
            [2, ['cimfoo_sub', 'newval'], None,
             CIMError(CIM_ERR_INVALID_NAMESPACE), OK],
            # Path and instance classnames differ. Changes inst classname
            [1, ['cimfoo_sub', 'newval'], None,
             CIMError(CIM_ERR_INVALID_PARAMETER), OK],
            # Do one where path has bad classname
            [3, ['cimfoo_sub', 'newval'], None,
             CIMError(CIM_ERR_INVALID_PARAMETER), OK],
            # 4 path and inst classnames same but not in repo
            [4, ['cimfoo_sub', 'newval'], None,
             CIMError(CIM_ERR_INVALID_CLASS), RUN],
            # 5, no properties in modified instance
            [5, [], None, False, OK],

            # TODO additional tests.
            # 1. only some properties in modifiedinstance and variations of
            #    property list
        ]
    )
    def test_modifyinstance(self, conn, ns, sp, nv, pl, exp_resp, condition,
                            tst_classeswqualifiers, tst_instances):
        # pylint: disable=no-self-use
        """
        Test the mock of modifying an existing instance. Gets the instance
        from the repo, modifies a property and calls ModifyInstance
        """
        if not condition:
            pytest.skip("This test marked to be skipped")

        if condition == 'pdb':
            import pdb  # pylint: disable=import-outside-toplevel
            pdb.set_trace()  # pylint: disable=no-member

        add_objects_to_repo(conn, ns, [tst_classeswqualifiers, tst_instances])

        insts = conn.EnumerateInstances('CIM_Foo_sub_sub', namespace=ns)
        assert insts
        orig_instance = insts[0]
        modify_instance = orig_instance.copy()

        # property values from the nv parameter.
        if nv:
            if not isinstance(nv[0], (list, tuple)):
                nv = [nv]
            for item in nv:
                modify_instance[item[0]] = item[1]

        # Code to change characteristics of modify_instance based on
        # sp parameter

        if sp == 0:
            pass
        elif sp == 1:
            modify_instance.classname = 'CIM_NoSuchClass'
        elif sp == 2:
            modify_instance.path.namespace = 'BadNamespace'
        elif sp == 3:
            modify_instance.path.classname = 'changedpathclassname'
        elif sp == 4:
            modify_instance.path.classname = 'CIM_NoSuchClass'
            modify_instance.classname = 'CIM_NoSuchClass'
        elif sp == 5:
            modify_instance.properties = NocaseDict()
        else:
            assert False

        if isinstance(exp_resp, CIMError):
            with pytest.raises(CIMError) as exec_info:
                conn.ModifyInstance(modify_instance, PropertyList=pl)
            exc = exec_info.value
            assert exc.status_code == exp_resp.status_code
        else:
            conn.ModifyInstance(modify_instance, PropertyList=pl)

            rtn_instance = conn.GetInstance(modify_instance.path)
            tst_class = conn.GetClass(modify_instance.path.classname,
                                      modify_instance.path.namespace,
                                      LocalOnly=False)
            if exp_resp:
                for p in rtn_instance:
                    assert rtn_instance.properties[p] == \
                        modify_instance.properties[p]
                    assert rtn_instance.properties[p].name == \
                        tst_class.properties[p].name
            else:
                for p in rtn_instance:
                    assert rtn_instance.properties[p] == \
                        orig_instance.properties[p]
                    assert rtn_instance.properties[p].name == \
                        tst_class.properties[p].name

    @pytest.mark.parametrize(
        # defines the namespace to be used.
        "ns", EXPANDED_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "cln, key, exp_status", [
            # cln : Class name
            # key: Key for error tests where this is invalid key.
            # exp_status: None or expected CIM status code

            ['CIM_Foo', None, None],                   # valid class
            ['CIM_Foo_sub', None, None],               # valid subclass
            ['CIM_Foo', 'xxx', CIM_ERR_NOT_FOUND],   # instance not found
            ['CIM_DoesNotExist', 'blah', CIM_ERR_INVALID_CLASS],  # cls not fnd
            ['CIM_Foo', 'blah', CIM_ERR_INVALID_NAMESPACE],  # ns not fnd
        ]
    )
    def test_deleteinstance(self, conn, tst_classeswqualifiers, tst_instances,
                            ns, cln, key, exp_status):
        # pylint: disable=no-self-use
        """
        Test delete instance by inserting instances into the repository
        and then deleting them. Deletes all instances that are in cln and
        subclasses.

        Error cases confirm that exp_status is received
        """

        add_objects_to_repo(conn, ns, [tst_classeswqualifiers, tst_instances])

        if not exp_status:
            # Test deletes all instances for defined class
            inst_name_list = conn.EnumerateInstanceNames(cln, ns)
            for iname in inst_name_list:
                conn.DeleteInstance(iname)

            for iname in inst_name_list:
                with pytest.raises(CIMError) as exec_info:
                    conn.DeleteInstance(iname)
                exc = exec_info.value
                assert exc.status_code == CIM_ERR_NOT_FOUND
        else:
            tst_ns = ns or conn.default_namespace

            if exp_status == CIM_ERR_INVALID_NAMESPACE:
                tst_ns = 'BadNamespaceName'

            iname = CIMInstanceName(cln, keybindings={'InstanceID': key},
                                    namespace=tst_ns)
            with pytest.raises(CIMError) as exec_info:
                conn.DeleteInstance(iname)
            exc = exec_info.value
            assert exc.status_code == exp_status

    @pytest.mark.parametrize(
        "interop_ns",
        ['interop', 'root/interop', 'root/PG_InterOp']
    )
    @pytest.mark.parametrize(
        "desc, additional_objs, new_inst, delete, exp_ns, exp_exc",
        [
            (
                "Delete namespace that exists and is empty, with already "
                "normalized name",
                {},
                CIMInstance('PG_Namespace',
                            properties=dict(Name='root/blah')),
                False,
                'root/blah', None
            ),
            (
                "Delete namespace that exists and is empty, with not yet "
                "normalized name",
                {},
                CIMInstance('PG_Namespace',
                            properties=dict(Name='//root/blah//')),
                False,
                'root/blah', None
            ),
            (
                "Delete namespace that does not exist",
                {},
                CIMInstance('PG_Namespace',
                            properties=dict(Name='root/blah')),
                True,
                None, CIMError(CIM_ERR_NOT_FOUND)
            ),
            (
                "Delete namespace that exists but contains a class",
                {'root/blah': [CIMClass('CIM_Foo')]},
                CIMInstance('PG_Namespace',
                            properties=dict(Name='root/blah')),
                False,
                None, CIMError(CIM_ERR_NAMESPACE_NOT_EMPTY)
            ),
            (
                "Delete namespace that exists but contains an instance",
                {'root/blah': [
                    CIMInstance(
                        'CIM_Foo',
                        path=CIMInstanceName(
                            'CIM_Foo', keybindings=dict(InstanceID='foo1'))
                    )
                ]},
                CIMInstance('PG_Namespace',
                            properties=dict(Name='root/blah')),
                False,
                None, CIMError(CIM_ERR_NAMESPACE_NOT_EMPTY)
            ),
            (
                "Delete namespace that exists but contains a qualifier",
                {'root/blah': [
                    CIMQualifierDeclaration('Qual', type='string')
                ]},
                CIMInstance('PG_Namespace',
                            properties=dict(Name='root/blah')),
                False,
                None, CIMError(CIM_ERR_NAMESPACE_NOT_EMPTY)
            ),
        ]
    )
    def test_deleteinstance_namespace(
            self, conn, tst_pg_namespace_class, tst_qualifiers,
            desc, interop_ns, additional_objs, new_inst, delete, exp_ns,
            exp_exc):
        # pylint: disable=no-self-use,unused-argument
        """
        Test the faked DeleteInstance with a namespace instance to delete ns.
        """
        conn.add_namespace(interop_ns)
        conn.add_cimobjects(tst_qualifiers, namespace=interop_ns)
        conn.add_cimobjects(tst_pg_namespace_class, namespace=interop_ns)

        # Because it is complex to build the instance path of the namespace
        # instance, we create it to obtain its instance path,
        # and the case of a non-existng namespace is swet up by deleting
        # the namespace again.
        new_path = conn.CreateInstance(new_inst, namespace=interop_ns)
        if delete:
            conn.DeleteInstance(new_path)

        for ns in additional_objs:
            if ns not in conn.namespaces:
                conn.add_namespace(ns)
            conn.add_cimobjects(additional_objs[ns], namespace=ns)

        if not exp_exc:

            # The code to be tested
            conn.DeleteInstance(new_path)

            act_ns = new_path.keybindings['Name']
            assert act_ns not in conn.namespaces
        else:
            with pytest.raises(exp_exc.__class__) as exec_info:

                # The code to be tested
                conn.DeleteInstance(new_path)

            exc = exec_info.value
            if isinstance(exp_exc, CIMError):
                assert exc.status_code == exp_exc.status_code


class TestPullOperations(object):
    """
    Mock the open and pull operations
        ClassName, namespace=None,
        FilterQueryLanguage=None, FilterQuery=None,
        OperationTimeout=None, ContinueOnError=None,
        MaxObjectCount=None,
    """

    @pytest.mark.parametrize(
        "ns", EXPANDED_NAMESPACES + [None])
    @pytest.mark.parametrize(
        # src_inst: Source instance definitions (classname and name property
        # ro: Role
        # rc: ResultClass
        # exp_rslt: list of tuples where each tuple is class and key for inst,
        #           or expected CIMError status code
        "src_inst, ro, rc, exp_rslt", [
            [('TST_Person', 'Mike'), None, 'TST_Lineage',
             [('TST_Lineage', 'MikeSofi'),
              ('TST_Lineage', 'MikeGabi')]],

            [('TST_Person', 'Saara'), None, 'TST_Lineage',
             [('TST_Lineage', 'SaaraSofi'), ]],

            [('TST_Person', 'Saara'), None, 'TST_Lineage',
             CIM_ERR_INVALID_NAMESPACE],
        ]
    )
    def test_openreferenceinstancepaths(self, conn, ns, src_inst, ro, rc,
                                        exp_rslt, tst_assoc_mof):
        # pylint: disable=no-self-use,invalid-name
        """
        Test openenueratepaths where the open is the complete response
        and all parameters are default
        """
        skip_if_moftab_regenerated()

        add_objects_to_repo(conn, ns, [tst_assoc_mof])

        source_inst_name = CIMInstanceName(src_inst[0],
                                           keybindings=dict(name=src_inst[1]),
                                           namespace=ns)

        if isinstance(exp_rslt, (list, tuple)):
            result_tuple = conn.OpenReferenceInstancePaths(source_inst_name,
                                                           ResultClass=rc,
                                                           Role=ro)

            assert result_tuple.eos is True
            assert result_tuple.context is None

            exp_ns = ns or conn.default_namespace

            # build list of expected paths from exp_rslt
            exp_paths = []
            for exp in exp_rslt:
                exp_paths.append(CIMInstanceName(
                    exp[0],
                    keybindings=dict(InstanceID=exp[1]),
                    namespace=exp_ns,
                    host=conn.host))

            rslt_paths = result_tuple.paths

            assert_equal_ciminstancenames(rslt_paths, exp_paths)
        else:
            exp_status = exp_rslt
            if exp_status == CIM_ERR_INVALID_NAMESPACE:
                source_inst_name.namespace = 'BadNamespaceName'

            with pytest.raises(CIMError) as exec_info:
                conn.OpenReferenceInstancePaths(source_inst_name,
                                                ResultClass=rc,
                                                Role=ro)
            exc = exec_info.value
            assert exc.status_code == exp_status

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        # src_inst: Source instance definition (classname and name property
        # ro: Role
        # ac: AssocClass
        # rc: ResultClass
        # rr: ResultRole
        # exp_rslt: list of tuples where each tuple is class and key for
        #           expected instance path returned, or CIMError status code
        #           if error response expected.
        "src_inst, ro, ac, rc, rr, exp_rslt", [
            [('TST_Person', 'Mike'), 'parent', 'TST_Lineage', 'TST_Person',
             'child',
             [('TST_Person', 'Sofi'),
              ('TST_Person', 'Gabi')]],

            [('TST_Person', 'Mike'), None, 'TST_Lineage', 'TST_Person',
             'child',
             [('TST_Person', 'Sofi'),
              ('TST_Person', 'Gabi')]],

            [('TST_Person', 'Mike'), None, 'TST_Lineage', 'TST_Person',
             None,
             [('TST_Person', 'Sofi'),
              ('TST_Person', 'Gabi')]],

            [('TST_Person', 'Saara'), 'parent', 'TST_Lineage', 'TST_Person',
             'child', [('TST_Person', 'Sofi'), ]],

            [('TST_Person', 'Saara'), 'parent', 'TST_Lineage', 'TST_Person',
             'child', CIM_ERR_INVALID_NAMESPACE],
        ]
    )
    def test_openassociatorinstancepaths(self, conn, ns, src_inst, ro, ac,
                                         rc, rr, exp_rslt, tst_assoc_mof):
        # pylint: disable=no-self-use,invalid-name
        """
            Test openenueratepaths where the open is the complete response
            and all parameters are default
        """
        skip_if_moftab_regenerated()
        conn.compile_mof_string(tst_assoc_mof, namespace=ns)

        source_inst_name = CIMInstanceName(src_inst[0],
                                           keybindings=dict(name=src_inst[1]),
                                           namespace=ns)

        if isinstance(exp_rslt, (list, tuple)):
            result_tuple = conn.OpenAssociatorInstancePaths(source_inst_name,
                                                            AssocClass=ac,
                                                            Role=ro,
                                                            ResultClass=rc,
                                                            ResultRole=rr)

            assert result_tuple.eos is True
            assert result_tuple.context is None

            exp_ns = ns or conn.default_namespace

            # build list of expected paths from exp_rslt
            exp_paths = []
            for exp in exp_rslt:
                exp_paths.append(CIMInstanceName(
                    exp[0],
                    keybindings=dict(name=exp[1]),
                    namespace=exp_ns,
                    host=conn.host))

            rslt_paths = result_tuple.paths

            assert_equal_ciminstancenames(rslt_paths, exp_paths)

        else:
            exp_status = exp_rslt
            if exp_status == CIM_ERR_INVALID_NAMESPACE:
                source_inst_name.namespace = 'BadNamespaceName'

            with pytest.raises(CIMError) as exec_info:
                conn.OpenAssociatorInstancePaths(source_inst_name,
                                                 AssocClass=ac,
                                                 Role=ro,
                                                 ResultClass=rc,
                                                 ResultRole=rr)
            exc = exec_info.value
            assert exc.status_code == exp_status

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        # src_inst: Source instance definition (classname and name property
        # ro: Role
        # ac: AssocClass
        # rc: ResultClass
        # rr: ResultRole
        # exp_rslt: list of tuples where each tuple is class and key for
        #           expected instance path returned, or CIMError status code
        #           if error response expected.
        "src_inst, ro, ac, rc, rr, exp_rslt", [
            [('TST_Person', 'Mike'), 'parent', 'TST_Lineage', 'TST_Person',
             'child',
             [('TST_Person', 'Sofi'),
              ('TST_Person', 'Gabi')]],

            [('TST_Person', 'Mike'), None, 'TST_Lineage', 'TST_Person',
             'child',
             [('TST_Person', 'Sofi'),
              ('TST_Person', 'Gabi')]],

            [('TST_Person', 'Mike'), None, 'TST_Lineage', 'TST_Person',
             None,
             [('TST_Person', 'Sofi'),
              ('TST_Person', 'Gabi')]],

            [('TST_Person', 'Saara'), 'parent', 'TST_Lineage', 'TST_Person',
             'child', [('TST_Person', 'Sofi'), ]],

            [('TST_Person', 'Saara'), 'parent', 'TST_Lineage', 'TST_Person',
             'child', CIM_ERR_INVALID_NAMESPACE],
        ]
    )
    def test_openassociatorinstances(self, conn, ns, src_inst, ro, ac,
                                     rc, rr, exp_rslt, tst_assoc_mof):
        # pylint: disable=no-self-use,invalid-name
        """
            Test openenueratepaths where the open is the complete response
            and all parameters are default
        """
        skip_if_moftab_regenerated()
        conn.compile_mof_string(tst_assoc_mof, namespace=ns)

        source_inst_name = CIMInstanceName(src_inst[0],
                                           keybindings=dict(name=src_inst[1]),
                                           namespace=ns)

        if isinstance(exp_rslt, (list, tuple)):
            result_tuple = conn.OpenAssociatorInstances(source_inst_name,
                                                        AssocClass=ac,
                                                        Role=ro,
                                                        ResultClass=rc,
                                                        ResultRole=rr)

            assert result_tuple.eos is True
            assert result_tuple.context is None

            exp_ns = ns or conn.default_namespace

            # build list of expected paths from exp_rslt
            exp_paths = []
            for exp in exp_rslt:
                exp_paths.append(CIMInstanceName(
                    exp[0],
                    keybindings=dict(name=exp[1]),
                    namespace=exp_ns))

            rslt_paths = [inst.path for inst in result_tuple.instances]

            assert_equal_ciminstancenames(rslt_paths, exp_paths)
            # TODO test instances returned rather than just paths and
            # test for propertylist specifically

        else:
            exp_status = exp_rslt
            if exp_status == CIM_ERR_INVALID_NAMESPACE:
                source_inst_name.namespace = 'BadNamespaceName'

            with pytest.raises(CIMError) as exec_info:
                conn.OpenAssociatorInstances(source_inst_name,
                                             AssocClass=ac,
                                             Role=ro,
                                             ResultClass=rc,
                                             ResultRole=rr)
            exc = exec_info.value
            assert exc.status_code == exp_status

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "test, cln, omoc, pmoc, exp_exc", [

            # Test closing after open with moc
            [0, 'CIM_Foo', 0, 1, None],

            # Execute close after sequence conplete
            [1, 'CIM_Foo', 100, 100, 'Value Not Used'],

            # Execute close with valid context but after sequence complete
            [2, 'CIM_Foo', 0, 100,
             CIMError(CIM_ERR_INVALID_ENUMERATION_CONTEXT)],
            # TODO FUTURE: test with timer
        ]
    )
    def test_closeenumeration(self, conn, ns, test, cln, omoc, pmoc,
                              exp_exc, tst_classeswqualifiers, tst_instances):
        # pylint: disable=no-self-use
        """
        Test variations on closing enumerate the enumeration context with
        the CloseEnumeration operation.  Tests both valid and invalid
        calls.
        """
        conn.add_cimobjects(tst_classeswqualifiers, namespace=ns)
        conn.add_cimobjects(tst_instances, namespace=ns)

        result_tuple = conn.OpenEnumerateInstancePaths(
            cln, namespace=ns, MaxObjectCount=omoc)

        if test == 0:
            assert result_tuple.eos is False
            assert result_tuple.context is not None
            conn.CloseEnumeration(result_tuple.context)

        elif test == 1:
            while not result_tuple.eos:
                result_tuple = conn.PullInstancePaths(
                    result_tuple.context, MaxObjectCount=pmoc)
            assert result_tuple.eos is True
            assert result_tuple.context is None
            with pytest.raises(ValueError) as exec_info:
                conn.CloseEnumeration(result_tuple.context)

        elif test == 2:
            save_result_tuple = pull_path_result_tuple(*result_tuple)

            while not result_tuple.eos:
                result_tuple = conn.PullInstancePaths(
                    result_tuple.context, MaxObjectCount=pmoc)
            assert result_tuple.eos is True
            assert result_tuple.context is None
            with pytest.raises(exp_exc.__class__) as exec_info:
                assert save_result_tuple.context is not None
                conn.CloseEnumeration(save_result_tuple.context)
            exc = exec_info.value
            if isinstance(exp_exc, CIMError):
                assert exc.status_code == exp_exc.status_code
        else:
            assert False, 'Invalid test code %s' % test


class TestQualifierOperations(object):
    """
    Tests the qualifier set, enumerate, get and delete operations.
    Note this is really QualifierDeclarations
    """
    @staticmethod
    def _build_qualifiers():
        """
        Static method to build test qualifier declarations. Builds
        2 valid declarations and returns list
        """
        q1 = CIMQualifierDeclaration('FooQualDecl1', 'uint32')

        q2 = CIMQualifierDeclaration('FooQualDecl2', 'string',
                                     value='my string', tosubclass=True,
                                     overridable=False)
        return [q1, q2]

    @staticmethod
    def _build_expected_rtn_qualifiers():
        """
        Static method to build test qualifier declarations. Builds
        2 valid declarations and returns list
        """
        q1 = CIMQualifierDeclaration('FooQualDecl1', 'uint32', tosubclass=True,
                                     overridable=True, translatable=False)

        q2 = CIMQualifierDeclaration('FooQualDecl2', 'string',
                                     value='my string', tosubclass=True,
                                     overridable=False, translatable=False)
        return [q1, q2]

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "qname, exp_status", [
            ['FooQualDecl1', None],
            ['fooqualdecl1', None],
            ['badqualname', CIM_ERR_NOT_FOUND],
            ['whatever', CIM_ERR_INVALID_NAMESPACE],
        ]
    )
    def test_getqualifier(self, conn, ns, qname, exp_status):
        """
        Test adding a qualifierdecl to the repository and doing a
        WBEMConnection get to retrieve it.
        """
        q_list = self._build_qualifiers()
        conn.add_cimobjects(q_list, namespace=ns)

        q_rtn_list = self._build_expected_rtn_qualifiers()

        exp_q_rtn = None
        for q in q_rtn_list:
            if q.name.lower() == qname.lower():
                exp_q_rtn = q

        if not exp_status:
            rtn_q1 = conn.GetQualifier(qname, namespace=ns)
            assert rtn_q1.name.lower() == exp_q_rtn.name.lower()

        else:
            if exp_status == CIM_ERR_INVALID_NAMESPACE:
                ns = 'badnamespace'

            with pytest.raises(CIMError) as exec_info:
                conn.GetQualifier(qname, namespace=ns)
            exc = exec_info.value
            assert exc.status_code == exp_status

    @pytest.mark.parametrize(
        "ns", EXPANDED_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "exp_status", [None, CIM_ERR_INVALID_NAMESPACE])
    def test_enumeratequalifiers(self, conn, ns, exp_status):
        """
        Test adding qualifier declarations to the repository and using
        EnumerateQualifiers to retrieve them
        """
        q_list = self._build_qualifiers()

        q_exp_rtn_list = self._build_expected_rtn_qualifiers()

        add_objects_to_repo(conn, ns, q_list)

        if not exp_status:
            q_rtns = conn.EnumerateQualifiers(namespace=ns)
            for q in q_rtns:
                assert isinstance(q, CIMQualifierDeclaration)

            q_rtns.sort(key=lambda x: x.name)
            q_exp_rtn_list.sort(key=lambda x: x.name)

        else:
            if exp_status == CIM_ERR_INVALID_NAMESPACE:
                ns = 'badnamespace'

            with pytest.raises(CIMError) as exec_info:
                conn.EnumerateQualifiers(namespace=ns)
            exc = exec_info.value
            assert exc.status_code == exp_status

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "qual, exp_status", [
            [CIMQualifierDeclaration('FooQualDecl3', 'string',
                                     value='my string'), None],
            # Invalid definition for qualifierdeclaration
            [CIMClass('FooQualDecl3'), CIM_ERR_INVALID_PARAMETER],
        ]
    )
    def test_setqualifier(self, conn, ns, qual, exp_status):
        # pylint: disable=no-self-use
        """
            Test create class. Tests for namespace variable,
            correctly adding, and invalid add where class has superclass
        """

        if not exp_status:
            conn.SetQualifier(qual, namespace=ns)

            rtn_qualifier = conn.GetQualifier(qual.name, namespace=ns)

            assert rtn_qualifier == qual

            # Test for uses modify by Setting second qualifier with same name
            conn.SetQualifier(qual, namespace=ns)

        else:
            if exp_status == CIM_ERR_INVALID_NAMESPACE:
                ns = 'badnamespace'

            with pytest.raises(CIMError) as exec_info:
                conn.SetQualifier(qual, namespace=ns)
            exc = exec_info.value
            assert exc.status_code == exp_status

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "qname, exp_status", [
            ['FooQualDecl1', None],
            ['badqualname', CIM_ERR_NOT_FOUND],
            ['whatever', CIM_ERR_INVALID_NAMESPACE],
        ]
    )
    def test_deletequalifier(self, conn, ns, qname, exp_status):
        """
        Test  fake delete of qualifier declaration method. Adds qualifier
        declarations to repository and then deletes qualifier defined
        by qname. Tries to delete again and this should fail as not found.
        """
        q_list = self._build_qualifiers()
        conn.add_cimobjects(q_list, namespace=ns)

        if not exp_status:
            conn.DeleteQualifier('FooQualDecl2', namespace=ns)

            with pytest.raises(CIMError) as exec_info:
                conn.DeleteQualifier('QualDoesNotExist', namespace=ns)
            exc = exec_info.value
            assert exc.status_code == CIM_ERR_NOT_FOUND
        else:
            if exp_status == CIM_ERR_INVALID_NAMESPACE:
                ns = 'badnamespace'

            with pytest.raises(CIMError) as exec_info:
                conn.GetQualifier(qname, namespace=ns)
            exc = exec_info.value
            assert exc.status_code == exp_status


PERSON_MIKE_NME = CIMInstanceName('TST_Person', keybindings=(('name',
                                                              'Mike'),))
PERSONS_MIKE_NME = CIMInstanceName('tst_person', keybindings=(('name',
                                                               'Mike'),))
PERSON_SOFI_NME = CIMInstanceName('TST_Person', keybindings=(('name',
                                                              'Sofi'),))
PERSON_GABI_NME = CIMInstanceName('TST_Person', keybindings=(('name',
                                                              'Gabi'),))
LINEAGE_MIKESOFI_NME = CIMInstanceName('TST_Lineage',
                                       keybindings=(('InstanceID',
                                                     'MikeSofi'),))
LINEAGE_MIKEGABI_NME = CIMInstanceName('TST_Lineage',
                                       keybindings=(('InstanceID',
                                                     'MikeGabi'),))
FAM_COLL_FAM2_NME = CIMInstanceName('TST_FamilyCollection',
                                    keybindings=(('name', 'Family2'),))
MEMBER_FAM2MIKE_NME = CIMInstanceName(
    'TST_MemberOfFamilyCollection',
    keybindings=(('family', FAM_COLL_FAM2_NME),
                 ('member', PERSON_MIKE_NME)))


class TestReferenceOperations(object):
    """
    Tests of References class and instance operations
    """
    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    def test_compile_assoc_mof(self, conn, ns, tst_assoc_mof):
        # pylint: disable=no-self-use
        """
        Test the tst_assoc_mof compilation and verify number of instances
        created.
        """
        skip_if_moftab_regenerated()
        if ns is None:
            ns = conn.default_namespace
        conn.compile_mof_string(tst_assoc_mof, namespace=ns)

        classes = [u'TST_Lineage', u'TST_MemberOfFamilyCollection',
                   u'TST_Person', u'TST_Personsub', u'TST_FamilyCollection']
        assert set(classes) == set(
            conn.EnumerateClassNames(namespace=ns, DeepInheritance=True))

        assert len(conn.EnumerateInstanceNames("TST_Person", namespace=ns)) == \
            TST_PERSONWITH_SUB_INST_COUNT

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "cln", ['TST_Person', 'tst_person', CIMClassName('TST_Person'),
                CIMClassName('tst_person')])
    @pytest.mark.parametrize(
        # rc: ResultClass
        # ro: Role
        # exp_rslt: list of associator classnames that should be returned if
        #   good result expected. CIMError exception object if error
        #   return expected.
        "rc, ro, exp_rslt", [
            [None, None, ['TST_Lineage', 'TST_MemberOfFamilyCollection']],
            ['TST_Lineage', None, ['TST_Lineage']],
            ['tst_lineage', None, ['TST_Lineage']],
            ['TST_Lineage', 'parent', ['TST_Lineage']],
            ['TST_Lineage', 'child', ['TST_Lineage']],
            ['TST_Lineage', 'CHILD', ['TST_Lineage']],
            [None, 'parent', ['TST_Lineage']],
            [None, 'child', ['TST_Lineage']],
            [None, 'blah', []],
            ['TST_MemberOfFamilyCollection', None,
             ['TST_MemberOfFamilyCollection']],
            ['TST_MemberOfFamilyCollection', 'member',
             ['TST_MemberOfFamilyCollection']],
            ['TST_MemberOfFamilyCollection', 'family',
             ['TST_MemberOfFamilyCollection']],
            [None, 'member', ['TST_MemberOfFamilyCollection']],
            [None, 'family', ['TST_MemberOfFamilyCollection']],
            [None, 'family', ['TST_MemberOfFamilyCollection']],
            ['TST_Lineagexxx', None, CIMError(CIM_ERR_INVALID_PARAMETER)],
            [None, None, CIMError(CIM_ERR_INVALID_NAMESPACE)],
        ]
    )
    def test_reference_classnames(self, conn, ns, cln, tst_assoc_mof, rc, ro,
                                  exp_rslt):
        # pylint: disable=no-self-use
        """
        Test getting reference classnames with no options on call and default
        namespace. Tests for both string and CIMClassName input
        """
        skip_if_moftab_regenerated()

        conn.compile_mof_string(tst_assoc_mof, namespace=ns)

        # account for api where string classname only allowed with default
        # classname
        if ns is not None:
            if isinstance(cln, six.string_types):
                cim_cln = CIMClassName(classname=cln, namespace=ns)
            else:
                cim_cln = cln.copy()
                cim_cln.namespace = ns
        else:
            cim_cln = cln

        if isinstance(exp_rslt, list):    # if list exp OK result
            clns = conn.ReferenceNames(cim_cln, ResultClass=rc, Role=ro)
            exp_ns = ns or conn.default_namespace
            assert isinstance(clns, list)
            assert len(clns) == len(exp_rslt)
            for _cln in clns:
                assert isinstance(_cln, CIMClassName)
                assert _cln.host == conn.host
                assert _cln.namespace == exp_ns
            exp_clns = [CIMClassName(classname=n, namespace=exp_ns,
                                     host=conn.host)
                        for n in exp_rslt]

            assert set(cln.classname.lower() for cln in exp_clns) == \
                set(cln.classname.lower() for cln in clns)

        else:
            assert isinstance(exp_rslt, CIMError)
            exp_exc = exp_rslt
            # Fix the targetclassname for some of the tests
            if isinstance(cim_cln, six.string_types):
                cim_cln = CIMClassName(classname=cln)

            if exp_exc.status_code == CIM_ERR_INVALID_NAMESPACE:
                cim_cln.namespace = 'non_existent_namespace'

            with pytest.raises(CIMError) as exec_info:
                conn.ReferenceNames(cim_cln, ResultClass=rc, Role=ro)
            exc = exec_info.value
            assert exc.status_code == exp_exc.status_code

    def test_reference_instnames_min(self, conn, tst_assoc_mof):
        # pylint: disable=no-self-use
        """
        Test getting reference instnames with no options
        """
        skip_if_moftab_regenerated()

        conn.compile_mof_string(tst_assoc_mof)

        inst_name = CIMInstanceName('TST_Person',
                                    keybindings={'name': 'Mike'})
        inames = conn.ReferenceNames(inst_name)
        assert isinstance(inames, list)
        assert len(inames) == 3
        assert isinstance(inames[0], CIMInstanceName)
        exp_rslt = [
            CIMInstanceName(classname='TST_Lineage',
                            keybindings=NocaseDict({'InstanceID': 'MikeSofi'}),
                            namespace='root/cimv2', host=conn.host),
            CIMInstanceName(classname='TST_Lineage',
                            keybindings=NocaseDict({'InstanceID': 'MikeGabi'}),
                            namespace='root/cimv2', host='FakedUrl:5988'),
            CIMInstanceName(
                classname='TST_MemberOfFamilyCollection',
                keybindings=NocaseDict({
                    'family': CIMInstanceName(
                        classname='TST_FamilyCollection',
                        keybindings=NocaseDict({'name': 'Family2'}),
                        namespace='root/cimv2', host=None),
                    'member': CIMInstanceName(
                        classname='TST_Person',
                        keybindings=NocaseDict({'name': 'Mike'}),
                        namespace='root/cimv2', host=None)}),
                namespace='root/cimv2', host=conn.host)]
        assert_equal_ciminstancenames(inames, exp_rslt)

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(  # Don't really need this since rslts tied to cl.
        # target instance name
        "targ_iname", [PERSON_MIKE_NME,
                       PERSONS_MIKE_NME, ]
    )
    @pytest.mark.parametrize(
        # rc: ResultClass
        # ro: Role
        # exp_rslt: list of associator class/key tuples that should be returned
        #    if good result expected.  CIMError exception object if error
        #   return expected.
        "rc, ro, exp_rslt", [
            [None, None, (LINEAGE_MIKESOFI_NME,
                          LINEAGE_MIKEGABI_NME, MEMBER_FAM2MIKE_NME)],
            ['TST_Lineage', None, (LINEAGE_MIKESOFI_NME,
                                   LINEAGE_MIKEGABI_NME)],
            ['tst_lineage', None, (LINEAGE_MIKESOFI_NME,
                                   LINEAGE_MIKEGABI_NME)],
            ['TST_Lineage', 'parent', (LINEAGE_MIKESOFI_NME,
                                       LINEAGE_MIKEGABI_NME)],
            ['TST_Lineage', 'child', ()],
            ['TST_Lineage', 'CHILD', ()],
            [None, 'parent', (LINEAGE_MIKESOFI_NME,
                              LINEAGE_MIKEGABI_NME)],
            [None, 'child', ()],
            ['TST_MemberOfFamilyCollection', None, (MEMBER_FAM2MIKE_NME,)],
            ['TST_MemberOfFamilyCollection', 'member', (MEMBER_FAM2MIKE_NME,)],
            ['TST_MemberOfFamilyCollection', 'family', ()],
            [None, 'member', (MEMBER_FAM2MIKE_NME,)],
            [None, 'family', ()],
            # Verify role name not in class return nothing
            ['TST_Lineage', 'blah', []],
            # Verify ResultClass not in environment returns nothing
            ['TST_LineageXXX', None, CIMError(CIM_ERR_INVALID_PARAMETER)],
            # Specific test that generates error
            ['TST_Lineage', None, CIMError(CIM_ERR_INVALID_NAMESPACE, "blah")]
        ]
    )
    def test_reference_instnames(self, conn, ns, targ_iname, rc, ro, exp_rslt,
                                 tst_assoc_mof):
        # pylint: disable=no-self-use
        """
        Test getting reference classnames
        """
        skip_if_moftab_regenerated()

        conn.compile_mof_string(tst_assoc_mof, namespace=ns)
        targ_iname.namespace = ns

        # Fixup exp_rslt by completing at least namespace
        if isinstance(exp_rslt, (tuple, list)):
            exp_inames = []

            # set namespace in target instance name if a namespace is specified
            if ns is None:
                ns = conn.default_namespace
                local_targ_iname = targ_iname
            else:
                local_targ_iname = targ_iname.copy()
                local_targ_iname.namespace = ns

            for iname in exp_rslt:
                local_iname = iname.copy()
                local_iname.namespace = ns
                for kb in local_iname.keybindings:
                    if isinstance(local_iname.keybindings[kb], CIMInstanceName):
                        local_iname.keybindings[kb].namespace = ns

                exp_inames.append(local_iname.to_wbem_uri('canonical'))

            rslt_paths = conn.ReferenceNames(targ_iname, ResultClass=rc,
                                             Role=ro)

            assert isinstance(rslt_paths, list)

            assert len(rslt_paths) == len(exp_rslt)

            # test if inames returned in exp_inames.
            # We remove host because the return is scheme + url and when we
            # expand exp_inames it expands only to url (i.e. the htp:// missing)
            for path in rslt_paths:
                assert isinstance(path, CIMInstanceName)
                path.host = None
                assert path.to_wbem_uri('canonical') in exp_inames

        else:  # expecting error
            assert isinstance(exp_rslt, CIMError)
            exp_exc = exp_rslt
            if exp_exc.status_code == CIM_ERR_INVALID_NAMESPACE:
                targ_iname = targ_iname.copy()   # copy to not mod original
                targ_iname.namespace = 'non_existent_namespace'

            with pytest.raises(CIMError) as exec_info:
                conn.ReferenceNames(targ_iname, ResultClass=rc, Role=ro)
            exc = exec_info.value
            assert exc.status_code == exp_exc.status_code

    # TODO not sure we really need this testcase? Combine with next case
    # The only thing special about this test is it sets all parameters to
    # default
    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    def test_reference_instances_min(self, conn, tst_assoc_mof, ns):
        # pylint: disable=no-self-use
        """
        Test getting reference instances from default namespace with
        detault parameters
        """
        skip_if_moftab_regenerated()

        conn.compile_mof_string(tst_assoc_mof)

        # Build the expected result instance list
        # the paths for association instances must include the correct
        # namespace for each key that is a CIMInstanceName
        ns = ns or conn.default_namespace
        fam2mike = fix_instname_namespace_keys(MEMBER_FAM2MIKE_NME, ns)
        exp_rslt = [conn.GetInstance(path) for path in (LINEAGE_MIKESOFI_NME,
                                                        LINEAGE_MIKEGABI_NME,
                                                        fam2mike)]
        # set the server name in the expected response
        for inst in exp_rslt:
            if inst.path.host is None:
                inst.path.host = conn.host
        assert len(exp_rslt) == 3

        inst_name = CIMInstanceName('TST_Person',
                                    keybindings=dict(name='Mike'))

        act_rslt = conn.References(inst_name)

        assert isinstance(act_rslt, list)

        assert_equal_ciminstances(exp_rslt, act_rslt)

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "rc, role, exp_rtn", [
            # rc: ResultClass parameter
            # role: Role parameter
            # exp_rtn: tuple of classname and tuple of keys
            # in expected return CIMInstanceNames. Used to build expected
            # return keys.
            [None, None, (('TST_Lineage', ('InstanceID', 'MikeGabi')),
                          ('TST_Lineage', ('InstanceID', 'MikeSofi')),
                          ('TST_MemberOfFamilyCollection', (
                              ('TST_FamilyCollection', 'family', 'name',
                               "Family2"),
                              ('TST_Person', 'member', 'name', 'Mike'))))],

            ['TST_Lineage', None, (('TST_Lineage', ('InstanceID', 'MikeGabi')),
                                   ('TST_Lineage',
                                    ('InstanceID', 'MikeSofi')))],
            ['tst_lineage', None, (('TST_Lineage', ('InstanceID', 'MikeGabi')),
                                   ('TST_Lineage',
                                    ('InstanceID', 'MikeSofi')))],
            [None, 'parent', (('TST_Lineage', ('InstanceID', 'MikeGabi')),
                              ('TST_Lineage', ('InstanceID', 'MikeSofi')))],
            [None, 'PARENT', (('TST_Lineage', ('InstanceID', 'MikeGabi')),
                              ('TST_Lineage', ('InstanceID', 'MikeSofi')))],
            ['TST_Lineage', 'parent', (('TST_Lineage',
                                        ('InstanceID', 'MikeGabi')),
                                       ('TST_Lineage',
                                        ('InstanceID', 'MikeSofi')))],
            [None, 'friend', []],
        ]
    )
    def test_reference_instances_opts(self, conn, ns, rc, role, exp_rtn,
                                      tst_assoc_mof):
        # pylint: disable=no-self-use
        """
        Test getting reference instance names with rc and role options.
        """
        skip_if_moftab_regenerated()

        conn.compile_mof_string(tst_assoc_mof, namespace=ns)

        inst_name = CIMInstanceName('TST_Person',
                                    keybindings=dict(name='Mike'),
                                    namespace=ns)

        insts = conn.References(inst_name, ResultClass=rc, Role=role)

        paths = [i.path for i in insts]

        assert isinstance(insts, list)
        assert len(insts) == len(exp_rtn)
        for inst in insts:
            assert isinstance(inst, CIMInstance)

        exp_ns = ns or conn.default_namespace

        # create the expected paths from exp_rtn fixture.
        exp_paths = []
        for exp_path in exp_rtn:
            kbs = OrderedDict()
            kys = exp_path[1]
            if not isinstance(kys[0], (tuple, list)):
                kys = [ kys ]  # noqa E201, E202 pylint: disable=bad-whitespace
            for ky in kys:
                if len(ky) == 2:   # simple instance path, 3 values
                    kbs[ky[0]] = ky[1]
                else:
                    assert len(ky) == 4
                    kbs[ky[1]] = CIMInstanceName(ky[0], namespace=exp_ns,
                                                 keybindings={ky[2]: ky[3]})
            path = CIMInstanceName(exp_path[0], namespace=exp_ns,
                                   keybindings=kbs, host=conn.host)
            exp_paths.append(path)

        assert_equal_ciminstancenames(exp_paths, paths)

    # TODO test for references propertylist.

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "targ_obj", ['XXX_Blan',
                     CIMInstanceName('XXX_Blah',
                                     keybindings={'InstanceID': 3})])
    def test_reference_target_err(self, conn, ns, targ_obj, tst_assoc_mof):
        # pylint: disable=no-self-use
        """
        Test getting reference classnames with no options on call and default
        namespace. Tests for both string and CIMClassName input
        """
        skip_if_moftab_regenerated()

        conn.compile_mof_string(tst_assoc_mof, namespace=ns)
        with pytest.raises(CIMError) as exec_info:
            conn.ReferenceNames(targ_obj)
        exc = exec_info.value
        assert exc.status_code == CIM_ERR_INVALID_PARAMETER


class TestAssociatorOperations(object):
    """
    Tests of Associator class and instance operations
    """

    @pytest.mark.parametrize(
        "ns", EXPANDED_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "target_cln", ['TST_Person', 'tst_person'])
    @pytest.mark.parametrize(
        "role, ac, rr, rc, exp_rslt", [
            # role: role attribute
            # ac: associated class attribute
            # rr: resultrole attribute
            # rc: resultclass attribute
            # exp_result: Either list of names of expected classes returned
            #             or string defining error response
            [None, None, None, None, ['TST_Person']],
            [None, 'TST_Lineage', None, None, ['TST_Person']],
            ['Parent', 'TST_Lineage', None, None, ['TST_Person']],
            ['parent', 'TST_Lineage', None, None, ['TST_Person']],
            ['parent', 'tst_lineage', None, None, ['TST_Person']],
            ['parent', 'TST_Lineage', None, None, ['tst_person']],
            ['Parent', 'TST_Lineage', 'child', 'TST_Person', ['TST_Person']],
            ['parent', 'TST_Lineage', 'Child', 'TST_Person', ['TST_Person']],
            ['PARENT', 'TST_Lineage', 'CHILD', 'TST_Person', ['TST_Person']],
            [None, None, 'child', 'TST_Person', ['TST_Person']],
            ['Parent', 'TST_Lineagexxx', 'child', 'TST_Person',
             CIMError(CIM_ERR_INVALID_PARAMETER)],
            ['Parent', 'TST_Lineage', 'child', 'TST_Personxxx',
             CIMError(CIM_ERR_INVALID_PARAMETER)],
            ['Parent', 'TST_Lineage', 'child', 'TST_Person',
             CIMError(CIM_ERR_INVALID_NAMESPACE)],
        ]
    )
    def test_associator_classnames(self, conn, ns, target_cln, role, rr, ac, rc,
                                   exp_rslt, tst_assoc_mof):
        # pylint: disable=no-self-use
        """
        Test getting reference classnames with no options on call and default
        namespace. Tests for both string and CIMClassName input
        """
        skip_if_moftab_regenerated()

        add_objects_to_repo(conn, ns, [tst_assoc_mof])

        if ns is not None:
            target_cln = CIMClassName(target_cln, namespace=ns)

        if isinstance(exp_rslt, (list, tuple)):

            rtn_clns = conn.AssociatorNames(target_cln, AssocClass=ac,
                                            Role=role,
                                            ResultRole=rr, ResultClass=rc)
            exp_ns = ns if ns else conn.default_namespace
            assert isinstance(rtn_clns, list)
            assert len(rtn_clns) == len(exp_rslt)
            for cln in rtn_clns:
                assert isinstance(cln, CIMClassName)
                assert cln.host == conn.host
                assert cln.namespace == exp_ns

            exp_clns = [CIMClassName(classname=n, namespace=exp_ns,
                                     host=conn.host)
                        for n in exp_rslt]

            assert set(cln.classname.lower() for cln in exp_clns) == \
                set(cln.classname.lower() for cln in rtn_clns)

        else:
            assert isinstance(exp_rslt, CIMError)
            exp_exc = exp_rslt

            # Set up test for invalid namespace exception
            if exp_exc.status_code == CIM_ERR_INVALID_NAMESPACE:
                if isinstance(target_cln, six.string_types):
                    target_cln = CIMClassName(target_cln,
                                              namespace='badnamespacename')
                else:
                    target_cln.namespace = 'badnamespacename'

            with pytest.raises(CIMError) as exec_info:
                conn.AssociatorNames(target_cln, AssocClass=ac, Role=role,
                                     ResultRole=rr, ResultClass=rc)
            exc = exec_info.value
            assert exc.status_code == exp_exc.status_code

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "targ_iname", [
            PERSON_MIKE_NME,
            PERSONS_MIKE_NME,
        ]
    )
    @pytest.mark.parametrize(
        "role, ac, rr, rc, exp_rslt", [
            # role: associator role parameter
            # ac: associator operation AssocClass parameter
            # rr: associator operation ResultRole parameter
            # rc: associator operation ResultClass parameter
            # exp_rslt: Expected result.  If list, list of instances in response
            #           If failed, CIMError exception object with expected
            #           status code

            # Test for assigned role and assoc class
            ['parent', 'TST_Lineage', None, None, (PERSON_SOFI_NME,
                                                   PERSON_GABI_NME,)],
            # Test for assigned role, asoc class, result role, resultclass
            ['parent', 'TST_Lineage', 'child', 'TST_Person',
             (PERSON_SOFI_NME, PERSON_GABI_NME,)],
            # test for case independence for role, assocclass, result role,
            # and resultclass
            ['PARENT', 'TST_Lineage', 'child', 'TST_Person',
             (PERSON_SOFI_NME, PERSON_GABI_NME,)],
            ['parent', 'tst_lineage', 'child', 'TST_Person',
             (PERSON_SOFI_NME, PERSON_GABI_NME,)],
            ['parent', 'TST_Lineage', 'CHILD', 'TST_Person',
             (PERSON_SOFI_NME, PERSON_GABI_NME,)],
            ['parent', 'TST_Lineage', 'child', 'tst_person',
             (PERSON_SOFI_NME, PERSON_GABI_NME,)],
            ['PARENT', 'tst_lineage', 'CHILD', 'tst_person',
             (PERSON_SOFI_NME, PERSON_GABI_NME,)],
            ['PARENT', 'tst_lineagexxx', 'CHILD', 'tst_person',
             CIMError(CIM_ERR_INVALID_PARAMETER, "blah")],
            ['PARENT', 'tst_lineage', 'CHILD', 'tst_personxxx',
             CIMError(CIM_ERR_INVALID_PARAMETER, "blah")],
            # Execute invalid namespace test
            ['Parent', 'TST_Lineage', 'child', 'TST_Person',
             CIMError(CIM_ERR_INVALID_NAMESPACE, "blah")],
            # TODO add more tests
        ]
    )
    def test_associator_instnames(self, conn, ns, targ_iname, role, rr, ac,
                                  rc, exp_rslt, tst_assoc_mof):
        # pylint: disable=no-self-use
        """
        Test getting associators with parameters for the response filters
        including role, etc.
        TODO add tests for IncludeQualifiers, PropertyList, IncludeClassOrigin
        """
        skip_if_moftab_regenerated()

        conn.compile_mof_string(tst_assoc_mof, namespace=ns)

        exp_ns = ns or conn.default_namespace
        targ_iname.namespace = ns

        if isinstance(exp_rslt, (tuple, list)):
            exp_inames = []
            for iname in exp_rslt:
                local_iname = iname.copy()
                local_iname.namespace = exp_ns
                for kb in local_iname.keybindings:
                    if isinstance(local_iname.keybindings[kb], CIMInstanceName):
                        local_iname.keybindings[kb].namespace = exp_ns
                exp_inames.append(local_iname.to_wbem_uri('canonical'))

            rpaths = conn.AssociatorNames(targ_iname, AssocClass=ac, Role=role,
                                          ResultRole=rr, ResultClass=rc)

            assert isinstance(rpaths, list)
            assert len(rpaths) == len(exp_rslt)
            for path in rpaths:
                assert isinstance(path, CIMInstanceName)
                path.host = None
                assert path.to_wbem_uri('canonical') in exp_inames

        else:
            assert isinstance(exp_rslt, CIMError)
            exp_exc = exp_rslt

            if exp_exc.status_code == CIM_ERR_INVALID_NAMESPACE:
                targ_iname.namespace = 'BadNameSpaceName'
            with pytest.raises(CIMError) as exec_info:
                conn.AssociatorNames(targ_iname, AssocClass=ac, Role=role,
                                     ResultRole=rr, ResultClass=rc)
            exc = exec_info.value
            assert exc.status_code == exp_exc.status_code

        # TODO expand associator instance names tests

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "cln, inst_id", [
            ['TST_Person', 'Mike'],
            ['tst_person', 'Mike'],
        ]
    )
    @pytest.mark.parametrize(
        "role, ac, rr, rc, exp_rslt", [
            # role: associator role parameter
            # ac: associator operation AssocClass parameter
            # rr: associator operation ResultRole parameter
            # rc: associator operation ResultClass parameter
            # exp_rslt: Expected result.  If list, list of instances in response
            #           If failed, CIMError exception object with expected
            #           status code

            # Test for assigned role and assoc class
            ['parent', 'TST_Lineage', None, None, (('TST_person', 'Sofi'),
                                                   ('TST_person', 'Gabi'),)],
            # Test for assigned role, asoc class, result role, resultclass
            ['parent', 'TST_Lineage', 'child', 'TST_Person',
             (('TST_person', 'Sofi'), ('TST_person', 'Gabi'),)],
            # Execute invalid namespace test
            ['parent', 'TST_Lineage', 'child', 'TST_Person',
             CIMError(CIM_ERR_INVALID_NAMESPACE)],
            # TODO add more tests
        ]
    )
    def test_associator_instances(self, conn, ns, cln, inst_id, role, rr, ac,
                                  rc, exp_rslt, tst_assoc_mof):
        # pylint: disable=no-self-use
        """
        Test getting associators with parameters for the response filters
        including role, etc.
        TODO add tests for IncludeQualifiers, PropertyList, IncludeClassOrigin
        """
        skip_if_moftab_regenerated()

        conn.compile_mof_string(tst_assoc_mof, namespace=ns)

        exp_ns = ns or conn.default_namespace

        inst_name = CIMInstanceName(cln, namespace=exp_ns,
                                    keybindings=dict(name=inst_id))

        if isinstance(exp_rslt, (tuple, list)):
            rtn_insts = conn.Associators(inst_name, AssocClass=ac, Role=role,
                                         ResultRole=rr, ResultClass=rc)

            assert isinstance(rtn_insts, list)
            assert len(rtn_insts) == len(exp_rslt)
            for inst in rtn_insts:
                assert isinstance(inst, CIMInstance)

            if isinstance(exp_rslt, (list, tuple)):

                exp_paths = [CIMInstanceName(p[0], keybindings={'name': p[1]},
                                             namespace=exp_ns)
                             for p in exp_rslt]
                rtn_paths = [inst.path for inst in rtn_insts]

                assert_equal_ciminstancenames(rtn_paths, exp_paths)

        else:
            assert isinstance(exp_rslt, CIMError)
            exp_exc = exp_rslt

            if exp_exc.status_code == CIM_ERR_INVALID_NAMESPACE:
                inst_name.namespace = 'BadNameSpaceName'

            with pytest.raises(CIMError) as exec_info:
                conn.Associators(inst_name, AssocClass=ac, Role=role,
                                 ResultRole=rr, ResultClass=rc)
            exc = exec_info.value
            assert exc.status_code == exp_exc.status_code

        # TODO expand associator instance tests

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "cln", ['TST_Person'])
    @pytest.mark.parametrize(
        "role, ac, rr, rc, exp_rslt", [
            # role: associator role parameter
            # ac: associator operation AssocClass parameter
            # rr: associator operation ResultRole parameter
            # rc: associator operation ResultClass parameter
            # exp_rslt: Either list of names of expected classes returned
            #           or CIMError exception object with expected status code
            # TODO: Review this and its results. I am uncomfortable I have not
            #       covered all the essentials
            [None, None, None, None, ['TST_Person']],
            [None, 'TST_Lineage', None, None, ['TST_Person']],
            ['Parent', 'TST_Lineage', None, None, ['TST_Person']],
            ['parent', 'TST_Lineage', None, None, ['TST_Person']],
            ['Parent', 'TST_Lineage', 'child', 'TST_Person', ['TST_Person']],
            ['parent', 'TST_Lineage', 'Child', 'TST_Person', ['TST_Person']],
            ['PARENT', 'TST_Lineage', 'CHILD', 'TST_Person', ['TST_Person']],
            [None, None, 'child', 'TST_Person', ['TST_Person']],
            ['Parent', 'TST_Lineage', 'child', 'TST_Person',
             CIMError(CIM_ERR_INVALID_NAMESPACE)],
        ]
    )
    def test_associator_classes(self, conn, ns, cln, role, rr, ac, rc,
                                exp_rslt, tst_assoc_mof):
        # pylint: disable=no-self-use
        """
        Test getting reference classnames with no options on call and default
        namespace. Tests for both string and CIMClassName input
        """
        skip_if_moftab_regenerated()

        conn.compile_mof_string(tst_assoc_mof, namespace=ns)

        if ns is not None:
            cln = CIMClassName(cln, namespace=ns)

        if isinstance(exp_rslt, (list, tuple)):
            results = conn.Associators(cln, AssocClass=ac, Role=role,
                                       ResultRole=rr, ResultClass=rc)

            assert isinstance(results, list)
            assert len(results) == len(exp_rslt)
            for result in results:
                assert isinstance(result, tuple)
                assert isinstance(result[0], CIMClassName)
                assert isinstance(result[1], CIMClass)

            clns = [result[0].classname for result in results]
            assert set(clns) == set(exp_rslt)

        else:
            assert isinstance(exp_rslt, CIMError)
            exp_exc = exp_rslt
            if exp_exc.status_code == CIM_ERR_INVALID_NAMESPACE:
                if isinstance(cln, six.string_types):
                    cln = CIMClassName(cln, namespace='badnamespacename')
                else:
                    cln.namespace = 'badnamespacename'
            with pytest.raises(CIMError) as exec_info:
                conn.Associators(cln, AssocClass=ac, Role=role,
                                 ResultRole=rr, ResultClass=rc)
            exc = exec_info.value
            assert exc.status_code == exp_exc.status_code

        # TODO expand associator classes test to test for correct properties
        # in response

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        "targ_obj", ['XXX_Blan',
                     CIMInstanceName('XXX_Blah',
                                     keybindings={'InstanceID': 3})])
    def test_associator_target_err(self, conn, ns, targ_obj, tst_assoc_mof):
        # pylint: disable=no-self-use
        """
        Test getting reference classnames with no options on call and default
        namespace. Tests for both string and CIMClassName input
        """
        skip_if_moftab_regenerated()

        conn.compile_mof_string(tst_assoc_mof, namespace=ns)
        with pytest.raises(CIMError) as exec_info:
            conn.AssociatorNames(targ_obj)
        exc = exec_info.value
        assert exc.status_code == CIM_ERR_INVALID_PARAMETER


class Method1TestProvider(MethodProvider):
    """
    User test provider for InvokeMethod using CIM_Foo_sub_sub and method1.
    This is basis for testing passing of input parameters correctly and
    generating some exceptions.  It uses only one input parameter where the
    value defines the test and one return parameter that provides data from the
    provider, normally the value of the parameter defined with the input
    parameter. Test for existence of method named method1
    """

    def __init__(self, cimrepository):
        super(Method1TestProvider, self).__init__(cimrepository)

    def InvokeMethod(self, namespace, methodname, objectname, Params):
        """
        Simplistic test method. Validates methodname, objectname, Params
        and returns rtn value 0 and one parameter

        The parameters and return for Invoke method are defined in
        :meth:`~pywbem_mock.MethodProvider.InvokeMethod`
        """
        # validate namespace using method in BaseProvider
        self.validate_namespace(namespace)

        # get classname and validate. This provider uses only one class
        if isinstance(objectname, six.string_types):
            classname = objectname
        else:
            classname = objectname.classname
        assert classname.lower() == 'cim_foo_sub_sub'

        # Test if class exists.
        if not self.class_exists(namespace, classname):
            raise CIMError(
                CIM_ERR_NOT_FOUND,
                _format("class {0|A} does not exist in CIM repository, "
                        "namespace {1!A}", classname, namespace))

        if isinstance(objectname, CIMInstanceName):
            instance_store = self.get_instance_store(namespace)
            inst = self.find_instance(objectname, instance_store,
                                      copy_inst=False)
            if inst is None:
                raise CIMError(
                    CIM_ERR_NOT_FOUND,
                    _format("Instance {0|A} does not exist in CIM repository, "
                            "namespace {1!A}", objectname, namespace))
        # This method expects a single parameter input
        # Used to test the inputs.  The single input parameter is a string
        # and the value determines the method actions:
        # value = 'namespace' return the namespace name in the output parameter
        # value = 'methodname' return the method name in output parameter
        # value = 'objectname' return the object name in output parameter
        # value = 'returnvalue' return value 1
        if methodname.lower() == 'method1':
            if Params:
                # This should not be an assert.
                assert len(Params) == 1
                # Consider InputParam1 a required parameter if Params exist.
                if "InputParam1" not in Params:
                    raise CIMError(
                        CIM_ERR_INVALID_PARAMETER,
                        _format("Input parameter {0} does not exist in "
                                "method input parameters, {1!A}.",
                                "InputParam1", Params))
                assert isinstance(Params, NocaseDict)
                param = Params["InputParam1"]
                if not isinstance(param, CIMParameter):
                    raise CIMError(CIM_ERR_INVALID_PARAMETER)

                if param.type != 'string':
                    raise CIMError(CIM_ERR_INVALID_PARAMETER)

                # Generate OutputParam1 based on value in the input parameter
                val = param.value
                return_value = 0
                if val == 'namespace':
                    rtn_params = [CIMParameter('OutputParam1', 'string',
                                               value=namespace)]
                elif val == 'methodname':
                    rtn_params = [CIMParameter('OutputParam1', 'string',
                                               value=methodname)]
                elif val == 'objectname':
                    rtn_params = [CIMParameter('OutputParam1', 'string',
                                               value=objectname)]
                elif val == 'returnvalue':
                    return_value = 1
                    rtn_params = [CIMParameter('OutputParam1', 'string',
                                               value='returnvalue')]
            else:
                rtn_params = None

            return (return_value, rtn_params)

        raise CIMError(CIM_ERR_METHOD_NOT_AVAILABLE)


class TestInvokeMethod(object):
    # pylint: disable=too-few-public-methods
    """
    Test invoking extrinsic methods in Fake_WBEMConnection
    """

    @pytest.mark.parametrize(
        "ns", INITIAL_NAMESPACES + [None])
    @pytest.mark.parametrize(
        # desc: description of test.
        # inputs: dictionary of input object_name, methodname, Params and
        #         optionally params.
        # exp_output: dictionary of expected returnvalue ('return') and output
        #            params('params') as list of tuples.
        # exp_exc: None or expected exception object.
        # run_tst: Run test if True

        "desc, inputs, exp_output, exp_exc, run_tst", [

            ['Execution of Method1 namespace returns param with value of ns',
             {'object_name': CIMClassName('CIM_Foo_sub_sub'),
              'Params': [('InputParam1', 'namespace')]},
             {'return': 0, 'params': [CIMParameter('OutputParam1', 'string',
                                                   value='')]},
             None, OK],

            ['Execution of Method1 method with single input param. Tests '
             'object name case insensitivity and returns namespace',
             {'object_name': CIMClassName('cim_foo_sub_sub'),
              'Params': [('InputParam1', 'namespace')]},
             {'return': 0, 'params': [CIMParameter('OutputParam1', 'string',
                                                   value='')]},
             None, OK],

            ['Execution of Method1 method with single input param. Tests '
             'methodname case insensitivity and returns namespace',
             {'object_name': CIMClassName('cim_foo_sub_sub'),
              'Params': [('InputParam1', 'namespace')]},
             {'return': 0, 'params': [CIMParameter('OutputParam1', 'string',
                                                   value='')]},
             None, OK],

            ['Execution of Method1 method with single input param. Tests '
             'method name case insensitivity',
             {'object_name': CIMClassName('CIM_Foo_sub_sub'),
              'Params': [('InputParam1', 'objectname')]},
             {'return': 0, 'params': [CIMParameter('OutputParam1', 'string',
                                                   value='CIM_Foo_sub_sub')]},
             None, OK],

            ['Execution of Method1 method with objectname string. Test '
             ' methodname case insensitivity',
             {'object_name': 'CIM_Foo_sub_sub',
              'Params': None,
              'params': {'InputParam1': 'namespace'}},
             {'return': 1, 'params': [CIMParameter('OutputParam1', 'string',
                                                   value='FirstData')]},
             None, OK],


            ['Execution of Method1 method with objectname string. Test '
             ' methodname case insensitivity',
             {'object_name': 'CIM_Foo_sub_sub',
              'Params': [],
              'params': {'InputParam1': 'namespace'}},
             {'return': 1, 'params': [CIMParameter('OutputParam1', 'string',
                                                   value='FirstData')]},
             None, OK],

            ['Execution of Method1 method with invalid input param name',
             {'object_name': CIMClassName('CIM_Foo_sub_sub'),
              'Params': [('InputParamx', 'FirstData')]},
             {'return': 0, 'params': [CIMParameter('OutputParam1',
                                                   type='string')]},
             CIMError(CIM_ERR_INVALID_PARAMETER), RUN],

            ['Execution of Method1 method with CIMParam on input',
             {'object_name': CIMClassName('CIM_Foo_sub_sub'),
              'Params': [CIMParameter('InputParam1', type='string',
                                      value='methodname')]},
             {'return': 0, 'params': [CIMParameter('OutputParam1',
                                                   type='string')]},
             None, OK],

            ['Execute method name with valid instancename',
             {'object_name':
              CIMInstanceName('CIM_Foo_sub_sub',
                              keybindings={'InstanceID': 'CIM_Foo_sub_sub21'}),
              'Params': [CIMParameter('InputParam1', type='string',
                                      value='objectname')]},
             {'return': 0,
              'params': [CIMParameter('InputParam1', type='string',
                                      value=CIMInstanceName(
                                          'CIM_Foo_sub_sub',
                                          keybindings={
                                              'InstanceID':
                                              'CIM_Foo_sub_sub21'}))]},
             None, OK],

        ]
    )
    def test_invokemethod1(self, conn, ns, desc, inputs, exp_output,
                           exp_exc, tst_instances_mof, run_tst):
        # pylint: disable=no-self-use,unused-argument
        """
        Test extrinsic method invocation through the
        WBEMConnection.InovkeMethod method
        """
        if not run_tst:
            pytest.skip("This test marked to be skipped")
        skip_if_moftab_regenerated()

        conn.compile_mof_string(tst_instances_mof, namespace=ns)

        if 'test_class' not in inputs:
            test_class = Method1TestProvider
        else:
            test_class = inputs['test_class']

        if 'methodname' not in inputs:
            methodname = 'method1'
        else:
            methodname = inputs['methodname']

        tst_ns = ns or conn.default_namespace

        conn.register_provider(tst_ns, 'CIM_Foo_sub_sub', 'method',
                               test_class)

        # set namespace in object_name if required.
        object_name = inputs['object_name']

        if isinstance(object_name, (CIMClassName, CIMInstanceName)):
            object_name.namespace = ns
        else:
            # String object_name does not allow anything but default namespace
            # Bypass test if ns is not None
            if ns:
                return

        assert inputs['Params'] is None or len(inputs['Params']) <= 1
        if not exp_exc:
            # Two calls to account for **params
            if 'params' in inputs:
                result = conn.InvokeMethod(methodname,
                                           object_name,
                                           inputs['Params'],
                                           **inputs['params'])
            else:
                result = conn.InvokeMethod(methodname,
                                           object_name,
                                           inputs['Params'])

            # Test the return values against the input_param value
            return_values = result[1]

            input_params_dict = NocaseDict()
            if return_values:
                # build common dictionary from input Params and input params
                if 'Params' in inputs and inputs['Params'] is not None:
                    for param in inputs['Params']:
                        if isinstance(param, CIMParameter):
                            input_params_dict[param.name] = param
                        else:
                            input_params_dict[param[0]] = param[1]
                if 'params' in inputs:
                    for param in inputs['params']:
                        input_params_dict[param] = inputs['params'][param]

                for input_param in input_params_dict:
                    if isinstance(input_param, CIMParameter):
                        input_param = (input_param.name, input_param.value)

                    if input_param[1] == 'namespace':
                        assert return_values['OutputParam1'] == tst_ns
                    elif input_param[1] == 'objectname':
                        if isinstance(object_name, CIMClassName):
                            assert return_values['OutputParam1'] == \
                                object_name.classname
                        else:
                            assert return_values['OutputParam1'] == object_name

                    elif input_param[1] == 'methodname':
                        assert return_values['OutputParam1'] == methodname
                    elif input_param[1] == 'returnvalue':
                        assert result[0] == 1

            else:   # if no input params, should be no output params
                assert not input_params_dict

        else:
            if isinstance(exp_exc, CIMError) and \
                    exp_exc.status_code == CIM_ERR_INVALID_NAMESPACE:
                object_name.namespace = 'Reallybadnamespace'

            with pytest.raises(exp_exc.__class__) as exec_info:
                conn.InvokeMethod(methodname,
                                  object_name,
                                  inputs['Params'], )

            exc = exec_info.value
            if isinstance(exp_exc, CIMError):
                assert exc.status_code == exp_exc.status_code


@pytest.fixture()
def test_schema_root_dir():
    """
    Fixture defines the test_schema root directory for the schema and also
    removes the directory if it exists at the end of each test.
    This is a temporary directory and should be removed at the end of
    each test.
    """
    schema_dir = os.path.join(TEST_DIR, 'test_schema')
    yield schema_dir

    # Executes at the close of each test function
    if os.path.isdir(schema_dir):
        shutil.rmtree(schema_dir)


# TODO ks Rewrite the following tests into a single test with parameterization
class TestDMTFCIMSchema(object):
    """
    Test the DMTFCIMSchema class in pywbem_mock.  Since we do not want to always
    be downloading the DMTF schema for CI testing, we will generally skip the
    first test.
    """

    def test_current_schema(self):
        # pylint: disable=no-self-use
        """
        Test the current schema in the TESTSUITE_SCHEMA_DIR directory.
        The schema should be loaded and available.
        The tests should not change the TESTSUITE_SCHEMA_DIR directory in any
        way.
        """
        schema = DMTFCIMSchema(DMTF_TEST_SCHEMA_VER, TESTSUITE_SCHEMA_DIR,
                               verbose=False)

        assert schema.schema_version == DMTF_TEST_SCHEMA_VER
        assert schema.schema_root_dir == TESTSUITE_SCHEMA_DIR
        assert schema.schema_version_str == '%s.%s.%s' % DMTF_TEST_SCHEMA_VER
        assert os.path.isdir(schema.schema_root_dir)
        assert os.path.isdir(schema.schema_mof_dir)
        assert os.path.isfile(schema.schema_mof_file)
        assert os.path.isfile(schema.schema_pragma_file)
        assert os.path.isfile(schema.schema_zip_file)
        assert schema.schema_mof_file == schema.schema_pragma_file

        mof_dir = 'mofFinal%s' % schema.schema_version_str
        test_schema_mof_dir = os.path.join(TESTSUITE_SCHEMA_DIR, mof_dir)
        assert schema.schema_mof_dir == test_schema_mof_dir

        assert schema.schema_mof_file == \
            os.path.join(test_schema_mof_dir,
                         'cim_schema_%s.mof' % (schema.schema_version_str))

        assert repr(schema) == 'DMTFCIMSchema(' \
                               'schema_version=%s, ' \
                               'schema_root_dir=%s, schema_zip_file=%s, ' \
                               'schema_mof_dir=%s, ' \
                               'schema_pragma_file=%s, ' \
                               'schema_zip_url=%s)' % \
                               (DMTF_TEST_SCHEMA_VER,
                                TESTSUITE_SCHEMA_DIR,
                                schema.schema_zip_file,
                                test_schema_mof_dir,
                                schema.schema_pragma_file,
                                schema.schema_zip_url)

        schema_mof = schema.build_schema_mof(['CIM_ComputerSystem', 'CIM_Door'])

        exp_mof = '#pragma locale ("en_US")\n' \
                  '#pragma include ("Device/CIM_Door.mof")\n' \
                  '#pragma include ("System/CIM_ComputerSystem.mof")\n'

        assert schema_mof == exp_mof

    def test_schema_final_load(self, test_schema_root_dir):
        # pylint: disable=no-self-use
        """
        Test the DMTFCIMSchema class and its methods to get a schema from the
        DMTF, expand it, and to create a partial MOF schema definition for
        compilation into a new directory. This should completely clean the
        directory before the test.
        """
        if not os.environ.get('TEST_SCHEMA_DOWNLOAD', False):
            pytest.skip("Test run only if TEST_SCHEMA_DOWNLOAD is non-empty.")

        schema = DMTFCIMSchema(DMTF_TEST_SCHEMA_VER, test_schema_root_dir,
                               verbose=False)

        assert schema.schema_version == DMTF_TEST_SCHEMA_VER
        assert schema.schema_root_dir == test_schema_root_dir
        assert schema.schema_version_str == '%s.%s.%s' % DMTF_TEST_SCHEMA_VER
        assert os.path.isdir(schema.schema_root_dir)
        assert os.path.isdir(schema.schema_mof_dir)
        assert os.path.isfile(schema.schema_mof_file)
        assert os.path.isfile(schema.schema_pragma_file)
        assert os.path.isfile(schema.schema_zip_file)
        assert schema.schema_mof_file == schema.schema_pragma_file

        mof_dir = 'mofFinal%s' % schema.schema_version_str
        test_schema_mof_dir = os.path.join(test_schema_root_dir, mof_dir)
        assert schema.schema_mof_dir == test_schema_mof_dir

        assert schema.schema_mof_file == \
            os.path.join(test_schema_mof_dir,
                         'cim_schema_%s.mof' % (schema.schema_version_str))

        assert repr(schema) == 'DMTFCIMSchema(' \
                               'schema_version=%s, ' \
                               'schema_root_dir=%s, schema_zip_file=%s, ' \
                               'schema_mof_dir=%s, ' \
                               'schema_mof_file=%s, schema_zip_url=%s)' % \
                               (DMTF_TEST_SCHEMA_VER, test_schema_root_dir,
                                schema.schema_zip_file,
                                schema.schema_mof_dir,
                                schema.schema_mof_file,
                                schema.schema_zip_url)

        schema_mof = schema.build_schema_mof(['CIM_ComputerSystem', 'CIM_Door'])

        exp_mof = '#pragma locale ("en_US")\n' \
                  '#pragma include ("Device/CIM_Door.mof")\n' \
                  '#pragma include ("System/CIM_ComputerSystem.mof")\n'

        assert schema_mof == exp_mof

    def test_schema_experimental_load(self):
        # pylint: disable=no-self-use
        """
        Test the DMTFCIMSchema class and its methods to get a schema from the
        DMTF, expand it, and to create a partial MOF schema definition for
        compilation. This test downloads a second schema into the
        TESTSUITE_SCHEMA_DIR directory and then removes it.  It should not
        touch the existing schema.
        """
        if not os.environ.get('TEST_SCHEMA_DOWNLOAD', False):
            pytest.skip("Test run only if TEST_SCHEMA_DOWNLOAD is non-empty.")

        schema = DMTFCIMSchema(DMTF_TEST_SCHEMA_VER, TESTSUITE_SCHEMA_DIR,
                               use_experimental=True, verbose=False)

        assert schema.schema_version == DMTF_TEST_SCHEMA_VER
        assert schema.schema_version_str == '%s.%s.%s' % DMTF_TEST_SCHEMA_VER
        assert os.path.isdir(schema.schema_root_dir)
        assert os.path.isdir(schema.schema_mof_dir)
        assert os.path.isfile(schema.schema_mof_file)
        assert schema.schema_root_dir == TESTSUITE_SCHEMA_DIR
        mof_dir = 'mofExperimental%s' % schema.schema_version_str
        test_schema_mof_dir = os.path.join(TESTSUITE_SCHEMA_DIR, mof_dir)
        assert test_schema_mof_dir == mof_dir

        assert schema.schema_mof_file == \
            os.path.join(test_schema_mof_dir,
                         'cim_schema_%s.mof' % (schema.schema_version_str))

        # remove the second schema and test to be sure removed.
        schema.remove()
        assert not os.path.isdir(test_schema_mof_dir)
        assert not os.path.isfile(schema.schema_mof_file)
        assert os.path.isdir(schema.schema_root_dir)

    def test_second_schema_load(self):
        # pylint: disable=no-self-use
        """
        Test loading a second schema. This test loads a second schema
        into the TESTSUITE_SCHEMA_DIR directory and then removes it.
        """
        if not os.environ.get('TEST_SCHEMA_DOWNLOAD', False):
            pytest.skip("Test run only if TEST_SCHEMA_DOWNLOAD is non-empty.")

        schema = DMTFCIMSchema((2, 50, 0), TESTSUITE_SCHEMA_DIR, verbose=False)

        assert schema.schema_version == (2, 50, 0)
        assert schema.schema_version_str == '2.50.0'
        assert os.path.isdir(schema.schema_root_dir)
        assert os.path.isdir(schema.schema_mof_dir)
        assert os.path.isfile(schema.schema_mof_file)

        assert schema.schema_root_dir == TESTSUITE_SCHEMA_DIR
        mof_dir = 'mofFinal%s' % schema.schema_version_str
        test_schema_mof_dir = os.path.join(TESTSUITE_SCHEMA_DIR, mof_dir)
        assert schema.schema_mof_dir == test_schema_mof_dir

        assert schema.schema_mof_file == \
            os.path.join(test_schema_mof_dir,
                         'cim_schema_%s.mof' % (schema.schema_version_str))

        zip_path = schema.schema_zip_file
        assert os.path.isfile(zip_path)

        schema_mof = schema.build_schema_mof(['CIM_ComputerSystem', 'CIM_Door'])

        exp_mof = '#pragma locale ("en_US")\n' \
                  '#pragma include ("Device/CIM_Door.mof")\n' \
                  '#pragma include ("System/CIM_ComputerSystem.mof")\n'

        assert schema_mof == exp_mof

        schema.clean()
        assert not os.path.exists(schema.schema_mof_dir)
        assert os.path.exists(zip_path)

        schema.remove()
        assert not os.path.exists(zip_path)
        assert os.path.exists(TESTSUITE_SCHEMA_DIR)

    @pytest.mark.parametrize(
        "schema_version, excep", [
            [(1, 2), ValueError],
            ['blah', TypeError],
            [(1, 'fred', 2), TypeError],
            [(1, 205, 0), ValueError]
        ]
    )
    def test_schema_invalid_version(self, test_schema_root_dir, schema_version,
                                    excep):
        # pylint: disable=no-self-use
        """
        Test case where the class requested for the partial schema is not
        in the DMTF schema
        """
        with pytest.raises(excep):
            DMTFCIMSchema(schema_version, test_schema_root_dir, verbose=False)

    @pytest.mark.parametrize(
        # classes - iterable of leaf classnames or string with single classname
        # result = String defining the resulting cim_schema build list OR
        #          Exception expected
        "classes, result", [
            [['CIM_ComputerSystem', 'CIM_Door'],
             '#pragma locale ("en_US")\n' \
             '#pragma include ("Device/CIM_Door.mof")\n' \
             '#pragma include ("System/CIM_ComputerSystem.mof")\n'],

            [['CIM_Door'],
             '#pragma locale ("en_US")\n' \
             '#pragma include ("Device/CIM_Door.mof")\n'],

            ['CIM_Door',
             '#pragma locale ("en_US")\n' \
             '#pragma include ("Device/CIM_Door.mof")\n'],

            [['CIM_Blah'], ValueError],

            [['CIM_ComputerSystem', 'CIM_Door', 'CIM_Blah'], ValueError],

        ]
    )
    def test_schema_build(self, classes, result):
        # pylint: disable=no-self-use
        """
        Test case we use the existing DMTF schema used by other tests and
        create a partial schema mof.
        """
        schema = DMTFCIMSchema(DMTF_TEST_SCHEMA_VER, TESTSUITE_SCHEMA_DIR,
                               verbose=False)

        if isinstance(result, six.string_types):
            schema_mof = schema.build_schema_mof(classes)

            assert schema_mof == result
        else:
            try:
                schema_mof = schema.build_schema_mof(classes)
                assert True
            except result as re:
                print(re)
                re_str = "{}".format(re)
                for item in classes:
                    assert re_str.find(item)
