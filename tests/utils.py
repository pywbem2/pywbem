"""
Utility functions for pywbem testing
"""

from __future__ import absolute_import

import sys
import os
import pytest
import ply
from packaging.version import parse as parse_version


def skip_if_moftab_regenerated():
    """
    Skip the testcase if we run against an installed version of pywbem (as
    indicated by the TEST_INSTALLED environment variable), and the testcase
    would re-generate the MOF parsing table files.

    This function should be used by test cases that parse MOF files, so the
    test case is skipped in that case.

    Background:

    Pywbem uses the `ply` package to parse CIM MOF files and part of a pywbem
    installation are parsing table files named mofparsetab.py and moflextab.py
    that are generated by `ply`. Before pywbem 0.14.5, the version of `ply`
    module that was used to build the pywbem distribution archive needed to be
    compatible with the version of `ply` installed in the Python environment,
    otherwise `ply` attempted to re-generate these parse table files in the
    `pywbem` installation directory. Thus, if the `pywbem` installation
    directory is in the system Python, a normal user will typically encounter
    a permission denied error.

    If the installed version of `pywbem` is 0.14.5 or higher, it has tolerance
    against mismatches between these `ply` versions, by having `ply`
    re-generate the parsing tables in memory if needed, but no longer writing
    them out to the pywbem installation directory.
    """

    test_installed = os.getenv('TEST_INSTALLED', False)

    pywbem = import_installed('pywbem')

    try:
        from pywbem import mofparsetab, moflextab
    except ImportError:
        if test_installed:
            # The mofparsetab and moflextab files should not be auto-generated
            # in this case.
            pytest.fail("Cannot run this MOF testcase against an installed "
                        "pywbem (version {0}, installed at {1}) "
                        "because that installation does not contain the "
                        "mofparsetab.py or moflextab.py files".
                        format(pywbem.__version__, pywbem.__file__))
        else:
            # The mofparsetab and moflextab files will be auto-generated.
            return

    pywbem_not_tolerant = parse_version(pywbem.__version__) <= \
        parse_version('0.14.4')  # This causes 0.14.5.devN to be tolerant

    # pylint: disable=protected-access
    mofparsetab_version = mofparsetab._tabversion
    moflextab_version = moflextab._tabversion
    # pylint: enable=protected-access
    ply_version = ply.__version__

    mofparsetab_mismatch = parse_version(mofparsetab_version) != \
        parse_version(ply_version)
    moflextab_mismatch = parse_version(moflextab_version) != \
        parse_version(ply_version)

    if test_installed and pywbem_not_tolerant and \
            (mofparsetab_mismatch or moflextab_mismatch):
        pytest.skip("Cannot run this MOF testcase against an installed "
                    "pywbem (version {0}, installed at {1}) because that "
                    "pywbem version does not tolerate version mismatches "
                    "between the current ply version and the ply version that "
                    "was used to create the pywbem mof*tab files: "
                    "current ply: {2}, ply in mofparsetab.py: {3}, "
                    "ply in moflextab.py: {4}".
                    format(pywbem.__version__, pywbem.__file__,
                           ply_version,
                           mofparsetab_version, moflextab_version))


def import_installed(module_name):
    """
    Import a Python module/package, controlling whether it is loaded from the
    normal Python module search path, or from an installed version (excluding
    the module in the current directory).

    The TEST_INSTALLED environment variable controls this as follows:

      * If not set or empty, the normal Python module search path is used.
        Because that search path contains the current directory in front of the
        list, this will cause a module directory in the current directory to
        have precedence over any installed versions of the module.

      * If non-empty, the current directory is removed from the Python module
        search path, and an installed version of the module is thus used, even
        when a module directory exists in the current directory. This can be
        used for testing an OS-installed version of the module.

    Example usage, e.g. in a pywbem test program::

        from ...utils import import_installed
        pywbem = import_installed('pywbem')  # pylint: disable=invalid-name
        from pywbem import ...

    The number of dots in `from ..utils` depends on where the test program
    containing this code is located, relative to the tests/utils.py file.
    """
    test_installed = os.getenv('TEST_INSTALLED', False)
    if test_installed:

        # Remove '' directory.
        dirpath = ''
        try:
            ix = sys.path.index(dirpath)
        except ValueError:
            ix = None
        if ix is not None:
            if test_installed == 'DEBUG':
                print("Debug: Removing {0} at index {1} from module search "
                      "path".format(dirpath, ix))
            del sys.path[ix]

        # Move CWD to end. Reason is that when testing with an editable
        # installation, the CWD is needed, but when testing with a non-editable
        # installation, the package should not be found inthe CWD.
        # Note that somehow the CWD gets inserted at the begin of the search
        # path every time, so we need a loop.
        dirpath = os.getcwd()
        while True:
            try:
                ix = sys.path.index(dirpath)
            except ValueError:
                if test_installed == 'DEBUG':
                    print("Debug: Appending {0} to end of module search "
                          "path".format(dirpath))
                sys.path.append(dirpath)
                break
            if ix == len(sys.path) - 1:
                # it exists once at the end
                break
            if test_installed == 'DEBUG':
                print("Debug: Removing {0} at index {1} from module search "
                      "path".format(dirpath, ix))
            del sys.path[ix]

    if module_name not in sys.modules:
        module = __import__(module_name, level=0)  # only absolute imports
        if test_installed == 'DEBUG':
            print("Debug: {0} module newly loaded from: {1}".
                  format(module_name, module.__file__))
    else:
        module = sys.modules[module_name]
        if test_installed == 'DEBUG':
            print("Debug: {0} module was already loaded from: {1}".
                  format(module_name, module.__file__))
    return module
