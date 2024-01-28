from __future__ import annotations

import dataclasses
import sys
import time
import typing
from enum import Enum
from typing import AbstractSet, Union

import usb1

from cy_serial_bridge import driver
from cy_serial_bridge.driver import usb_context
from cy_serial_bridge.usb_constants import DEFAULT_PID, DEFAULT_VID, CyType
from cy_serial_bridge.utils import CySerialBridgeError, log


@dataclasses.dataclass
class DeviceListEntry:
    """
    Represents one detected device on the system
    """

    # USBDevice object for the discovered device
    usb_device: usb1.USBDevice

    # Vendor ID
    vid: int

    # Product ID
    pid: int

    # Current CyType setting (SPI, I2C, or UART)
    curr_cytype: CyType

    # If this is true, opening the device failed and the manufacturer, product, and serial_number fields
    # will not be populated.
    # On Windows, opening will fail for any USB devices which do not have the WinUSB driver attached
    # and are not HID devices.
    open_failed: bool

    # Manufacturer string
    manufacturer_str: str | None = None

    # Product name string
    product_str: str | None = None

    # Serial number string
    serial_number: str | None = None


def list_devices(
    vid_pids: AbstractSet[tuple[int, int]] | None = frozenset(((DEFAULT_VID, DEFAULT_PID),)),
) -> list[DeviceListEntry]:
    """
    Scan for USB devices which look like they could be CY6C652xx chips based on their USB descriptor layout.

    If a vid and pid set is given, only devices with the specified vid and pid will be considered.
    If the vid and pid set is left at the default, only the driver default vid and pid will be used.
    If the vid and pid set is set to None, all devices which *could* be CY6C652xx chips are returned.
    """
    device_list: list[DeviceListEntry] = []

    dev: usb1.USBDevice
    for dev in usb_context.getDeviceIterator(skip_on_error=True):
        if vid_pids is not None and (dev.getVendorID(), dev.getProductID()) not in vid_pids:
            # Not a VID-PID we're looking for
            continue

        # CY7C652xx devices always have one configuration
        if len(dev) != 1:
            continue
        cfg: usb1.USBConfiguration = dev[0]

        # CY7C652xx devices always have two interfaces: one for the actual USB-serial bridge
        # and one for the configuration interface.
        if cfg.getNumInterfaces() != 2:
            continue
        scb_interface_settings: usb1.USBInterfaceSetting = cfg[0][0]
        mfg_interface_settings: usb1.USBInterfaceSetting = cfg[1][0]

        # Check SCB interface -- the Class should be 0xFF (vendor defined/no rules)
        # and the SubClass value gives the CyType
        if scb_interface_settings.getClass() != 0xFF:
            continue
        if scb_interface_settings.getSubClass() not in {CyType.UART.value, CyType.SPI.value, CyType.I2C.value}:
            continue

        # Check SCB endpoints
        if scb_interface_settings.getNumEndpoints() != 3:
            continue
        # Bulk host-to-dev endpoint
        if scb_interface_settings[0].getAddress() != 0x01 or (scb_interface_settings[0].getAttributes() & 0x3) != 2:
            continue
        # Bulk dev-to-host endpoint
        if scb_interface_settings[1].getAddress() != 0x82 or (scb_interface_settings[1].getAttributes() & 0x3) != 2:
            continue
        # Interrupt dev-to-host endpoint
        if scb_interface_settings[2].getAddress() != 0x83 or (scb_interface_settings[2].getAttributes() & 0x3) != 3:
            continue

        # Check manufacturer interface.
        # It has a defined class/subclass and has no endpoints
        if mfg_interface_settings.getClass() != 0xFF:
            continue
        if mfg_interface_settings.getSubClass() != CyType.MFG:
            continue
        if mfg_interface_settings.getNumEndpoints() != 0:
            continue

        # If we got all the way here, it looks like a CY6C652xx device!
        # Record attributes and add it to the list
        list_entry = DeviceListEntry(
            usb_device=dev,
            vid=dev.getVendorID(),
            pid=dev.getProductID(),
            curr_cytype=CyType(scb_interface_settings.getSubClass()),
            open_failed=False,
        )
        try:
            opened_device = dev.open()
            list_entry.manufacturer_str = opened_device.getManufacturer()
            list_entry.product_str = opened_device.getProduct()
            list_entry.serial_number = opened_device.getSerialNumber()
        except usb1.USBError:
            list_entry.open_failed = True

        device_list.append(list_entry)

    return device_list


class OpenMode(Enum):
    """
    Enumeration of the modes a serial bridge chip can be opened in.

    Value is a tuple of:
    - CY_TYPE that the chip must be in to use this mode, or None for any
    - Driver class that will be instantiated and returned
    """

    I2C_CONTROLLER = (CyType.I2C, driver.CyI2CControllerBridge)
    SPI_CONTROLLER = (CyType.SPI, driver.CySPIControllerBridge)
    MFGR_INTERFACE = (None, driver.CyMfgrIface)


