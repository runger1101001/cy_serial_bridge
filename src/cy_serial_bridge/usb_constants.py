import struct
from enum import IntEnum

"""
Various constants use for communicating with the bridge device over USB.
Most of these are taken from the open-source libusb driver, others are reverse-
engineered.
"""

EP_BULK = 2
EP_INTR = 3

EP_OUT = 0x00
EP_IN = 0x80

CY_VENDOR_REQUEST = 0x40
CY_VENDOR_REQUEST_DEVICE_TO_HOST = CY_VENDOR_REQUEST | EP_IN
CY_VENDOR_REQUEST_HOST_TO_DEVICE = CY_VENDOR_REQUEST | EP_OUT
CY_CLASS_INTERFACE_REQUEST = 0x21

# used to set which SCB to configure
CY_SCB_INDEX_POS = 15

# Flash constants.  From the comments in CyProgUserFlash
USER_FLASH_PAGE_SIZE = 128
USER_FLASH_SIZE = 512


class CyClass(IntEnum):
    DISABLED = 0x00  # None or the interface is disabled
    CDC = 0x02  # CDC ACM class
    PHDC = 0x0F  # PHDC class
    VENDOR = 0xFF  #


class CyType(IntEnum):
    """
    Enumeration of possible device types and their integer codes.

    From CyUSBSerial.h.
    This code is used in the configuration descriptor and also is returned as the interface settings subclass
    (USBInterfaceSetting.getSubClass()) when enumerating devices.
    """

    DISABLED = 0
    UART = 1
    SPI = 2
    I2C = 3
    JTAG = 4
    MFG = 5  # Manufacturing interface.  This is used to configure settings of the device.


class CyVendorCmds(IntEnum):
    CY_GET_VERSION_CMD = 0xB0
    CY_GET_SIGNATURE_CMD = 0xBD

    CY_UART_GET_CONFIG_CMD = 0xC0
    CY_UART_SET_CONFIG_CMD = 0xC1
    CY_SPI_GET_CONFIG_CMD = 0xC2
    CY_SPI_SET_CONFIG_CMD = 0xC3
    CY_I2C_GET_CONFIG_CMD = 0xC4
    CY_I2C_SET_CONFIG_CMD = 0xC5

    CY_I2C_WRITE_CMD = 0xC6
    CY_I2C_READ_CMD = 0xC7
    CY_I2C_GET_STATUS_CMD = 0xC8
    CY_I2C_RESET_CMD = 0xC9

    CY_SPI_READ_WRITE_CMD = 0xCA
    CY_SPI_RESET_CMD = 0xCB
    CY_SPI_GET_STATUS_CMD = 0xCC

    CY_JTAG_ENABLE_CMD = 0xD0
    CY_JTAG_DISABLE_CMD = 0xD1
    CY_JTAG_READ_CMD = 0xD2
    CY_JTAG_WRITE_CMD = 0xD3

    CY_GPIO_GET_CONFIG_CMD = 0xD8
    CY_GPIO_SET_CONFIG_CMD = 0xD9
    CY_GPIO_GET_VALUE_CMD = 0xDA
    CY_GPIO_SET_VALUE_CMD = 0xDB

    CY_PROG_USER_FLASH_CMD = 0xE0
    CY_READ_USER_FLASH_CMD = 0xE1

    CY_DEVICE_RESET_CMD = 0xE3


# I2C related macros
class CyI2c(IntEnum):
    CONFIG_LENGTH = 16
    WRITE_COMMAND_POS = 3
    WRITE_COMMAND_LEN_POS = 4
    GET_STATUS_LEN = 3
    MODE_WRITE = 1
    MODE_READ = 0
    ERROR_BIT = 1
    ARBITRATION_ERROR_BIT = 1 << 1
    NAK_ERROR_BIT = 1 << 2
    BUS_ERROR_BIT = 1 << 3
    STOP_BIT_ERROR = 1 << 4
    BUS_BUSY_ERROR = 1 << 5
    ENABLE_PRECISE_TIMING = 1
    EVENT_NOTIFICATION_LEN = 3
    SCB_INDEX_POS = 15


# SPI related Macros
class CySpi(IntEnum):
    CONFIG_LEN = 16
    EVENT_NOTIFICATION_LEN = 2
    READ_BIT = 1
    WRITE_BIT = 1 << 1
    SCB_INDEX_BIT = 1 << 15
    GET_STATUS_LEN = 4
    UNDERFLOW_ERROR = 1
    BUS_ERROR = 1 << 1


# Vendor UART related macros
class CyUart(IntEnum):
    SET_LINE_CONTROL_STATE_CMD = 0x22
    SET_FLOW_CONTROL_CMD = 0x60
    SEND_BREAK_CMD = 0x23
    CONFIG_LEN = 16
    EVENT_NOTIFICATION_LEN = 10

    SERIAL_STATE_CARRIER_DETECT = 1
    SERIAL_STATE_TRANSMISSION_CARRIER = 1 << 1
    SERIAL_STATE_BREAK_DETECTION = 1 << 2
    SERIAL_STATE_RING_SIGNAL_DETECTION = 1 << 3
    SERIAL_STATE_FRAMING_ERROR = 1 << 4
    SERIAL_STATE_PARITY_ERROR = 1 << 5
    SERIAL_STATUE_OVERRUN = 1 << 6


# Bootloader related macros
CY_BOOT_CONFIG_SIZE = 64
CY_DEVICE_CONFIG_SIZE = 512
CY_CONFIG_STRING_MAX_LEN_BYTES = 64
CY_FIRMWARE_BREAKUP_SIZE = 4096
CY_GET_SILICON_ID_LEN = 4
CY_GET_FIRMWARE_VERSION_LEN = 8
CY_GET_SIGNATURE_LEN = 4


# PHDC related macros
class CyPhdc(IntEnum):
    SET_FEATURE = 0x03
    CLR_FEATURE = 0x01
    GET_DATA_STATUS = 0x00


# JTAG related Macros
CY_JTAG_OUT_EP = 0x04
CY_JTAG_IN_EP = 0x85

# GPIO related Macros
CY_GPIO_GET_LEN = 2
CY_GPIO_SET_LEN = 1

# PHDC related macros
CY_PHDC_GET_STATUS_LEN = 2
CY_PHDC_CLR_FEATURE_WVALUE = 0x1
CY_PHDC_SET_FEATURE_WVALUE = 0x0101

# Struct packings

# C structure layout:
# typedef struct
# {
#     UINT32 frequency;           /* Frequency of operation. Only valid values are
#                                    100KHz and 400KHz. */ <--this comment seems to be wrong
#     UINT8 sAddress;             /* Slave address to be used when in slave mode. */
#     bool isMsbFirst;            /* Whether to transmit most significant bit first. */
#     bool isMaster;              /* Whether to block is to be configured as a master:
#                                    CyTrue - The block functions as I2C master;
#                                    CyFalse - The block functions as I2C slave. */
#     bool sIgnore;               /* Ignore general call in slave mode. */
#     bool clockStretch;          /* Whether to stretch clock in case of no FIFO availability. */
#     bool isLoopback;            /* Whether to loop back TX data to RX. Valid only
#                                    for debug purposes. */
#     UCHAR reserved[6];          /*Reserved for future use*/
# } CyUsI2cConfig_t;
CY_USB_I2C_CONFIG_STRUCT_LAYOUT = "<I6B6x"
assert struct.calcsize(CY_USB_I2C_CONFIG_STRUCT_LAYOUT) == CyI2c.CONFIG_LENGTH
