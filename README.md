# Pywbem - A WBEM client and related utilities, written in pure Python

[![Version on Pypi](https://img.shields.io/pypi/v/pywbem.svg)](https://pypi.python.org/pypi/pywbem/)
[![Test status (master)](https://github.com/pywbem/pywbem/actions/workflows/test.yml/badge.svg?branch=master)](https://github.com/pywbem/pywbem/actions/workflows/test.yml?query=branch%3Amaster)
[![Docs status (master)](https://readthedocs.org/projects/pywbem/badge/?version=latest)](https://readthedocs.org/projects/pywbem/builds/)
[![Test coverage (master)](https://coveralls.io/repos/github/pywbem/pywbem/badge.svg?branch=master)](https://coveralls.io/github/pywbem/pywbem?branch=master)
[![Supported Python](https://img.shields.io/pypi/pyversions/pywbem.svg?color=brightgreen)](https://pypi.python.org/pypi/pywbem/)

# Overview

Pywbem is a WBEM client and WBEM indication listener and provides
related WBEM client-side functionality. It is written in pure Python and
runs on Python 3.

WBEM is a standardized approach for systems management defined by the
[DMTF](https://www.dmtf.org) that is used in the industry for a wide
variety of systems management tasks. See [WBEM
Standards](https://www.dmtf.org/standards/wbem) for more information. An
important use of this approach is the
[SMI-S](https://www.snia.org/tech_activities/standards/curr_standards/smi)
standard defined by [SNIA](https://www.snia.org) for managing storage.

# Functionality

The major components of pywbem are shown in this diagram:

![pywbem components](images/pywbemcomponents.png)

The green components all have Python APIs for use by user applications.
The yellow components are command line utilities. The blue components
are not part of the pywbem or pywbemtools packages.

The pywbem components all run on the client side and communicate with a
remote WBEM server using the standard CIM operations over HTTP (CIM-XML)
protocol defined by the DMTF.

Pywbem provides the following Python APIs:

- [WBEM Client Library](https://pywbem.readthedocs.io/en/latest/client.html) -
  An API that supports issuing WBEM operations to a WBEM server, using the CIM
  operations over HTTP (CIM-XML) protocol defined by the DMTF.
- [WBEM Server Library](https://pywbem.readthedocs.io/en/latest/server.html) -
  An API that encapsulates selected functionality of a WBEM server for use by a
  WBEM client application, such as determining the Interop namespace and other
  basic information about the server, or the management profiles advertised by
  the server.
- [WBEM Indication Listener](https://pywbem.readthedocs.io/en/latest/indication.html) -
  An API for creating and managing a thread-based WBEM listener that waits for
  indications (i.e. event notifications) emitted by a WBEM server using the
  CIM-XML protocol. The API supports registering callback functions that get
  called when indications are received by the listener.
- [WBEM Subscription Manager](https://pywbem.readthedocs.io/en/latest/subscription.html) -
  An API for viewing and managing subscriptions for indications on a WBEM server.
- [MOF Compiler](https://pywbem.readthedocs.io/en/latest/compiler.html) -
  An API for compiling MOF files or strings into a CIM repository (e.g. on a
  WBEM server), or for test-compiling MOF.
- [Mock WBEM server](https://pywbem.readthedocs.io/en/latest/mockwbemserver.html) -
  An API for setting up a mocked WBEM server that is used instead of a real WBEM
  server. This allows setting up well-defined WBEM servers locally that can be
  used for example for prototyping or testing user applications.

Pywbem provides this command line utility:

- [mof_compiler](https://pywbem.readthedocs.io/en/latest/utilities.html#mof-compiler) -
  A MOF compiler that takes MOF files as input and compiles them into a CIM
  repository (e.g. on a WBEM server).

The related [pywbemtools project](https://github.com/pywbem/pywbemtools)
provides the following command line utilities:

- [pywbemcli](https://pywbemtools.readthedocs.io/en/latest/pywbemcli) -
  A client-side command line interface for a WBEM server, supporting a command
  line mode and an interactive (repl) mode.
- [pywbemlistener](https://pywbemtools.readthedocs.io/en/latest/pywbemlistener) -
  A command that runs and manages WBEM indication listeners that can receive
  indications from a WBEM server.

# Installation

To install the latest released version of pywbem into your active Python
environment:

``` bash
$ pip install pywbem
```

or, if you want to use [uv](https://docs.astral.sh/uv/):

``` bash
$ uv pip install pywbem
```

This will also install any prerequisite Python packages.

Starting with version 1.0.0, pywbem has no OS-level prerequisite packages.

On newer versions of some operating systems (ex. Ubuntu 23.04, Debian 12)
pip will install Python packages only into virtual Python environments. This is
by design to avoid conflicts between OS distributed python packages and other
user installed packages and is documented in
[Python PEP 668](https://peps.python.org/pep-0668/). See the pywbem documentation
[Troubleshooting section](https://pywbem.readthedocs.io/en/latest/appendix.html#troubleshooting)
for more information if an \"Externally-managed-environment\" error
occurs during installation.

For more details and alternative ways to install, see the
[Installation section](https://pywbem.readthedocs.io/en/latest/intro.html#installation)
in the pywbem documentation.

# Documentation

- [Documentation](https://pywbem.readthedocs.io/en/latest/) -
  Concepts, tutorials, Python API, command line tools, and developer
  documentation.
- [Tutorial](https://pywbem.readthedocs.io/en/latest/tutorial.html) -
  The tutorials in the documentation are provided as Jupyter notebooks
  and provide working examples of pywbem API usage.
- [Change log](https://pywbem.readthedocs.io/en/latest/changes.html) -
  Detailed change history in the documentation.
- [Presentations](https://pywbem.github.io/pywbem/documentation.html) -
  status, concepts, and implementation of pywbem.

# Quick Start

The following simple example script lists the namespaces and the Interop
namespace in a particular WBEM server:

``` python
#!/usr/bin/env python

import pywbem

server_url = 'http://localhost'
user = 'fred'
password = 'blah'

conn = pywbem.WBEMConnection(server_url, (user, password))

server = pywbem.WBEMServer(conn)

print(f"Interop namespace:\n  {server.interop_ns}")

print("All namespaces:")
for ns in server.namespaces:
    print(f"  {ns}")
```

# Project Planning

For each upcoming release, the bugs and feature requests that are planned to be
addressed in that release are listed in the
[issue tracker](https://github.com/pywbem/pywbem/issues) with an according
milestone set that identifies the target release. The due date on the milestone
definition is the planned release date. There is usually also an issue that
sets out the major goals for an upcoming release.

# Planned Next Release

Fix versions of pywbem are released as needed.

The next planned feature version(s) of pywbem can be found by listing the
[release definition issues](https://github.com/pywbem/pywbem/issues?q=is%3Aissue+is%3Aopen+label%3A%22release+definition%22).

# Contributing

For information on how to contribute to pywbem, see the
[Contributing section](https://pywbem.readthedocs.io/en/latest/development.html#contributing)
in the pywbem documentation.

# License

Pywbem is provided under the
[GNU Lesser General Public License (LGPL) version 2.1](https://raw.githubusercontent.com/pywbem/pywbem/master/LICENSE.txt),
or (at your option) any later version.
