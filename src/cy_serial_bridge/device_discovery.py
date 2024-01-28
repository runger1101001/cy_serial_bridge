from __future__ import annotations

import dataclasses

import usb1

from cy_serial_bridge.driver import usb_context
from cy_serial_bridge.usb_constants import DEFAULT_PID, DEFAULT_VID, CyType


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
    vid_pids: set[tuple[int, int]] | None = frozenset((DEFAULT_VID, DEFAULT_PID)),
) -> list[DeviceListEntry]:
    """
    Scan for USB devices which look like they could be CY6C652xx chips based on their USB descriptor layout.

    If a vid and pid set is given, only devices with the specified vid and pid will be considered.
    If the vid and pid set is left at the default, only the driver default vid and pid will be used.
    If the vid and pid set is set to None, all devices which *could* be CY6C652xx chips are returned.
    """
    device_list: list[DeviceListEntry] = []

    for dev in usb_context.getDeviceIterator(skip_on_error=True):
        dev: usb1.USBDevice

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
