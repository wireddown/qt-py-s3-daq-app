# QT Py Sensor Node

This folder and its subfolders are an overlay for a CircuitPython device.
The code adds functions to perform data logging from analog channels and I2C devices.

- Homepage
  - https://github.com/wireddown/qt-py-s3-daq-app/wiki
- Source code
  - https://github.com/wireddown/qt-py-s3-daq-app/tree/main/src/qtpy_datalogger/sensor_node

## Quick start

1. Connect a QT Py device to the computer with USB
1. Install the `qtpy_datalogger` package into a Python environment
1. Install the sensor node bundle onto the QT Py device
   ```pwsh
   # Use the equip command to install or upgrade
   qtpy-datalogger equip
   ```

## Manual bring-up

1. Copy this folder and its subfolders to the QT Py device
1. Use `circup` to install the CircuitPython support libraries
   - adafruit_minimqtt
