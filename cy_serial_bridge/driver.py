from __future__ import annotations

import struct
import sys
from dataclasses import dataclass
from typing import Iterator, Tuple, cast

import usb1

from cy_serial_bridge.configuration_block import ConfigurationBlock
from cy_serial_bridge.usb_constants import *
from cy_serial_bridge.utils import ByteSequence, log

"""
Module containing the logic for communicating with the CY7C652xx USB device.
Note that this does NOT include logic for (a) scanning the device tree to find
the correct USB device or (b) manipulating configuration blocks.  Those get their own
modules.
"""

# For now, just use one global context.  This might have to be changed later but seems OK for initial development.
usb_context = usb1.USBContext()
usb_context.open()


def find_device(vid=None, pid=None) -> Iterator[usb1.USBDevice]:
    """Finds USB device by VID/PID"""
    for dev in usb_context.getDeviceList(skip_on_error=True):
        if vid and dev.getVendorID()  != vid: continue
        if pid and dev.getProductID() != pid: continue
        yield dev


def find_path(ux, func, hist=[]):
    """Scans through USB device structure"""
    try:
        hist.insert(0, ux)
        if func(ux):
            yield hist.copy()
        for ux_child in ux:
            yield from find_path(ux_child, func, hist)
    except TypeError:
        pass
    finally:
        hist.pop(0)


def get_type(us):
    """Returns CY_TYPE of USB Setting"""
    if us.getClass() == CyClass.VENDOR:
        return CyType(us.getSubClass())
    return CyType.DISABLED


def find_type(ud: usb1.USBDevice, cy_type):
    """Finds USB interface by CY_TYPE. Yields list of (us, ui, uc, ud) set"""
    def check_match(ux):
        return isinstance(ux, usb1.USBInterfaceSetting) and get_type(ux) == cy_type
    yield from find_path(ud, check_match)


