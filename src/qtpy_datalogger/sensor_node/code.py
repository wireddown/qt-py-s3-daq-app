"""code.py file is the main loop from qtpy_datalogger.sensor_node."""

from gc import collect
from time import monotonic, sleep
from traceback import print_exception

from snsr.core import paint_uart_line, read_one_uart_line
from snsr.node.mqtt import get_broadcast_topic, get_command_topic
from snsr.rxtx import connect_and_subscribe, create_mqtt_client, unsubscribe_and_disconnect
from snsr.settings import settings

settings.boot_time = monotonic()
print(f"Booted at {settings.boot_time:.3f}")

mqtt_topics = [
    get_broadcast_topic(settings.node_group),
    get_command_topic(settings.node_group, settings.mqtt_client_id),
]


def main_loop() -> str:
    """Run the main node loop."""
    settings.connect_to_wifi()
    mqtt_client = create_mqtt_client(settings.node_group, settings.mqtt_client_id)
    connect_and_subscribe(mqtt_client, mqtt_topics)

    response = ""
    while response.lower() not in ["exit", "quit"]:
        uart_connected = settings.uart_connected
        if uart_connected:
            paint_uart_line(f"  {settings.uptime:>12.3f}    Poll UART     [ Poll MQTT ]     ")
        did_receive = mqtt_client.loop(timeout=1.0)  # Smallest supported timeout
        if not (did_receive or uart_connected):
            sleep(4)  # Conserve battery by not constantly polling the network

        if uart_connected:
            paint_uart_line(f"  {settings.uptime:>12.3f}  [ Poll UART ]     Poll MQTT       ")
            sleep(0.2)
            if not settings.uart_bytes_waiting:
                continue
            print()
            response = read_one_uart_line()
            if not response:
                response = read_one_uart_line()
            print(f"Received '{response}' with {settings.used_kb:.3f} kB / {settings.free_kb:.3f} kB  (used/free)")

    unsubscribe_and_disconnect(mqtt_client, mqtt_topics)
    return response


most_recent_error = type(None)
error_count = 0
error_limit = 3
while True:
    print("Entering root loop")
    try:
        result = main_loop()
        if result.lower() in ["exit", "quit"]:
            print("Exiting to REPL...")
            break
    except Exception as e:
        print()
        print(f"Encountered {type(e)} {e.args}")
        print_exception(e)
        collect()
        if type(e) is most_recent_error:
            error_count = error_count + 1
            if error_count >= error_limit:
                raise
        else:
            most_recent_error = type(e)
            error_count = 0
        print("Trying again...")
        continue
