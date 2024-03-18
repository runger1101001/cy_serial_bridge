"""
A port of Cypress USB Serial Library (libcyusbserial) in pure python.

This code is still in alpha stage. Many protocols and data format
details are discovered, but information still needs to be cleaned
out and API/code/tools need further refactoring.

"""

from cy_serial_bridge import configuration_block, device_discovery, driver
from cy_serial_bridge.configuration_block import ConfigurationBlock
from cy_serial_bridge.device_discovery import OpenMode, list_devices, open_device, scan_for_device
from cy_serial_bridge.driver import (
    CyI2CControllerBridge,
    CySerialBridgeError,
    CySPIConfig,
    CySPIControllerBridge,
    CySPIMode,
    I2CArbLostError,
    I2CBusError,
    I2CNACKError,
)
from cy_serial_bridge.usb_constants import *
from cy_serial_bridge.utils import ByteSequence
