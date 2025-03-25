"""code.py file is the main loop from qtpy_datalogger.sensor_node."""  # noqa: INP001 -- we must hide 'code' to use this entry point for CircuitPython devices (IMP001)

import gc

import usb_cdc
from snsr.pysh.py_shell import PromptSession

serial = usb_cdc.console
if usb_cdc.data:
    print("Switching to usb_cdc.data for serial IO with host")  # noqa: T201 -- using print() because this is an interactive terminal program
    serial = usb_cdc.data
else:
    print("Using sys.stdio for serial IO with host")  # noqa: T201 -- using print() because this is an interactive terminal program

session = PromptSession(in_stream=serial, out_stream=serial)  # type: ignore -- CircuitPython Serial objects have no parents

while True:
    used_bytes = gc.mem_alloc()
    free_bytes = gc.mem_free()
    response = session.prompt(f"[{used_bytes / 1024:.3f} kB {free_bytes / 1024:.3f} kB] ")

    print(f"(echo)\n{response}", file=serial)
