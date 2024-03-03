import dataclasses
import logging
import pathlib
import random
import sys
from typing import Annotated, Optional, cast

import click
import rich
import typer
import usb1

import cy_serial_bridge
from cy_serial_bridge.usb_constants import DEFAULT_PID, DEFAULT_VID
from cy_serial_bridge.utils import log

app = typer.Typer(help="Cypress serial bridge CLI -- reprogram and communicate with CY7C652xx")


# Global options (passed before the subcommand)
# ---------------------------------------------------------------------------------------------


def parse_vid_pid(value: str | int | None) -> int | None:
    if value is None:
        return None

    if type(value) is int:
        val_int = value
    else:
        # value can only be str at this point but mypy can't figure that out
        value = cast(str, value)

        try:
            val_int = int(value, 0)
        except ValueError:
            message = "VIDs and PIDs must be integers"
            raise typer.BadParameter(message) from None

    if val_int < 0 or val_int > 0xFFFF:
        message = "VIDs and PIDs must be between 0 and 0xFFFF"
        raise typer.BadParameter(message)

    return val_int


VIDOption = typer.Option(
    "-V",
    "--vid",
    callback=parse_vid_pid,
    help=f"VID of device to connect [default: 0x{DEFAULT_VID:04x}]",
    show_default=False,
)
PIDOption = typer.Option(
    "-P",
    "--pid",
    callback=parse_vid_pid,
    help=f"PID of device to connect [default: 0x{DEFAULT_PID:04x}]",
    show_default=False,
)
SerialNumOption = typer.Option("-S", "--serno", help="Serial number string of of device to connect.")
SCBOption = typer.Option("-s", "--scb", min=0, max=1, help="SCB channel to use.  For dual channel devices only.")
VerboseOption = typer.Option("-v", "--verbose", help="Enable verbose logging")


@dataclasses.dataclass
class GlobalOptions:
    vid: int
    pid: int
    serial_number: str | None
    scb: int


# Note: we know that this value will always be set via the global callback before any of the CLI commands run.
# However, mypy doesn't and will generate errors that it might be None.  So, we annotate it as always having
# a value even though it's None initially.
global_opt: GlobalOptions = cast(GlobalOptions, None)


@app.callback()
def handle_global_options(
    vid: Annotated[int, VIDOption] = DEFAULT_VID,
    pid: Annotated[int, PIDOption] = DEFAULT_PID,
    serial_number: Annotated[Optional[str], SerialNumOption] = None,
    scb: Annotated[int, SCBOption] = 0,
    verbose: Annotated[bool, VerboseOption] = False,
) -> None:
    # Set global log level based on 'verbose'
    log_level = logging.INFO if verbose else logging.WARN
    logging.basicConfig(level=log_level)
    log.setLevel(log_level)

    # Also set libusb log level based on 'verbose'
    cy_serial_bridge.driver.usb_context.setDebug(usb1.LOG_LEVEL_INFO if verbose else usb1.LOG_LEVEL_ERROR)

    # Save other options
    global global_opt  # noqa: PLW0603
    global_opt = GlobalOptions(vid, pid, serial_number, scb)


# Save command
# ---------------------------------------------------------------------------------------------
OutputConfigurationArgument = typer.Argument(
    exists=False, dir_okay=False, file_okay=True, writable=True, help="Path to save the configuration block to"
)


@app.command(help="Save configuration block from connected device to bin file")
def save(file: Annotated[pathlib.Path, OutputConfigurationArgument]) -> None:
    with cast(
        cy_serial_bridge.driver.CyMfgrIface,
        cy_serial_bridge.open_device(
            global_opt.vid, global_opt.pid, cy_serial_bridge.OpenMode.MFGR_INTERFACE, global_opt.serial_number
        ),
    ) as dev:
        dev.connect()
        buf = dev.read_config()
        dev.disconnect()

        # As a sanity check, parse the bytes to make sure the checksum is valid
        config_block = cy_serial_bridge.configuration_block.ConfigurationBlock(block_bytes=buf)
        log.info("Read the following configuration from the device: %s", str(config_block))

        # Save to file
        pathlib.Path(file).write_bytes(bytes(buf))


