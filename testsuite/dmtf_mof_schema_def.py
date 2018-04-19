"""
Definition of the DMTF MOF Schema to be used in this testsuite and the
code to install it if not already installed and unzipped.

The version defined below will be installed in the directory SCHEMA_DIR
(testsuite/schema) if that directory is empty or the file does not exist.

Otherwise, the tests will be executed with that defined version of the
schema.

NOTE: The zip expansion is NOT committed to git, just the original zip file.

To change the schema used:

1. Change the DMTF_SCHEMA_DIR to reflect the version of the schema that will
   be the pywbem tests test schema

2. Delete the SCHEMA_DIR (testsuite/schema). Be sure to delete the directory
   to be sure the new schema gets downloaded and correctly expanded.

3. Execute testsuite/test_mof_compiler.py. This should cause the new schema
   to be downloaded and expanded as part of the test.

4. The first test should generate an error if the values for total number of
   classes or qualifiers have changed. Modify the  variables below to define
   the correct numbers and re-execute test_mof_compiler.
   NOTE: We are keeping some history of the counts for previous versions of
   the schema (see the comments at the end of this file)
"""

import os

from pywbem_mock import DMTFSchema


# Change the following variables when a new version of the CIM Schema is used
# and remove the SCHEMA_DIR directory
# This defines the version and the location of the schema zip file on the
# DMTF web site.
# See the page http://www.dmtf.org/standards/cim if there are issues
# downloading a particular version.

# Location of the schema for use by test_mof_compiler.
# This should not change unless you intend to use another schema directory
SCRIPT_DIR = os.path.dirname(__file__)
SCHEMA_DIR = os.path.join(SCRIPT_DIR, 'schema')

# Defines the version of DMTF schema to be downloaded and installed
DMTF_SCHEMA_VER = (2, 49, 0)

# Expected total of qualifiers and classes in the DMTF Schema.
# These may change for each schema release and will need to be manually
# modified here to correctly execute the tests.
# 2.49.0
TOTAL_QUALIFIERS = 70
TOTAL_CLASSES = 1631

# Qualifier and Class counts for previous DMTF schema.
# 2.48.0
# TOTAL_QUALIFIERS = 70
# TOTAL_CLASSES = 1630


def install_test_dmtf_schema():
    """
    Install the DMTF schema if it is not already installed.  All the
    definitions of the installation are in the module variables.
    The user of ths should need
    """
    schema = DMTFSchema(DMTF_SCHEMA_VER, SCHEMA_DIR)

    return schema
