"""Core functions for the sensor_node runtime."""

import analogio

from snsr.apps import SnsrApp
from snsr.node.classes import ActionInformation
from snsr.settings import settings


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


def get_app(received_action: ActionInformation) -> SnsrApp:
    """Return the sensor_node app that matches received_action."""
    snsr_app_name = received_action.command.split(" ")[0]
    if snsr_app_name == "custom" and received_action.parameters["input"].startswith("qtpycmd "):
        snsr_app_name = "qtpycmd"
    if snsr_app_name not in settings.app_catalog:
        snsr_app_name = "echo"

    snsr_app_module = __import__(f"snsr/apps/{snsr_app_name}")
    app = snsr_app_module.create_app(received_action)
    return app


def blink_neopixel(color: int) -> None:
    """Blink the NeoPixel three times with the specified RGB color."""
    from time import sleep

    pixel = settings.get_neopixel()
    for _ in range(3):
        pixel.fill(color)
        pixel.show()
        sleep(0.2)
        pixel.fill(0)
        pixel.show()
        sleep(0.2)
    settings.release_neopixel()


def do_analog_scan(channels: list[str], count: int) -> list[float]:
    """Read the specified AI channels 'count' times each and return a list of averaged codes."""
    results = []
    analog_input_channels = [settings.get_ai_pin(pin_name) for pin_name in channels]
    for analog_input in analog_input_channels:
        average_channel_code = adc_take_n(analog_input, count)
        results.append(average_channel_code)
    for pin_name in channels:
        settings.release_pin(pin_name)
    return results


def adc_take_n(ai_pin: analogio.AnalogIn, count: int) -> float:
    """Read ai_pin 'count' times and return the average code."""
    total = 0.0
    for _ in range(count):
        total = total + ai_pin.value
    average = total / count
    return average
