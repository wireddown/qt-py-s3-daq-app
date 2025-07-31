"""code.py file is the main loop from qtpy_datalogger.sensor_node."""  # noqa: INP001 -- this is the entry point for CircuitPython devices

from gc import collect
from time import monotonic, sleep
from traceback import print_exception

from microcontroller import cpu
from snsr.core import get_memory_info, get_neopixel, blink_neopixel, paint_uart_line, read_one_uart_line
from snsr.rxtx import connect_and_subscribe, connect_to_wifi, create_mqtt_client, unsubscribe_and_disconnect
from snsr.settings import settings
from supervisor import runtime

settings.boot_time = monotonic()
print(f"Booted at {settings.boot_time:.3f}")  # noqa: T201 -- use direct IO for user REPL

node_identifier = f"node-{cpu.uid.hex().lower()}-0"  # Matches boot_out.txt
mqtt_topics = [
    f"qtpy/v1/{settings.node_group}/broadcast",
    f"qtpy/v1/{settings.node_group}/{node_identifier}/command",
]

pixel = get_neopixel()

def main_loop() -> str:
    """Run the main node loop."""
    radio = connect_to_wifi()
    mqtt_client = create_mqtt_client(radio, settings.node_group, node_identifier)
    connect_and_subscribe(mqtt_client, mqtt_topics)

    response = ""
    while response.lower() not in ["exit", "quit"]:
        uptime = monotonic() - settings.boot_time
        paint_uart_line(f"  {uptime:>12.3f}    Poll UART     [ Poll MQTT ]     ")
        mqtt_client.loop()

        uptime = monotonic() - settings.boot_time
        paint_uart_line(f"  {uptime:>12.3f}  [ Poll UART ]     Poll MQTT       ")
        sleep(0.2)
        if runtime.usb_connected and runtime.serial_connected and runtime.serial_bytes_available > 0:
            print()  # noqa: T201 -- use direct IO for user REPL
            response = read_one_uart_line()
            if not response:
                response = read_one_uart_line()
            used_kb, free_kb = get_memory_info()
            print(f"Received '{response}' with {used_kb} / {free_kb}  (used/free)")  # noqa: T201 -- use direct IO for user REPL

    unsubscribe_and_disconnect(mqtt_client, mqtt_topics)
    return response


most_recent_error = type(None)
error_count = 0
while True:
    print("Entering root loop")  # noqa: T201 -- use direct IO for user REPL
    try:
        pixel.fill((0, 0, 0))
        pixel.show()
        result = main_loop()
        if result.lower() in ["exit", "quit"]:
            print("Exiting to REPL...")  # noqa: T201 -- use direct IO for user REPL
            break
    except Exception as e:
        blink_neopixel(pixel)
        print()  # noqa: T201 -- use direct IO for user REPL
        print(f"Encountered {type(e)} {e.args}")  # noqa: T201 -- use direct IO for user REPL
        print_exception(e)
        collect()
        if type(e) is most_recent_error:
            error_count = error_count + 1
            if error_count > 4:
                raise
        else:
            most_recent_error = type(e)
            error_count = 0
        print("Trying again...")  # noqa: T201 -- use direct IO for user REPL
        continue
