#
# (C) Copyright 2020 InovaDevelopment.comn
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
Implementation of the BaseRepository abstract classes that defines an in-memory
repository based on dictionaries.
"""

from __future__ import absolute_import, print_function

import six

from pywbem import CIMClass, CIMQualifierDeclaration, CIMInstance

from pywbem._nocasedict import NocaseDict
from pywbem._utils import _format

from ._baserepository import BaseObjectStore, BaseRepository
from ._utils import _uprint

__all__ = ['InMemoryRepository', 'InMemoryObjectStore']


class InMemoryObjectStore(BaseObjectStore):
    """
    Derived from the :class:`BaseObjectStore`, this class implements a
    dictionary based in-memory repository for CIM objects that manages
    CIM classes, CIM instances, and CIM qualifier declarations.

    Documentation for the methods and properties inherited from
    ~pywbem_mock:`BaseObjectStore` is also inherited in the pywbem
    documentation. Therefore the methods in this class have no
    documentation string.
    """
    # pylint: disable=line-too-long
    def __init__(self, cim_object_type):

        super(InMemoryObjectStore, self).__init__(cim_object_type)

        # Define the dictionary that implements the object store.
        # The keys in this dictionary are the names of the objects and
        # the values the corresponding CIM objects.
        if cim_object_type.__name__ in ("CIMClass", 'CIMQualifierDeclaration'):
            self._data = NocaseDict()
        elif cim_object_type.__name__ == 'CIMInstance':
            self._data = {}
        else:
            assert False, "InMemoryObjectStore: Invalid input parameter {}." \
                .format(cim_object_type)
    # pylint: enable=line-too-long

    def __repr__(self):
        return _format('InMemoryObjectStore(type={0},  dict={1}, size={2}',
                       self._cim_object_type, type(self._data),
                       len(self._data))

    def exists(self, name):
        return name in self._data

    def get(self, name, copy=True):
        # pylint: disable=no-else-return
        if name in self._data:
            if copy:
                return self._data[name].copy()
            return self._data[name]
        else:
            raise KeyError('{} not in {} object store'
                           .format(name, self._cim_object_type))

    def create(self, name, cim_object):
        assert isinstance(cim_object, self._cim_object_type)

        if name in self._data:
            raise ValueError('{} already in {} object store'
                             .format(name, self._cim_object_type))

        self._data[name] = cim_object.copy()

    def update(self, name, cim_object):
        assert isinstance(cim_object, self._cim_object_type)

        if name not in self._data:
            raise KeyError('{} not in {} object store'
                           .format(name, self._cim_object_type))

        # Replace the existing object with a copy of the input object
        self._data[name] = cim_object.copy()

    def delete(self, name):
        if name in self._data:
            del self._data[name]
        else:
            raise KeyError('{} not in {} object store'
                           .format(name, self._cim_object_type))

    def iter_names(self):
        return six.iterkeys(self._data)

    def iter_values(self, copy=True):
        for value in six.itervalues(self._data):
            if copy:
                yield(value.copy())
            else:
                yield(value)

    def len(self):
        return len(self._data)


class InMemoryRepository(BaseRepository):
    """
    A CIM repository that maintains its data in memory.

    Documentation for the methods and properties inherited from
    ~pywbem_mock:`BaseObjectStore` is also inherited in the pywbem
    documentation. Therefore the methods in this class have no
    documentation string.
    """
    def __init__(self, initial_namespace=None):
        """
        Initialize the InMemoryRepository.

        Parameters:

          initial_namespace:(:term:`string` or None):
            Optional initial namespace that will be added to
            the CIM repository.
        """

        # Create the in memory repository.  This defines the top level
        # NocaseDict which defines the namespaces. The keys of this
        # dictionary are namespace names and the values are the dictionaries
        # defining the CIM classes, CIM instances, and CIM qualifier
        # declarations where the keys are "classes", "instance", and
        # "qualifiers" and the value for each is an instance of the
        # class InMemoryObjectStore
        self._repository = NocaseDict()

        # If an initial namespace is defined, add it to the repository
        if initial_namespace:
            self.add_namespace(initial_namespace)

    def print_repository(self, dest=None, ):
        """
        Display the items in the repository. This displays information on
        the items in the data base and is only a diagnostic tool.

        Parameters:
          dest (:term:`string`):
            File-like object(ex. file_path, or other data stream definition )
            for the output. If `None`, the output is written to stdout.
        """
        def objstore_info(objstore_name):
            """
            Display the data for the object store
            """
            for ns in self._repository:
                if objstore_name == 'class':
                    repo = self.get_class_repo(ns)
                elif objstore_name == 'qualifier':
                    repo = self.get_qualifier_repo(ns)
                elif objstore_name == 'instance':
                    repo = self.get_instance_repo(ns)
                else:
                    assert objstore_name == 'instance'
                    repo = self.get_instance_repo(ns)

                rtn_str = u'Namespace: {} Repo: {} len:{}\n'.format(
                    ns, objstore_name, repo.len())
                for val in repo.iter_values():
                    rtn_str += (u'{}\n'.format(val))
                return rtn_str

        namespaces = ",".join(self._repository.keys())
        _uprint(dest, _format(u'NAMESPACES: {0}', namespaces))
        _uprint(dest, _format(u'QUALIFIERS: {0}', objstore_info('qualifier')))
        _uprint(dest, _format(u'CLASSES: {0}', objstore_info('class')))
        _uprint(dest, _format(u'INSTANCES: {0}', objstore_info('instance')))

    def validate_namespace(self, namespace):
        if namespace is None:
            raise ValueError("Namespace argument must not be None")

        namespace = namespace.strip('/')
        try:
            self._repository[namespace]
        except KeyError:
            raise KeyError('Namespace {} does not exist in repository'.
                           format(namespace))

    def add_namespace(self, namespace):
        if namespace is None:
            raise ValueError("Namespace argument must not be None")

        namespace = namespace.strip('/')

        if namespace in self._repository:
            raise ValueError('Namespace {} already in repository'.
                             format(namespace))

        self._repository[namespace] = {}

        # Create the data store for each of the object types.
        self._repository[namespace]['classes'] = InMemoryObjectStore(CIMClass)

        self._repository[namespace]['instances'] = InMemoryObjectStore(
            CIMInstance)

        self._repository[namespace]['qualifiers'] = InMemoryObjectStore(
            CIMQualifierDeclaration)

    def remove_namespace(self, namespace):
        self.validate_namespace(namespace)
        namespace = namespace.strip('/')

        if self.get_class_repo(namespace).len() != 0 or \
                self.get_qualifier_repo(namespace).len() != 0 or \
                self.get_instance_repo(namespace).len() != 0:
            raise ValueError('Namespace {} removal invalid. Namespace not '
                             'empty'.format(namespace))

        del self._repository[namespace]

    @property
    def namespaces(self):
        return list(self._repository)

    def get_class_repo(self, namespace):
        if namespace is None:
            raise ValueError("Namespace None not permitted.")
        namespace = namespace.strip('/')
        self.validate_namespace(namespace)
        return self._repository[namespace]['classes']

    def get_instance_repo(self, namespace):
        if namespace is None:
            raise ValueError("Namespace None not permitted.")
        namespace = namespace.strip('/')
        self.validate_namespace(namespace)
        return self._repository[namespace]['instances']

    def get_qualifier_repo(self, namespace):
        if namespace is None:
            raise ValueError("Namespace None not permitted.")
        namespace = namespace.strip('/')
        self.validate_namespace(namespace)
        return self._repository[namespace]['qualifiers']
