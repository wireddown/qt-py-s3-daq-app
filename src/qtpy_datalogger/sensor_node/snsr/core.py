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


def get_system_info() -> dict[str, str]:
    """Return a dictionary that describes the node."""
    return {}


def get_notice_info() -> dict:
    """Return a json representation of the notice.toml file."""
    import json

    notice_contents = []
    with open("/snsr/notice.toml", "r") as notice_toml:
        notice_contents = notice_toml.read().splitlines()
    notice_info = {}
    for line in notice_contents:
        key_and_value = line.split("=")
        key = key_and_value[0].strip()
        value = key_and_value[1].strip().replace('"', "")
        notice_info[key] = value
    return notice_info


def get_descriptor_payload():
    import json

    from snsr.node.classes import (
        DescriptorInformation,
        DescriptorPayload,
        NoticeInformation,
        SenderInformation,
        StatusInformation,
    )

    notice_info = get_notice_info()
    notice = NoticeInformation(**notice_info)
    descriptor = DescriptorInformation(node_id="me", hardware_name="esp", system_name="cpy", python_implementation="9.2.1", ip_address="wifi", notice=notice)
    status = StatusInformation(used_memory="xx kB", free_memory="yy kB", cpu_temperature="zz C")
    sender = SenderInformation(descriptor_topic="qtpy/v1/....", sent_at="now", status=status)
    response = DescriptorPayload(descriptor=descriptor, sender=sender)
    return json.dumps(response.as_dict())


def get_command_payload(message: str) -> dict[str, str]:
    import json

    from snsr.node.classes import ActionPayload

    action_payload = ActionPayload.from_dict(json.loads(message))
    return action_payload
