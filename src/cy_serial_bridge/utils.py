import collections.abc
import logging
import sys

"""
Module with basic definitions used by multiple cy_serial_bridge modules.
"""

# Get type annotation for "any type of byte sequence".  This changed in Python 3.12
if sys.version_info < (3, 12):
    ByteSequence = collections.abc.ByteString
else:
    ByteSequence = collections.abc.Buffer

# Logger for the package
log = logging.getLogger("cy_serial_bridge")
