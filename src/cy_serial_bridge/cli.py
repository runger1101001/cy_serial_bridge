import logging
import pathlib
import random
import sys
from argparse import ArgumentParser

import cy_serial_bridge
from cy_serial_bridge.utils import log

VID = 0x04b4
PID = 0x0004


def main(opt):
    cmd = opt.args[0]

    if cmd == "decode":
        # Just decode the configuration block, then exit.
        cfg_block = cy_serial_bridge.configuration_block.ConfigurationBlock(*opt.args[1:])
        print(str(cfg_block))
        return

    found = list(cy_serial_bridge.find_device(opt.vid, opt.pid))

    if len(found) - 1 < opt.nth:
        message = "No USB device found"
        raise RuntimeError(message)

    # ux == USB Device/Configuration/Interface/Setting/Endpoint
    ud = found[opt.nth]
    uc = ud[0]
    ui = uc[0]
    us = ui[0]
    ue = us[0]

    log.info("Connecting...")

    with cy_serial_bridge.driver.CyMfgrIface(ud, scb_index=opt.scb) as dev:
        if cmd == "save": do_save(dev, *opt.args[1:])
        if cmd == "load": do_load(dev, *opt.args[1:])
        if cmd == "type": do_change_type(dev, *opt.args[1:])
        if cmd == "randomize_serno": do_randomize_serno(dev)


def to_int(v):
    return int(v, 0)


def format_usage():
    p = pathlib.Path(sys.argv[0]).name
    return """
{p} - Reprogram Cypress USB-to-Serial chip (CY7C65211, etc)
Usage: {p} [options] (save|load|mode) args...
Options:
  -V, --vid vid : VID of device to connect (0x04b4)
  -P, --pid pid : PID of device to connect (0x0004)
  -n, --nth N   : Select Nth device (0)
  -s, --scb N   : Select Nth SCB block (0)
  -v, --verbose : Enable logging
Example:
  $ {p} save save.bin       - Saves configuration block into the given bin file
  $ {p} load save.bin       - Loads configuration block from the given bin file
  $ {p} decode save.bin     - Decode and display basic information from the given bin file
  $ {p} randomize_serno     - Set the serial number of the given device to 32 random integers
  $ {p} type [SPI|I2C|UART] - Set the type of device that the serial bridge acts as.  Used for configurable bridge devices (65211/65215)
""".lstrip().format(**locals())

def usage():
    sys.stderr.write(format_usage())
    sys.exit(0)

def do_save(dev: cy_serial_bridge.CyUSB, file):
    dev.connect()
    buf = dev.read_config()
    dev.disconnect()

    # As a sanity check, parse the bytes to make sure the checksum is valid
    config_block = cy_serial_bridge.configuration_block.ConfigurationBlock(block_bytes=buf)
    log.info("Read the following configuration from the device: %s", str(config_block))

    # Save to file
    pathlib.Path(file).write_bytes(bytes(buf))


def do_load(dev: cy_serial_bridge.CyUSB, file):
    # Load bytes and check checksum
    config_block = cy_serial_bridge.configuration_block.ConfigurationBlock(file)

    log.info("Writing the following configuration to the device: %s", str(config_block))

    dev.connect()

    log.info("Writing configuration...")
    ret = dev.write_config(config_block.config_bytes)
    dev.disconnect()

    log.info("Done!")

    return ret


def do_randomize_serno(dev: cy_serial_bridge.CyUSB):
    dev.connect()

    try:
        buffer = dev.read_config()

        config_block = cy_serial_bridge.configuration_block.ConfigurationBlock(block_bytes=buffer)
        log.info("Read the following configuration from the device: %s", str(config_block))

        # Generate a random integer with 32 digits
        serial_number_max = 10**32 - 1
        random_serial_number = random.randint(0, serial_number_max)
        random_serial_number_str = f"{random_serial_number:032}"

        config_block.serial_number = random_serial_number_str

        log.info("Writing the following configuration to the device: %s", str(config_block))

        log.info("Writing configuration...")
        dev.write_config(config_block)

        dev.disconnect()
        log.info("Done!")

        print(f"Assigned random serial number: {random_serial_number_str}")
        print("Note that you may need to unplug and replug the device for the change to take effect.")

    except:
        dev.disconnect()
        raise


def do_change_type(dev: cy_serial_bridge.driver.CyMfgrIface, type_string: str):

    # Convert/validate type
    # Note: There is also a "JTAG" device class which can be set, but I'm unsure if this is actually
    # a valid setting as it doesn't appear in the config tool UI.
    if type_string.upper() == "UART":
        cy_type = cy_serial_bridge.CyType.UART
    elif type_string.upper() == "SPI":
        cy_type = cy_serial_bridge.CyType.SPI
    elif type_string.upper() == "I2C":
        cy_type = cy_serial_bridge.CyType.I2C
    else:
        message = "Invalid type argument!"
        raise ValueError(message)

    dev.connect()

    try:
        buffer = dev.read_config()

        config_block = cy_serial_bridge.configuration_block.ConfigurationBlock(block_bytes=buffer)
        log.info("Read the following configuration from the device: %s", str(config_block))

        # Change the type
        config_block.device_type = cy_type

        log.info("Writing the following configuration to the device: %s", str(config_block))

        log.info("Writing configuration...")
        dev.write_config(config_block)

        dev.disconnect()

        log.info("Done!")

    except:
        dev.disconnect()
        raise

    # Reset the device so that the new configuration loads
    dev.reset_device()


if __name__ == '__main__' and '__file__' in globals():
    ap = ArgumentParser()
    ap.format_help = ap.format_usage = format_usage
    ap.add_argument('-V', '--vid', type=to_int, default=VID)
    ap.add_argument('-P', '--pid', type=to_int, default=PID)
    ap.add_argument('-n', '--nth', type=int, default=0)
    ap.add_argument('-s', '--scb', type=int, default=0)
    ap.add_argument('-v', '--verbose', action="store_true")
    ap.add_argument('args', nargs='*')

    opt = ap.parse_args()

    if not opt.args:
        usage()

    log_level = (logging.INFO if opt.verbose else logging.WARN)
    logging.basicConfig(level=log_level)
    log.setLevel(log_level)

    main(opt)
