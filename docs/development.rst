
.. _`Development`:

Development
===========

This section only needs to be read by developers of the pywbem package.
People that want to make a fix or develop some extension, and people that
want to test the project are also considered developers for the purpose of
this section.


.. _`Repository`:

Repository
----------

The repository for pywbem is on GitHub:

https://github.com/pywbem/pywbem


.. _`Setting up the development environment`:

Setting up the development environment
--------------------------------------

You may use any supported OS platform as the development environment for
pywbem. On native Windows, you need to use a Windows command prompt in
administrator mode.

1. It is recommended that you set up a `virtual Python environment`_.
   Have the virtual Python environment active for all remaining steps.

2. Make sure the following commands are available:

   - ``git``
   - ``make`` (GNU make)
   - ``choco`` on native Windows (`Chocolatey package manager`_)

3. Clone the Git repo of this project and switch to its working directory:

   .. code-block:: bash

       $ git clone git@github.com:pywbem/pywbem.git
       $ cd pywbem

4. Install the prerequsites for pywbem development.
   This will install Python packages into the active Python environment,
   and OS-level packages:

   .. code-block:: bash

       $ make develop

5. This project uses Make to do things in the currently active Python
   environment. The command:

   .. code-block:: bash

       $ make

   displays a list of valid Make targets and a short description of what each
   target does. See the next sections for details.

.. _virtual Python environment: https://docs.python-guide.org/en/latest/dev/virtualenvs/

.. _`Chocolatey package manager`: https://chocolatey.org/


.. _`Building the documentation`:

Building the documentation
--------------------------

The ReadTheDocs (RTD) site is used to publish the documentation for the
pywbem package at https://pywbem.readthedocs.io/

This page is automatically updated whenever the Git repo for this package
changes the branch from which this documentation is built.

In order to build the documentation locally from the Git work directory,
execute:

.. code-block:: bash

    $ make builddoc

The top-level document to open with a web browser will be
``build_doc/html/docs/index.html``.


.. _`Testing`:

.. # Keep the tests/README file in sync with this 'Testing' section.

Testing
-------

All of the following `make` commands run the tests in the currently active
Python environment, and need to be invoked in the Git repo work directory.

By default, the tests use the `pywbem` and `pywbem_mock` modules from the
respective directories in the Git repo work directory.
Pywbem 0.14.5 introduced a way to test installed versions of the pywbem
package. For details, see :ref:`Testing installed versions of pywbem`.

The `tests` directory has the following subdirectory structure:

::

    tests
     +-- unittest            Unit tests
     |    +-- utils               Utility functions used by unit tests
     |    +-- pywbem              Unit tests for the pywbem package
     |    +-- pywbem_mock         Unit tests for the pywbem_mock package
     |    +-- unittest_utils      Unit tests for tests/unittest/utils
     |    +-- functiontest        Unit tests for tests/functiontest
     |    +-- end2endtest_utils   Unit tests for tests/end2endtest/utils
     |    +-- servers             Unit tests for tests/servers
     +-- functiontest        Function tests
     +-- end2endtest         End2end tests
     |    +-- utils               Utility functions used by end2end tests
     +-- manualtest          Manual tests
     +-- server_definitions  WBEM server definition file used by some tests and module
     |                         for accessing it
     +-- profiles            Simple definitions of management profiles used by some tests
     +-- schema              The CIM schema MOF files used by some MOF tests
     +-- dtd                 The CIM DTD file used by some CIM-XML validation tests

There are multiple types of tests in pywbem:

1. Unit tests and function tests

   These tests do not require any WBEM server to be available, and the tests
   validate their results automatically.

   The distinction between unit tests and function tests as used in pywbem is
   that function tests exercise the entire pywbem client component or entire
   pywbem scripts, while unit tests exercise single modules.

   They are run by executing:

   .. code-block:: bash

       $ make test

   Test execution can be modified by a number of environment variables, as
   documented in the make help (execute `make help`).

   An alternative that does not depend on the makefile and thus can be executed
   from the source distribution archive, is:

   .. code-block:: bash

       $ ./setup.py test

   Options for pytest can be passed using the ``--pytest-options`` option.