class CySerBridgeBase:
    """
    Base class containing functionality common to all modes of a CY7C652xx
    """

    def __init__(self, ud: usb1.USBDevice, cy_type: CyType, scb_index: int, timeout: int):
        """
        Create a CySerBridgeBase.

        :param ud: USB device to open
        :param cy_type: Type to open the device as.
        :param index: Index of the SCB to open, for multi-port devices
        :param timeout: Timeout to use for USB operations in milliseconds
        """
        self.scb_index = scb_index
        found = list(find_type(ud, cy_type))
        if not found:
            raise RuntimeError("No device found with given type")
        if len(found) - 1 > scb_index:
            raise RuntimeError("Not enough interfaces (SCBs) found")

        # setup parameters
        us: usb1.USBInterfaceSetting
        ui: usb1.USBInterface
        uc: usb1.USBConfiguration
        ud: usb1.USBDevice
        us, ui, uc, ud = found[scb_index]
        self.us_num = us.getAlternateSetting()
        self.if_num = us.getNumber()
        self.uc_num = uc.getConfigurationValue()
        self.timeout = timeout

        # scan EPs
        self.ep_in = None
        self.ep_out = None
        for ep in us:
            ep_attr = ep.getAttributes()
            ep_addr = ep.getAddress()
            if ep_attr == EP_BULK:
                if ep_addr & EP_IN:
                    self.ep_in = ep_addr
                else:
                    self.ep_out = ep_addr
            elif ep_attr == EP_INTR:
                self.ep_intr = ep_addr

        # TODO why doesn't this check work?  Need to debug
        # if self.ep_in is None or self.ep_out is None or self.ep_intr is None:
        #     raise RuntimeError("Failed to find CY7C652xx USB endpoints in USB device -- not a Cypress serial bridge device?")

        log.info("Discovered USB endpoints successfully")

        # open USBDeviceHandle
        try:
            self.dev = ud.open()
        except usb1.USBErrorNotFound as ex:
            if sys.platform == "win32":
                raise RuntimeError("Failed to open USB device, ensure that WinUSB driver has been loaded for it using Zadig") from ex
            else:
                raise

        if usb1.hasCapability(usb1.CAP_SUPPORTS_DETACH_KERNEL_DRIVER):
            # detach kernel driver to gain access
            self.dev.setAutoDetachKernelDriver(True)

    def __enter__(self):

        try:
            #
            # NOTE:
            # Windows and others seems to differ in expected order of
            # when to claim interface and when to set configuration.
            #
            self.dev.setConfiguration(self.uc_num)
            if self.us_num > 0:
                self.dev.setInterfaceAltSetting(self.if_num, self.us_num)

            self.dev.claimInterface(self.if_num)

            # Check the device signature
            signature = bytes(self.get_signature())
            log.info("Device signature: %s", repr(signature))
            if signature != b"CYUS":

                # __exit__ won't be called if we raise an exception here
                self.dev.releaseInterface(self.if_num)
                self.close()

                raise RuntimeError("Invalid signature for CY7C652xx device")

            # Get and print the firmware version
            firmware_version = self.get_firmware_version()
            print("Connected to CY7C652xx device, firmware version %d.%d.%d build %d" % firmware_version)

        except usb1.USBErrorNotSupported as ex:
            if sys.platform == "win32":
                raise RuntimeError("Failed to claim USB device, ensure that WinUSB driver has been loaded for it using Zadig") from ex
            else:
                raise

        return self

    def __exit__(self, err_type, err_value, tb):
        self.dev.releaseInterface(self.if_num)

        if self.dev:
            self.dev.close()
        self.dev = None

    def _wait_for_notification(self, event_notification_len: int, timeout: int):
        """
        Wait for a transfer complete notification from the serial bridge.

        This is used for background serial transfers.

        :param event_notification_len: Length of event notification
        :param timeout: Transfer timeout in milliseconds. 0 to disable.
        """
        transfer = self.dev.getTransfer(0)
        transfer.setInterrupt(self.ep_intr, event_notification_len, timeout=timeout)
        transfer.submit()

    # Common functions which work in all interface modes --------------------------------
    def get_firmware_version(self) -> tuple[int, int, int, int]:
        """
        This API retrieves the firmware version of the USB Serial device.

        :return: Firmware version as a 4-tuple of (major ver, minor ver, patch ver, build number)
        """
        bm_request_type = CY_VENDOR_REQUEST | EP_IN
        bm_request = CyVendorCmds.CY_GET_VERSION_CMD
        w_value = 0
        w_index = 0
        w_length = CY_GET_FIRMWARE_VERSION_LEN

        firmware_version_bytes = self.dev.controlRead(bm_request_type, bm_request,
                                   w_value, w_index, w_length, self.timeout)

        # C definition:
        # typedef struct _CY_FIRMWARE_VERSION {
        #
        #     UINT8 majorVersion;                 /*Major version of the Firmware*/
        #     UINT8 minorVersion;                 /*Minor version of the Firmware*/
        #     UINT16 patchNumber;                 /*Patch Number of the Firmware*/
        #     UINT32 buildNumber;                 /*Build Number of the Firmware*/
        #
        # } CY_FIRMWARE_VERSION, *PCY_FIRMWARE_VERSION;

        return cast(Tuple[int, int, int, int], struct.unpack("<BBHI", firmware_version_bytes))

    def get_signature(self) -> ByteSequence:
        """
        This API is used to get the signature of the device.

        It would be CYUS when we are in actual device mode and CYBL when we are bootloader mode.
        """
        bm_request_type = CY_VENDOR_REQUEST | EP_IN
        bm_request = CyVendorCmds.CY_GET_SIGNATURE_CMD
        w_value = 0
        w_index = 0
        w_length = CY_GET_SIGNATURE_LEN

        return self.dev.controlRead(bm_request_type, bm_request,
                                   w_value, w_index, w_length, self.timeout)

    def reset_device(self):
        """
        The API will reset the device by sending a vendor request to the firmware. The device
        will be re-enumerated.

        After calling this function, the serial bridge object that you called it on will become
        nonfunctional and should be closed.  You must open a new instance of the driver
        after the device re-enumerates.
        """
        bm_request_type = CY_VENDOR_REQUEST | EP_IN
        bm_request = CyVendorCmds.CY_DEVICE_RESET_CMD
        w_value = 0xA6B6
        w_index = 0xADBA
        data = b""

        # Resetting the device always seems to result in a pipe error -- it seems like the
        # low level USB control operation always returns USBD_STATUS_XACT_ERROR (0xc0000011)
        try:
            self.dev.controlWrite(bm_request_type, bm_request,
                                   w_value, w_index, data, self.timeout)
        except usb1.USBErrorPipe:
            return

    def program_user_flash(self, addr: int, buff: ByteSequence):
        """
        The API programs user flash area. The total space available is 512 bytes.

        The flash area address offset is from 0x0000 to 0x00200 and should be written
        in even pages (page size is 128 bytes)

        :param addr: Address to start writing data at.  Must be a multiple of 128 and between 0 and 384.
        :param buff: Buffer of data to write.  Must be a multiple of 128 bytes long.
        """
        if addr % USER_FLASH_PAGE_SIZE != 0 or len(buff) % USER_FLASH_PAGE_SIZE != 0 or len(buff) == 0:
            raise ValueError("Program operation not aligned correctly!")
        if addr < 0 or len(buff) + addr > USER_FLASH_SIZE:
            raise ValueError("Program operation outside user flash bounds!")

        num_pages = len(buff) // USER_FLASH_PAGE_SIZE
        for page_idx in range(num_pages):
            first_byte_idx = page_idx * USER_FLASH_PAGE_SIZE
            bytes_to_send = buff[first_byte_idx:first_byte_idx+USER_FLASH_PAGE_SIZE]
            self.dev.controlWrite(
                request_type=CY_VENDOR_REQUEST_DEVICE_TO_HOST,
                request=CyVendorCmds.CY_PROG_USER_FLASH_CMD,
                value=0,
                index=addr + first_byte_idx,
                data=bytes_to_send,
                timeout=self.timeout)

    def read_user_flash(self, addr: int, size: int) -> bytearray:
        """
        Read from the user flash area (this can be programmed with program_user_flash(), see
        that function for more details).

        :param addr: Address to start reading data from.  Must be a multiple of 128 and between 0 and 384.
        :param size: Count of data bytes to read.  Must be a multiple of 128.
        """
        if addr % USER_FLASH_PAGE_SIZE != 0 or size % USER_FLASH_PAGE_SIZE != 0 or size == 0:
            raise ValueError("Read operation not aligned correctly!")
        if addr < 0 or size + addr > USER_FLASH_SIZE:
            raise ValueError("Read operation outside user flash bounds!")

        result_bytes = bytearray()

        num_pages = size // USER_FLASH_PAGE_SIZE
        for page_idx in range(num_pages):
            page_bytes = self.dev.controlRead(
                request_type=CY_VENDOR_REQUEST_DEVICE_TO_HOST,
                request=CyVendorCmds.CY_READ_USER_FLASH_CMD,
                value=0,
                index=addr + page_idx * USER_FLASH_PAGE_SIZE,
                length=USER_FLASH_PAGE_SIZE,
                timeout=self.timeout)
            result_bytes.extend(page_bytes)

        return result_bytes


