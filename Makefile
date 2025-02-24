# ------------------------------------------------------------------------------
# Makefile for pybem repository of pywbem project
#
# Supported OS platforms for this Makefile:
#     Linux (any distro)
#     OS-X
#     Windows with UNIX-like env such as CygWin (with a UNIX-like shell and
#       Python in the UNIX-like env)
#     native Windows (with the native Windows command processor and Python in
#       Windows)
#
# Prerequisites for running this Makefile:
#   These commands are used on all supported OS platforms. On native Windows,
#   they may be provided by UNIX-like environments such as CygWin:
#     make (GNU make)
#     python (This Makefile uses the active Python environment, virtual Python
#       environments are supported)
#     pip (in the active Python environment)
#     twine (in the active Python environment)
#   These additional commands are used on Linux, OS-X and on Windows with
#   UNIX-like environments:
#     uname
#     rm, find, xargs, cp
#     The commands listed in pywbem_os_setup.sh
#   These additional commands are used on native Windows:
#     del, copy, rmdir
#     The commands listed in pywbem_os_setup.bat
# ------------------------------------------------------------------------------

# No built-in rules needed:
MAKEFLAGS += --no-builtin-rules
.SUFFIXES:

# Python / Pip commands
ifndef PYTHON_CMD
  PYTHON_CMD := python
endif
ifndef PIP_CMD
  PIP_CMD := pip
endif

# Package level
ifndef PACKAGE_LEVEL
  PACKAGE_LEVEL := latest
endif
ifeq ($(PACKAGE_LEVEL),minimum)
  pip_level_opts := -c minimum-constraints.txt
else
  ifeq ($(PACKAGE_LEVEL),latest)
    pip_level_opts := --upgrade --upgrade-strategy eager
  else
    $(error Error: Invalid value for PACKAGE_LEVEL variable: $(PACKAGE_LEVEL))
  endif
endif

# Run type (normal, scheduled, release)
ifndef RUN_TYPE
  RUN_TYPE := normal
endif

# Make variables are case sensitive and some native Windows environments have
# ComSpec set instead of COMSPEC.
ifndef COMSPEC
  ifdef ComSpec
    COMSPEC = $(ComSpec)
  endif
endif

# Determine OS platform make runs on.
#
# The PLATFORM variable is set to one of:
# * Windows_native: Windows native environment (the Windows command processor
#   is used as shell and its internal commands are used, such as "del").
# * Windows_UNIX: A UNIX-like envieonment on Windows (the UNIX shell and its
#   internal commands are used, such as "rm").
# * Linux: Some Linux distribution
# * Darwin: OS-X / macOS
#
# This in turn determines the type of shell that is used by make when invoking
# commands, and the set of internal shell commands that is assumed to be
# available (e.g. "del" for the Windows native command processor and "rm" for
# a UNIX-like shell). Note that GNU make always uses the value of the SHELL
# make variable to invoke the shell for its commands, but it does not always
# read that variable from the environment. In fact, the approach GNU make uses
# to set the SHELL make variable is very special, see
# https://www.gnu.org/software/make/manual/html_node/Choosing-the-Shell.html.
# On native Windows this seems to be implemented differently than described:
# SHELL is not set to COMSPEC, so we do that here. When COMSPEC includes a
# path, it specifies it using backslashes. GNU make internally changes any
# backslashes in SHELL to forward slashes, so $(SHELL) cannot be used on
# native Windows to invoke the shell. Using $(shell ...) works.
#
# Note: Native Windows and CygWin are hard to distinguish: The native Windows
# envvars are set in CygWin as well. COMSPEC (or ComSpec) is set on both
# platforms. Using "uname" will display CYGWIN_NT-.. on both platforms. If the
# CygWin make is used on native Windows, most of the CygWin behavior is visible
# in context of that make (e.g. a SHELL variable is set, PATH gets converted to
# UNIX syntax, execution of batch files requires execute permission, etc.).
ifeq ($(OS),Windows_NT)
  ifdef PWD
    PLATFORM := Windows_UNIX
  else
    PLATFORM := Windows_native
    ifdef COMSPEC
      # Some GNU make versions convert backslashes automatically (but not all?)
      SHELL := $(subst \,/,$(COMSPEC))
    else
      SHELL := cmd.exe
    endif
    .SHELLFLAGS := /c
  endif
else
  # Values: Linux, Darwin
  PLATFORM := $(shell uname -s)
endif

ifeq ($(PLATFORM),Windows_native)
  # Note: The substituted backslashes must be doubled.
  # Remove files (blank-separated list of wildcard path specs)
  RM_FUNC = del /f /q $(subst /,\\,$(1))
  # Remove files recursively (single wildcard path spec)
  RM_R_FUNC = del /f /q /s $(subst /,\\,$(1))
  # Remove directories (blank-separated list of wildcard path specs)
  RMDIR_FUNC = rmdir /q /s $(subst /,\\,$(1))
  # Remove directories recursively (single wildcard path spec)
  RMDIR_R_FUNC = rmdir /q /s $(subst /,\\,$(1))
  # Copy a file, preserving the modified date
  CP_FUNC = copy /y $(subst /,\\,$(1)) $(subst /,\\,$(2))
  ENV = set
  WHICH = where
  DEV_NULL = nul
else
  RM_FUNC = rm -f $(1)
  RM_R_FUNC = find . -type f -name '$(1)' -delete
  RMDIR_FUNC = rm -rf $(1)
  RMDIR_R_FUNC = find . -type d -name '$(1)' | xargs -n 1 rm -rf
  CP_FUNC = cp -r $(1) $(2)
  ENV = env | sort
  WHICH = which
  DEV_NULL = /dev/null
endif

# Name of this Python package
package_name := pywbem

mock_package_name := pywbem_mock

# Determine if coverage details report generated
# The variable can be passed in as either an environment variable or
# command line variable. When set, generates a set of reports of the
# pywbem/*.py files showing line by line coverage.
ifdef COVERAGE_REPORT
  coverage_report := --cov-report=annotate --cov-report=html
else
  coverage_report :=
endif

# Test root directory
test_dir := tests

# Directory for coverage html output. Must be in sync with the one in .coveragerc.
coverage_html_dir := coverage_html