# Load command
# ---------------------------------------------------------------------------------------------
InputConfigurationArgument = typer.Argument(
    exists=True, dir_okay=False, file_okay=True, readable=True, help="Path to load the configuration block from"
)


@app.command(help="Load configuration block to connected device from bin file")
def load(file: Annotated[pathlib.Path, InputConfigurationArgument]) -> None:
    with cast(
        cy_serial_bridge.driver.CyMfgrIface,
        cy_serial_bridge.open_device(
            global_opt.vid, global_opt.pid, cy_serial_bridge.OpenMode.MFGR_INTERFACE, global_opt.serial_number
        ),
    ) as dev:
        # Load bytes and check checksum
        config_block = cy_serial_bridge.configuration_block.ConfigurationBlock(file)

        log.info("Writing the following configuration to the device: %s", str(config_block))

        dev.connect()

        log.info("Writing configuration...")
        dev.write_config(config_block)
        dev.disconnect()
        dev.reset_device()

        log.info("Done!")


# Decode command
# ---------------------------------------------------------------------------------------------
@app.command(help="Decode and display basic information from configuration block bin file")
def decode(file: Annotated[pathlib.Path, InputConfigurationArgument]) -> None:
    # Just decode the configuration block, then exit.
    cfg_block = cy_serial_bridge.configuration_block.ConfigurationBlock(file)
    print(str(cfg_block))


# Reconfigure command
# ---------------------------------------------------------------------------------------------

RandomizeSernoOption = typer.Option("--randomize-serno", help="Set the serial number of the device to a random value.")
SetSernoOption = typer.Option("--set-serno", help="Set the serial number of the device.")
SetVIDOption = typer.Option(
    "--set-vid",
    help="Set the USB Vendor ID to a given value.  Needs a 0x prefix for hex values!",
    callback=parse_vid_pid,
)
SetPIDOption = typer.Option(
    "--set-pid",
    help="Set the USB Product ID to a given value.  Needs a 0x prefix for hex values!",
    callback=parse_vid_pid,
)


@app.command(help="Change configuration of the connected device via the CLI")
def reconfigure(
    randomize_serno: Annotated[bool, RandomizeSernoOption] = False,
    set_serno: Annotated[Optional[str], SetSernoOption] = None,
    set_vid: Annotated[Optional[int], SetVIDOption] = None,
    set_pid: Annotated[Optional[int], SetPIDOption] = None,
) -> None:
    if randomize_serno and set_serno is not None:
        message = "You cannot pass both --randomize-serno and --set-serno at the same time!"
        raise typer.BadParameter(message)

    with cast(
        cy_serial_bridge.driver.CyMfgrIface,
        cy_serial_bridge.open_device(
            global_opt.vid, global_opt.pid, cy_serial_bridge.OpenMode.MFGR_INTERFACE, global_opt.serial_number
        ),
    ) as dev:
        dev.connect()

        try:
            buffer = dev.read_config()

            config_block = cy_serial_bridge.configuration_block.ConfigurationBlock(block_bytes=buffer)
            log.info("Read the following configuration from the device: %s", str(config_block))

            if randomize_serno:
                # Generate a random integer with 32 digits
                serial_number_max = 10**32 - 1
                random_serial_number = random.randint(0, serial_number_max)
                random_serial_number_str = f"{random_serial_number:032}"
                print(f"Assigned random serial number: {random_serial_number_str}")

                config_block.serial_number = random_serial_number_str
            elif set_serno is not None:
                config_block.serial_number = set_serno

            if set_vid is not None:
                config_block.vid = set_vid

            if set_pid is not None:
                config_block.pid = set_pid

            log.info("Writing the following configuration to the device: %s", str(config_block))

            log.info("Writing configuration...")
            dev.write_config(config_block)
            dev.disconnect()

            log.info("Done!  Resetting device now...")

            # Reset the device so that the new configuration loads
            dev.reset_device()

        except:
            dev.disconnect()
            raise


# Change type command
# ---------------------------------------------------------------------------------------------

# Incredibly annoyingly, Typer has no way to use an Enum to map between names and integer values.
# https://github.com/tiangolo/typer/issues/151
# So we have to use a workaround by dropping down to the underlying Click
# https://github.com/tiangolo/typer/issues/182#issuecomment-1708245110

