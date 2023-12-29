#!/usr/bin/env python3
# -*- coding: utf-8-unix -*-
"""
A port of Cypress USB Serial Library (libcyusbserial) in pure python.

This code is still in alpha stage. Many protocols and data format
details are discovered, but information still needs to be cleaned
out and API/code/tools need further refactoring.

"""
import collections.abc
import struct
import sys
import os
import usb1 # from "libusb1" package
import logging

from struct import pack, unpack
from usb1 import USBContext, USBInterfaceSetting
from enum import Enum, IntEnum

from typing import Iterator, Tuple

from . import configuration_block
from .utils import ByteSequence, log
from .usb_constants import *

from .configuration_block import CY_TYPE

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
    if us.getClass() == CY_CLASS.VENDOR:
        return CY_TYPE(us.getSubClass())
    return CY_TYPE.DISABLED

def find_type(ud: usb1.USBDevice, cy_type):
    """Finds USB interface by CY_TYPE. Yields list of (us, ui, uc, ud) set"""
    def check_match(ux):
        return isinstance(ux, USBInterfaceSetting) and get_type(ux) == cy_type
    yield from find_path(ud, check_match)

class CyUSB(object):

    ######################################################################
    # WARNING: Many APIs are not yet complete and/or tested.
    ######################################################################

    def CyGetSpiConfig(self):
        scbIndex = 1 if self.if_num > 0 else 0
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_VENDOR_CMDS.CY_SPI_GET_CONFIG_CMD
        wValue = (scbIndex << CY_SCB_INDEX_POS)
        wIndex = 0
        wLength = CY_SPI.CONFIG_LEN

        ret = self.dev.controlRead(bmRequestType, bmRequest,
                                   wValue, wIndex, wLength, self.timeout)
        return ret

    def CySetSpiConfig(self, config):
        scbIndex = 1 if self.if_num > 0 else 0
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_VENDOR_CMDS.CY_SPI_SET_CONFIG_CMD
        wValue = (scbIndex << CY_SCB_INDEX_POS)
        wIndex = 0
        wLength = CY_SPI.CONFIG_LEN
        wBuffer = bytearray()

        ret = self.dev.controlWrite(bmRequestType, bmRequest,
                                    wValue, wIndex, wBuffer, self.timeout)
        return ret

    def CySpiReset(self):
        scbIndex = 1 if self.if_num > 0 else 0
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_VENDOR_CMDS.CY_SPI_RESET_CMD
        wValue = (scbIndex << CY_SCB_INDEX_POS)
        wIndex = 0
        wLength = 0

        ret = self.dev.controlRead(bmRequestType, bmRequest,
                                   wValue, wIndex, wLength, self.timeout)
        return ret

    def CySpiRead(self, size):
        return self.dev.bulkRead(self.ep_in, size, timeout=self.timeout)

    def CySpiWrite(self, buff):
        return self.dev.bulkWrite(self.ep_out, buff, timeout=self.timeout)

    def CyGetSpiStatus(self):
        scbIndex = 1 if self.if_num > 0 else 0
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_VENDOR_CMDS.CY_SPI_GET_STATUS_CMD
        wValue = ((scbIndex << CY_SCB_INDEX_POS))
        wIndex = 0
        wLength = CY_SPI.GET_STATUS_LEN

        ret = self.dev.controlRead(bmRequestType, bmRequest,
                                   wValue, wIndex, wLength, self.timeout)
        return ret

    def CySpiReadWrite(self, wrbuff, rdsize):
        spiTransferMode = 0
        wIndex = 0
        if len(wrbuff) > 0:
            spiTransferMode |= CY_SPI.WRITE_BIT
            wIndex = len(wrbuff)
        if rdsize > 0:
            spiTransferMode |= CY_SPI.READ_BIT
            wIndex = rdsize

        scbIndex = 1 if self.if_num > 0 else 0
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_VENDOR_CMDS.CY_SPI_READ_WRITE_CMD
        wValue = (scbIndex << CY_SCB_INDEX_POS) | spiTransferMode
        wBuffer = bytearray(0)

        ret = self.dev.controlWrite(bmRequestType, bmRequest,
                                    wValue, wIndex, wBuffer, self.timeout)

        if not spiTransferMode & CY_SPI.READ_BIT:
            return self.CySpiWrite(wrbuff)

        if not spiTransferMode & CY_SPI.WRITE_BIT:
            return self.CySpiRead(rdsize)

        # FIXME: Not sure what Cypress is doing in read-write case

        return ret

    def CyGetI2cConfig(self):
        scbIndex = 1 if self.if_num > 0 else 0
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_VENDOR_CMDS.CY_I2C_GET_CONFIG_CMD
        wValue = ((scbIndex << CY_SCB_INDEX_POS))
        wIndex = 0
        wLength = CY_I2C.CONFIG_LENGTH

        ret = self.dev.controlRead(bmRequestType, bmRequest,
                                   wValue, wIndex, wLength, self.timeout)
        return ret

    def CySetI2cConfig(self, config):
        scbIndex = 1 if self.if_num > 0 else 0
        bmRequestType = CY_VENDOR_REQUEST | EP_IN
        bmRequest = CY_VENDOR_CMDS.CY_I2C_SET_CONFIG_CMD
        wValue = ((scbIndex << CY_SCB_INDEX_POS))
        wIndex = 0
        wLength = CY_I2C.CONFIG_LENGTH

        ret = self.dev.controlRead(bmRequestType, bmRequest,
                                   wValue, wIndex, wLength, self.timeout)
        return ret

    def CyI2cRead(self, config, size):
        scbIndex = 1 if self.if_num > 0 else 0
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_VENDOR_CMDS.CY_I2C_READ_CMD
        wValue = ((scbIndex << 7) | (0x7F & config.slaveAddress)) << 8
        wValue |= config.isStopBit | (config.isNakBtit << 1)
        wIndex = size
        wBuffer = bytearray(0)

        ret = self.dev.controlWrite(bmRequestType, bmRequest,
                                    wValue, wIndex, wBuffer, self.timeout)

        ret = self.dev.bulkRead(self.ep_in, size, timeout=self.timeout)

        return ret

    def CyI2cWrite(self, buff):
        scbIndex = 1 if self.if_num > 0 else 0
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_VENDOR_CMDS.CY_I2C_WRITE_CMD
        wValue = ((scbIndex << 7) | (0x7F & config.slaveAddress)) << 8
        wValue |= config.isStopBit
        wIndex = len(buff)
        wBuffer = bytearray(0)

        ret = self.dev.controlWrite(bmRequestType, bmRequest,
                                    wValue, wIndex, wBuffer, self.timeout)

        ret = self.dev.bulkWrite(self.ep_out, buff, timeout=self.timeout)
        return ret

    def CyI2cGetStatus(self, mode=0):
        dev = self.dev

        scbIndex = 1 if self.if_num > 0 else 0
        bmRequestType = CY_VENDOR_REQUEST | EP_IN
        bmRequest = CY_VENDOR_CMDS.CY_I2C_GET_STATUS_CMD
        wValue = (scbIndex << CY_SCB_INDEX_POS) | mode
        wIndex = 0
        wLength = CY_I2C.GET_STATUS_LEN

        ret = dev.controlRead(bmRequestType, bmRequest,
                              wValue, wIndex, wLength, self.timeout)
        return ret

    def CyI2cReset(self, mode=0):
        dev = self.dev

        scbIndex = 1 if self.if_num > 0 else 0
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_VENDOR_CMDS.CY_I2C_RESET_CMD
        wValue = (scbIndex << CY_SCB_INDEX_POS) | mode
        wIndex = 0
        wBuffer = bytearray(0)

        ret = dev.controlWrite(bmRequestType, bmRequest,
                               wValue, wIndex, wBuffer, self.timeout)
        return ret

    def CyGetUartConfig(self):
        scbIndex = 1 if self.if_num > 0 else 0
        bmRequestType = CY_VENDOR_REQUEST | EP_IN
        bmRequest = CY_VENDOR_CMDS.CY_UART_GET_CONFIG_CMD
        wValue = (scbIndex << CY_SCB_INDEX_POS)
        wIndex = 0
        wLength = CY_UART.CONFIG_LEN

        ret = self.dev.controlRead(bmRequestType, bmRequest,
                                   wValue, wIndex, wLength, self.timeout)
        return ret

    def CySetUartConfig(self):
        dev = self.dev

        scbIndex = 1 if self.if_num > 0 else 0
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_VENDOR_CMDS.CY_UART_SET_CONFIG_CMD
        wValue = (scbIndex << CY_SCB_INDEX_POS)
        wIndex = 0
        wBuffer = bytearray(CY_UART.CONFIG_LEN)

        ret = dev.controlWrite(bmRequestType, bmRequest,
                               wValue, wIndex, wBuffer, self.timeout)
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

        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_VENDOR_CMDS.CY_UART_SET_FLOW_CONTROL_CMD
        wValue = mode
        wIndex = self.if_num
        wBuffer = bytearray(0)

        ret = self.dev.controlWrite(bmRequestType, bmRequest,
                                    wValue, wIndex, wBuffer, self.timeout)
        return ret

    def CyUartGetHwFlowControl(self):
        return self.uart_flowcontrol_mode

    def CyUartSetBreak(self, ms):
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_VENDOR_CMDS.CY_UART_SEND_BREAK_CMD
        wValue = ms
        wIndex = self.if_num
        wBuffer = bytearray(0)

        ret = self.dev.controlWrite(bmRequestType, bmRequest,
                                    wValue, wIndex, wBuffer, self.timeout)
        return ret

    def CyUartSetRts(self):
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_UART.SET_LINE_CONTROL_STATE_CMD
        wValue = (1<<1) | self.dtrValue
        wIndex = self.if_num
        wBuffer = bytearray(0)

        ret = self.dev.controlWrite(bmRequestType, bmRequest,
                                    wValue, wIndex, wBuffer, self.timeout)
        self.rtsValue = 1
        return ret

    def CyUartClearRts(self):
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_UART.SET_LINE_CONTROL_STATE_CMD
        wValue = self.dtrValue
        wIndex = self.if_num
        wBuffer = bytearray(0)

        ret = self.dev.controlWrite(bmRequestType, bmRequest,
                                    wValue, wIndex, wBuffer, self.timeout)
        self.rtsValue = 0
        return ret

    def CyUartSetDtr(self):
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_UART.SET_LINE_CONTROL_STATE_CMD
        wValue = (self.rtsValue << 1) | 1
        wIndex = self.if_num
        wBuffer = bytearray(0)

        ret = self.dev.controlWrite(bmRequestType, bmRequest,
                                    wValue, wIndex, wBuffer, self.timeout)
        self.dtrValue = 1
        return ret

    def CyUartClearDtr(self):
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_UART.SET_LINE_CONTROL_STATE_CMD
        wValue = (self.rtsValue << 1)
        wIndex = self.if_num
        wBuffer = bytearray(0)

        ret = self.dev.controlWrite(bmRequestType, bmRequest,
                                    wValue, wIndex, wBuffer, self.timeout)
        self.dtrValue = 0
        return ret

    def CySetGpioValue(self, gpio, value):
        bmRequestType = CY_VENDOR_REQUEST | EP_IN
        bmRequest = CY_VENDOR_CMDS.CY_GPIO_SET_VALUE_CMD
        wValue = gpio
        wIndex = value
        wLength = 0

        ret = self.dev.controlRead(bmRequestType, bmRequest,
                                   wValue, wIndex, wLength, self.timeout)
        return ret

    def CyGetGpioValue(self, gpio):
        bmRequestType = CY_VENDOR_REQUEST | EP_IN
        bmRequest = CY_VENDOR_CMDS.CY_GPIO_GET_VALUE_CMD
        wValue = gpio
        wIndex = 0
        wLength = CY_GPIO_GET_LEN

        ret = self.dev.controlRead(bmRequestType, bmRequest,
                                   wValue, wIndex, wLength, self.timeout)
        return ret

    def CyProgUserFlash(self, addr, buff):
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = CY_VENDOR_CMDS.CY_PROG_USER_FLASH_CMD
        wValue = 0
        wIndex = addr
        wBuffer = buff

        ret = self.dev.controlWrite(bmRequestType, bmRequest,
                                    wValue, wIndex, wBuffer, self.timeout)
        return ret

    def CyReadUserFlash(self, addr, size):
        bmRequestType = CY_VENDOR_REQUEST | EP_IN
        bmRequest = CY_VENDOR_CMDS.CY_READ_USER_FLASH_CMD
        wValue = 0
        wIndex = addr
        wLength = size

        ret = self.dev.controlRead(bmRequestType, bmRequest,
                                   wValue, wIndex, wLength, self.timeout)
        return ret

    ######################################################################
    # Non-Cypress APIs still under experimental stage
    ######################################################################

    def ping(self):
        """Send whatever USCU sends on startup"""
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = 203
        wValue = 0
        wIndex = 0
        wBuffer = bytearray(0)

        ret = self.dev.controlWrite(bmRequestType, bmRequest,
                                    wValue, wIndex, wBuffer, self.timeout)
        return ret

    def probe0(self):
        """Send whatever USCU sends on startup - some signature?"""
        bmRequestType = CY_VENDOR_REQUEST | EP_IN
        bmRequest = 177
        wValue = 0
        wIndex = 0
        wLength = 4

        ret = self.dev.controlRead(bmRequestType, bmRequest,
                                   wValue, wIndex, wLength, self.timeout)
        return ret

    def probe1(self):
        """Send whatever USCU sends on startup - firmware version?"""
        bmRequestType = CY_VENDOR_REQUEST | EP_IN
        bmRequest = 176
        wValue = 0
        wIndex = 0
        wLength = 8

        ret = self.dev.controlRead(bmRequestType, bmRequest,
                                   wValue, wIndex, wLength, self.timeout)
        return ret

    def connect(self):
        """Send whatever USCU sends on connect"""
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = 226
        wValue = 0xa6bc
        wIndex = 0xb1b0
        wBuffer = bytearray(0)

        ret = self.dev.controlWrite(bmRequestType, bmRequest,
                                    wValue, wIndex, wBuffer, self.timeout)
        return ret

    def disconnect(self):
        """Send whatever USCU sends on disconnect"""
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = 226
        wValue = 0xa6bc
        wIndex = 0xb9b0
        wBuffer = bytearray(0)

        ret = self.dev.controlWrite(bmRequestType, bmRequest,
                                    wValue, wIndex, wBuffer, self.timeout)
        return ret

    def read_config(self) -> ByteSequence:
        """Send whatever USCU sends on config read"""
        bmRequestType = CY_VENDOR_REQUEST | EP_IN
        bmRequest = 181
        wValue = 0
        wIndex = 0
        wLength = 512

        ret = self.dev.controlRead(bmRequestType, bmRequest,
                                   wValue, wIndex, wLength, self.timeout)
        return ret

    def write_config(self, config: configuration_block.ConfigurationBlock):
        """Send whatever USCU sends on config write"""
        bmRequestType = CY_VENDOR_REQUEST | EP_OUT
        bmRequest = 182
        wValue = 0
        wIndex = 0

        wBuffer = config.bytes

        ret = self.dev.controlWrite(bmRequestType, bmRequest,
                                    wValue, wIndex, wBuffer, self.timeout)
        return ret

######################################################################