# Time we allow for the device to change its type and be enumerated on the USB bus:
# On Windows, this nominally takes about 400 ms.
CHANGE_TYPE_TIMEOUT = 5.0  # s


def _scan_for_device(vid: int, pid: int, serial_number: str | None) -> DeviceListEntry:
    """
    Helper function for open_scb_device().
    """
    devices = list_devices({(vid, pid)})

    if len(devices) == 0:
        message = f"No devices found with VID:PID {vid:04x}:{pid:04x}"
        raise CySerialBridgeError(message)
    elif len(devices) == 1:
        # Exactly 1 device found
        device_to_open = devices[0]

        if device_to_open.open_failed:
            message = f"Found device with VID:PID {vid:04x}:{pid:04x} but cannot open it!"
            if sys.platform == "win32":
                message += "  This is likely because it does not have the WinUSB driver attached."
            raise CySerialBridgeError(message)

        if serial_number is not None and device_to_open.serial_number != serial_number:
            message = "The only detected device does not have a matching serial number!"
            raise CySerialBridgeError(message)

    else:  # Multiple devices
        # Search by serial number
        if serial_number is None:
            message = f"Multiple devices found with VID:PID {vid:04x}:{pid:04x} but no serial number provided!"
            raise CySerialBridgeError(message)

        any_unopenable_devices = False
        device_to_open = None
        for device in devices:
            if device.open_failed:
                any_unopenable_devices = True
            elif device.serial_number == serial_number:
                device_to_open = device
                break

        if device_to_open is None:
            if any_unopenable_devices:
                message = (
                    f"Did not find an exact match for serial number.  However, at least one candidate device with "
                    f"VID:PID {vid:04x}:{pid:04x} was found that could not be opened!"
                )
                if sys.platform == "win32":
                    message += "  This is likely because it does not have the WinUSB driver attached."
                raise CySerialBridgeError(message)
            else:
                message = f"Multiple devices found with VID:PID {vid:04x}:{pid:04x} but none matched the specified serial number!"
                raise CySerialBridgeError(message)

    return device_to_open


AnyDriverClass = Union[driver.CySPIControllerBridge, driver.CyI2CControllerBridge, driver.CyMfgrIface]


def open_device(vid: int, pid: int, open_mode: OpenMode, serial_number: str | None = None) -> AnyDriverClass:
    """
    Convenience function for opening a CY7C652xx SCB device in a desired mode.

    Unlike creating an instance of the driver class directly, this function attempts to abstract away
    management of the device's CyType and will automatically change its type to the needed one.

    :param vid: Vendor ID of the device you want to open
    :param pid: Product ID of the device you want to open
    :param serial_number: Serial number of the device you want to open.  May be left as None if there is only one device attached.
    :param open_mode: Mode to open the SCB device in
    """
    # Step 1: Search for matching devices on the system
    device_to_open = _scan_for_device(vid, pid, serial_number)

    # Step 2: Change type of the device, if needed
    needed_cytype: CyType | None = open_mode.value[0]
    driver_class: type[driver.CySerBridgeBase] = open_mode.value[1]
    if needed_cytype is not None and device_to_open.curr_cytype != needed_cytype:
        log.info(
            f"The CyType of this device must be changed to {needed_cytype.name} in order to open it as {open_mode.name}"
        )
        change_type_start_time = time.time()

        # Open the device in manufacturer mode and change its type
        with driver.CyMfgrIface(device_to_open.usb_device) as mfgr_driver:
            mfgr_driver.change_type(needed_cytype)
            mfgr_driver.reset_device()

        # Wait for the device to re-enumerate with the new type
        while True:
            try:
                device_to_open = None
                device_to_open = _scan_for_device(vid, pid, serial_number)

                # log.debug(f"Scan found a device with CyType {device_to_open.curr_cytype}")

                if device_to_open.curr_cytype == needed_cytype:
                    break
            except Exception as ex:
                if time.time() < change_type_start_time + CHANGE_TYPE_TIMEOUT:
                    # Not found but still within the timeout, wait a bit and try again
                    time.sleep(0.01)
                else:
                    message = "Timeout waiting for device to re-enumerate after changing its type."
                    raise CySerialBridgeError(message) from ex

            if (
                device_to_open is not None
                and time.time() >= change_type_start_time + CHANGE_TYPE_TIMEOUT
                and device_to_open.curr_cytype != needed_cytype
            ):
                message = "The CyType of the device did not change to the correct value within the timeout!"
                raise CySerialBridgeError(message)

        log.info(f"Changed type of device in {time.time() - change_type_start_time:.04f} sec")

    # Step 3: Instantiate the driver!
    return typing.cast(AnyDriverClass, driver_class(device_to_open.usb_device))