TypeArgument = typer.Argument(
    help="Communication type to change the bridge into",
    click_type=click.Choice(cy_serial_bridge.CyType._member_names_, case_sensitive=False),  # noqa: SLF001
    show_default=False,
)


@app.command(
    help="Set the type of device that the serial bridge acts as.  For configurable bridge devices (65211/65215)"
)
def change_type(type: Annotated[str, TypeArgument]) -> None:  # noqa: A002
    cy_type = cy_serial_bridge.CyType[type]

    # MFG is not a type that can actually be set because the vendor interface is always active along with
    # whatever other interface is needed
    if cy_type == cy_serial_bridge.CyType.MFG:
        message = "Invalid CyType value, cannot set MFG as the device type"
        raise typer.BadParameter(message)

    if cy_type == cy_serial_bridge.CyType.UART_VENDOR:
        print(
            "UART_VENDOR devices cannot be accessed by the cy_serial_bridge library.  If you want to use the device"
            " in UART mode with this library, use UART_CDC instead."
        )
        typer.confirm("Are you sure you want to continue with this mode?", abort=True)
    elif cy_type == cy_serial_bridge.CyType.UART_PHDC:
        print(
            "UART_PHDC devices cannot be accessed by the cy_serial_bridge library and additionally UART_PHDC mode "
            "has not been tested by the cy_serial_bridge authors.  If you want to use the device"
            " in UART mode with this library, use UART_CDC instead."
        )
        typer.confirm("Are you sure you want to continue with this mode?", abort=True)
    elif cy_type == cy_serial_bridge.CyType.JTAG:
        print(
            "CyType.JTAG is only usable for SCB1 on the CY7C65215, and JTAG is currently not supported "
            "by this driver."
        )
        typer.confirm("Are you sure you want to continue with this mode?", abort=True)

    dev: cy_serial_bridge.driver.CyMfgrIface
    with cast(
        cy_serial_bridge.driver.CyMfgrIface,
        cy_serial_bridge.open_device(
            global_opt.vid, global_opt.pid, cy_serial_bridge.OpenMode.MFGR_INTERFACE, global_opt.serial_number
        ),
    ) as dev:
        dev.change_type(cy_type)

        # Reset the device so that the new configuration loads
        dev.reset_device()


# Scan command
# ---------------------------------------------------------------------------------------------
ScanAllOption = typer.Option(
    "--all", "-a", help="Scan all USB devices on the system instead of just ones with the specified vid and pid"
)


@app.command(help="Scan for USB devices which look like CY7C652xx serial bridges")
def scan(scan_all: Annotated[bool, ScanAllOption] = False) -> None:
    """
    Scan for candidate USB devices on the system
    """
    scan_filter = None if scan_all else {(global_opt.vid, global_opt.pid)}
    devices = cy_serial_bridge.device_discovery.list_devices(scan_filter)

    if len(devices) == 0:
        if scan_all:
            print("No devices found on the system that look like a CY7C652xx!")
        else:
            print(f"No devices found on the system with VID:PID {global_opt.vid:04x}:{global_opt.pid:04x}.")
            print("Maybe try again with --all to search all VIDs and PIDs?")
    else:
        print("Detected Devices:")
        for device in devices:
            rich.print(
                f"- [bold yellow]{device.vid:04x}[/bold yellow]:[bold yellow]{device.pid:04x}[/bold yellow] ([bold]Type:[/bold] {device.curr_cytype.name})",
                end="",
            )

            if device.open_failed:
                if sys.platform == "win32":
                    rich.print(
                        "[red]<Open failed, cannot get name, com port, or serno.  Attach WinUSB driver with Zadig!>[/red]"
                    )
                else:
                    rich.print(
                        "[red]<Open failed, cannot get name, tty, or serial number.  Check udev rules and permissions.>[/red]"
                    )
            else:
                rich.print(
                    f" ([bold]SerNo:[/bold] {device.serial_number}) ([bold]Name:[/bold] {device.manufacturer_str} {device.product_str})",
                    end="",
                )
                if device.serial_port_name is not None:
                    rich.print(f" ([bold]Serial Port:[/bold] '{device.serial_port_name}')", end="")
                rich.print("")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
