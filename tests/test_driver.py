import logging
import pathlib
import random

import pytest
import usb1

import cy_serial_bridge

"""
Test suite for the CY7C652xx driver.
This test suite _requires access to hardware_ and MUST BE run on a machine
with a matching device plugged into it.  Additionally, at certain points in the test, jumper
changes are required, so you will be prompted to make changes
"""

PROJECT_ROOT_DIR = pathlib.Path(__file__).parent.parent

# Eval kit has a 24LC128 EEPROM with A[2..0] = 001
EEPROM_I2C_ADDRESS = 0x51
EEPROM_PAGE_SIZE = 64


@pytest.fixture()
def serial_bridge() -> usb1.USBDevice:
    """
    Fixture which finds a serial bridge USB device
    """
    found = list(cy_serial_bridge.driver.find_device())
    assert len(found) >= 1
    return found[0]


def test_cfg_block_generation():
    """
    Test that we can get and set each property of a configuration block
    """
    config_block = cy_serial_bridge.ConfigurationBlock(
        PROJECT_ROOT_DIR / "example_config_blocks" / "mbed_ce_cy7c65211_spi.bin"
    )

    # Regression test: make sure that all the attributes of a known config block decode as expected
    assert config_block.config_format_version == (1, 0, 3)
    assert config_block.device_type == cy_serial_bridge.CyType.SPI
    assert config_block.vid == 0x04B4
    assert config_block.pid == 0x0004
    assert config_block.mfgr_string == "Cypress Semiconductor"
    assert config_block.product_string == "Mbed CE CY7C65211"
    assert config_block.serial_number == "14224672048496620243684302669570"
    assert not config_block.capsense_on

    # Make sure that we can modify the attributes which support being changed
    config_block.device_type = cy_serial_bridge.CyType.UART
    assert config_block.device_type == cy_serial_bridge.CyType.UART

    config_block.vid = 0x1234
    config_block.pid = 0x5678
    assert config_block.vid == 0x1234
    assert config_block.pid == 0x5678

    config_block.mfgr_string = "Rockwell Automation"
    config_block.product_string = "Turbo Encabulator"
    config_block.serial_number = "1337"

    assert config_block.mfgr_string == "Rockwell Automation"
    assert config_block.product_string == "Turbo Encabulator"
    assert config_block.serial_number == "1337"

    # Also verify that strings can be changed to None and this works
    config_block.mfgr_string = None
    config_block.product_string = None
    config_block.serial_number = None

    assert config_block.mfgr_string is None
    assert config_block.product_string is None
    assert config_block.serial_number is None


def test_user_flash(serial_bridge: usb1.USBDevice):
    """
    Test ability to use the user flash programming functionality of the device
    """
    # Enable more detailed logs during the tests
    logging.basicConfig(level=logging.INFO)
    cy_serial_bridge.utils.log.setLevel(logging.INFO)

    # Note: the mode that we open the device in doesn't really matter, it can be anything
    # for this test
    with cy_serial_bridge.driver.CyMfgrIface(serial_bridge) as dev:
        # Create a random 8-digit number which will be used in the test.
        # This ensures the flash is actually getting programmed and we aren't just reusing old data.
        random_number = random.randint(0, 10**8 - 1)

        # Page 1 wil be programmed in the first operation
        page_1_message = f"Hello from page 1! Number is {random_number:08}"
        page_1_bytes = page_1_message.encode("utf-8") + b"a" * (
            cy_serial_bridge.USER_FLASH_PAGE_SIZE - len(page_1_message)
        )

        # Pages 2-4 will be programmed in the second operation
        page_3_message = f"Hello from page 3! Number is {random_number:08}"
        page_3_bytes = page_3_message.encode("utf-8") + b"c" * (
            cy_serial_bridge.USER_FLASH_PAGE_SIZE - len(page_3_message)
        )
        remaining_pages_bytes = (
            b"b" * cy_serial_bridge.USER_FLASH_PAGE_SIZE + page_3_bytes + b"d" * cy_serial_bridge.USER_FLASH_PAGE_SIZE
        )

        print("Programming page 1: " + repr(page_1_bytes))
        dev.program_user_flash(0, page_1_bytes)

        print("Programming pages 2-4: " + repr(remaining_pages_bytes))
        dev.program_user_flash(cy_serial_bridge.USER_FLASH_PAGE_SIZE, remaining_pages_bytes)

        # First read the entire memory contents and check that it's as expected
        entire_mem = dev.read_user_flash(0, cy_serial_bridge.USER_FLASH_SIZE)
        print("Read entire memory space: " + repr(entire_mem))
        assert entire_mem == (page_1_bytes + remaining_pages_bytes)

        # Also test a 1 page read
        page_3_mem = dev.read_user_flash(
            2 * cy_serial_bridge.USER_FLASH_PAGE_SIZE, cy_serial_bridge.USER_FLASH_PAGE_SIZE
        )
        print("Read page 3 only: " + repr(page_3_mem))
        assert page_3_mem == page_3_bytes


