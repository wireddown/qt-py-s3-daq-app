"""Classes and functions for control communication over MQTT."""

import os

import adafruit_connection_manager
import adafruit_minimqtt.adafruit_minimqtt as minimqtt
import wifi

_BROKER_IP_ADDRESS = "192.168.0.167"


def connect_to_wifi() -> wifi.Radio:
    """Connect to the SSID from settings.toml and return the radio instance."""
    wifi.radio.connect(os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD"))
    print("Connected to WiFi")

    print()
    print("     Network information")
    print(f"Hostname: {wifi.radio.hostname}")
    print(f"Tx Power: {wifi.radio.tx_power} dBm")
    print(f"IP:       {wifi.radio.ipv4_address}")
    print(f"DNS:      {wifi.radio.ipv4_dns}")
    print(f"SSID:     {wifi.radio.ap_info.ssid}")
    print(f"RSSI:     {wifi.radio.ap_info.rssi} dBm")
    print()

    return wifi.radio

# Define callback methods which are called when events occur
def connect(mqtt_client, userdata, flags, rc):
    # This function will be called when the mqtt_client is connected
    # successfully to the broker.
    print("Connected to MQTT Broker!")
    print(f"Flags: {flags}\n RC: {rc}")


def disconnect(mqtt_client, userdata, rc):
    # This method is called when the mqtt_client disconnects
    # from the broker.
    print("Disconnected from MQTT Broker!")


def subscribe(mqtt_client, userdata, topic, granted_qos):
    # This method is called when the mqtt_client subscribes to a new feed.
    print(f"Subscribed to {topic} with QOS level {granted_qos}")


def unsubscribe(mqtt_client, userdata, topic, pid):
    # This method is called when the mqtt_client unsubscribes from a feed.
    print(f"Unsubscribed from {topic} with PID {pid}")


def publish(mqtt_client, userdata, topic, pid):
    # This method is called when the mqtt_client publishes data to a feed.
    print(f"Published to {topic} with PID {pid}")


def message(client, topic, message):
    print(f"New message on topic {topic}: {message}")
    topic_parts = topic.split("/")
    last_part = topic_parts[-1]
    if last_part == "broadcast":
        from .core import get_descriptor_payload
        descriptor_topic = f"qtpy/v1/{client.user_data['node_group']}/{client.user_data['node_identifier']}/$DESCRIPTOR"
        descriptor_message = get_descriptor_payload()
        client.publish(descriptor_topic, descriptor_message)
    elif last_part == "command":
        from .core import get_command_payload
        result_topic = f"qtpy/v1/{client.user_data['node_group']}/{client.user_data['node_identifier']}/result"
        command_information = get_command_payload(message)
        client.publish(result_topic, f"{command_information.as_dict()}")


def create_mqtt_client(radio, node_group: str, node_identifier: str) -> minimqtt.MQTT:
    """Create an MQTT client and set its callback functions."""
    # Set up a MiniMQTT Client
    pool = adafruit_connection_manager.get_radio_socketpool(radio)
    mqtt_client = minimqtt.MQTT(
        broker=_BROKER_IP_ADDRESS,
        socket_pool=pool,
        user_data={
            "node_group": node_group,
            "node_identifier": node_identifier,
        }
    )

    # Connect callback handlers to mqtt_client
    mqtt_client.on_connect = connect
    mqtt_client.on_disconnect = disconnect
    mqtt_client.on_subscribe = subscribe
    mqtt_client.on_unsubscribe = unsubscribe
    mqtt_client.on_publish = publish
    mqtt_client.on_message = message
    return mqtt_client


def connect_and_subscribe(mqtt_client, topics: list[str]) -> None:
    mqtt_client.connect()
    for topic in topics:
        mqtt_client.subscribe(topic)


def unsubscribe_and_disconnect(mqtt_client, topics: list[str]) -> None:
    for topic in topics:
        mqtt_client.unsubscribe(topic)
    mqtt_client.disconnect()


def do_full_client_publish(mqtt_client, message) -> None:
    """Connect, publish, and disconnect."""
    mqtt_topic = "qtpy/snsr/__serial_number__/status"

    print(f"Attempting to connect to {mqtt_client.broker}")
    mqtt_client.connect()

    print(f"Subscribing to {mqtt_topic}")
    mqtt_client.subscribe(mqtt_topic)

    print(f"Publishing to {mqtt_topic}")
    mqtt_client.publish(mqtt_topic, message)

    print(f"Unsubscribing from {mqtt_topic}")
    mqtt_client.unsubscribe(mqtt_topic)

    print(f"Disconnecting from {mqtt_client.broker}")
    mqtt_client.disconnect()