# Package version (full version, including any pre-release suffixes, e.g. "0.1.0.dev1").
# Note: The package version is defined in pywbem/_version.py.
# Note: Errors in getting the version (e.g. if wheel package is not installed) are
# detected in _check_version. We avoid confusion by suppressing such errors here.
package_version := $(shell $(PYTHON_CMD) setup.py --version 2>$(DEV_NULL))

# Python versions
python_version := $(shell $(PYTHON_CMD) tools/python_version.py 3)
python_mn_version := $(shell $(PYTHON_CMD) tools/python_version.py 2)
python_m_version := $(shell $(PYTHON_CMD) tools/python_version.py 1)
pymn := py$(python_mn_version)

# Tags for file name of cythonized wheel archive
cython_pytag := $(shell $(PYTHON_CMD) -c "import sys; print('cp{}{}'.format(*sys.version_info[0:2]))")
cython_abitag := $(shell $(PYTHON_CMD) -c "import sys; print('cp{}{}{}'.format(sys.version_info[0],sys.version_info[1],getattr(sys, 'abiflags','mu')))")
# The setup.py based approach for building the cythonized archive uses this formula, see wheel package code
cython_platform := $(shell $(PYTHON_CMD) -c "from wheel.bdist_wheel import get_platform; print(get_platform('.').lower().replace('-', '_').replace('.', '_'))")

# OpenSSL version used by Python's ssl
openssl_version := $(shell $(PYTHON_CMD) -c "import ssl; print(ssl.OPENSSL_VERSION)")

# Directory for vendored packages
vendor_dir := $(package_name)/_vendor

# Directory for the generated distribution files
dist_dir := dist

# Distribution archives
# These variables are set with "=" for the same reason as package_version.
bdist_file = $(dist_dir)/$(package_name)-$(package_version)-py2.py3-none-any.whl
bdistc_file = $(dist_dir)/$(package_name)-$(package_version)-$(cython_pytag)-$(cython_abitag)-$(cython_platform).whl
sdist_file = $(dist_dir)/$(package_name)-$(package_version).tar.gz

# Only the normal wheel and source distribution archives
dist_files = $(bdist_file) $(sdist_file)

# Cython compiler flags (for clang compiler)
cython_cflags = -g0 -Wno-deprecated-declarations

# Source files in the packages
package_py_files := \
    $(wildcard $(package_name)/*.py) \
    $(wildcard $(package_name)/*/*.py) \

# Lex/Yacc table files, generated from and by mof_compiler.py
moftab_files := $(package_name)/_mofparsetab.py $(package_name)/_moflextab.py

# Dependents for Lex/Yacc table files
moftab_dependent_files := \
    $(package_name)/_mof_compiler.py \

# Directory for generated API documentation
doc_build_dir := build_doc

# Directory where Sphinx conf.py is located
doc_conf_dir := docs

# Paper format for the Sphinx LaTex/PDF builder.
# Valid values: a4, letter
doc_paper_format := a4

# Documentation generator command
doc_cmd := sphinx-build
# Options as seen from docs directory:
doc_opts := -v -n -d ../$(doc_build_dir)/doctrees -c ../$(doc_conf_dir) -D latex_elements.papersize=$(doc_paper_format) .

# File names of automatically generated utility help message text output
doc_utility_help_files := \
    $(doc_conf_dir)/mof_compiler.help.txt \

