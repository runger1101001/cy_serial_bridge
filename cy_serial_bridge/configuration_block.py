import pathlib
from typing import Union, Optional
import struct
from enum import IntEnum
import re
from cy_serial_bridge.utils import ByteSequence
from cy_serial_bridge.usb_constants import CY_TYPE

CONFIG_BLOCK_EXPECTED_MAGIC = b"CYUS"
CONFIG_BLOCK_EXPECTED_VERSION = 0x30001


class ConfigurationBlock:

    """
    Module which implements basic reading/writing of CY7C652xx memory configuration blocks.

    These blocks are written to the chip using the reverse engineered API in order to configure the interface
    mode (UART/I2C/SPI) and set other settings such as GPIOs.  Nominally, only the Cypress USB-Serial Configuration
    Utility know how to create this data, and this program is only available as a Windows GUI application.

    This class is based on the reverse-engineered description of the format located here: https://github.com/tai/cyusb-hack/blob/master/config.txt
    """

    def __init__(self, block_file: Optional[Union[pathlib.Path, str]] = None, block_bytes: Optional[ByteSequence] = None):
        """
        Create a configuration_block from a file or byte array.  Must pass either a file path OR a bytes object.
        :param block_file:
        :param block_bytes:
        """

        if (block_bytes is None and block_file is None) or (block_bytes is not None and block_file is not None):
            raise ValueError("Invalid usage!")

        if block_file is not None:
            # Load bytes from file.
            self._cfg_bytes = bytearray(pathlib.Path(block_file).read_bytes())
        elif block_bytes is not None:
            self._cfg_bytes = bytearray(block_bytes)

        if len(self._cfg_bytes) < 512:
            raise ValueError("Configuration block data is not long enough (should be 512 bytes)")

        # Some dumps contain extra bytes so trim to 512 bytes.
        self._cfg_bytes = self._cfg_bytes[:513]

        # Check magic, format, and checksum
        if self._cfg_bytes[0:4] != CONFIG_BLOCK_EXPECTED_MAGIC:
            raise ValueError("Incorrect magic at start of configuration block")
        cfg_version = struct.unpack("<I", self._cfg_bytes[4:8])[0]
        if cfg_version != CONFIG_BLOCK_EXPECTED_VERSION:
            raise ValueError(f"Only know how to decode config block version 0x{CONFIG_BLOCK_EXPECTED_VERSION:x}, this is 0x{cfg_version:x}")
        if self._get_checksum() != self._calculate_checksum():
            raise ValueError(f"Checksum failed for configuration block.  Expected 0x{self._calculate_checksum():x} but read 0x{self._get_checksum():x} from header")

    def _decode_string_field(self, flag_addr, data_start_addr) -> Optional[str]:
        """
        Decode a variable-length string from the config block.
        :param flag_addr: Address of the flag indicating whether this data is set or not
        :param data_start_addr: Address that the data starts at (this is the address of the length field, 2 bytes before the first character)
        :return: String data, or None if unset
        """
        # The string fields have three parts (turns out to be slightly different than what's described in the
        # original reverse engineering document):
        # - 4 byte flag, set to 0xffffffff if present, 0x00000000 otherwise
        # - length field -- gives 2 longer than the number of bytes in the string (no idea why it's 2 longer)
        # - 64 bytes of data (encoded as UTF-16)
        #
        # Note: There is always a 0x3 byte after the length byte before the data.  No idea what this is for.

        if self._cfg_bytes[flag_addr:flag_addr + 4] == b"\xff\xff\xff\xff":
            byte_count = self._cfg_bytes[data_start_addr] - 2
            chars_start_addr = data_start_addr + 2
            chars_end_addr = chars_start_addr + byte_count

            return self._cfg_bytes[chars_start_addr:chars_end_addr].decode("utf-16-le")
        elif self._cfg_bytes[flag_addr:flag_addr + 4] == b"\x00\x00\x00\x00":
            return None
        else:
            raise ValueError("Unparseable data in descriptor")

    def _encode_string_field(self, flag_addr, data_start_addr, value: Optional[str]):
        """
        Encode a variable-length string from the config block.
        :param flag_addr: Address of the flag indicating whether this data is set or not
        :param data_start_addr: Address that the data starts at (this is the address of the length field, 2 bytes before the first character)
        :param value: String data, or None if unset
        """
        if value is None:
            self._cfg_bytes[flag_addr:flag_addr+4] = b"\x00\x00\x00\x00" # Set present flag to false
            self._cfg_bytes[data_start_addr] = 2 # Set length to 0 chars (can't forget the 2 offset)
            self._cfg_bytes[data_start_addr+2:data_start_addr+66] = 64 * b"\x00" # Zero out data
        else:
            # Write data (padded with 0s)
            encoded_string = value.encode("utf-16-le")
            if len(encoded_string) > 64:
                raise ValueError("String value to long to fit in binary configuration block!")
            self._cfg_bytes[data_start_addr+2:data_start_addr+66] = encoded_string + (64 - len(encoded_string)) * b"\x00"

            self._cfg_bytes[data_start_addr] = len(encoded_string) + 2 # Set length
            self._cfg_bytes[flag_addr:flag_addr+4] = b"\xff\xff\xff\xff" # Set present flag to true

    def _calculate_checksum(self) -> int:
        """Return checksum of 512-byte config bytes"""
        return 0xFFFFFFFF & sum(struct.unpack("<125I", self._cfg_bytes[12:]))

    def _get_checksum(self):
        """Extract checksum value in 512-byte config bytes"""
        return struct.unpack("<I", self._cfg_bytes[8:12])[0]

    @property
    def device_type(self) -> CY_TYPE:
        """
        Type of device that this configuration describes (SPI/I2C/UART/etc)
        """
        return CY_TYPE(self._cfg_bytes[0x1c])

    @device_type.setter
    def device_type(self, value: CY_TYPE):
        self._cfg_bytes[0x1c] = value.value

    @property
    def capsense_on(self) -> bool:
        """
        Whether CapSense touch sensing is enabled in this configuration [note that this utility currently doesn't
        support writing all the fields needed to make capsense work]
        """
        return self._cfg_bytes[0x4c] == 1

    @property
    def vid(self) -> int:
        """
        USB Vendor ID of the device
        """
        return struct.unpack("<H", self._cfg_bytes[0x94:0x96])[0]

    @vid.setter
    def vid(self, value: int):
        self._cfg_bytes[0x94:0x96] = struct.pack("<H", (value))

    @property
    def pid(self) -> int:
        """
        USB Product ID of the device
        """
        return struct.unpack("<H", self._cfg_bytes[0x96:0x98])[0]

    @pid.setter
    def pid(self, value: int):
        self._cfg_bytes[0x96:0x98] = struct.pack("<H", (value))

    @property
    def mfgr_string(self) -> Optional[str]:
        """
        Manufacturer String of the device.  Up to 32 characters (seems to be UTF-16 type encoded in descriptor).
        May be set to None, indicating that the field is unset.
        """
        return self._decode_string_field(0xa0, 0xee)

    @mfgr_string.setter
    def mfgr_string(self, value: Optional[str]):
        self._encode_string_field(0xa0, 0xee, value)

    @property
    def product_string(self) -> Optional[str]:
        """
        Product String of the device.  Up to 32 characters (seems to be UTF-16 type encoded in descriptor).
        May be set to None, indicating that the field is unset.
        """
        return self._decode_string_field(0xa4, 0x130)

    @product_string.setter
    def product_string(self, value: Optional[str]):
        self._encode_string_field(0xa4, 0x130, value)

    @property
    def serial_number(self) -> Optional[str]:
        """
        Serial Number of the device.  Up to 32 characters (seems to be UTF-16 type encoded in descriptor).
        May be set to None, indicating that the field is unset.
        The serial number, according the config utility, may only be set to alphabetic and numeric characters.
        """
        return self._decode_string_field(0xa8, 0x172)

    @serial_number.setter
    def serial_number(self, value: Optional[str]):
        if value is not None and re.fullmatch(r"[0-9a-zA-Z]+", value) is None:
            raise ValueError("Serial number may only be set to alphanumeric characters")

        self._encode_string_field(0xa8, 0x172, value)

    @property
    def bytes(self):
        """
        Get the raw bytes for this buffer.
        Calling this function also updates the checksum to account for any changes made to the bytes since
        the config block was updated.
        """
        self._cfg_bytes[8:12] = struct.pack("<I", self._calculate_checksum())
        return self._cfg_bytes

    def __str__(self) -> str:
        """
        Dump the decodable information from this config block.
        """
        return f"""ConfigurationBlock(
    device_type=CY_TYPE.{self.device_type.name},
    vid=0x{self.vid:04x},
    pid=0x{self.pid:04x},
    mfgr_string=\"{self.mfgr_string}\",
    product_string=\"{self.product_string}\",
    serial_number=\"{self.serial_number}\",
    capsense_on={self.capsense_on},
)"""