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
    """Return a serializable representation of the notice.toml file."""
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


def build_descriptor_information(role: str, serial_number: str, ip_address: str):
    from os import uname
    from sys import implementation, version_info

    from board import board_id

    from snsr.node.classes import NoticeInformation

    pid = 0
    system_info = uname()
    micropython_base = ".".join([f"{version_number}" for version_number in version_info])
    python_implementation = f"{implementation.name}-{system_info.release}"
    notice_info = get_notice_info()
    notice = NoticeInformation(**notice_info)

    descriptor = _build_descriptor(
        role=role,
        serial_number=serial_number,
        pid=pid,
        hardware_name=board_id,
        micropython_base=micropython_base,
        python_implementation=python_implementation,
        ip_address=ip_address,
        notice=notice,
    )
    return descriptor


def _build_descriptor(
    role, serial_number, pid, hardware_name, micropython_base, python_implementation, ip_address, notice
):
    from snsr.node.classes import DescriptorInformation
    from snsr.node.mqtt import format_mqtt_client_id

    descriptor = DescriptorInformation(
        node_id=format_mqtt_client_id(role, serial_number, pid),
        serial_number=serial_number,
        hardware_name=hardware_name,
        system_name=micropython_base,
        python_implementation=python_implementation,
        ip_address=ip_address,
        notice=notice,
    )
    return descriptor


def build_sender_information(descriptor_topic: str):
    import gc
    from time import monotonic

    from microcontroller import cpu

    from snsr.node.classes import SenderInformation, StatusInformation

    used_bytes = gc.mem_alloc()
    free_bytes = gc.mem_free()
    cpu_celsius = cpu.temperature
    monotonic_time = monotonic()
    status = StatusInformation(
        used_memory=str(used_bytes), free_memory=str(free_bytes), cpu_temperature=str(cpu_celsius)
    )
    sender = SenderInformation(descriptor_topic=descriptor_topic, sent_at=str(monotonic_time), status=status)
    return sender


def get_descriptor_payload(role: str, serial_number: str, ip_address: str) -> str:
    import json

    from snsr.node.classes import DescriptorPayload
    from snsr.node.mqtt import format_mqtt_client_id, get_descriptor_topic

    pid = 0
    group_id = "centrifuge"

    descriptor = build_descriptor_information(role, serial_number, ip_address)
    client_id = format_mqtt_client_id(role, serial_number, pid)
    descriptor_topic = get_descriptor_topic(group_id, client_id)
    sender = build_sender_information(descriptor_topic)
    response = DescriptorPayload(descriptor=descriptor, sender=sender)
    return json.dumps(response.as_dict())
