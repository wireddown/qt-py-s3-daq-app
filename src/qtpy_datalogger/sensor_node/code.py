"""code.py file is the main loop from qtpy_datalogger.sensor_node."""  # noqa: INP001 -- this is the entry point for CircuitPython devices

from microcontroller import cpu
from snsr.core import get_memory_info, read_one_uart_line, paint_uart_line
from snsr.rxtx import connect_to_wifi, create_mqtt_client, connect_and_subscribe, unsubscribe_and_disconnect
from supervisor import runtime
from time import sleep
from usb_cdc import console

radio = connect_to_wifi()

node_group = "centrifuge"
node_identifier = f"node-{cpu.uid.hex().lower()}-0"  # Matches boot_out.txt
mqtt_topics = [
    f"qtpy/v1/{node_group}/broadcast",
    f"qtpy/v1/{node_group}/{node_identifier}/command",
]
descriptor_topic = f"qtpy/v1/{node_group}/{node_identifier}/$DESCRIPTOR"
result_topic = f"qtpy/v1/{node_group}/{node_identifier}/result"

mqtt_client = create_mqtt_client(radio, node_group, node_identifier)
connect_and_subscribe(mqtt_client, mqtt_topics)

response = ""
while response.lower() not in ["exit", "quit"]:
    paint_uart_line(" [ Poll UART ]     Poll MQTT  ")
    sleep(0.2)
    if runtime.usb_connected and runtime.serial_connected and runtime.serial_bytes_available > 0:
        print()
        response = read_one_uart_line()
        if not response:
            response = read_one_uart_line()
        used_kB, free_kB = get_memory_info()
        print(f"Received '{response}' with {used_kB} / {free_kB}  (used/free)")

    paint_uart_line("   Poll UART     [ Poll MQTT ]")
    mqtt_client.loop()

unsubscribe_and_disconnect(mqtt_client, mqtt_topics)
