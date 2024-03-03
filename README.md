# cy_serial_bridge
![CY7C65211 Picture](https://ce8dc832c.cloudimg.io/v7/_cdn_/42/19/C0/00/0/823588_1.jpg?width=640&height=480&wat=1&wat_url=_tme-wrk_%2Ftme_new.png&wat_scale=100p&ci_sign=f9de9ea97a6a5472cf6133a7f2b36109c2910153)

This package is a pure Python driver which controls a CY7C652xx USB to SPI/I2C/UART bridge IC.  It is based on @tai's reverse engineering work [here](https://github.com/tai/cyusb-hack).

## Background
The [CY7C652xx family](https://www.infineon.com/cms/en/product/universal-serial-bus/usb-2.0-peripheral-controllers/ez-usb-serial-bridge-controller/) of chips from Cypress (now Infineon) are "serial bridge controllers" which convert USB into embedded busses such as UART (serial port), I2C, and SPI.  They can be thought of as competitors to the more popular FT2232H and FT232H chips which are often found at the heart of commercial USB to I2C/SPI adapters.  However, in my experience so far, they are easier to work with and simpler to design your circuit board around.  In particular, they do not need an external EEPROM, and they are much better documented on the electrical side.  Why the industry still prefers the FTDI chips is... something of a mystery to me at this point.

One disadvantage of the CY7C652xx chips is that their software options are somewhat less fleshed out than the corresponding FTDI libraries.  Cypress provides two driver options: a Windows-only library which works through a proprietary Cypress driver (cyusb3.sys), and a cross-platform, open-source libusb1 driver.  The libusb driver can be downloaded [here](https://www.infineon.com/cms/en/product/universal-serial-bus/usb-2.0-peripheral-controllers/ez-usb-serial-bridge-controller/cy7c65211-24ltxi/#!designsupport), and is the basis for much of this driver (the C code is able to be adapted to Python via the `libusb1` package).

However, the available drivers provide absolutely no provision for reprogramming the "configuration block", the binary structure stored in the chip's flash memory which defines its USB attributes.  This includes manufacturer-set stuff such as the VID, PID, and serial number, but also the flag that tells it whether it should be a UART, I2C, or SPI bridge, and the default settings which are used for each bus type.  The configuration block can only be programmed using the closed-source Cypress USB Serial Configuration Utility (USCU) -- and to add to the pain, this is only available as a Windows GUI application!

This driver is being worked on with the goal of, in addition to providing a translation of the libusb C driver into Python, also reverse-engineering the format of the config block and providing utilities to modify and rewrite it.  Basic config rewriting functionality is working, and I have been able to dynamically edit the parameters of a CY7C65211 and change it between I2C, SPI, and UART mode!  Additionally, since the code quality of the libusb1 driver is... not great (it uses multiple threads internally rather than the libusb asynchronous API), I've been trying to clean up and simplify the way that data is transferred to and from the device.

### You *should* use this driver if you want to
- Have a nice Python API for interacting with CY7C652xx bridge chips in UART, I2C, and SPI mode
- Switch a CY7C652xx in between UART, I2C, and SPI mode at runtime (the official driver does NOT support this at all)
- Use an OS-agnostic CLI and/or Python API to provision CY7C652xx chips with the correct VID, PID, description, and serial number values

### You should *not* use this driver if you want to
- Ship an easy solution that works with no additional user setup on Windows machines (see Windows section below)
- Just use the serial bridge chip as a USB-UART adapter only (in this case, just use USCU to configure it once and then use a regular serial port library to operate it)
- Rapidly switch between I2C/SPI/UART modes (it takes up to a few seconds to reprogram the config block and re-enumerate the device)

## Warnings

This driver is not very well tested yet, and I would advise against relying on it for anything important without additional testing.  I am testing it only with a CY7C65211 dev kit, and have not tried it with the single-purpose devices or with a dual-channel device like the CY7C65215.  It should work for those devices, but I cannot guarantee anything.

Additionally, I assume that it would be possible to brick your CY7C652xx by loading an incorrect configuration block onto it.  Rather than downloading any of the configuration bin files in this repo, I would highly recommend doing a load operation first to download the configuration block from your specific model of chip, and then modifying it and writing it back (this is already how the reconfigure functionality works).  Writing back configurations obtained from anywhere else could be a dangerous operation!  I take no responsibility for any chips bricked through usage of this tool.

## Functionality
### Currently Supported
- Basic reprogramming (changing type, VID/PID, and serial number)
- I2C controller/master mode operation
- SPI controller/master mode operation
- User flash reading & writing
- UART CDC operation (this library changes the type of the device and finds the right tty / COM port, then pyserial handles the actual UART communication)
### Not supported yet
- vendor mode UART operation
- I2C peripheral/slave mode operation
- SPI peripheral/slave mode operation
- CapSense
- GPIO
- JTAG (only supported on the larger dual channel devices)
- Scanning & discovering dual channel CY7C652xx devices (e.g. CY7C65215)

## Using the Command-Line Interface

This driver installs a command-line interface script, `cy_serial_cli`.  It supports a number of functions:
```
usage: cy_serial_cli [-h] [-V VID] [-P PID] [-n NTH] [-s SCB] [-v] {scan,save,load,decode,type,reconfigure} ...

positional arguments:
  {scan,save,load,decode,type,reconfigure}
    scan                Scan for USB devices which look like CY7C652xx serial bridges
    save                Save configuration block from connected device to bin file
    load                Load configuration block to connected device from bin file
    decode              Decode and display basic information from configuration block bin file
    type                Set the type of device that the serial bridge acts as. Used for configurable bridge devices (65211/65215)
    reconfigure         Change configuration of the connected device via the CLI

options:
  -h, --help            show this help message and exit
  -V VID, --vid VID     VID of device to connect (default 0x04b4)
  -P PID, --pid PID     PID of device to connect (default 0xe010)
  -n NTH, --nth NTH     Select Nth device (default 0)
  -s SCB, --scb SCB     Select Nth SCB block (default 0). Used for dual channel chips only.
  -v, --verbose         Enable verbose logging

```

### Changing Settings
The `reconfigure` subcommand can be used to edit settings of a connected device, then write those settings back.  The options you pass tell it what to reconfigure:
```
usage: cy_serial_cli reconfigure [-h] [--randomize-serno] [--set-vid SET_VID] [--set-pid SET_PID]

options:
  -h, --help         show this help message and exit
  --randomize-serno  Set the serial number of the device to a random value.
  --set-vid SET_VID  Set the USB Vendor ID to a given value. Needs a 0x prefix for hex values!
  --set-pid SET_PID  Set the USB Product ID to a given value. Needs a 0x prefix for hex values!
```

Additionally, the `type` subcommand can be used to change the device's type.  However, this is mostly for debugging and for using the serial bridge with other programs, because the type is changed automatically when you open the device in SPI, I2C, or UART mode.

### Scanning for Devices
The `scan` command can be used to find CY7C652xx devices attached to your system.  Since these devices have configurable VIDs and PIDs, a heuristic search is used based on each connected device's USB descriptor.  By default, only devices with the default VID and PIDs (see "Setting Up New Devices" below) are considered, but if you use `scan --all`, that will search all USB devices on your system.

For each detected device, the serial number, type, and (if in UART CDC mode) the corresponding serial port is output.

```
> cy_serial_cli scan --all
Detected Devices:
- 04b4:e011 (Type: UART_CDC) (SerNo: 14224672048496620243684302669570) (Type: UART_CDC) (Serial Port: 'COM6')
```

## Using the Python API

cy_serial_bridge provides a rich Python API that can be used to communicate with the serial bridge in each mode. 

### I2C controller mode

First, you must open the device and set the configuration:
```python
import cy_serial_bridge

with cy_serial_bridge.open_device(cy_serial_bridge.DEFAULT_VID, 
                                  cy_serial_bridge.DEFAULT_PID, 
                                  cy_serial_bridge.OpenMode.I2C_CONTROLLER) as bridge:
    bridge.set_i2c_configuration(cy_serial_bridge.driver.CyI2CConfig(frequency=400000))
```

## OS-Specific Info

### Windows
On Windows, cy_serial_bridge (and other libusb based programs) cannot connect to USB devices unless they have the "WinUSB" driver attached to them.

To set this up, you will need to use [Zadig](https://zadig.akeo.ie/).  Simply run this program, click "Options > List All Devices" in the menu, find whichever USB devices represent the CY7C652xx (you might have to look at the VID & PID values), and install the WinUSB driver for them.  Note that there will be at least two USB devices in the list for each bridge chip -- one for the communication interface and one for the configuration interface.  You need to install the driver for *both* for this driver to work.

This process might have to be redone the first time that the bridge is used in each mode -- for example, if I connect a CY7C652xx to a fresh machine in SPI mode and install the driver using Zadig, then change the chip to operate in I2C mode in code, I may have to use Zadig again before Python code can open it in I2C mode.  Zadig installation will also have to be redone if the VID or PID is changed, though it only has to be done once per machine for a given VID-PID-operation mode combination.

I believe that it would be possible to script this a bit more gracefully, by writing a script to change the serial bridge into each mode and then invoke Zadig for each interface.  This should be looked into more.

Also note that [NirSoft USBLogView](https://www.nirsoft.net/utils/usb_log_view.html) is extremely useful for answering the question of "what are the VID & PID of the USB device I just plugged in".

### Linux
To grant access to the serial bridge USB device without root, you will need to install a udev rules file.  We've provided one for you under the `rules` folder of this repository.  First, copy it to the `/etc/udev/rules.d` folder.  Then, run:
```shell
$ sudo udevadm control --reload-rules
$ sudo udevadm trigger
```

Finally, make sure your user is in the `plugdev` group:
```shell
$ sudo usermod -a -G plugdev <your username>
```
(you may have to log out and back in for this to take effect)

This should allow you to access the serial bridge chip without any special privileges.  

Note, however, that the rules file is written for the driver default VID and PID values (see "Setting Up New Devices").  If your device is using different VID & PID values (e.g. a factory new chip), you will need to update the rules file or temporarily run as root.

## Setting Up New Devices
When new CY76C65211 devices arrive, and you use USCU to configure them, they will get the Cypress VID (0x4b4), and can end up with one of several PID values (e.g. 0x0003, 0x0004, etc) depending on what model of chip they are and what mode they are configured as (I2C, SPI, etc).  

However, when using the chips with this driver, we generally want them to have a consistent VID & PID so that the driver can reliably find them.  Additionally, using the default VID & PID causes major problems on Windows because Windows "knows" that Cypress's CYUSB3 driver is the best driver for this chip, so it will replace the WinUSB driver installed by Zadig with CYUSB3 each time the chip is re-plugged in.  

To get around these issues, I'm adopting the convention that we'll assign CY7C65xx devices the regular Cypress VID, but use an arbitrary new VID of 0xE010.  You can set this configuration on a new device with a command like:
```shell
cy_serial_cli --vid 0x04b4 --pid <pid of your device> reconfigure --set-pid 0xE010
```
(note that this has to be run from a `poetry shell` if developing locally)

To determine what the VID and PID of your device currently are, you can use:
```shell
cy_serial_cli scan --all
```

Also note that adding `--randomize-serno` to the reconfigure command will assign a random serial number to the chip, which is helpful for provisioning new boards.

Another issue: On Windows, if you have a given VID and PID assigned to use the WinUSB driver via Zadig, Windows will not try and use the USB CDC driver to enumerate COM ports from the device.  This means that a device in SPI/I2C mode cannot use the same VID and PID as a device in UART CDC mode.  To solve this, this driver automatically uses two PIDs for each device.  The even PID is used in SPI/I2C mode, and the odd PID is used in UART CDC mode.

WARNING: This setup is for dev testing only!  If you plan to use this driver in a real product, this strategy will not be usable, this VID space is owned by Cypress.  You will have to purchase a VID and two consecutive PID values for yourself.

## To Do List / Known Issues
- If the I2C lines are not pulled up to 3.3V, I2C read and write bulk transfers hang forever and we don't have error handling for this
- Need to understand the formatting of the data argument for SPI when frame size is not 8 bits
- I2CNACKError.bytes_written is not correct
- Need to characterize the largest transfer size that can be done of each type -- e.g. can we do transfers larger than the 256 byte (SPI/I2C) / 190 byte (UART) buffer on the chip?
- Need to understand the deal with the "notification LED" settings on this chip.  It seems like the notification LED is constantly on whenever I enable it.  The docs say it "drives a GPIO on both USB transmit and receive", but what does that mean exactly?

### Note about Vendor UART Mode
Currently, this driver does not support the "vendor UART" mode of the serial bridge chip.  In vendor UART mode, the serial bridge chip still displays the custom "vendor" interface to the PC, and the Python driver has to manually send and receive bytes via the correct endpoints.  The problem, however, is that the A in UART stands for Asynchronous: other devices can send bytes to the serial bridge asynchronously whenever they want to, and it's up to the host software to get the bytes off the chip before its 190 byte buffer fills up.

Unfortunately, the way that a naive python driver would work, bytes would only be read when a thread calls a read function on the UART driver.  They aren't read at any other time.  So, if somebody is sending you data over UART and your application code does not poll the UART fast enough, you would lose data.

One way to fix this would be to have the driver continually submit USB transfers to the CY7C652xx in the background, so that data is transferred to the host machine as soon as the bridge chip makes it available.  This would help with the buffering situation a lot, and python-libusb1 does support the async API needed to make it work.  However, the threading situation would get complicated: either we would need a new background thread to be in charge of submitting all the transfers and monitoring when they finish (and also this might mean converting every single transfer done anywhere in the driver into an asynchronous transfer so that that thread is the only one processing events), OR we need support for the `handleEventsCompleted()` function, which is [not currently included](https://github.com/vpelletier/python-libusb1/issues/94) in the python-libusb1 wrapper.

However, even that method wouldn't be the best possible solution, because data could still be lost if the Python thread doing the USB operations doesn't run fast enough.  Instead, using UART CDC mode lets the OS driver handle all of the nitty-gritty USB stuff.  On the application side, the well-established Pyserial library can be used to read from the standard serial port provided by the CY7C652xx.
