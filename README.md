# cy_serial_bridge
![CY7C65211 Picture](https://ce8dc832c.cloudimg.io/v7/_cdn_/42/19/C0/00/0/823588_1.jpg?width=640&height=480&wat=1&wat_url=_tme-wrk_%2Ftme_new.png&wat_scale=100p&ci_sign=f9de9ea97a6a5472cf6133a7f2b36109c2910153)

This package is a pure Python driver which controls a CY7C652xx USB to SPI/I2C/UART bridge IC.  It is based on @tai's reverse engineering work [here](https://github.com/tai/cyusb-hack).

## Background
The [CY7C652xx family](https://www.infineon.com/cms/en/product/universal-serial-bus/usb-2.0-peripheral-controllers/ez-usb-serial-bridge-controller/) of chips from Cypress (now Infineon) are "serial bridge controllers" which convert USB into embedded busses such as UART (serial port), I2C, and SPI.  They can be thought of as competitors to the more popular FT2232H and FT232H chips which are often found at the heart of commercial USB to I2C/SPI adapters.  However, in my experience so far, they are easier to work with and simpler to design your circuit board around.  In particular, they do not need an external EEPROM, and they are much better documented on the electrical side.  Why the industry still prefers the FTDI chips is... something of a mystery to me at this point.

One disadvantage of the CY7C652xx chips is that their software options are somewhat less fleshed out than the corresponding FTDI libraries.  Cypress provides two driver options: a Windows-only library which works through a proprietary Cypress driver (cyusb3.sys), and a cross-platform, open-source libusb1 driver.  The libusb driver can be downloaded [here](https://www.infineon.com/cms/en/product/universal-serial-bus/usb-2.0-peripheral-controllers/ez-usb-serial-bridge-controller/cy7c65211-24ltxi/#!designsupport), and is the basis for much of this driver (the C code is able to be adapted to Python via the `libusb1` package).

However, the available drivers provide absolutely no provision for reprogramming the "configuration block", the binary structure stored in the chip's flash memory which defines its USB attributes.  This includes manufacturer-set stuff such as the VID, PID, and serial number, but also the flag that tells it whether it should be a UART, I2C, or SPI bridge, and the default settings which are used for each bus type.  The configuration block can only be programmed using the closed-source Cypress USB Serial Configuration Utility (USCU) -- and to add to the pain, this is only available as a Windows GUI application!

This driver is being worked on with the goal of, in addition to providing a translation of the normal C driver into Python, also reverse-engineering the format of the config block and providing utilities to modify and rewrite it.  Basic config rewriting functionality is working, and I have been able to dynamically edit the parameters of a CY7C65211 and change it between I2C, SPI, and UART mode!  Additionally, since the code quality of the libusb1 driver is... not great (it uses multiple threads internally for no good reason I can find), I've been trying to clean up and simplify the way that data is transferred to and from the device.

### You *should* use this driver if you want to
- Have a nice Python API for interacting with CY7C652xx bridge chips in UART, I2C, and SPI mode
- Switch a CY7C652xx in between UART, I2C, and SPI mode at runtime (the official driver does NOT support this at all)
- Use an OS-agnostic CLI and/or Python API to provision CY7C652xx chips with the correct VID, PID, description, and serial number values

### You should *not* use this driver if you want to
- Ship an easy solution that works with no additional user setup on Windows machines
- Just use the serial bridge chip as a plug-and-play COM port (just use USCU to configure it in that case!)

## Warnings

This driver is not very well tested yet, and I would advise against relying on it for anything important.  I am testing it only with a CY7C65211 dev kit, and have not tried it with the single-purpose devices or with a dual-channel device like the CY7C65215.  It should work for those devices, but I cannot guarantee anything.

Additionally, I assume that it would be possible to brick your CY7C652xx by loading an incorrect configuration block onto it.  I would highly recommend doing a load operation first to download the configuration block from your specific model of chip, and then modifying it and writing it back.  Writing back configurations obtained from anywhere else could be a dangerous operation!  I take no responsibility for any chips bricked through usage of this tool.

## Functionality
### Currently Supported
- Basic reprogramming (changing type, VID/PID, and serial number)
- I2C controller/master mode operation
- SPI controller/master mode operation
- User flash reading & writing
### Not supported yet
- UART operation
- I2C peripheral/slave mode operation
- SPI peripheral/slave mode operation
- CapSense
- GPIO

## Using the Command-Line Interface

This driver installs a command-line interface script, `cy_serial_bridge_cli`.  It supports a number of functions:
```
usage: cy_serial_bridge_cli [-h] [-V VID] [-P PID] [-n NTH] [-s SCB] [-v] {save,load,decode,type,reconfigure} ...

positional arguments:
  {save,load,decode,type,reconfigure}
    save                Save configuration block from connected device to bin file
    load                Load configuration block to connected device from bin file
    decode              Decode and display basic information from configuration block bin file
    type                Set the type of device that the serial bridge acts as. Used for configurable bridge devices (65211/65215)
    reconfigure         Change configuration of the connected device via the CLI

options:
  -h, --help            show this help message and exit
  -V VID, --vid VID     VID of device to connect (default 0x04b4)
  -P PID, --pid PID     PID of device to connect (default 0x04b4)
  -n NTH, --nth NTH     Select Nth device (default 0)
  -s SCB, --scb SCB     Select Nth SCB block (default 0). Used for dual channel chips only.
  -v, --verbose         Enable verbose logging
```

In particular, the `reconfigure` option can be used to edit settings of a connected device, then write those settings back.  The options you pass tell it what to reconfigure:
```
usage: cy_serial_bridge_cli reconfigure [-h] [--randomize-serno] [--set-vid SET_VID] [--set-pid SET_PID]

options:
  -h, --help         show this help message and exit
  --randomize-serno  Set the serial number of the device to a random value.
  --set-vid SET_VID  Set the USB Vendor ID to a given value. Needs a 0x prefix for hex values!
  --set-pid SET_PID  Set the USB Product ID to a given value. Needs a 0x prefix for hex values!
```

## OS-Specific Info

### Windows
On Windows, cy_serial_bridge (and other libusb based programs) cannot connect to USB devices unless they have the "WinUSB" driver attached to them.

To set this up, you will need to use [Zadig](https://zadig.akeo.ie/).  Simply run this program, click "Options > List All Devices" in the menu, find whichever USB devices represent the CY7C652xx (you might have to look at the VID & PID values), and install the WinUSB driver for them.  Note that there will be at least two USB devices in the list for each bridge chip -- one for the communication interface and one for the configuration interface.  You need to install the driver for *both* for this driver to work.

This process might have to be redone the first time that the bridge is used in each mode -- for example, if I connect a CY7C652xx to a fresh machine in SPI mode and install the driver using Zadig, then change the chip to operate in I2C mode in code, I may have to use Zadig again before Python code can open it in I2C mode.  Zadig installation will also have to be redone if the VID or PID is changed, though it should stick for multiple devices in the same mode and with the same VIDs/PIDs.

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

However, when using the chips with this driver, we generally want them to have a consistent VID & PID, so that the driver can reliably find them.  Additionally, using the default VID & PID causes major problems on Windows because Windows "knows" that Cypress's CYUSB3 driver is the best driver for this chip, so it will replace the WinUSB driver installed by Zadig with CYUSB3 each time the chip is re-plugged in.  

To get around these issues, I'm adopting the convention that we'll assign CY7C65xx devices the regular Cypress VID, but use an arbitrary new VID of 0xE010.  You can set this configuration on a new device with a command like:
```shell
cy_serial_bridge_cli --vid 0x04b4 --pid <pid of your device> reconfigure --set-pid 0x0E10
```
(note that this has to be run from a `poetry shell` if developing locally)

Also note that adding `--randomize-serno` to that command will assign a random serial number to the chip, which is helpful for provisioning new boards.

Be careful with this, though.  If you plan to use this driver in a real product, this strategy will not be usable, as we are basically "squatting" on Cypress's VID space without paying.  You will have to sort out a VID and PID value for yourself I'm afraid.
