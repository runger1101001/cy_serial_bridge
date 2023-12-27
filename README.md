# cy_serial_bridge
This package is a pure Python driver which controls a CY7C652xx USB to SPI/I2C/UART bridge IC.  It is based on @tai's reverse engineering work [here](https://github.com/tai/cyusb-hack).

## Background
The [CY7C652xx family](https://www.infineon.com/cms/en/product/universal-serial-bus/usb-2.0-peripheral-controllers/ez-usb-serial-bridge-controller/) of chips from Cypress (now Infineon) are "serial bridge controllers" which convert USB into embedded busses such as UART (serial port), I2C, and SPI.  They can be thought of as competitors to the more popular FT2232H and FT232H chips which are often found at the heart of commercial USB to I2C/SPI adapters, but they actually (in my experience so far) are easier to work with and simpler to design your circuit board around.  In particular, they do not need an external EEPROM, and they are much better documented on the electrical side.  Why the industry still prefers the FTDI chips is... something of a mystery to me at this point.

One disadvantage of the CY7C652xx chips is that their software options are somewhat less fleshed out than the corresponding FTDI libraries.  Cypress provides two driver options: a Windows binary DLL which works through a proprietary Cypress driver (cyusb3.sys), and a cross-platform, open-source libusb1 driver.  The libusb driver can be downloaded [here](https://www.infineon.com/cms/en/product/universal-serial-bus/usb-2.0-peripheral-controllers/ez-usb-serial-bridge-controller/cy7c65211-24ltxi/#!designsupport), and is the basis for much of this driver (the C code is able to be translated to Python via the `libusb1` package).

However, the available drivers provide absolutely no provision for reprogramming the "configuration block", the binary structure stored in the chip's flash memory which defines its USB attributes.  This includes manufacturer-set stuff such as the VID, PID, and serial number, but also the flag that tells it whether it should be a UART, I2C, or SPI bridge, and the default settings which are used for each bus type.  The configuration block can only be programmed using the closed-source Cypress USB Serial Configuration Utility (USCU) -- and to add to the pain, this is only available as a Windows GUI application!

This driver is being worked on with the goal of, in addition to providing a translation of the normal C driver into Python, also reverse-engineering the format of the config block and prividing utilities to modify and rewrite it.  Basic config rewriting functionality is working, and I have been able to dynamically edit the parameters of a CY7C65211 and change it between I2C, SPI, and UART mode!

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

## OS-Specific Info

### Windows
#### Attaching WinUSB
On Windows, cy_serial_bridge (and other libusb based programs) cannot see USB devices unless they have the "WinUSB" driver attached to them.

To set this up, you will need to use [Zadig](https://zadig.akeo.ie/).  Simply run this program, click "Options > List All Devices" in the menu, find whichever USB devices represent the CY7C652xx (you might have to look at the VID & PID values), and install the WinUSB driver for them.  Note that there will be at least two USB devices in the list for each bridge chip -- one for the communication interface and one for the configuration interface.  You need to install the driver for *both* for this driver to work.

Also note that [NirSoft USBLogView](https://www.nirsoft.net/utils/usb_log_view.html) is extremely useful for answering the question of "what are the VID & PID of the USB device I just plugged in".

#### Removing cyusb3
If you have previously installed the cyusb3 driver, it will likely re-assert priority over the WinUSB driver whenever the bridge chip is reconfigured.  This will cause the Python code to be unable to open the bridge chip after any operation that changes its configuration block.  In order to fix this, we have to uninstall the cyusb3 driver from the driver store.

I found a very useful guide to this process [here](https://github.com/pbatard/libwdi/wiki/Zadig#the-workaround).  In short, there are three steps:
1. Download and run [NirSoft USBDeview](https://www.nirsoft.net/utils/usb_devices_view.html)
2. Sort by the "Driver Filename" column (scroll sideways!) and find entries containing "CYUSB3.sys".  Then check the Driver InfPath column; for each one it should be a filename like "oem205.inf".
3. For each of the inf filenames from step 2, run the following command from an administrator command prompt, replacing `<filename>` with the filename:
```
pnputil /delete-driver <filename> /force /uninstall
```

## Using the Command-Line Reprogrammer