# Dependents for Sphinx documentation build
doc_dependent_files := \
    $(doc_conf_dir)/conf.py \
    $(wildcard $(doc_conf_dir)/*.rst) \
    $(wildcard $(doc_conf_dir)/client/*.rst) \
    $(wildcard $(doc_conf_dir)/notebooks/*.ipynb) \
		$(wildcard $(package_name)/*.py) \
		$(wildcard $(mock_package_name)/*.py) \

# PyLint config file
pylint_rc_file := pylintrc

# PyLint additional options
pylint_todo_opts := --disable=fixme
pylint_no_todo_opts := --enable=fixme

# Safety policy files
safety_install_policy_file := .safety-policy-install.yml
safety_all_policy_file := .safety-policy-all.yml

# Flake8 config file
flake8_rc_file := .flake8

# Python source files to be checked by PyLint and Flake8
py_src_files := \
    setup.py \
    $(filter-out $(moftab_files), $(wildcard $(package_name)/*.py)) \
    $(wildcard $(mock_package_name)/*.py) \
		mof_compiler \

py_test_files := \
    $(wildcard $(test_dir)/*.py) \
    $(wildcard $(test_dir)/*/*.py) \
    $(wildcard $(test_dir)/*/*/*.py) \
    $(wildcard $(test_dir)/*/*/*/*.py) \

# Python source files for test (unit test and function test)
test_src_files := \
    $(wildcard $(test_dir)/unittest/*.py) \
    $(wildcard $(test_dir)/unittest/*/*.py) \
    $(wildcard $(test_dir)/functiontest/*.py) \

test_yaml_files := \
    $(wildcard $(test_dir)/unittest/*.y*ml) \
    $(wildcard $(test_dir)/unittest/*/*.y*ml) \
    $(wildcard $(test_dir)/functiontest/*.y*ml) \

ifdef TESTCASES
  pytest_opts := $(TESTOPTS) -k $(TESTCASES)
else
  pytest_opts := $(TESTOPTS)
endif
pytest_end2end_opts := -v --tb=short $(pytest_opts) --es-file $(test_dir)/end2endtest/es_server.yml --es-schema-file $(test_dir)/end2endtest/es_schema.yml

pytest_cov_opts := --cov $(package_name) --cov $(mock_package_name) $(coverage_report) --cov-config .coveragerc

ifeq ($(python_m_version),3)
  pytest_warning_opts := -W default
  pytest_end2end_warning_opts := $(pytest_warning_opts)
else
  pytest_warning_opts := -W default
  pytest_end2end_warning_opts := $(pytest_warning_opts)
endif

# Versions of the vendorized packages:
nocasedict_version := 1.1.2
nocaselist_version := 1.1.1

# Dist info directories of the vendorized packages:
nocasedict_dist_dir := nocasedict-$(nocasedict_version).dist-info
nocaselist_dist_dir := nocaselist-$(nocaselist_version).dist-info

# Files to be put into distribution archive.
# Keep in sync with dist_dependent_files.
# This is used for 'include' statements in MANIFEST.in. The wildcards are used
# as specified, without being expanded.
dist_manifest_in_files := \
    LICENSE.txt \
    README.md \
    README_PYPI.md \
    INSTALL.md \
    requirements.txt \
    test-requirements.txt \
    setup.py \
    build_moftab.py \
    mof_compiler \
    mof_compiler.bat \
    $(package_name)/*.py \
    $(mock_package_name)/*.py \
    $(vendor_dir)/__init__.py \
    $(vendor_dir)/nocasedict/*.py \
    $(vendor_dir)/nocaselist/*.py \
    $(vendor_dir)/nocasedict/LICENSE \
    $(vendor_dir)/nocaselist/LICENSE \

# Files that are dependents of the distribution archive.
# Keep in sync with dist_manifest_in_files.
dist_dependent_files := \
    LICENSE.txt \
    README.md \
    README_PYPI.md \
    INSTALL.md \
    requirements.txt \
    test-requirements.txt \
    setup.py \
    build_moftab.py \
    mof_compiler \
    mof_compiler.bat \
    $(wildcard $(package_name)/*.py) \
    $(wildcard $(mock_package_name)/*.py) \
    $(wildcard $(vendor_dir)/__init__.py) \
    $(wildcard $(vendor_dir)/nocasedict/*.py) \
    $(wildcard $(vendor_dir)/nocaselist/*.py) \
    $(vendor_dir)/nocasedict/LICENSE \
    $(vendor_dir)/nocaselist/LICENSE \

# Packages whose dependencies are checked using pip-missing-reqs
ifeq ($(python_m_version),2)
  check_reqs_packages := pytest coverage coveralls flake8 pylint twine jupyter notebook
else
ifeq ($(python_mn_version),3.6)
  check_reqs_packages := pytest coverage coveralls flake8 pylint twine jupyter notebook
else
ifeq ($(python_mn_version),3.7)
  check_reqs_packages := pytest coverage coveralls flake8 pylint safety twine jupyter notebook
else
  check_reqs_packages := pytest coverage coveralls flake8 pylint safety sphinx twine jupyter notebook
endif
endif
endif

PIP_INSTALL_CMD := $(PYTHON_CMD) -m pip install

# Directory for .done files
done_dir := done

.PHONY: help
help:
	@echo "Makefile for $(package_name) package"
	@echo "$(package_name) package version: $(package_version)"
	@echo ""
	@echo "Make targets:"
	@echo "  install    - Install pywbem and its Python installation and runtime prereqs"
	@echo "  develop    - Install Python development prereqs (includes develop_os once after clobber)"
	@echo "  vendor     - Install or update the vendorized packages"
	@echo "  check_reqs - Perform missing dependency checks"
	@echo "  build      - Build the source and wheel distribution archives in: $(dist_dir)"
	@echo "  builddoc   - Build documentation in: $(doc_build_dir)"
	@echo "  check      - Run Flake8 on sources"
	@echo "  ruff       - Run Ruff (an alternate lint tool) on sources"
	@echo "  pylint     - Run PyLint on sources"
	@echo "  installtest - Run install tests"
	@echo "  safety     - Run Safety for install and all"
	@echo "  test       - Run unit and function tests (in tests/unittest and tests/functiontest)"
	@echo "  leaktest   - Run memory leak tests (in tests/leaktest)"
	@echo "  resourcetest - Run resource consumption tests (in tests/resourcetest)"
	@echo "  perftest   - Run performance tests (in tests/perftest)"
	@echo "  all        - Do all of the above"
	@echo "  buildc     - Build the cythonized wheel distribution archive in: $(dist_dir)"
	@echo "  installc   - Install the cythonized wheel distribution archive"
	@echo "  testc      - Run unit and function tests against cythonized wheel distribution archive"
	@echo "  todo       - Check for TODOs in Python and docs sources"
	@echo "  end2endtest - Run end2end tests (in $(test_dir)/end2endtest)"
	@echo "  develop_os - Install OS-level development prereqs"
	@echo "  upload     - build + upload the distribution archive files to PyPI"
	@echo "  clean      - Remove any temporary files"
	@echo "  clobber    - Remove everything created to ensure clean start - use after setting git tag"
	@echo "  pip_list   - Display the Python packages as seen by make"
	@echo "  platform   - Display the information about the platform as seen by make"
	@echo "  env        - Display the environment as seen by make"
	@echo ""
	@echo "Environment variables:"
	@echo "  COVERAGE_REPORT - When non-empty, the 'test' target creates a coverage report as"
	@echo "      annotated html files showing lines covered and missed, in the directory:"
	@echo "      $(coverage_html_dir)"
	@echo "      Optional, defaults to no such coverage report."
	@echo "  DOCKER_CACHE_DIR - Path name of Docker cache directory used for end2end tests"
	@echo "      Optional, for default see end2end tests."
	@echo "  TESTCASES - When non-empty, 'test' target runs only the specified test cases. The"
	@echo "      value is used for the -k option of pytest (see 'pytest --help')."
	@echo "      Optional, defaults to running all tests."
	@echo "  TESTOPTS - Optional: Additional options for py.tests (see 'pytest --help')."
	@echo "  TEST_SCHEMA_DOWNLOAD - When non-empty, enables test cases in test_wbemconnection_mock"
	@echo "      to test downloading of DMTF schema from the DMTF web site."
	@echo "      Optional, defaults to disabling these test cases."
	@echo "  TEST_INSTALLED - When non-empty, run any tests using the installed version of pywbem"
	@echo "      and assume all Python and OS-level prerequisites are already installed."
	@echo "      When set to 'DEBUG', print location from where pywbem and pywbem_mock are loaded."
	@echo "  PACKAGE_LEVEL - Package level to be used for installing dependent Python"
	@echo "      packages in 'install' and 'develop' targets:"
	@echo "        latest - Latest package versions available on Pypi"
	@echo "        minimum - A minimum version as defined in minimum-constraints.txt"
	@echo "      Optional, defaults to 'latest'."
	@echo "  PYTHON_CMD - Python command to be used. Useful for Python 3 in some envs."
	@echo "      Optional, defaults to 'python'."
	@echo "  PIP_CMD - Pip command to be used. Useful for Python 3 in some envs."
	@echo "      Optional, defaults to 'pip'."
	@echo "  YAGOT - Optional: When non-empty, 'test' target checks for garbage (=collected and "
	@echo "      uncollectable) objects caused by the pytest test cases."
	@echo "  YAGOT_LEAKS_ONLY - Optional: When non-empty, garbage checks are limited to "
	@echo "      uncollectable (=leak) objects only."
	@echo "  YAGOT_IGNORE_TYPES - Optional: Ignore the specified comma-separated list of types in"
	@echo "      garbage checks."

.PHONY: platform
platform:
	@echo "Makefile: Platform related information as seen by make:"
	@echo "Platform: $(PLATFORM)"
	@echo "Shell used for commands: $(SHELL)"
	@echo "Shell flags: $(.SHELLFLAGS)"
	@echo "Current locale settings: LANG=$(LANG), LC_ALL=$(LC_ALL), LC_CTYPE=$(LC_CTYPE)"
	@echo "Make command location: $(MAKE)"
	@echo "Make version: $(MAKE_VERSION)"
	@echo "Python command name: $(PYTHON_CMD)"
	@echo "Python command location: $(shell $(WHICH) $(PYTHON_CMD))"
	@echo "Python version: $(python_version)"
	@$(PYTHON_CMD) tools/python_bitsize.py
	@$(PYTHON_CMD) tools/python_unicodesize.py
	@echo "OpenSSL version used by Python ssl: $(openssl_version)"
	@echo "Pip command name: $(PIP_CMD)"
	@echo "Pip command location: $(shell $(WHICH) $(PIP_CMD))"
	@echo "Pip command version: $(shell $(PIP_CMD) --version)"
	@echo "$(package_name) package version: $(package_version)"

.PHONY: pip_list
pip_list:
	@echo "Makefile: Python packages as seen by make:"
	$(PIP_CMD) list

.PHONY: env
env:
	@echo "Makefile: Environment as seen by make:"
	$(ENV)

.PHONY: _check_version
_check_version:
ifeq (,$(package_version))
	$(error Package version could not be determined)
endif

$(done_dir)/pip_upgrade_$(pymn)_$(PACKAGE_LEVEL).done: Makefile
	-$(call RM_FUNC,$@)
ifeq ($(PLATFORM),Windows_native)
	@echo "Makefile: On Windows, there is no automatic upgrade of Pip to a minimum version of 9.x. Current Pip version:"
	$(PIP_CMD) --version
else
	bash -c 'pv=$$($(PIP_CMD) --version); if [[ $$pv =~ (^pip [1-8]\..*) ]]; then $(PIP_INSTALL_CMD) pip==9.0.1; fi'
endif
	$(PIP_INSTALL_CMD) $(pip_level_opts) pip
	echo "done" >$@

$(done_dir)/install_basic_$(pymn)_$(PACKAGE_LEVEL).done: Makefile $(done_dir)/pip_upgrade_$(pymn)_$(PACKAGE_LEVEL).done
	@echo "Makefile: Installing/upgrading basic Python packages with PACKAGE_LEVEL=$(PACKAGE_LEVEL)"
	-$(call RM_FUNC,$@)
	$(PIP_INSTALL_CMD) $(pip_level_opts) setuptools wheel
	echo "done" >$@
	@echo "Makefile: Done installing/upgrading basic Python packages"

$(done_dir)/install_pywbem_$(pymn)_$(PACKAGE_LEVEL).done: Makefile $(done_dir)/pip_upgrade_$(pymn)_$(PACKAGE_LEVEL).done requirements.txt setup.py
	-$(call RM_FUNC,$@)
ifdef TEST_INSTALLED
	@echo "Makefile: Skipping installation of pywbem and its Python runtime prerequisites because TEST_INSTALLED is set"
	@echo "Makefile: Checking whether pywbem is actually installed:"
	$(PIP_CMD) show $(package_name)
else
	@echo "Makefile: Installing pywbem (as editable) and its Python installation prerequisites (with PACKAGE_LEVEL=$(PACKAGE_LEVEL))"
	-$(call RMDIR_FUNC,build $(package_name).egg-info .eggs)
	$(PIP_INSTALL_CMD) $(pip_level_opts) -r requirements.txt
	$(PIP_INSTALL_CMD) $(pip_level_opts) -e .
	@echo "Makefile: Done installing pywbem and its Python runtime prerequisites"
endif
	echo "done" >$@

$(done_dir)/installc_pywbem_$(pymn)_$(PACKAGE_LEVEL).done: Makefile $(done_dir)/pip_upgrade_$(pymn)_$(PACKAGE_LEVEL).done $(bdistc_file)
	-$(call RM_FUNC,$@)
ifdef TEST_INSTALLED
	@echo "Makefile: Skipping installation of pywbem and its Python runtime prerequisites because TEST_INSTALLED is set"
	@echo "Makefile: Checking whether pywbem is actually installed:"
	$(PIP_CMD) show $(package_name)
else
	@echo "Makefile: Installing cythonized wheel archive"
	$(PIP_CMD) uninstall -y $(package_name)
	$(PIP_INSTALL_CMD) $(bdistc_file)
	@echo "Makefile: Done installing cythonized wheel archive"
endif
	echo "done" >$@

.PHONY: install
install: $(done_dir)/install_$(pymn)_$(PACKAGE_LEVEL).done
	@echo "Makefile: Target $@ done."

$(done_dir)/install_$(pymn)_$(PACKAGE_LEVEL).done: Makefile $(done_dir)/install_basic_$(pymn)_$(PACKAGE_LEVEL).done $(done_dir)/install_pywbem_$(pymn)_$(PACKAGE_LEVEL).done
	-$(call RM_FUNC,$@)
	$(PYTHON_CMD) -c "import $(package_name)"
	$(PYTHON_CMD) -c "import $(mock_package_name)"
	echo "done" >$@

.PHONY: installc
installc: $(done_dir)/installc_$(pymn)_$(PACKAGE_LEVEL).done
	@echo "Makefile: Target $@ done."

$(done_dir)/installc_$(pymn)_$(PACKAGE_LEVEL).done: Makefile $(done_dir)/install_basic_$(pymn)_$(PACKAGE_LEVEL).done $(done_dir)/installc_pywbem_$(pymn)_$(PACKAGE_LEVEL).done
	-$(call RM_FUNC,$@)
ifeq ($(PLATFORM),Windows_native)
	cmd /c "set TEST_INSTALLED=1 & $(PYTHON_CMD) -c "from tests.utils import import_installed; pkg=import_installed('$(package_name)'); print('$(package_name).__file__={}'.format(pkg.__file__))""
else
	TEST_INSTALLED=1 $(PYTHON_CMD) -c "from tests.utils import import_installed; pkg=import_installed('$(package_name)'); print('$(package_name).__file__={}'.format(pkg.__file__))"
endif
	echo "done" >$@

.PHONY: develop_os
develop_os: $(done_dir)/develop_os_$(pymn)_$(PACKAGE_LEVEL).done
	@echo "Makefile: Target $@ done."

$(done_dir)/develop_os_$(pymn)_$(PACKAGE_LEVEL).done: Makefile $(done_dir)/pip_upgrade_$(pymn)_$(PACKAGE_LEVEL).done pywbem_os_setup.sh pywbem_os_setup.bat
	@echo "Makefile: Installing OS-level development requirements"
	-$(call RM_FUNC,$@)
ifeq ($(PLATFORM),Windows_native)
	pywbem_os_setup.bat develop
else
	./pywbem_os_setup.sh develop
endif
	echo "done" >$@
	@echo "Makefile: Done installing OS-level development requirements"

.PHONY: develop
develop: $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done
	@echo "Makefile: Target $@ done."

$(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done: $(done_dir)/pip_upgrade_$(pymn)_$(PACKAGE_LEVEL).done $(done_dir)/install_$(pymn)_$(PACKAGE_LEVEL).done $(done_dir)/develop_os_$(pymn)_$(PACKAGE_LEVEL).done $(done_dir)/install_basic_$(pymn)_$(PACKAGE_LEVEL).done dev-requirements.txt test-requirements.txt
	@echo "Makefile: Installing Python development requirements (with PACKAGE_LEVEL=$(PACKAGE_LEVEL))"
	-$(call RM_FUNC,$@)
	$(PIP_INSTALL_CMD) $(pip_level_opts) -r dev-requirements.txt
	echo "done" >$@
	@echo "Makefile: Done installing Python development requirements"

.PHONY: vendor
vendor: $(done_dir)/vendor_$(pymn)_$(PACKAGE_LEVEL).done
	@echo "Makefile: Target $@ done."

$(done_dir)/vendor_$(pymn)_$(PACKAGE_LEVEL).done: vendorize.toml Makefile
	@echo "Makefile: Vendoring nocasedict and nocaselist"
	bash -c "cd $(vendor_dir); rm -rf *"
	python-vendorize
	bash -c "cd $(vendor_dir); cp $(nocasedict_dist_dir)/LICENSE nocasedict/; rm -rf $(nocasedict_dist_dir)"
	bash -c "cd $(vendor_dir); cp $(nocaselist_dist_dir)/LICENSE nocaselist/; rm -rf $(nocaselist_dist_dir)"
	@echo "Makefile: Done vendoring nocasedict and nocaselist"
	echo "done" >$@

vendorize.toml: Makefile
	@echo "Makefile: Creating the vendorize file: $@"
	echo "# file GENERATED by Makefile, do NOT edit" >$@
	echo "target = '$(package_name)/_vendor'" >>$@
	echo "packages = [" >>$@
	echo "    'nocasedict==$(nocasedict_version)'," >>$@
	echo "    'nocaselist==$(nocaselist_version)'," >>$@
	echo "]" >>$@
	@echo "Makefile: Done creating the vendorize file: $@"

.PHONY: build
build: _check_version $(bdist_file) $(sdist_file)
	@echo "Makefile: Target $@ done."

.PHONY: buildc
buildc: _check_version $(bdistc_file)
	@echo "makefile: Target $@ done."

.PHONY: builddoc
builddoc: html
	@echo "Makefile: Target $@ done."

.PHONY: check
check: $(done_dir)/flake8_$(pymn)_$(PACKAGE_LEVEL).done
	@echo "Makefile: Target $@ done."

.PHONY: ruff
ruff: $(done_dir)/ruff_$(pymn)_$(PACKAGE_LEVEL).done
	@echo "Makefile: Target $@ done."

.PHONY: pylint
pylint: $(done_dir)/pylint_$(pymn)_$(PACKAGE_LEVEL).done
	@echo "Makefile: Target $@ done."

.PHONY: safety
safety: $(done_dir)/safety_all_$(pymn)_$(PACKAGE_LEVEL).done $(done_dir)/safety_install_$(pymn)_$(PACKAGE_LEVEL).done
	@echo "Makefile: Target $@ done."

.PHONY: todo
todo: $(done_dir)/todo_$(pymn)_$(PACKAGE_LEVEL).done
	@echo "Makefile: Target $@ done."

.PHONY: all
all: install develop check_reqs build builddoc check ruff pylint installtest test leaktest resourcetest perftest
	@echo "Makefile: Target $@ done."

.PHONY: clobber
clobber: clean
	@echo "Makefile: Removing everything for a fresh start"
	-$(call RM_FUNC,epydoc.log $(moftab_files) $(dist_files) $(dist_dir)/$(package_name)-$(package_version)*.egg pywbem/*cover pywbem_mock/*cover)
	-$(call RM_R_FUNC,*.done)
	-$(call RMDIR_FUNC,$(doc_build_dir) .tox $(coverage_html_dir) build_build_ext build_cythonize)
	@echo "Makefile: Done removing everything for a fresh start"
	@echo "Makefile: Target $@ done."

# Also remove any build products that are dependent on the Python version
.PHONY: clean
clean:
	@echo "Makefile: Removing temporary build products"
	-$(call RM_R_FUNC,*.pyc)
	-$(call RM_R_FUNC,*~)
	-$(call RM_R_FUNC,.*~)
	-$(call RMDIR_R_FUNC,__pycache__)
	-$(call RM_FUNC,MANIFEST parser.out .coverage $(package_name)/parser.out)
	-$(call RM_FUNC,$(package_name)/mofparsetab.py* $(package_name)/moflextab.py*)
	-$(call RMDIR_FUNC,build .cache $(package_name).egg-info .eggs)
	@echo "Makefile: Done removing temporary build products"
	@echo "Makefile: Target $@ done."

.PHONY: upload
upload: _check_version $(dist_files)
	@echo "Makefile: Checking files before uploading to PyPI"
	twine check $(dist_files)
	@echo "Makefile: Uploading to PyPI: pywbem $(package_version)"
	twine upload $(dist_files)
	@echo "Makefile: Done uploading to PyPI"
	@echo "Makefile: Target $@ done."

.PHONY: html
html: $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done $(doc_build_dir)/html/index.html
	@echo "Makefile: Target $@ done."

# Boolean variable indicating that Sphinx should be run
# We run Sphinx only on Python>=3.8 because lower Python versions require too old Sphinx versions
run_sphinx := $(shell $(PYTHON_CMD) -c "import sys; py=sys.version_info[0:2]; sys.stdout.write('true' if py>=(3,8) else 'false')")

$(doc_build_dir)/html/index.html: Makefile $(doc_utility_help_files) $(doc_dependent_files)
ifeq ($(run_sphinx),true)
	@echo "Makefile: Creating the documentation as HTML pages"
	-$(call RM_FUNC,$@)
	bash -c "pushd docs; $(doc_cmd) -b html $(doc_opts) ../$(doc_build_dir)/html"
	@echo "Makefile: Done creating the documentation as HTML pages; top level file: $@"
else
	@echo "Skipping Sphinx to create HTML pages on Python version $(python_version)"
endif

.PHONY: pdf
pdf: $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done Makefile $(doc_utility_help_files) $(doc_dependent_files)
ifeq ($(run_sphinx),true)
	@echo "Makefile: Creating the documentation as PDF file"
	-$(call RM_FUNC,$@)
	bash -c "pushd docs; $(doc_cmd) -b latex $(doc_opts) ../$(doc_build_dir)/pdf"
	@echo "Makefile: Running LaTeX files through pdflatex..."
	$(MAKE) -C $(doc_build_dir)/pdf all-pdf
	@echo "Makefile: Done creating the documentation as PDF file in: $(doc_build_dir)/pdf/"
else
	@echo "Skipping Sphinx to create PDF files on Python version $(python_version)"
endif
	@echo "Makefile: Target $@ done."

.PHONY: man
man: $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done Makefile $(doc_utility_help_files) $(doc_dependent_files)
ifeq ($(run_sphinx),true)
	@echo "Makefile: Creating the documentation as man pages"
	-$(call RM_FUNC,$@)
	bash -c "pushd docs; $(doc_cmd) -b man $(doc_opts) ../$(doc_build_dir)/man/man1"
	@echo "Makefile: Done creating the documentation as man pages in: $(doc_build_dir)/man/man1"
else
	@echo "Skipping Sphinx to create man files on Python version $(python_version)"
endif
	@echo "Makefile: Target $@ done."

.PHONY: docchanges
docchanges: $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done
ifeq ($(run_sphinx),true)
	@echo "Makefile: Creating the doc changes overview file"
	bash -c "pushd docs; $(doc_cmd) -b changes $(doc_opts) ../$(doc_build_dir)/changes"
	@echo
	@echo "Makefile: Done creating the doc changes overview file in: $(doc_build_dir)/changes/"
else
	@echo "Skipping Sphinx to create doc changes overview file on Python version $(python_version)"
endif
	@echo "Makefile: Target $@ done."

.PHONY: doclinkcheck
doclinkcheck: $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done
ifeq ($(run_sphinx),true)
	@echo "Makefile: Creating the doc link errors file"
	bash -c "pushd docs; $(doc_cmd) -b linkcheck $(doc_opts) ../$(doc_build_dir)/linkcheck"
	@echo
	@echo "Makefile: Done creating the doc link errors file: $(doc_build_dir)/linkcheck/output.txt"
else
	@echo "Skipping Sphinx to create doc link errors file on Python version $(python_version)"
endif
	@echo "Makefile: Target $@ done."

.PHONY: doccoverage
doccoverage: $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done
ifeq ($(run_sphinx),true)
	@echo "Makefile: Creating the doc coverage results file"
	bash -c "pushd docs; $(doc_cmd) -b coverage $(doc_opts) ../$(doc_build_dir)/coverage"
	@echo "Makefile: Done creating the doc coverage results file: $(doc_build_dir)/coverage/python.txt"
else
	@echo "Skipping Sphinx to create doc coverage results file on Python version $(python_version)"
endif
	@echo "Makefile: Target $@ done."

# Note: distutils depends on the right files specified in MANIFEST.in, even when
# they are already specified e.g. in 'package_data' in setup.py.
# We generate the MANIFEST.in file automatically, to have a single point of
# control (this Makefile) for what gets into the distribution archive.
MANIFEST.in: Makefile $(dist_manifest_in_files)
	@echo "Makefile: Creating the manifest input file"
	echo "# file GENERATED by Makefile, do NOT edit" >$@
ifeq ($(PLATFORM),Windows_native)
	for %%f in ($(dist_manifest_in_files)) do (echo include %%f >>$@)
	echo recursive-include $(test_dir) * >>$@
	echo recursive-exclude $(test_dir) *.pyc >>$@
else
	echo "$(dist_manifest_in_files)" |xargs -n 1 echo include >>$@
	echo "recursive-include $(test_dir) *" >>$@
	echo "recursive-exclude $(test_dir) *.pyc" >>$@
endif
	@echo "Makefile: Done creating the manifest input file: $@"

# Distribution archives.
# Note: Deleting MANIFEST causes distutils (setup.py) to read MANIFEST.in and to
# regenerate MANIFEST. Otherwise, changes in MANIFEST.in will not be used.
# Note: Deleting build is a safeguard against picking up partial build products
# which can lead to incorrect hashbangs in the pywbem scripts in wheel archives.
$(sdist_file): setup.py MANIFEST.in $(dist_dependent_files) $(moftab_files) $(done_dir)/vendor_$(pymn)_$(PACKAGE_LEVEL).done
	@echo "Makefile: Creating the source distribution archive: $(sdist_file)"
	-$(call RM_FUNC,MANIFEST)
	-$(call RMDIR_FUNC,build $(package_name).egg-info-INFO .eggs)
	$(PYTHON_CMD) -m build --sdist --outdir $(dist_dir) .
	@echo "Makefile: Done creating the source distribution archive: $(sdist_file)"

$(bdist_file): setup.py MANIFEST.in $(dist_dependent_files) $(moftab_files) $(done_dir)/vendor_$(pymn)_$(PACKAGE_LEVEL).done
	@echo "Makefile: Creating the normal wheel distribution archive: $(bdist_file)"
	-$(call RM_FUNC,MANIFEST)
	-$(call RMDIR_FUNC,build $(package_name).egg-info-INFO .eggs)
	$(PYTHON_CMD) -m build --wheel --outdir $(dist_dir) -C--universal .
	@echo "Makefile: Done creating the normal wheel distribution archive: $(bdist_file)"

$(bdistc_file): setup.py MANIFEST.in $(dist_dependent_files) $(moftab_files) $(done_dir)/vendor_$(pymn)_$(PACKAGE_LEVEL).done
	@echo "Makefile: Creating the cythonized wheel distribution archive: $(bdistc_file)"
	-$(call RM_FUNC,MANIFEST)
	-$(call RMDIR_FUNC,build $(package_name).egg-info-INFO .eggs)
ifeq ($(PLATFORM),Windows_native)
	cmd /c "set CFLAGS=$(cython_cflags) & $(PYTHON_CMD) setup.py bdist_wheel -d $(dist_dir) --universal --cythonized"
	cmd /c dir $(dist_dir)
else
	CFLAGS='$(cython_cflags)' $(PYTHON_CMD) setup.py bdist_wheel -d $(dist_dir) --universal --cythonized
	ls -l $(dist_dir)
endif
	@echo "Makefile: Done creating the cythonized wheel distribution archive: $(bdistc_file)"

# Note: The mof*tab files need to be removed in order to rebuild them (make rules vs. ply rules)
# Note: Because the current directory is by default in front of the Python module
# search path, the pywbem module will be imported from ./pywbem even
# when an installed version of pywbem is tested. This is correct, because the
# purpose of this rule is to build the mof*tab files in ./pywbem.
$(moftab_files): $(done_dir)/install_$(pymn)_$(PACKAGE_LEVEL).done $(moftab_dependent_files) build_moftab.py
	@echo "Makefile: Creating the LEX/YACC table modules"
	-$(call RM_FUNC,$(package_name)/_mofparsetab.py* $(package_name)/_moflextab.py*)
	$(PYTHON_CMD) -c "from pywbem import _mof_compiler; _mof_compiler._build(verbose=True)"
	@echo "Makefile: Done creating the LEX/YACC table modules: $(moftab_files)"

# PyLint status codes:
# * 0 if everything went fine
# * 1 if fatal messages issued
# * 2 if error messages issued
# * 4 if warning messages issued
# * 8 if refactor messages issued
# * 16 if convention messages issued
# * 32 on usage error
# Status 1 to 16 will be bit-ORed.
$(done_dir)/pylint_$(pymn)_$(PACKAGE_LEVEL).done: $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done Makefile $(pylint_rc_file) $(py_src_files) $(py_test_files)
ifeq ($(python_m_version),2)
	@echo "Makefile: Warning: Skipping Pylint on Python $(python_version)" >&2
else
	@echo "Makefile: Running Pylint"
	-$(call RM_FUNC,$@)
	pylint --version
	pylint $(pylint_no_todo_opts) --rcfile=$(pylint_rc_file) $(py_src_files)
	pylint $(pylint_todo_opts) --rcfile=$(pylint_rc_file) $(py_test_files)
	echo "done" >$@
	@echo "Makefile: Done running Pylint"
endif

$(done_dir)/flake8_$(pymn)_$(PACKAGE_LEVEL).done: $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done Makefile $(flake8_rc_file) $(py_src_files) $(py_test_files)
	@echo "Makefile: Running Flake8"
	-$(call RM_FUNC,$@)
	flake8 --version
	flake8 --statistics --config=$(flake8_rc_file) --filename='*' $(py_src_files) $(py_test_files)
	echo "done" >$@
	@echo "Makefile: Done running Flake8"

$(done_dir)/ruff_$(pymn)_$(PACKAGE_LEVEL).done: Makefile $(py_src_files) $(py_test_files)
ifeq ($(python_mn_version),2.7)
	@echo "Makefile: Warning: Skipping Ruff on Python $(python_version)" >&2
else
ifeq ($(python_mn_version),3.6)
	@echo "Makefile: Warning: Skipping Ruff on Python $(python_version)" >&2
else
	@echo "Makefile: Running Ruff"
	-$(call RM_FUNC,$@)
	ruff --version
	ruff check --unsafe-fixes $(py_src_files) $(py_test_files)
	echo "done" >$@
	@echo "Makefile: Done running Ruff"
endif
endif

$(done_dir)/safety_all_$(pymn)_$(PACKAGE_LEVEL).done: $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done Makefile $(safety_all_policy_file) minimum-constraints.txt minimum-constraints-install.txt
ifeq ($(python_m_version),2)
	@echo "Makefile: Warning: Skipping Safety for all packages on Python $(python_version)" >&2
else
ifeq ($(python_mn_version),3.6)
	@echo "Makefile: Warning: Skipping Safety for all packages on Python $(python_version)" >&2
else
	@echo "Makefile: Running Safety for all packages"
	-$(call RM_FUNC,$@)
	bash -c "safety check --policy-file $(safety_all_policy_file) -r minimum-constraints.txt --full-report || test '$(RUN_TYPE)' != 'release' || exit 1"
	echo "done" >$@
	@echo "Makefile: Done running Safety for all packages"
endif
endif

$(done_dir)/safety_install_$(pymn)_$(PACKAGE_LEVEL).done: $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done Makefile $(safety_install_policy_file) minimum-constraints-install.txt
ifeq ($(python_m_version),2)
	@echo "Makefile: Warning: Skipping Safety for install packages on Python $(python_version)" >&2
else
ifeq ($(python_mn_version),3.6)
	@echo "Makefile: Warning: Skipping Safety for install packages on Python $(python_version)" >&2
else
	@echo "Makefile: Running Safety for install packages"
	-$(call RM_FUNC,$@)
	safety check --policy-file $(safety_install_policy_file) -r minimum-constraints-install.txt --full-report
	echo "done" >$@
	@echo "Makefile: Done running Safety for install packages"
endif
endif

ifdef TEST_INSTALLED
  test_deps =
else
  test_deps = $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done $(moftab_files)
endif

$(done_dir)/todo_$(pymn)_$(PACKAGE_LEVEL).done: $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done Makefile $(pylint_rc_file) $(py_src_files) $(py_test_files)
ifeq ($(python_m_version),2)
	@echo "Makefile: Warning: Skipping checking for TODOs on Python $(python_version)" >&2
else
	@echo "Makefile: Checking for TODOs"
	-$(call RM_FUNC,$@)
	pylint --exit-zero --reports=n --jobs=1 --disable=all --enable=fixme $(py_src_files) $(py_test_files)
	-grep TODO $(doc_conf_dir) -r --include="*.rst"
	echo "done" >$@
	@echo "Makefile: Done checking for TODOs"
endif

.PHONY: check_reqs
check_reqs: $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done minimum-constraints-install.txt requirements.txt
ifeq ($(python_m_version),2)
	@echo "Makefile: Warning: Skipping the checking of missing dependencies on Python $(python_version)" >&2
else
	@echo "Makefile: Checking missing dependencies of the package"
	pip-missing-reqs $(package_name) --requirements-file=requirements.txt
	pip-missing-reqs $(package_name) --requirements-file=minimum-constraints-install.txt
	@echo "Makefile: Done checking missing dependencies of the package"
ifeq ($(PLATFORM),Windows_native)
# Reason for skipping on Windows is https://github.com/r1chardj0n3s/pip-check-reqs/issues/67
	@echo "Makefile: Warning: Skipping the checking of missing dependencies of site-packages directory on native Windows" >&2
else
	@echo "Makefile: Checking missing dependencies of some development packages"
	@rc=0; for pkg in $(check_reqs_packages); do dir=$$($(PYTHON_CMD) -c "import $${pkg} as m,os; dm=os.path.dirname(m.__file__); d=dm if not dm.endswith('site-packages') else m.__file__; print(d)"); cmd="pip-missing-reqs $${dir} --requirements-file=minimum-constraints.txt"; echo $${cmd}; $${cmd}; rc=$$(expr $${rc} + $${?}); done; exit $${rc}
	@echo "Makefile: Done checking missing dependencies of some development packages"
endif
endif
	@echo "Makefile: $@ done."

.PHONY: test
test: $(test_deps)
	@echo "Makefile: Running unit and function tests"
	py.test --color=yes $(pytest_cov_opts) $(pytest_warning_opts) $(pytest_opts) $(test_dir)/unittest $(test_dir)/functiontest -s
	@echo "Makefile: Done running unit and function tests"

.PHONY: testc
testc: $(test_deps) $(done_dir)/installc_$(pymn)_$(PACKAGE_LEVEL).done
	@echo "Makefile: Running unit and function tests on cythonized archive"
ifeq ($(PLATFORM),Windows_native)
	cmd /c "set TEST_INSTALLED=1 & py.test --color=yes $(pytest_cov_opts) $(pytest_warning_opts) $(pytest_opts) $(test_dir)/unittest $(test_dir)/functiontest -s"
else
	TEST_INSTALLED=1 py.test --color=yes $(pytest_cov_opts) $(pytest_warning_opts) $(pytest_opts) $(test_dir)/unittest $(test_dir)/functiontest -s
endif
	@echo "Makefile: Done running unit and function tests on cythonized archive"

.PHONY: installtest
installtest: $(bdist_file) $(sdist_file) $(test_dir)/installtest/test_install.sh
	@echo "Makefile: Running install tests"
ifeq ($(PLATFORM),Windows_native)
	@echo "Makefile: Warning: Skipping install test on native Windows" >&2
else
	$(test_dir)/installtest/test_install.sh $(bdist_file) $(sdist_file) $(PYTHON_CMD)
endif
	@echo "Makefile: Done running install tests"

.PHONY: leaktest
leaktest: $(test_deps)
	@echo "Makefile: Running memory leak tests"
	py.test --color=yes $(pytest_warning_opts) $(pytest_opts) $(test_dir)/leaktest -s
	@echo "Makefile: Done running memory leak tests"

.PHONY: end2endtest
end2endtest: $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done $(moftab_files)
	@echo "Makefile: Running end2end tests"
	py.test --color=yes $(pytest_end2end_warning_opts) $(pytest_end2end_opts) $(test_dir)/end2endtest -s
	@echo "Makefile: Done running end2end tests"

.PHONY: resourcetest
resourcetest: $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done $(moftab_files)
ifeq ($(python_m_version),2)
	@echo "Makefile: Warning: Skipping resource consumption tests on Python $(python_version)" >&2
else
	@echo "Makefile: Running resource consumption tests"
	py.test --color=yes $(pytest_warning_opts) $(pytest_opts) $(test_dir)/resourcetest -s
	@echo "Makefile: Done running resource consumption tests"
endif

.PHONY: perftest
perftest: $(done_dir)/develop_$(pymn)_$(PACKAGE_LEVEL).done $(moftab_files)
ifeq ($(python_m_version),2)
	@echo "makefile: Warning: Skipping performance tests on Python $(python_version)" >&2
else
	@echo "makefile: Running performance tests"
	py.test --color=yes $(pytest_warning_opts) $(pytest_opts) $(test_dir)/perftest -s
	@echo "makefile: Done running performance tests"
endif

$(doc_conf_dir)/mof_compiler.help.txt: mof_compiler $(package_name)/_mof_compiler.py
	@echo "Makefile: Creating mof_compiler script help message file"
ifeq ($(PLATFORM),Windows_native)
	mof_compiler.bat --help >$@
else
	./mof_compiler --help >$@
endif
	@echo "Makefile: Done creating mof_compiler script help message file: $@"