2. End2end tests

   These tests are run against one or more WBEM servers, and the tests validate
   their results automatically.

   They are run by preparing a server definition file:

   ::

       tests/server_definitions/server_definition_file.yml

   from the provided example, and by executing:

   .. code-block:: bash

       $ make end2endtest

   Again, test execution can be modified by a number of environment variables,
   as documented in the make help (execute `make help`).

   An alternative that does not depend on the makefile, is:

   .. code-block:: bash

       $ ./setup.py end2endtest

   Options for pytest can be passed using the ``--pytest-options`` option.

3. Manual tests

   There are several Python scripts and shell scripts that can be run manually.
   The results need to be validated manually.

   These scripts are in the directory:

   ::

       tests/manualtest/

   and are executed by simply invoking them from within the main directory
   of the repository, e.g.:

   ::

       tests/manualtest/run_cim_operations.py

   Some of the scripts support a `--help` option that informs about their
   usage.

   The `run_cim_operations.py` script needs a particular MOF file loaded in the
   repository of the WBEM server that is used for the test. This can be done
   using the MOF compiler of pywbem:

   .. code-block:: bash

       $ mof_compiler -s <target_url> tests/unittest/pywbem/test.mof

To run the unit and function tests in all supported Python environments, the
Tox tool can be used. It creates the necessary virtual Python environments and
executes `make test` (i.e. the unit and function tests) in each of them.

For running Tox, it does not matter which Python environment is currently
active, as long as the Python `tox` package is installed in it:

.. code-block:: bash

    $ tox                              # Run tests on all supported Python versions
    $ tox -e py27                      # Run tests on Python 2.7


.. _`Testing from the source archives on Pypi or GitHub`:

Testing from the source archives on Pypi or GitHub
--------------------------------------------------

The wheel distribution archives on Pypi
(e.g. ``pywbem-1.0.0-py2.py3-none-any.whl``)
contain only the files needed to run pywbem, but not the files needed to test
it.

The source distribution archives on Pypi and GitHub
(e.g. ``pywbem-1.0.0.tar.gz``)
contain all files that are needed to run and to test pywbem.

This allows testing pywbem without having to check out the entire repository,
and is convenient for testing e.g. when packaging pywbem into OS-level packages.

When installing these source distribution archives, the files needed for
running pywbem are installed into the active Python environment, but not the
test files.

The following commands download the source distribution archive on Pypi for a
particular version of pywbem into the current directory and unpack it:

.. code-block:: bash

    $ pip download --no-deps --no-binary :all: pywbem==1.0.0
    $ tar -xf pywbem-1.0.0.tar.gz
    $ cd pywbem-1.0.0
    $ ls -1
    -rw-r--r--   1 maiera  staff    468 Jun 29 22:31 INSTALL.md
    -rw-r--r--   1 maiera  staff  26436 May 26 06:45 LICENSE.txt
    -rw-r--r--   1 maiera  staff    367 Jul  3 07:54 MANIFEST.in
    -rw-r--r--   1 maiera  staff   3451 Jul  3 07:55 PKG-INFO
    -rw-r--r--   1 maiera  staff   7665 Jul  2 23:20 README.md
    -rw-r--r--   1 maiera  staff   1624 Jul  2 23:20 README_PYPI.md
    -rwxr-xr-x   1 maiera  staff   2881 Jun 29 22:31 build_moftab.py
    -rwxr-xr-x   1 maiera  staff  13850 Jun 29 22:31 mof_compiler
    -rw-r--r--   1 maiera  staff    105 May 26 06:45 mof_compiler.bat
    drwxr-xr-x  29 maiera  staff    928 Jul  3 07:55 pywbem
    drwxr-xr-x   8 maiera  staff    256 Jul  3 07:55 pywbem.egg-info
    drwxr-xr-x  18 maiera  staff    576 Jul  3 07:55 pywbem_mock
    -rw-r--r--   1 maiera  staff   1067 Jun 29 22:31 requirements.txt
    -rw-r--r--   1 maiera  staff     38 Jul  3 07:55 setup.cfg
    -rwxr-xr-x   1 maiera  staff   7555 Jul  3 07:24 setup.py
    -rw-r--r--   1 maiera  staff   2337 Jul  2 23:20 test-requirements.txt
    drwxr-xr-x  15 maiera  staff    480 Jul  3 07:55 tests