class CyMfgrIface(CySerBridgeBase):
    """
    Class allowing access to a CY7C652xx in the manufacturing interface mode.

    This is the interface that USCU uses to configure the device, and is reverse-engineered from
    the operation of that program.
    """

    def __init__(self, ud: usb1.USBDevice, scb_index=0, timeout=1000):
        """
        Create a CySerBridgeBase.

        :param ud: USB device to open
        :param scb_index: Index of the SCB to open, for multi-port devices
        :param timeout: Timeout to use for USB operations in milliseconds
        """
        super().__init__(ud, CyType.MFG, scb_index, timeout)

    ######################################################################
    # Non-public APIs still under experimental stage
    ######################################################################

    def ping(self):
        """Send whatever USCU sends on startup"""
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = 203
        w_value = 0
        w_index = 0
        w_buffer = bytearray(0)

        return self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)

    def probe0(self):
        """Send whatever USCU sends on startup - some signature?"""
        bm_request_type = CY_VENDOR_REQUEST | EP_IN
        bm_request = 177
        w_value = 0
        w_index = 0
        w_length = 4

        return self.dev.controlRead(bm_request_type, bm_request,
                                   w_value, w_index, w_length, self.timeout)

    # Note that there used to be a "probe1" function here for another mystery sequence, but that was revealed to be just
    # getting the firmware version (equivalent to get_firmware_version())

    def connect(self):
        """Send whatever USCU sends on connect"""
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = 226
        w_value = 0xa6bc
        w_index = 0xb1b0
        w_buffer = bytearray(0)

        ret = self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)
        return ret

    def disconnect(self):
        """Send whatever USCU sends on disconnect"""
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = 226
        w_value = 0xa6bc
        w_index = 0xb9b0
        w_buffer = bytearray(0)

        return self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)

    def read_config(self) -> ByteSequence:
        """Send whatever USCU sends on config read"""
        bm_request_type = CY_VENDOR_REQUEST | EP_IN
        bm_request = 181
        w_value = 0
        w_index = 0
        w_length = 512

        return self.dev.controlRead(bm_request_type, bm_request,
                                   w_value, w_index, w_length, self.timeout)

    def write_config(self, config: ConfigurationBlock):
        """Send whatever USCU sends on config write"""
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = 182
        w_value = 0
        w_index = 0

        w_buffer = config.bytes

        return self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)


