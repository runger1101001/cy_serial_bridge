import logging
import pathlib
import random
from argparse import ArgumentParser

import usb1

import cy_serial_bridge
from cy_serial_bridge.usb_constants import DEFAULT_PID, DEFAULT_VID
from cy_serial_bridge.utils import log


def find_device(args) -> usb1.USBDevice:
    found = list(cy_serial_bridge.driver.find_device(args.vid, args.pid))

    if len(found) - 1 < args.nth:
        message = "No USB device found"
        raise RuntimeError(message)

    # ux == USB Device/Configuration/Interface/Setting/Endpoint
    ud = found[args.nth]
    # uc = ud[0]
    # ui = uc[0]
    # us = ui[0]
    # ue = us[0]

    log.info("Connecting...")
    return ud


def to_int(v):
    return int(v, 0)


def do_save(args):
    with cy_serial_bridge.driver.CyMfgrIface(find_device(args), scb_index=args.scb) as dev:
        dev.connect()
        buf = dev.read_config()
        dev.disconnect()

        # As a sanity check, parse the bytes to make sure the checksum is valid
        config_block = cy_serial_bridge.configuration_block.ConfigurationBlock(block_bytes=buf)
        log.info("Read the following configuration from the device: %s", str(config_block))

        # Save to file
        pathlib.Path(args.file).write_bytes(bytes(buf))


def do_load(args):
    with cy_serial_bridge.driver.CyMfgrIface(find_device(args), scb_index=args.scb) as dev:
        # Load bytes and check checksum
        config_block = cy_serial_bridge.configuration_block.ConfigurationBlock(args.file)

        log.info("Writing the following configuration to the device: %s", str(config_block))

        dev.connect()

        log.info("Writing configuration...")
        dev.write_config(config_block.config_bytes)
        dev.disconnect()

        log.info("Done!")


def do_decode(args):
    # Just decode the configuration block, then exit.
    cfg_block = cy_serial_bridge.configuration_block.ConfigurationBlock(args.file)
    print(str(cfg_block))


def do_reconfigure(args):
    with cy_serial_bridge.driver.CyMfgrIface(find_device(args), scb_index=args.scb) as dev:
        dev.connect()

        try:
            buffer = dev.read_config()

            config_block = cy_serial_bridge.configuration_block.ConfigurationBlock(block_bytes=buffer)
            log.info("Read the following configuration from the device: %s", str(config_block))

            if args.randomize_serno:
                # Generate a random integer with 32 digits
                serial_number_max = 10**32 - 1
                random_serial_number = random.randint(0, serial_number_max)
                random_serial_number_str = f"{random_serial_number:032}"
                print(f"Assigned random serial number: {random_serial_number_str}")

                config_block.serial_number = random_serial_number_str

            if args.set_vid is not None:
                config_block.vid = args.set_vid

            if args.set_pid is not None:
                config_block.pid = args.set_pid

            log.info("Writing the following configuration to the device: %s", str(config_block))

            log.info("Writing configuration...")
            dev.write_config(config_block)

            log.info("Done!  Resetting device now...")

            # Reset the device so that the new configuration loads
            dev.reset_device()
            dev.disconnect()

        except:
            dev.disconnect()
            raise


def do_change_type(args):
    # Convert type
    # Note: There is also a "JTAG" device class which can be set, but I'm unsure if this is actually
    # a valid setting as it doesn't appear in the config tool UI.
    cy_type = cy_serial_bridge.CyType[args.type]

    with cy_serial_bridge.driver.CyMfgrIface(find_device(args), scb_index=args.scb) as dev:
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


if __name__ == "__main__" and "__file__" in globals():
    ap = ArgumentParser()
    ap.add_argument(
        "-V", "--vid", type=to_int, default=DEFAULT_VID, help=f"VID of device to connect (default 0x{DEFAULT_VID:04x})"
    )
    ap.add_argument(
        "-P", "--pid", type=to_int, default=DEFAULT_PID, help=f"PID of device to connect (default 0x{DEFAULT_VID:04x})"
    )
    ap.add_argument("-n", "--nth", type=int, default=0, help="Select Nth device (default 0)")
    ap.add_argument(
        "-s", "--scb", type=int, default=0, help="Select Nth SCB block (default 0).  Used for dual channel chips only."
    )
    ap.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    subparser = ap.add_subparsers()

    save_ap = subparser.add_parser("save", help="Save configuration block from connected device to bin file")
    save_ap.add_argument("file", type=str, help="Bin file to save configuration into.")
    save_ap.set_defaults(func=do_save)

    load_ap = subparser.add_parser("load", help="Load configuration block to connected device from bin file")
    load_ap.add_argument("file", type=str, help="Bin file to load configuration from.")
    load_ap.set_defaults(func=do_load)

    decode_ap = subparser.add_parser(
        "decode", help="Decode and display basic information from configuration block bin file"
    )
    decode_ap.add_argument("file", type=str, help="Bin file to decode")
    decode_ap.set_defaults(func=do_decode)

    type_ap = subparser.add_parser(
        "type",
        help="Set the type of device that the serial bridge acts as.  Used for configurable bridge devices (65211/65215)",
    )
    type_ap.add_argument("type", choices=["SPI", "I2C", "UART"])
    type_ap.set_defaults(func=do_change_type)

    reconfigure_ap = subparser.add_parser(
        "reconfigure", help="Change configuration of the connected device via the CLI"
    )
    reconfigure_ap.add_argument(
        "--randomize-serno", action="store_true", help="Set the serial number of the device to a random value."
    )
    reconfigure_ap.add_argument(
        "--set-vid", type=to_int, help="Set the USB Vendor ID to a given value.  Needs a 0x prefix for hex values!"
    )
    reconfigure_ap.add_argument(
        "--set-pid", type=to_int, help="Set the USB Product ID to a given value.  Needs a 0x prefix for hex values!"
    )
    reconfigure_ap.set_defaults(func=do_reconfigure)

    opt = ap.parse_args()

    log_level = logging.INFO if opt.verbose else logging.WARN
    logging.basicConfig(level=log_level)
    log.setLevel(log_level)

    opt.func(opt)

    # main(opt)