Pywbem, its dependent packages, and packages needed for testing pywbem can be
installed with the package extra named "test":

.. code-block:: bash

    $ pip install .[test]

When testing pywbem installations in Linux distributions that include pywbem as
an OS-level package, the corresponding OS-level packages would instead be
installed for these dependent Python packages. The ``test-requirements.txt``
file shows which dependent Python packages are needed for testing pywbem.

Finally, the tests can be run using the ``setup.py`` script:

.. code-block:: bash

    $ ./setup.py test
    $ ./setup.py leaktest
    $ ./setup.py end2endtest

These commands are listed in the help of the ``setup.py`` script:

.. code-block:: bash

    $ ./setup.py --help-commands
    . . .
    Extra commands:
      . . .
      test              pywbem: Run unit and function tests using pytest
      leaktest          pywbem: Run leak tests using pytest
      end2endtest       pywbem: Run end2end tests using pytest
      . . .

The additional options supported by these commands are shown in their help:

.. code-block:: bash

    $ ./setup.py test --help
    . . .
    Options for 'test' command:
      --pytest-options  additional options for pytest, as one argument
    . . .

Note: The ``test`` command of ``setup.py`` is not the deprecated built-in
command (see `<https://github.com/pypa/setuptools/issues/1684>`_), but has been
implemented in ``setup.py`` in such a way that it only runs the tests but
does not install anything upfront. The ``leaktest`` and
``end2endtest`` commands have been implemented in the same way. Therefore, this
approach can be used for testing pywbem installations from OS-level packages
in Linux distributions that include pywbem.


.. _`Testing installed versions of pywbem`:

Testing installed versions of pywbem
------------------------------------

By default, the tests use the pywbem and pywbem_mock modules from the
respective directories in the Git repo work directory.

Pywbem 0.14.5 introduced a way to test installed versions of the pywbem
package. This is useful for example for testing a version of pywbem that has
been packaged as an OS-level package. Typically, such a version would be
installed into the system Python.

Some words of caution:

* Testing an installed version of pywbem with test cases from a pywbem repo
  of a different version can result in failing test cases for several reasons:

  - If a new version of pywbem has added functionality, its test cases are also
    extended accordingly. Running such newer test cases against an older
    installed version of pywbem may fail simply because the installed version
    does not yet have the added functionality.

  - Fixes in pywbem or in the test cases may change behavior in a subtle way
    that causes test cases to fail.

  - Unit test cases are particularly vulnerable to version mismatches because
    they test at the module level, including module interfaces that are
    internal to pywbem and thus can legally change incompatibly between
    versions.

* If the version of the installed pywbem is before 0.14.5, some test cases
  that compile MOF will be skipped to avoid permission denied errors when
  ply attempts to re-generate its parsing table files in the pywbem
  installation directory in case of ply version mismatches. Starting with
  pywbem 0.14.5, it has tolerance against ply version mismatches.

In order to not clutter up the system Python with Python packages needed for
running the pywbem tests, the following steps use a virtual Python environment
that uses the packages of the system Python. That way, the installed version of
pywbem becomes available to the virtual Python environment from the system
Python, while any additional packages that are needed but not yet available
that way, will be installed into the virtual Python environment.

Follow these steps to run pywbem tests against a version of pywbem that is
installed into the system Python:

1. Verify that the following commands are available when the system Python
   is active:

   .. code-block:: bash

       $ virtualenv --version   # Python virtualenv package
       $ pip --version

2. Create and activate a virtual Python environment of the intended Python
   version, that is based on the system Python:

   .. code-block:: bash

       $ virtualenv --system-site-packages --no-setuptools --no-pip --no-wheel .virtualenv/test
       $ source .virtualenv/test/bin/activate

   The pywbem project is set up so that Git ignores the ``.virtualenv``
   directory, so use that directory name for ease of Git handling.

