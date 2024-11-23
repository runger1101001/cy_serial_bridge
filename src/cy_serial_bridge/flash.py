import binascii
import contextlib
import dataclasses
import enum
import logging
import pathlib
import random
import sys
from typing import Annotated, Optional, cast

import click
import rich
import serial
import typer
import usb1
from serial.tools import miniterm

import cy_serial_bridge
from cy_serial_bridge.usb_constants import DEFAULT_PID, DEFAULT_VID
from cy_serial_bridge.utils import log
"""
Module for flashing a device over SPI
"""



app = typer.Typer(
    help="Cypress Serial Bridge CLI -- reconfigure CY7C652xx serial bridge chips and use them to communicate over UART/I2C/SPI"
)


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
    metavar="VID",
    parser=parse_vid_pid,
    help=f"VID of device to connect [default: 0x{DEFAULT_VID:04x}]",
    show_default=False,
)
PIDOption = typer.Option(
    "-P",
    "--pid",
    metavar="PID",
    parser=parse_vid_pid,
    help=f"PID of device to connect [default: 0x{DEFAULT_PID:04x}]",
    show_default=False,
)
SerialNumOption = typer.Option("-S", "--serno", help="Serial number string of of device to connect.")
SCBOption = typer.Option("-s", "--scb", min=0, max=1, help="SCB channel to use.  For dual channel devices only.")
VerboseOption = typer.Option("-v", "--verbose", help="Enable verbose logging")
SPIFreqOption = typer.Option(
    "--frequency",
    "-f",
    min=cy_serial_bridge.CySpi.MIN_FREQUENCY,
    max=cy_serial_bridge.CySpi.MAX_MASTER_FREQUENCY,
    help="SPI frequency to use, in Hz.",
)
SPIModeOption = typer.Option(
    "--mode",
    "-m",
    help="SPI mode to use for the transfer",
    click_type=click.Choice(cy_serial_bridge.CySPIMode._member_names_, case_sensitive=False),  # noqa: SLF001
    show_default=False,
)
PreFlashOption = typer.Option("--pre-flash", help="Commands before flashing (e.g. desiable write protection)", default=None)
PostFlashOption = typer.Option("--post-flash", help="Commands after flashing (e.g. enable write protection)", default=None)
TransferSizeOption = typer.Option(
    "--transfer-size", 
    "-t", 
    min=cy_serial_bridge.CySpi.MIN_WORD_SIZE, 
    max=cy_serial_bridge.CySpi.MAX_WORD_SIZE, 
    help="Number of bits to transfer in each SPI transaction", 
    default=cy_serial_bridge.CySpi.MAX_WORD_SIZE
)
MsbFirstOption = typer.Option("--msb-first", help="Send data MSB first", is_flag=True, default=True)
ContinuousSselOption = typer.Option("--continuous-ssel", help="Keep the SSEL line low between transactions", is_flag=True, default=False)

AddressOption = typer.Option("--address", "-a", min=0, help="Address to start writing the binary data to", default=0)
BinaryLengthOption = typer.Option("--length", "-l", min=0, help="Length of binary data to read/write/erase. 0=default meaning to end of file", default=0)
BinaryOffsetOption = typer.Option("--offset", "-o", min=0, help="Offset in file to start reading binary data. 0=default", default=0)


@dataclasses.dataclass
class GlobalOptions:
    vid: int
    pid: int
    serial_number: str | None
    scb: int
    freq: int
    mode: str | int
    pre_flash: str | None
    post_flash: str | None
    transfer_size: int
    msb_first: bool
    continuous_ssel: bool
    address: int
    length: int
    offset: int

# Note: we know that this value will always be set via the global callback before any of the CLI commands run.
# However, mypy doesn't and will generate errors that it might be None.  So, we annotate it as always having
# a value even though it's None initially.
global_opt: GlobalOptions = cast(GlobalOptions, None)


# Global context instance.
# Fine to use a global one since the CLI can only talk to one device at a time.
context = cy_serial_bridge.CyScbContext()


