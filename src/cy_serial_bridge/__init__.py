"""
A port of Cypress USB Serial Library (libcyusbserial) in pure python.

This code is still in alpha stage. Many protocols and data format
details are discovered, but information still needs to be cleaned
out and API/code/tools need further refactoring.

"""

import usb1  # from "libusb1" package

from cy_serial_bridge import configuration_block, driver
from cy_serial_bridge.driver import CySerialBridgeError, I2CArbLostError, I2CBusErrorError, I2CNACKError
from cy_serial_bridge.usb_constants import *
from cy_serial_bridge.utils import ByteSequence