3. Verify that in that virtual Python environment, pywbem comes from the
   intended installation:

   .. code-block:: bash

       $ pip show pywbem

4. Ensure a fresh start of the make process. This should be done whenever
   switching between the installed version of pywbem and the local directories:

   .. code-block:: bash

       $ make clobber

5. Run the pywbem tests with environment variable ``TEST_INSTALLED`` being set:

   .. code-block:: bash

       $ TEST_INSTALLED=1 make test

   This will assume that the pywbem package and any prerequisite Python
   packages and OS-level packages are already installed.

   This will also move the current directory (i.e. the repo working directory)
   to the end of the module search path, so that the installed version of
   pywbem is used when importing it into the test scripts.

   Setting ``TEST_INSTALLED=DEBUG`` causes some debug messages to be printed
   that allow verifying from where the pywbem and pywbem_mock modules
   are loaded.

   This also works for the pywbem end2end tests:

   .. code-block:: bash

       $ TEST_INSTALLED=1 make end2end

Note that tox does not support creating its virtual Python environments
based on the system Python, so at this point, tox cannot be used for this
approach.


.. _`Updating the DMTF MOF Test Schema`:

Updating the DMTF MOF Test Schema
---------------------------------

Pywbem uses DMTF CIM Schemas in its CI testing.  The schema used is stored in
the form received from the DMTF in the directory ``tests/schema`` and is
expanded and compiled as part of the unit tests.

Since the DMTF regularly updates the schema, the pywbem project tries to stay
up-to-date with the current schema. At the same time, earlier schemas can be
used for testing also by changing the definitions for the dmtf schema to be
tested.

The schema used for testing can be modified by modifying the test file:

::

    tests/unittest/utils/dmtf_mof_schema_def.py


.. _`Developing Ipython Notebooks`:

Developing PyWBEM Ipython Documentation Notebooks
-------------------------------------------------

The pywbem developers are using ipython notebooks to demonstrate the use of
pywbem.  Today we generally have one notebook per operation or group of
operations including definition of the operation, references back to the
pywbem documentation, and one or more examples  (hopefully examples that
will actually execute against a wbem server)

These can easily be extended or supplemented using a local ipython or
jupyter server by:

1. Install ipython or Jupyter software using pip or pip3. The notebook server
may be installed as root or within a python virtual environment. For example:

.. code-block:: bash

    $ sudo pip install ipython
    or
    $ sudo pip3 install ipython
    or
    $ sudo pip install jupyter

The notebook server may be installed as root or within a python virtual
environment.

2. Start the local ipython/jupyter notebook server in the notebook directory
(`pywbem/docs/notebooks`) referencing that directory in the command line
call:

.. code-block:: bash

    $ ipython notebook docs/notebooks
    or
    $ jupyter notebook docs/notebooks

This will start the local ipython/juypter notebook server and on the first page
displayed in your web browser all existing pywbem ipython notebooks will be
available for editing. New ones can be created using the commands on that
ipython server web page.

New and changed notebooks must go through the same contribution process as other
components of pywbem to be integrated into the github repository.


.. _`Git workflow`:

Git workflow
------------

* Long-lived branches:

  - ``master`` - for next functional version
  - ``stable_M.N`` - for fix stream of released version M.N.

* We use topic branches for everything!

  - Based upon the intended long-lived branch, if no dependencies
  - Based upon an earlier topic branch, in case of dependencies
  - It is valid to rebase topic branches and force-push them.

* We use pull requests to review the branches.

  - Use the correct long-lived branch (e.g. ``master`` or ``stable_0.8``) as a
    merge target!
  - Review happens as comments on the pull requests.
  - At least two +1 are required for merging.

* GitHub meanwhile offers different ways to merge pull requests. We merge pull
  requests by creating merge commits, so the single commits of a topic branch
  remain unchanged, and we see the title line of the pull request in the merge
  commit message, which is often the only place that tells the issue that was
  fixed.


.. _`Releasing a version`:

Releasing a version
-------------------