@dataclass
class CyI2CConfig:
    frequency: int = 400000 # I2C frequency in Hz


class CyI2CControllerBridge(CySerBridgeBase):
    """
    Driver which uses a Cypress serial bridge in I2C controller (master) mode.
    """

    def __init__(self, ud: usb1.USBDevice, scb_index=0, timeout=1000):
        """
        Create a CySerBridgeBase.

        :param ud: USB device to open
        :param scb_index: Index of the SCB to open, for multi-port devices
        :param timeout: Timeout to use for USB operations in milliseconds
        """
        super().__init__(ud, CyType.MFG, scb_index, timeout)

    def set_i2c_configuration(self, config: CyI2CConfig):
        """
        This API configures the I2C module of USB Serial device.
        Currently the only setting configurable for I2C master is the frequency.

        You should always call this function after first opening the device because the configuration rewriting part of
        the module does not know how to set the default I2C settings in config and they may be garbage.

        Note: Using this API during an active transaction of I2C may result in data loss.
        """
        binary_configuration = struct.pack(CY_USB_I2C_CONFIG_STRUCT_LAYOUT,
        config.frequency,
            0,  # sAddress - seems to be ignored in master mode
            1,  # isMsbFirst - Driver always sets this to 1
            1,  # isMaster - set to true for master mode
            0,  # sIgnore - seems to be ignored in master mode
            0,  # clockStretch - seems to be ignored in master mode
            0,  # isLoopback - Driver always sets this to 0
        )

        self.dev.controlWrite(
            request_type=CY_VENDOR_REQUEST_HOST_TO_DEVICE,
            request=CyVendorCmds.CY_I2C_SET_CONFIG_CMD,
            value=(self.scb_index << CyI2c.SCB_INDEX_POS),
            index=0,
            data=binary_configuration,
            timeout=self.timeout)

    def read_i2c_configuration(self) -> CyI2CConfig:
        """
        Read the current I2C master mode configuration from the device.
        """
        config_bytes = self.dev.controlRead(
            request_type=CY_VENDOR_REQUEST_DEVICE_TO_HOST,
            request=CyVendorCmds.CY_I2C_GET_CONFIG_CMD,
            value=(self.scb_index << CyI2c.SCB_INDEX_POS),
            index=0,
            length=CyI2c.CONFIG_LENGTH,
            timeout=self.timeout)

        config_unpacked = struct.unpack(CY_USB_I2C_CONFIG_STRUCT_LAYOUT, config_bytes)
        config = CyI2CConfig(frequency=config_unpacked[0])

        return config
