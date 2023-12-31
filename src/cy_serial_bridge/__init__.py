#!/usr/bin/env python3
"""
A port of Cypress USB Serial Library (libcyusbserial) in pure python.

This code is still in alpha stage. Many protocols and data format
details are discovered, but information still needs to be cleaned
out and API/code/tools need further refactoring.

"""

import usb1  # from "libusb1" package

from src.cy_serial_bridge import configuration_block, driver
from src.cy_serial_bridge.configuration_block import CyType
from src.cy_serial_bridge.usb_constants import *
from src.cy_serial_bridge.utils import ByteSequence