This section describes how to release a version of pywbem to PyPI.

It covers all variants of versions that can be released:

* Releasing a new major version (Mnew.0.0) based on the master branch
* Releasing a new minor version (M.Nnew.0) based on the master branch
* Releasing a new update version (M.N.Unew) based on the stable branch of its
  minor version

This description assumes that you are authorized to push to the remote repo
at https://github.com/pywbem/pywbem and that the remote repo
has the remote name ``origin`` in your local clone.

Any commands in the following steps are executed in the main directory of your
local clone of the ``pywbem/pywbem`` Git repo.

1.  On GitHub, verify open items in milestone ``M.N.U``.

    Verify that milestone ``M.N.U`` has no open issues or PRs anymore. If there
    are open PRs or open issues, make a decision for each of those whether or
    not it should go into version ``M.N.U`` you are about to release.

    If there are open issues or PRs that should go into this version, abandon
    the release process.

    If none of the open issues or PRs should go into this version, change their
    milestones to a future version, and proceed with the release process. You
    may need to create the milestone for the future version.

2.  Run the Safety tool:

    .. code-block:: sh

        make safety

    If any of the two safety runs fails, fix the safety issues that are reported,
    in a separate branch/PR.

    Roll back the PR into any maintained stable branches.

3.  Check for any
    `dependabot alerts <https://github.com/pywbem/pywbem/security/dependabot>`_.

    If there are any dependabot alerts, fix them in a separate branch/PR.

    Roll back the PR into any maintained stable branches.

4.  Create and push the release branch (replace M,N,U accordingly):

    .. code-block:: sh

        VERSION=M.N.U make release_branch

    This uses the default branch determined from ``VERSION``: For ``M.N.0``,
    the ``master`` branch is used, otherwise the ``stable_M.N`` branch is used.
    That covers for all cases except if you want to release a new minor version
    based on an earlier stable branch. In that case, you need to specify that
    branch:

    .. code-block:: sh

        VERSION=M.N.0 BRANCH=stable_M.N make release_branch

    This includes the following steps:

    * create the release branch (``release_M.N.U``), if it does not yet exist
    * make sure the AUTHORS.md file is up to date
    * update the change log from the change fragment files, and delete those
    * commit the changes to the release branch
    * push the release branch

    If this command fails, the fix can be committed to the release branch
    and the command above can be retried.

5.  On GitHub, create a Pull Request for branch ``release_M.N.U``.

    Important: When creating Pull Requests, GitHub by default targets the
    ``master`` branch. When releasing based on a stable branch, you need to
    change the target branch of the Pull Request to ``stable_M.N``.

    Set the milestone of that PR to version ``M.N.U``.

    This PR should normally be set to be reviewed by at least one of the
    maintainers.

    The PR creation will cause the "test" workflow to run. That workflow runs
    tests for all defined environments, since it discovers by the branch name
    that this is a PR for a release.

6.  On GitHub, once the checks for that Pull Request have succeeded, merge the
    Pull Request (no review is needed). This automatically deletes the branch
    on GitHub.

    If the PR did not succeed, fix the issues.

7.  On GitHub, close milestone ``M.N.U``.

    Verify that the milestone has no open items anymore. If it does have open
    items, investigate why and fix (probably step 1 was not performed).

8.  Publish the package (replace M,N,U accordingly):

    .. code-block:: sh

        VERSION=M.N.U make release_publish

    or (see step 4):

    .. code-block:: sh

        VERSION=M.N.0 BRANCH=stable_M.N make release_publish

    This includes the following steps:

    * create and push the release tag
    * clean up the release branch

    Pushing the release tag will cause the "publish" workflow to run. That workflow
    builds the package, publishes it on PyPI, creates a release for it on
    GitHub, and finally creates a new stable branch on GitHub if the master
    branch was released.

