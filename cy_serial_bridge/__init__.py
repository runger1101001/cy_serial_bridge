#!/usr/bin/env python3
"""
A port of Cypress USB Serial Library (libcyusbserial) in pure python.

This code is still in alpha stage. Many protocols and data format
details are discovered, but information still needs to be cleaned
out and API/code/tools need further refactoring.

"""
import collections.abc
import logging
import os
import struct
import sys
from enum import Enum, IntEnum
from struct import pack, unpack
from typing import Iterator, Tuple

import usb1  # from "libusb1" package
from usb1 import USBContext, USBInterfaceSetting

from cy_serial_bridge import configuration_block
from cy_serial_bridge.configuration_block import CyType
from cy_serial_bridge.usb_constants import *
from cy_serial_bridge.utils import ByteSequence, log

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
        return isinstance(ux, USBInterfaceSetting) and get_type(ux) == cy_type
    yield from find_path(ud, check_match)

class CyUSB:

    ######################################################################
    # WARNING: Many APIs are not yet complete and/or tested.
    ######################################################################

    def CyGetSpiConfig(self):
        scbIndex = 1 if self.if_num > 0 else 0
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyVendorCmds.CY_SPI_GET_CONFIG_CMD
        w_value = (scbIndex << CY_SCB_INDEX_POS)
        w_index = 0
        w_length = CySpi.CONFIG_LEN

        ret = self.dev.controlRead(bm_request_type, bm_request,
                                   w_value, w_index, w_length, self.timeout)
        return ret

    def CySetSpiConfig(self, config):
        scbIndex = 1 if self.if_num > 0 else 0
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyVendorCmds.CY_SPI_SET_CONFIG_CMD
        w_value = (scbIndex << CY_SCB_INDEX_POS)
        w_index = 0
        w_length = CySpi.CONFIG_LEN
        w_buffer = bytearray()

        ret = self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)
        return ret

    def CySpiReset(self):
        scbIndex = 1 if self.if_num > 0 else 0
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyVendorCmds.CY_SPI_RESET_CMD
        w_value = (scbIndex << CY_SCB_INDEX_POS)
        w_index = 0
        w_length = 0

        ret = self.dev.controlRead(bm_request_type, bm_request,
                                   w_value, w_index, w_length, self.timeout)
        return ret

    def CySpiRead(self, size):
        return self.dev.bulkRead(self.ep_in, size, timeout=self.timeout)

    def CySpiWrite(self, buff):
        return self.dev.bulkWrite(self.ep_out, buff, timeout=self.timeout)

    def CyGetSpiStatus(self):
        scbIndex = 1 if self.if_num > 0 else 0
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyVendorCmds.CY_SPI_GET_STATUS_CMD
        w_value = (scbIndex << CY_SCB_INDEX_POS)
        w_index = 0
        w_length = CySpi.GET_STATUS_LEN

        ret = self.dev.controlRead(bm_request_type, bm_request,
                                   w_value, w_index, w_length, self.timeout)
        return ret

    def CySpiReadWrite(self, wrbuff, rdsize):
        spiTransferMode = 0
        w_index = 0
        if len(wrbuff) > 0:
            spiTransferMode |= CySpi.WRITE_BIT
            w_index = len(wrbuff)
        if rdsize > 0:
            spiTransferMode |= CySpi.READ_BIT
            w_index = rdsize

        scbIndex = 1 if self.if_num > 0 else 0
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyVendorCmds.CY_SPI_READ_WRITE_CMD
        w_value = (scbIndex << CY_SCB_INDEX_POS) | spiTransferMode
        w_buffer = bytearray(0)

        ret = self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)

        if not spiTransferMode & CySpi.READ_BIT:
            return self.CySpiWrite(wrbuff)

        if not spiTransferMode & CySpi.WRITE_BIT:
            return self.CySpiRead(rdsize)

        # FIXME: Not sure what Cypress is doing in read-write case

        return ret

    def CyGetI2cConfig(self):
        scbIndex = 1 if self.if_num > 0 else 0
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyVendorCmds.CY_I2C_GET_CONFIG_CMD
        w_value = (scbIndex << CY_SCB_INDEX_POS)
        w_index = 0
        w_length = CyI2c.CONFIG_LENGTH

        ret = self.dev.controlRead(bm_request_type, bm_request,
                                   w_value, w_index, w_length, self.timeout)
        return ret

    def CySetI2cConfig(self, config):
        scbIndex = 1 if self.if_num > 0 else 0
        bm_request_type = CY_VENDOR_REQUEST | EP_IN
        bm_request = CyVendorCmds.CY_I2C_SET_CONFIG_CMD
        w_value = (scbIndex << CY_SCB_INDEX_POS)
        w_index = 0
        w_length = CyI2c.CONFIG_LENGTH

        ret = self.dev.controlRead(bm_request_type, bm_request,
                                   w_value, w_index, w_length, self.timeout)
        return ret

    def CyI2cRead(self, config, size):
        scbIndex = 1 if self.if_num > 0 else 0
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyVendorCmds.CY_I2C_READ_CMD
        w_value = ((scbIndex << 7) | (0x7F & config.slaveAddress)) << 8
        w_value |= config.isStopBit | (config.isNakBtit << 1)
        w_index = size
        w_buffer = bytearray(0)

        ret = self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)

        ret = self.dev.bulkRead(self.ep_in, size, timeout=self.timeout)

        return ret

    def CyI2cWrite(self, buff):
        scbIndex = 1 if self.if_num > 0 else 0
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyVendorCmds.CY_I2C_WRITE_CMD
        w_value = ((scbIndex << 7) | (0x7F & config.slaveAddress)) << 8
        w_value |= config.isStopBit
        w_index = len(buff)
        w_buffer = bytearray(0)

        ret = self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)

        ret = self.dev.bulkWrite(self.ep_out, buff, timeout=self.timeout)
        return ret

    def CyI2cGetStatus(self, mode=0):
        dev = self.dev

        scbIndex = 1 if self.if_num > 0 else 0
        bm_request_type = CY_VENDOR_REQUEST | EP_IN
        bm_request = CyVendorCmds.CY_I2C_GET_STATUS_CMD
        w_value = (scbIndex << CY_SCB_INDEX_POS) | mode
        w_index = 0
        w_length = CyI2c.GET_STATUS_LEN

        ret = dev.controlRead(bm_request_type, bm_request,
                              w_value, w_index, w_length, self.timeout)
        return ret

    def CyI2cReset(self, mode=0):
        dev = self.dev

        scbIndex = 1 if self.if_num > 0 else 0
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyVendorCmds.CY_I2C_RESET_CMD
        w_value = (scbIndex << CY_SCB_INDEX_POS) | mode
        w_index = 0
        w_buffer = bytearray(0)

        ret = dev.controlWrite(bm_request_type, bm_request,
                               w_value, w_index, w_buffer, self.timeout)
        return ret

    def CyGetUartConfig(self):
        scbIndex = 1 if self.if_num > 0 else 0
        bm_request_type = CY_VENDOR_REQUEST | EP_IN
        bm_request = CyVendorCmds.CY_UART_GET_CONFIG_CMD
        w_value = (scbIndex << CY_SCB_INDEX_POS)
        w_index = 0
        w_length = CyUart.CONFIG_LEN

        ret = self.dev.controlRead(bm_request_type, bm_request,
                                   w_value, w_index, w_length, self.timeout)
        return ret

    def CySetUartConfig(self):
        dev = self.dev

        scbIndex = 1 if self.if_num > 0 else 0
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyVendorCmds.CY_UART_SET_CONFIG_CMD
        w_value = (scbIndex << CY_SCB_INDEX_POS)
        w_index = 0
        w_buffer = bytearray(CyUart.CONFIG_LEN)

        ret = dev.controlWrite(bm_request_type, bm_request,
                               w_value, w_index, w_buffer, self.timeout)
        return ret

    def CyUartWrite(self, buff):
        dev = self.dev
        ret = dev.bulkWrite(self.ep_out, buff, timeout=self.timeout)
        return ret

    def CyUartRead(self, size):
        dev = self.dev

        # FIXME: need to loop and append buffer until full size is read
        ret = dev.bulkRead(self.ep_in, size, timeout=self.timeout)
        return ret

    def CyUartSetHwFlowControl(self, mode):
        self.uart_flowcontrol_mode = mode

        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyVendorCmds.CY_UART_SET_FLOW_CONTROL_CMD
        w_value = mode
        w_index = self.if_num
        w_buffer = bytearray(0)

        ret = self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)
        return ret

    def CyUartGetHwFlowControl(self):
        return self.uart_flowcontrol_mode

    def CyUartSetBreak(self, ms):
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyVendorCmds.CY_UART_SEND_BREAK_CMD
        w_value = ms
        w_index = self.if_num
        w_buffer = bytearray(0)

        ret = self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)
        return ret

    def CyUartSetRts(self):
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyUart.SET_LINE_CONTROL_STATE_CMD
        w_value = (1<<1) | self.dtrValue
        w_index = self.if_num
        w_buffer = bytearray(0)

        ret = self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)
        self.rtsValue = 1
        return ret

    def CyUartClearRts(self):
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyUart.SET_LINE_CONTROL_STATE_CMD
        w_value = self.dtrValue
        w_index = self.if_num
        w_buffer = bytearray(0)

        ret = self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)
        self.rtsValue = 0
        return ret

    def CyUartSetDtr(self):
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyUart.SET_LINE_CONTROL_STATE_CMD
        w_value = (self.rtsValue << 1) | 1
        w_index = self.if_num
        w_buffer = bytearray(0)

        ret = self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)
        self.dtrValue = 1
        return ret

    def CyUartClearDtr(self):
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyUart.SET_LINE_CONTROL_STATE_CMD
        w_value = (self.rtsValue << 1)
        w_index = self.if_num
        w_buffer = bytearray(0)

        ret = self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)
        self.dtrValue = 0
        return ret

    def CySetGpioValue(self, gpio, value):
        bm_request_type = CY_VENDOR_REQUEST | EP_IN
        bm_request = CyVendorCmds.CY_GPIO_SET_VALUE_CMD
        w_value = gpio
        w_index = value
        w_length = 0

        ret = self.dev.controlRead(bm_request_type, bm_request,
                                   w_value, w_index, w_length, self.timeout)
        return ret

    def CyGetGpioValue(self, gpio):
        bm_request_type = CY_VENDOR_REQUEST | EP_IN
        bm_request = CyVendorCmds.CY_GPIO_GET_VALUE_CMD
        w_value = gpio
        w_index = 0
        w_length = CY_GPIO_GET_LEN

        ret = self.dev.controlRead(bm_request_type, bm_request,
                                   w_value, w_index, w_length, self.timeout)
        return ret

    def CyProgUserFlash(self, addr, buff):
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = CyVendorCmds.CY_PROG_USER_FLASH_CMD
        w_value = 0
        w_index = addr
        w_buffer = buff

        ret = self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)
        return ret

    def CyReadUserFlash(self, addr, size):
        bm_request_type = CY_VENDOR_REQUEST | EP_IN
        bm_request = CyVendorCmds.CY_READ_USER_FLASH_CMD
        w_value = 0
        w_index = addr
        w_length = size

        ret = self.dev.controlRead(bm_request_type, bm_request,
                                   w_value, w_index, w_length, self.timeout)
        return ret

    ######################################################################
    # Non-Cypress APIs still under experimental stage
    ######################################################################

    def ping(self):
        """Send whatever USCU sends on startup"""
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = 203
        w_value = 0
        w_index = 0
        w_buffer = bytearray(0)

        ret = self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)
        return ret

    def probe0(self):
        """Send whatever USCU sends on startup - some signature?"""
        bm_request_type = CY_VENDOR_REQUEST | EP_IN
        bm_request = 177
        w_value = 0
        w_index = 0
        w_length = 4

        ret = self.dev.controlRead(bm_request_type, bm_request,
                                   w_value, w_index, w_length, self.timeout)
        return ret

    def probe1(self):
        """Send whatever USCU sends on startup - firmware version?"""
        bm_request_type = CY_VENDOR_REQUEST | EP_IN
        bm_request = 176
        w_value = 0
        w_index = 0
        w_length = 8

        ret = self.dev.controlRead(bm_request_type, bm_request,
                                   w_value, w_index, w_length, self.timeout)
        return ret

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

        ret = self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)
        return ret

    def read_config(self) -> ByteSequence:
        """Send whatever USCU sends on config read"""
        bm_request_type = CY_VENDOR_REQUEST | EP_IN
        bm_request = 181
        w_value = 0
        w_index = 0
        w_length = 512

        ret = self.dev.controlRead(bm_request_type, bm_request,
                                   w_value, w_index, w_length, self.timeout)
        return ret

    def write_config(self, config: configuration_block.ConfigurationBlock):
        """Send whatever USCU sends on config write"""
        bm_request_type = CY_VENDOR_REQUEST | EP_OUT
        bm_request = 182
        w_value = 0
        w_index = 0

        w_buffer = config.bytes

        ret = self.dev.controlWrite(bm_request_type, bm_request,
                                    w_value, w_index, w_buffer, self.timeout)
        return ret

######################################################################
