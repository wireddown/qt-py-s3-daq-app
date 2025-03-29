"""Core classes and functions."""

from snsr.node.classes import DescriptorInformation, NoticeInformation


def read_one_uart_line() -> str:
    """Read characters from the USB UART until a newline."""
    import usb_cdc

    from snsr.pysh.py_shell import prompt

    # Using sys.stdio for serial IO with host
    serial = usb_cdc.console
    if usb_cdc.data:
        # Switching to usb_cdc.data for serial IO with host
        serial = usb_cdc.data

    if not serial:
        return ""

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

    redraw_line(line, out_stream=serial)  # type: ignore -- CircuitPython Serial objects have no parents


def get_memory_info() -> tuple[str, str]:
    """Return a tuple of formatted strings with used and free memory."""
    import gc

    used_bytes = gc.mem_alloc()
    free_bytes = gc.mem_free()
    return f"{used_bytes / 1024:.3f} kB", f"{free_bytes / 1024:.3f} kB"


def get_notice_info() -> dict:
    """Return a serializable representation of the notice.toml file."""
    notice_contents = []
    with open("/snsr/notice.toml") as notice_toml:  # noqa: PTH123 -- Path.open() is not available on CircuitPython
        notice_contents = notice_toml.read().splitlines()
    notice_info = {}
    for line in notice_contents:
        key_and_value = line.split("=")
        key = key_and_value[0].strip()
        value = key_and_value[1].strip().replace('"', "")
        notice_info[key] = value
    return notice_info


def get_new_descriptor(  # noqa: PLR0913 -- allow more than 5 parameters for this function
    role: str,
    serial_number: str,
    pid: int,
    hardware_name: str,
    micropython_base: str,
    python_implementation: str,
    ip_address: str,
    notice: NoticeInformation,
) -> DescriptorInformation:
    """Return a DescriptorInformation instance using the specified parameters."""
    from snsr.node.mqtt import format_mqtt_client_id

    descriptor = DescriptorInformation(
        node_id=format_mqtt_client_id(role, serial_number, pid),
        serial_number=serial_number,
        hardware_name=hardware_name,
        system_name=f"python-{micropython_base}",
        python_implementation=python_implementation,
        ip_address=ip_address,
        notice=notice,
    )
    return descriptor