11. Verify the publishing

    Wait for the "publish" workflow for the new release to have completed:
    https://github.com/pywbem/pywbem/actions/workflows/publish.yml

    Then, perform the following verifications:

    * Verify that the new version is available on PyPI at
      https://pypi.python.org/pypi/pywbem/

    * Verify that the new version has a release on Github at
      https://github.com/pywbem/pywbem/releases

    * Verify that the new version has documentation on ReadTheDocs at
      https://pywbem.readthedocs.io/en/stable/changes.html

      The new version M.N.U should be automatically active on ReadTheDocs,
      causing the documentation for the new version to be automatically built
      and published.

      If you cannot see the new version after some minutes, log in to
      https://readthedocs.org/projects/pywbem/versions/ and activate
      the new version.


.. _`Starting a new version`:

Starting a new version
----------------------

This section shows the steps for starting development of a new version.

This section covers all variants of new versions:

* Starting a new major version (Mnew.0.0) based on the master branch
* Starting a new minor version (M.Nnew.0) based on the master branch
* Starting a new update version (M.N.Unew) based on the stable branch of its
  minor version

This description assumes that you are authorized to push to the remote repo
at https://github.com/pywbem/pywbem and that the remote repo
has the remote name ``origin`` in your local clone.

Any commands in the following steps are executed in the main directory of your
local clone of the ``pywbem/pywbem`` Git repo.

1.  Create and push the start branch (replace M,N,U accordingly):

    .. code-block:: sh

        VERSION=M.N.U make start_branch

    This uses the default branch determined from ``VERSION``: For ``M.N.0``,
    the ``master`` branch is used, otherwise the ``stable_M.N`` branch is used.
    That covers for all cases except if you want to start a new minor version
    based on an earlier stable branch. In that case, you need to specify that
    branch:

    .. code-block:: sh

        VERSION=M.N.0 BRANCH=stable_M.N make start_branch

    This includes the following steps:

    * create the start branch (``start_M.N.U``), if it does not yet exist
    * create a dummy change
    * commit and push the start branch (``start_M.N.U``)

2.  On GitHub, create a milestone for the new version ``M.N.U``.

    You can create a milestone in GitHub via Issues -> Milestones -> New
    Milestone.

3.  On GitHub, create a Pull Request for branch ``start_M.N.U``.

    Important: When creating Pull Requests, GitHub by default targets the
    ``master`` branch. When starting a version based on a stable branch, you
    need to change the target branch of the Pull Request to ``stable_M.N``.

    No review is needed for this PR.

    Set the milestone of that PR to the new version ``M.N.U``.

4.  On GitHub, go through all open issues and pull requests that still have
    milestones for previous releases set, and either set them to the new
    milestone, or to have no milestone.

    Note that when the release process has been performed as described, there
    should not be any such issues or pull requests anymore. So this step here
    is just an additional safeguard.

5.  On GitHub, once the checks for the Pull Request for branch ``start_M.N.U``
    have succeeded, merge the Pull Request (no review is needed). This
    automatically deletes the branch on GitHub.

6.  Update and clean up the local repo (replace M,N,U accordingly):

    .. code-block:: sh

        VERSION=M.N.U make start_tag

    or (see step 1):

    .. code-block:: sh

        VERSION=M.N.0 BRANCH=stable_M.N make start_tag

    This includes the following steps:

    * checkout and pull the branch that was started (``master`` or ``stable_M.N``)
    * delete the start branch (``start_M.N.U``) locally and remotely
    * create and push the start tag (``M.N.Ua0``)


.. _`Contributing`:

Contributing
------------

Third party contributions to this project are welcome!

In order to contribute, create a `Git pull request`_, considering this:

.. _Git pull request: https://help.github.com/articles/using-pull-requests/

* Test is required.
* Each commit should only contain one "logical" change.
* A "logical" change should be put into one commit, and not split over multiple
  commits.
* Large new features should be split into stages.
* The commit message should not only summarize what you have done, but explain
  why the change is useful.
* The commit message must follow the format explained below.

What comprises a "logical" change is subject to sound judgement. Sometimes, it
makes sense to produce a set of commits for a feature (even if not large).
For example, a first commit may introduce a (presumably) compatible API change
without exploitation of that feature. With only this commit applied, it should
be demonstrable that everything is still working as before. The next commit may
be the exploitation of the feature in other components.

For further discussion of good and bad practices regarding commits, see:

* `OpenStack Git Commit Good Practice`_
* `How to Get Your Change Into the Linux Kernel`_

.. _OpenStack Git Commit Good Practice: https://wiki.openstack.org/wiki/GitCommitMessages
.. _How to Get Your Change Into the Linux Kernel: https://www.kernel.org/doc/Documentation/SubmittingPatches


.. _`Creating and submitting a change to pywbem`:

Creating and submitting a change to pywbem
------------------------------------------

All changes to pywbem are made through Github with PRs created on topic
branches and merged with the current master after successful group review.

To make a change, create a topic branch. You can assume that you are the only
one using that branch, so force-pushes to that branch and rebasing that branch
is fine.

When you are ready to push your change, describe the change for users of the
package in a change fragment file. That is a small file in RST format with just
a single change. For more background, read the
[towncrier concept](https://towncrier.readthedocs.io/en/stable/markdown.html)
(which uses Markdown format in that description and calls these files
'news fragment files').

To create a change fragment file, execute:

For changes that have a corresponding issue:

.. code-block:: sh

    towncrier create <issue>.<type>.rst --edit

For changes that have no corresponding issue:

.. code-block:: sh

    towncrier create noissue.<number>.<type>.rst --edit

For changes where you do not want to create a change log entry:

.. code-block:: sh

    towncrier create noissue.<number>.notshown.rst --edit
    # The file content will be ignored - it can also be empty

where:

* ``<issue>`` - The issue number of the issue that is addressed by the change.
  If the change addresses more than one issue, copy the new change fragment file
  after its content has been edited, using the other issue number in the file
  name. It is important that the file content is exactly the same, so that
  towncrier can create a single change log entry from the two (or more) files.

  If the change has no related issue, use the ``noissue.<number>.<type>.rst``
  file name format, where ``<number>`` is any number that results in a file name
  that does not yet exist in the ``changes`` directory.

* ``<type>`` - The type of the change, using one of the following values:

  - ``incompatible`` - An incompatible change. This will show up in the
    "Incompatible Changes" section of the change log. The text should include
    a description of the incompatibility from a user perspective and if
    possible, how to mitigate the change or what replacement functionality
    can be used instead.

  - ``deprecation`` - An externally visible functionality is being deprecated
    in this release.
    This will show up in the "Deprecations" section of the change log.
    The deprecated functionality still works in this release, but may go away
    in a future release. If there is a replacement functionality, the text
    should mention it.

  - ``fix`` - A bug fix in the code, documentation or development environment.
    This will show up in the "Bug fixes" section of the change log.

  - ``feature`` - A feature or enhancement in the code, documentation or
    development environment.
    This will show up in the "Enhancements" section of the change log.

  - ``cleanup`` - A cleanup in the code, documentation or development
    environment, that does not fix a bug and is not an enhanced functionality.
    This will show up in the "Cleanup" section of the change log.

  - ``notshown`` - The change will not be shown in the change log.

This command will create a new change fragment file in the ``changes``
directory and will bring up your editor (usually vim).

If your change does multiple things of different types listed above, create
a separate change fragment file for each type.

If you need to modify an existing change log entry as part of your change,
edit the existing corresponding change fragment file.

Add the new or changed change fragment file(s) to your commit. The test
workflow running on your Pull Request will check whether your change adds or
modifies change fragment files.

You can review how your changes will show up in the final change log for
the upcoming release by running:

.. code-block:: sh

    towncrier build --draft

Always make sure that your pushed branch has either just one commit, or if you
do multiple things, one commit for each logical change. What is not OK is to
submit for review a PR with the multiple commits it took you to get to the final
result for the change.


.. _`Core Development Team`:

Core Development Team
---------------------

Anyone can contribute to pywbem via pull requests as described in the previous
section.

The pywbem project has a core development team that holds regular web conferences
and that is using Slack for offline communication, on the Slack workspace:
https://pywbem.slack.com.

The web conference and the Slack workspace are by invitation, and if you want
to participate in the core team, please
`open an issue <https://github.com/pywbem/pywbem/issues>`_ to let us know.
