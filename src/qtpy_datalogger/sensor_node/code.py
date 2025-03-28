"""code.py file is the main loop from qtpy_datalogger.sensor_node."""  # noqa: INP001 -- this is the entry point for CircuitPython devices

from time import sleep

from snsr.core import get_memory_info, paint_uart_line, read_one_uart_line
from supervisor import runtime

response = ""
while response.lower() not in ["exit", "quit"]:
    paint_uart_line("   Poll UART     [ Poll MQTT ]")
    sleep(1.0)

    paint_uart_line(" [ Poll UART ]     Poll MQTT  ")
    sleep(0.2)
    if runtime.usb_connected and runtime.serial_connected and runtime.serial_bytes_available > 0:
        print()  # noqa: T201 -- use direct IO for user REPL
        response = read_one_uart_line()
        if not response:
            response = read_one_uart_line()
        used_kb, free_kb = get_memory_info()
        print(f"Received '{response}' with {used_kb} / {free_kb}  (used/free)")  # noqa: T201 -- use direct IO for user REPL
