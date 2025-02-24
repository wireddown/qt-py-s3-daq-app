"""code.py file is the main loop from qtpy_datalogger.sensor_node."""  # noqa: INP001 -- this is the entry point for CircuitPython devices

from snsr.core import get_memory_info, read_one_uart_line


while True:
    response = read_one_uart_line()
    used_kB, free_kB = get_memory_info()
    print(f"Received '{response}' with {used_kB} / {free_kB}  (used/free)")