@app.callback()
def handle_global_options(
    vid: Annotated[int, VIDOption] = DEFAULT_VID,
    pid: Annotated[int, PIDOption] = DEFAULT_PID,
    serial_number: Annotated[Optional[str], SerialNumOption] = None,
    scb: Annotated[int, SCBOption] = 0,
    verbose: Annotated[bool, VerboseOption] = False,
    freq: Annotated[int, SPIFreqOption] = cy_serial_bridge.CySpi.MAX_MASTER_FREQUENCY.value,
    mode: Annotated[cy_serial_bridge.CySPIMode, SPIModeOption] = cy_serial_bridge.CySPIMode.MOTOROLA_MODE_0,
    pre_flash: Annotated[str|None, PreFlashOption] = None,
    post_flash: Annotated[str|None, PostFlashOption] = None,
    transfer_size: Annotated[int, TransferSizeOption] = cy_serial_bridge.CySpi.MAX_WORD_SIZE,
    msb_first: Annotated[bool, MsbFirstOption] = True,
    continuous_ssel: Annotated[bool, ContinuousSselOption] = False,
    address: Annotated[int, AddressOption] = 0,
    length: Annotated[int, BinaryLengthOption] = 0,
    offset: Annotated[int, BinaryOffsetOption] = 0,
) -> None:
    # Set global log level based on 'verbose'
    log_level = logging.INFO if verbose else logging.WARN
    logging.basicConfig(level=log_level)
    log.setLevel(log_level)

    # Also set libusb log level based on 'verbose'
    context.usb_context.setDebug(usb1.LOG_LEVEL_INFO if verbose else usb1.LOG_LEVEL_ERROR)

    mode_enum = cy_serial_bridge.CySPIMode.MOTOROLA_MODE_0
    if type(global_opt.mode) is int:
        mode_enum = ([cy_serial_bridge.CySPIMode.MOTOROLA_MODE_0, cy_serial_bridge.CySPIMode.MOTOROLA_MODE_1, cy_serial_bridge.CySPIMode.MOTOROLA_MODE_2, cy_serial_bridge.CySPIMode.MOTOROLA_MODE_3])[mode]
    elif type(global_opt.mode) is str:
        mode_enum = cy_serial_bridge.CySPIMode[global_opt.mode]

    # Save other options
    global global_opt  # noqa: PLW0603
    global_opt = GlobalOptions(vid, pid, serial_number, scb, freq, mode_enum, pre_flash, post_flash, transfer_size, msb_first, continuous_ssel, address, length, offset)



def set_spi_configuration(bridge: cy_serial_bridge.driver.CySPIControllerBridge) -> None:
    global global_opt
    # set SPI configuration
    spi_config = cy_serial_bridge.driver.CySPIConfig(
                                                        frequency=global_opt.freq,
                                                        mode=global_opt.mode,
                                                        word_size=global_opt.transfer_size,
                                                        msbit_first=global_opt.msb_first,
                                                        continuous_ssel=global_opt.continuous_ssel
                                                    )
    bridge.set_spi_configuration(spi_config)


def pre_flash(bridge: cy_serial_bridge.driver.CySPIControllerBridge) -> None:
    global global_opt
    if global_opt.pre_flash is not None:
        data_to_send = binascii.a2b_hex(global_opt.pre_flash)
        response = bridge.spi_transfer(data_to_send)
        # TODO verbose output


def post_flash(bridge: cy_serial_bridge.driver.CySPIControllerBridge) -> None:
    global global_opt
    if global_opt.post_flash is not None:
        data_to_send = binascii.a2b_hex(global_opt.post_flash)
        response = bridge.spi_transfer(data_to_send)
        # TODO verbose output


def write_enable(bridge: cy_serial_bridge.driver.CySPIControllerBridge) -> None:
    data = [ 0x06 ]
    response = bridge.spi_transfer(data)
    # TODO verbose output

def read_status(bridge: cy_serial_bridge.driver.CySPIControllerBridge) -> None:
    data = [ 0x05 ]
    response = bridge.spi_transfer(data)
    # TODO verbose output

def erase_sector(bridge: cy_serial_bridge.driver.CySPIControllerBridge, address: int) -> None:
    data = [ 0x20 ] + address.to_bytes(3, 'big')
    response = bridge.spi_transfer(data)
    # TODO verbose output

def erase_all(bridge: cy_serial_bridge.driver.CySPIControllerBridge) -> None:
    data = [ 0x06 ]
    response = bridge.spi_transfer(data)
    # TODO verbose output

def erase_block(bridge: cy_serial_bridge.driver.CySPIControllerBridge, address: int) -> None:
    data = [ 0xD8 ] + address.to_bytes(3, 'big')
    response = bridge.spi_transfer(data)
    # TODO verbose output

def write_page(bridge: cy_serial_bridge.driver.CySPIControllerBridge, address: int, data: bytes) -> None:
    data = [ 0x02 ] + address.to_bytes(3, 'big') + data
    response = bridge.spi_transfer(data)
    # TODO verbose output


# Flash command
# ---------------------------------------------------------------------------------------------



BinaryFileArgument = typer.Argument(
    help="Binary data file to flash to the device or to write the data to.  If not provided, data will be read from stdin/written to stdout.",
    default=None,
)

@app.command(help="Program a flash memory or device over SPI")
def write(
    file: Annotated[pathlib.Path|None, BinaryFileArgument] = None,
) -> None:
    with cast(
        cy_serial_bridge.driver.CySPIControllerBridge,
        context.open_device(
            global_opt.vid, global_opt.pid, cy_serial_bridge.OpenMode.SPI_CONTROLLER, global_opt.serial_number
        ),
    ) as bridge:
        set_spi_configuration(bridge)
        pre_flash(bridge)
        # get input source - stdin or file and skip to offset
        if file is None:
            file = sys.stdin.buffer
        else:
            file = open(file, "rb")
        file.seek(global_opt.offset)
        # read data from file, write to flash
        bytes_written = 0
        if length==0:
            # TODO handle unknown length (read until EOF)
            length = len(file) - global_opt.offset
        while bytes_written < length:
            write_size = length if length < 4096 else 4096
            data = file.read(write_size)
            if not data:
                break
            response = bridge.spi_transfer(data)
            bytes_written += len(data)
            # TODO verbose output
        # TODO verbose output
        post_flash(bridge)
        # TODO close file if not stdin
        # TODO verbose output