# def test_i2c_config_set_get(serial_bridge: usb1.USBDevice):
#     """
#     Test that we can get and set the I2C controller mode config for the USB device
#     """
#
#     print("Please connect jumpers on the eval kit:")
#     print("J17 = 2-3")
#     print("J20 = 2-3")
#     input("Press [ENTER] when done...")
#
#     with cy_serial_bridge.driver.CyI2CControllerBridge(serial_bridge) as dev:
#         print("Setting speed to 400kHz...")
#         max_speed_config = cy_serial_bridge.driver.CyI2CConfig(400000)
#         dev.set_i2c_configuration(max_speed_config)
#
#         curr_config = dev.read_i2c_configuration()
#         print("Read back: " + str(curr_config))
#         assert curr_config == max_speed_config
#
#         print("Setting speed to 50kHz...")
#         low_speed_config = cy_serial_bridge.driver.CyI2CConfig(50000)
#         dev.set_i2c_configuration(low_speed_config)
#
#         curr_config = dev.read_i2c_configuration()
#         print("Read back: " + str(curr_config))
#         assert curr_config == low_speed_config

#
# def test_i2c_read_write(serial_bridge: usb1.USBDevice):
#     """
#     Test sending I2C read and write transactions
#     """
#     with cy_serial_bridge.driver.CyI2CControllerBridge(serial_bridge) as dev:
#         dev.set_i2c_configuration(cy_serial_bridge.driver.CyI2CConfig(400000))
#
#         # Basic read/write operations
#         # ---------------------------------------------------------------------------
#
#         # Try a 1 byte read from the EEPROM address to make sure it ACKs
#         dev.i2c_read(EEPROM_I2C_ADDRESS, 1)
#
#         # Try a 1 byte read from an incorrect address to make sure it does not ACK
#         with pytest.raises(cy_serial_bridge.I2CNACKError) as raises:
#             dev.i2c_read(EEPROM_I2C_ADDRESS + 0x10, 1)
#         assert raises.value.bytes_written == 0
#
#         # Try a short write to the EEPROM address to make sure it ACKs
#         dev.i2c_write(EEPROM_I2C_ADDRESS, b"\x00\x00")
#
#         # Try an addr-only write to an incorrect address to make sure it does not ACK
#         with pytest.raises(cy_serial_bridge.I2CNACKError) as raises:
#             dev.i2c_write(EEPROM_I2C_ADDRESS + 0x10, b"\x00\x00")
#
#         # TODO this seems to be not working
#         # assert raises.value.bytes_written == 0
#
#         # Write something to the EEPROM and then read it back
#         # ---------------------------------------------------------------------------
#
#         # Create a random 8-digit number which will be used in the test.
#         # This ensures the flash is actually getting programmed and we aren't just reusing old data.
#         random_number = random.randint(0, 10**8 - 1)
#         eeprom_message = f"Hello from EEPROM! Number is {random_number:08}".encode()
#         assert len(eeprom_message) <= EEPROM_PAGE_SIZE
#
#         eeprom_address = 0x0100  # Must be 64 byte aligned
#
#         write_command = bytes([(eeprom_address >> 8) & 0xFF, eeprom_address & 0xFF, *eeprom_message])
#         print("Writing: " + repr(write_command))
#         dev.i2c_write(EEPROM_I2C_ADDRESS, write_command)
#
#         time.sleep(0.01)  # EEPROM needs at least 5ms page program time before it can respond again
#
#         # Reset address pointer
#         dev.i2c_write(EEPROM_I2C_ADDRESS, bytes([(eeprom_address >> 8) & 0xFF, eeprom_address & 0xFF]))
#
#         # Read data back
#         read_data = dev.i2c_read(EEPROM_I2C_ADDRESS, len(eeprom_message))
#
#         print("Got back: " + repr(read_data))
#
#         assert read_data == eeprom_message


def test_spi_config_read_write(serial_bridge: usb1.USBDevice):
    """
    Test that we can read and write SPI configs from the device
    """
    print("Please connect jumpers on the eval kit:")
    print("J17 = 2-5")
    print("J19 = 2-3")
    print("J21 = 2-3")
    print("J20 = 2-5")
    input("Press [ENTER] when done...")

    with cy_serial_bridge.CySPIControllerBridge(serial_bridge) as dev:
        config_1 = cy_serial_bridge.CySPIConfig(
            frequency=20000,
            word_size=16,
            mode=cy_serial_bridge.CySpiMode.NATIONAL_MICROWIRE,
            msbit_first=False,
            continuous_ssel=False,
            ti_select_precede=True,
        )
        print("Setting SPI configuration: " + repr(config_1))
        dev.set_spi_configuration(config_1)

        read_config_1 = dev.read_spi_configuration()
        print("Got back SPI configuration: " + repr(read_config_1))
        assert read_config_1 == config_1

        config_2 = cy_serial_bridge.CySPIConfig(
            frequency=1000000,
            word_size=8,
            mode=cy_serial_bridge.CySpiMode.MOTOROLA_MODE_1,
            msbit_first=True,
            continuous_ssel=True,
            ti_select_precede=False,
        )
        print("Setting SPI configuration: " + repr(config_2))
        dev.set_spi_configuration(config_2)

        read_config_2 = dev.read_spi_configuration()
        print("Got back SPI configuration: " + repr(read_config_2))
        assert read_config_2 == config_2
