# QT Py Sensor Node

This folder and its subfolders are an overlay for a CircuitPython device.
The code adds functions to perform data logging from analog channels and I2C devices.

- Homepage: https://github.com/wireddown/qt-py-s3-daq-app/wiki
- Source code: https://github.com/wireddown/qt-py-s3-daq-app/tree/main/src/qtpy_datalogger/sensor_node

## Quick start

1. Install the `qtpy_datalogger` package into a Python environment
1. Install the sensor node bundle onto the QT Py ESP32-S3
   ```pwsh
   # Use the equip command to install or upgrade
   qtpy-datalogger equip
   ```

## Manual bringup

1. Copy this folder and its subfolders to the QT Py ESP32-S3
1. Update `code.py` to use the new code

### Terminal shell

This example demonstrates a console for a serial device.

`code.py`

```python
import gc
import usb_cdc

from snsr.pysh.py_shell import PromptSession

serial = usb_cdc.console
if usb_cdc.data:
    print("Switching to usb_cdc.data for serial IO with host")
    serial = usb_cdc.data
else:
    print("Using sys.stdio for serial IO with host")

session = PromptSession(in_stream=serial, out_stream=serial)

while True:
    used_bytes = gc.mem_alloc()
    free_bytes = gc.mem_free()
    response = session.prompt(f"[{used_bytes / 1024:.3f} kB {free_bytes / 1024:.3f} kB] ")

    print(f"(echo)\n{response}", file=serial)
```