@app.command(help="Read from flash memory or device over SPI")
def read(
    file: Annotated[pathlib.Path|None, BinaryFileArgument] = None,
) -> None:
    global global_opt
    with cast(
        cy_serial_bridge.driver.CySPIControllerBridge,
        context.open_device(
            global_opt.vid, global_opt.pid, cy_serial_bridge.OpenMode.SPI_CONTROLLER, global_opt.serial_number
        ),
    ) as bridge:
        set_spi_configuration(bridge)
        pre_flash(bridge)
        # get input source - stdin or file and skip to offset
        if file is None:
            file = sys.stdout.buffer
        else:
            file = open(file, "rb")
        bytes_read = 0
        if length==0:
            # TODO handle unknown length (read until EOF)
            length = len(file) - global_opt.offset
        while bytes_read < length:
            read_size = length if length < 4096 else 4096
            data = [ 0x03 ] + global_opt.address.to_bytes(3, 'big') + read_size.to_bytes(2, 'big') + [ 0x00 ] * read_size
            if not data:
                break
            response = bridge.spi_transfer(data)
            file.write(response)
            bytes_read += len(data)
            # TODO verbose output
        # TODO verbose output
        post_flash(bridge)
        # TODO close file if not stdin
        # TODO verbose output


@app.command(help="Erase flash memory or device over SPI")
def erase_all() -> None:
    global global_opt
    with cast(
        cy_serial_bridge.driver.CySPIControllerBridge,
        context.open_device(
            global_opt.vid, global_opt.pid, cy_serial_bridge.OpenMode.SPI_CONTROLLER, global_opt.serial_number
        ),
    ) as bridge:
        set_spi_configuration(bridge)
        pre_flash(bridge)
        # erase all flash
        data = [ 0x06 ]
        response = bridge.spi_transfer(data)
        # TODO verbose output
        post_flash(bridge)



@app.command(help="Erase a sector of flash memory or device over SPI")
def erase_sector() -> None:
    global global_opt
    with cast(
        cy_serial_bridge.driver.CySPIControllerBridge,
        context.open_device(
            global_opt.vid, global_opt.pid, cy_serial_bridge.OpenMode.SPI_CONTROLLER, global_opt.serial_number
        ),
    ) as bridge:
        set_spi_configuration(bridge)
        pre_flash(bridge)
        # erase sector
        data = [ 0x20 ] + global_opt.address.to_bytes(3, 'big')
        response = bridge.spi_transfer(data)
        # TODO verbose output
        post_flash(bridge)



@app.command(help="Get flash memory or device info over SPI")
def info() -> None:
    global global_opt
    with cast(
        cy_serial_bridge.driver.CySPIControllerBridge,
        context.open_device(
            global_opt.vid, global_opt.pid, cy_serial_bridge.OpenMode.SPI_CONTROLLER, global_opt.serial_number
        ),
    ) as bridge:
        set_spi_configuration(bridge)
        pre_flash(bridge)
        # get flash info
        data = [ 0x9F ]
        response = bridge.spi_transfer(data)
        # TODO verbose output
        post_flash(bridge)



@app.command(help="Read device ID over SPI")
def read_id() -> None:
    global global_opt
    with cast(
        cy_serial_bridge.driver.CySPIControllerBridge,
        context.open_device(
            global_opt.vid, global_opt.pid, cy_serial_bridge.OpenMode.SPI_CONTROLLER, global_opt.serial_number
        ),
    ) as bridge:
        set_spi_configuration(bridge)
        pre_flash(bridge)
        # read device ID
        data = [ 0x90, 0x00, 0x00, 0x00, 0x00 ]
        response = bridge.spi_transfer(data)
        # TODO verbose output
        post_flash(bridge)



@app.command(help="Read flash status over SPI")
def status() -> None:
    global global_opt
    with cast(
        cy_serial_bridge.driver.CySPIControllerBridge,
        context.open_device(
            global_opt.vid, global_opt.pid, cy_serial_bridge.OpenMode.SPI_CONTROLLER, global_opt.serial_number
        ),
    ) as bridge:
        set_spi_configuration(bridge)
        pre_flash(bridge)
        # get flash status
        data = [ 0x05 ]
        response = bridge.spi_transfer(data)
        # TODO verbose output
        post_flash(bridge)




def main() -> None:
    app()


if __name__ == "__main__":
    main()
