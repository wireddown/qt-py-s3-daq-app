"""Core classes and functions."""


def read_one_uart_line() -> str:
    """Read characters from the USB UART until a newline."""
    import usb_cdc

    from snsr.pysh.py_shell import prompt

    # Using sys.stdio for serial IO with host
    serial = usb_cdc.console
    if usb_cdc.data:
        # Switching to usb_cdc.data for serial IO with host
        serial = usb_cdc.data

    line = prompt(message="[uart] ", in_stream=serial, out_stream=serial)  # type: ignore -- CircuitPython Serial objects have no parents
    _ = serial.read(serial.in_waiting)
    return line


def paint_uart_line(line: str) -> None:
    """Erase and redraw the line with terminal control codes."""
    import usb_cdc

    from snsr.pysh.py_shell import redraw_line

    # Using sys.stdio for serial IO with host
    serial = usb_cdc.console
    if usb_cdc.data:
        # Switching to usb_cdc.data for serial IO with host
        serial = usb_cdc.data

    redraw_line(line, out_stream=serial)


def get_memory_info() -> tuple[str, str]:
    """Return a tuple of formatted strings with used and free memory."""
    import gc

    used_bytes = gc.mem_alloc()
    free_bytes = gc.mem_free()
    return f"{used_bytes / 1024:.3f} kB", f"{free_bytes / 1024:.3f} kB"
