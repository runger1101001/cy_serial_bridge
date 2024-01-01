import logging
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

# VID and PID of the device to search for
VID = 0x04B4
PID = 0x0004

# Eval kit has a 24LC128 EEPROM with A[2..0] = 001
EEPROM_I2C_ADDRESS = 0x51


@pytest.fixture()
def serial_bridge() -> usb1.USBDevice:
    """
    Fixture which finds a serial bridge USB device
    """
    found = list(cy_serial_bridge.driver.find_device(VID, PID))
    assert len(found) >= 1
    return found[0]


def test_i2c_config_set_get(serial_bridge: usb1.USBDevice):
    """
    Test that we can get and set the I2C controller mode config for the USB device
    """
    # Enable more detailed logs during the tests
    logging.basicConfig(level=logging.INFO)
    cy_serial_bridge.utils.log.setLevel(logging.INFO)

    with cy_serial_bridge.driver.CyI2CControllerBridge(serial_bridge) as dev:
        print("Setting speed to 400kHz...")
        max_speed_config = cy_serial_bridge.driver.CyI2CConfig(400000)
        dev.set_i2c_configuration(max_speed_config)

        curr_config = dev.read_i2c_configuration()
        print("Read back: " + str(curr_config))
        assert curr_config == max_speed_config

        print("Setting speed to 50kHz...")
        low_speed_config = cy_serial_bridge.driver.CyI2CConfig(50000)
        dev.set_i2c_configuration(low_speed_config)

        curr_config = dev.read_i2c_configuration()
        print("Read back: " + str(curr_config))
        assert curr_config == low_speed_config


def test_user_flash(serial_bridge: usb1.USBDevice):
    """
    Test ability to use the user flash programming functionality of the device
    """
    # Note: the mode that we open the device in doesn't really matter, it can be anything
    # for this test
    with cy_serial_bridge.driver.CyI2CControllerBridge(serial_bridge) as dev:
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


def test_i2c_read_write(serial_bridge: usb1.USBDevice):
    """
    Test sending I2C read and write transactions
    """
    with cy_serial_bridge.driver.CyI2CControllerBridge(serial_bridge) as dev:
        dev.set_i2c_configuration(cy_serial_bridge.driver.CyI2CConfig(400000))

        # Try a 1 byte read from the EEPROM address to make sure it ACKs
        dev.i2c_read(0x51, 1)

        # Try a 1 byte read from an incorrect address to make sure it does not ACK
        with pytest.raises(cy_serial_bridge.I2CNACKError):
            dev.i2c_read(EEPROM_I2C_ADDRESS + 0x10, 1)
