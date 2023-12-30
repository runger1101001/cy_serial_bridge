import logging

import cy_serial_bridge

"""
Test suite for the CY7C652xx driver.
This test suite _requires access to hardware_ and MUST BE run on a machine
with a matching device plugged into it.  Additionally, at certain points in the test, jumper
changes are required, so you will be prompted to make changes
"""


# VID and PID of the device to search for
VID = 0x04b4
PID = 0x0004


def test_i2c_config_set_get():

    # Enable more detailed logs during the tests
    logging.basicConfig(level=logging.INFO)
    cy_serial_bridge.utils.log.setLevel(logging.INFO)

    found = list(cy_serial_bridge.find_device(VID, PID))
    assert len(found) >= 1

    with cy_serial_bridge.driver.CyI2CControllerBridge(found[0]) as dev:

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

