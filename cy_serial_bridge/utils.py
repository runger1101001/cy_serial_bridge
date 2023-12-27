import collections.abc
import sys
import logging

"""
Module with basic definitions used by multiple cy_serial_bridge modules.
"""

# Get type annotation for "any type of byte sequence".  This changed in Python 3.12
if sys.version_info[0] > 3 or sys.version_info[1] >= 12:
    ByteSequence = collections.abc.Buffer
else:
    ByteSequence = collections.abc.ByteString

# Logger for the package
log = logging.getLogger("cy_serial_bridge")