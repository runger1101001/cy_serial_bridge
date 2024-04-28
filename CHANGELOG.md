# project-name Changelog

All notable changes to this project will be documented in this file.

The format is based on [CHANGELOG.md][CHANGELOG.md]
and this project adheres to [Semantic Versioning][Semantic Versioning].

<!-- 
TEMPLATE

## [major.minor.patch] - yyyy-mm-dd

A message that notes the main changes in the update.

### Added

### Changed

### Deprecated

### Fixed

### Removed

### Security

_______________________________________________________________________________
 
 -->

<!--
EXAMPLE

## [0.2.0] - 2021-06-02

Lorem Ipsum dolor sit amet.

### Added

- Cat pictures hidden in the library
- Added beeswax to the gears

### Changed

- Updated localisation files

-->

_______________________________________________________________________________

## [0.3.2] - 2024-04-28

### Fixed

- Added udev rule for CY7C65211A default PID
- Fixed scanning/reconfiguring devices in UART_CDC mode with no serial number (warning is printed instead of crashing)
- Fixed `default_frequency` missing from ConfigurationBlock string conversion
- Config block version 2 (observed on CY7C65211A) is now permitted for the driver, and seems to work OK


_______________________________________________________________________________

## [0.3.1] - 2024-03-19

### Fixed

- Work around [tiangolo/typer#463](https://github.com/tiangolo/typer/pull/463) by explicitly declaring a dependency on Click >=8.0
- Fix minimum Python version dependency

_______________________________________________________________________________

## [0.3.0] - 2024-03-18

First (hopefully) stable release!

### Added

- SPI and UART APIs are now documented
- Added new `cy_serial_cli serial-term` command which opens a miniterm instance on the SCB device
- Added new `cy_serial_cli spi-transaction` command which allows doing SPI transactions from the command line
- README now contains a section about MacOS usage.

### Changed

- Scanning for and opening devices is now done using a CyScbContext object rather than using global functions.  This allows one process to open multiple serial bridge devices.

### Fixed

- Check has been added for the issue that causes changing the type of a UART_CDC device to fail on MacOS.  Cannot completely fix the issue but can at least notify the user and ask them to rerun the command with sudo.

_______________________________________________________________________________

## [0.2.0] - 2024-03-03

I2C and CLI update!

### Added

- I2C API is now documented
- Added new `cy_serial_cli i2c-write` and `cy_serial_cli i2c-read` commands, which allow doing simple I2C transactions directly from the command line

### Changed

- CLI now uses typer instead of argparse.  Besides making it look cooler, this improves type safety and adds some much more understandable exception handlers for the CLI.

_______________________________________________________________________________

## [0.1.0] - 2024-02-25

Initial release.  

### Added

- Support for I2C controller, SPI controller, and UART CDC mode via a pure Python driver.
- Support for changing the VID, PID, and serial number of a device
- Support for changing the type of a device
- Device scanning
- open_device() functiion which automatically changes the type of a device as needed

[CHANGELOG.md]: https://keepachangelog.com/en/1.1.0/
[Semantic Versioning]: http://semver.org/

<!-- markdownlint-configure-file {
    "MD022": false,
    "MD024": false,
    "MD030": false,
    "MD032": false
} -->
<!--
    MD022: Blanks around headings
    MD024: No duplicate headings
    MD030: Spaces after list markers
    MD032: Blanks around lists
-->