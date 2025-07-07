"""code.py file is the main loop from qtpy_datalogger.sensor_node."""  # noqa: INP001 -- this is the entry point for CircuitPython devices

from gc import collect
from time import monotonic, sleep
from traceback import print_exception

import adafruit_connection_manager
import wifi
from microcontroller import cpu
from snsr.core import get_memory_info, paint_uart_line, read_one_uart_line
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

def main_loop() -> None:
    """Run the main node loop."""
    radio = connect_to_wifi()
    sleep(5)
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

while True:
    print("running root loop")
    try:
        main_loop()
    except Exception as e:  # OSError as os_error: #
        print(f"\nReceived {type(e)} {e.args}") #
        print_exception(e)
        handlers = {
            116: 5,  # ETIMEDOUT
            118: 5,  # EHOSTUNREACH
            128: 2,  # ENOTCONN
        }
        if True:  # os_error.errno in handlers: #
            collect()
            socketpool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
            adafruit_connection_manager.connection_manager_close_all(socketpool, release_references=True)
            wifi.radio.enabled = False
            # sleep(handlers[os_error.errno]) #
            sleep(5)
            collect()
            print("Trying again...")
            continue
        print("raising")
        raise
