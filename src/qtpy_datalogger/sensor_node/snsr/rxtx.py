"""Classes and functions for control and communication over MQTT."""

import adafruit_minimqtt.adafruit_minimqtt as minimqtt

from snsr.handlers import (
    can_handle_message,
    handle_broadcast_message,
    handle_command_message,
)
from snsr.settings import settings


def on_connect(client: minimqtt.MQTT, userdata: object, flags: int, rc: int) -> None:
    """Handle connection to the MQTT broker."""


def on_disconnect(client: minimqtt.MQTT, userdata: object, rc: int) -> None:
    """Handle disconnection from the MQTT broker."""


def on_subscribe(client: minimqtt.MQTT, userdata: object, topic: str, granted_qos: int) -> None:
    """Handle subscription on the specified topic."""


def on_unsubscribe(client: minimqtt.MQTT, userdata: object, topic: str, pid: int) -> None:
    """Handle unsubscription from the specified topic."""


def on_publish(client: minimqtt.MQTT, userdata: object, topic: str, pid: int) -> None:
    """Handle a publication to the topic."""


def on_message(client: minimqtt.MQTT, topic: str, message: str) -> None:
    """Handle the specified message on the specified topic."""
    # > print(f"New message on topic {topic}: {message}")
    topic_parts = topic.split("/")
    last_part = topic_parts[-1]
    action_payload = can_handle_message(message)
    if not action_payload:
        return
    if last_part == "broadcast":
        handle_broadcast_message(client, action_payload)
    elif last_part == "command":
        handle_command_message(client, action_payload)


def create_mqtt_client(node_group: str, node_identifier: str) -> minimqtt.MQTT:
    """Create an MQTT client and set its callback functions."""
    from adafruit_connection_manager import get_radio_socketpool

    # Set up a MiniMQTT Client
    pool = get_radio_socketpool(settings.wifi_radio)
    mqtt_client = minimqtt.MQTT(
        broker=settings.mqtt_broker,
        socket_pool=pool,
        user_data={
            "node_group": node_group,
            "node_identifier": node_identifier,
        },
    )

    # Connect callback handlers to mqtt_client
    mqtt_client.on_connect = on_connect  # type: ignore -- we're assigning callbacks
    mqtt_client.on_disconnect = on_disconnect  # type: ignore -- we're assigning callbacks
    mqtt_client.on_subscribe = on_subscribe  # type: ignore -- we're assigning callbacks
    mqtt_client.on_unsubscribe = on_unsubscribe  # type: ignore -- we're assigning callbacks
    mqtt_client.on_publish = on_publish  # type: ignore -- we're assigning callbacks
    mqtt_client.on_message = on_message  # type: ignore -- we're assigning callbacks
    return mqtt_client


def connect_and_subscribe(mqtt_client: minimqtt.MQTT, topics: list[str]) -> None:
    """Connect the client to the MQTT broker and subscribe to the specified topics."""
    mqtt_client.connect()
    for topic in topics:
        mqtt_client.subscribe(topic)


def unsubscribe_and_disconnect(mqtt_client: minimqtt.MQTT, topics: list[str]) -> None:
    """Unsubscribe from the specified topics and disconnect from the MQTT broker."""
    for topic in topics:
        mqtt_client.unsubscribe(topic)
    mqtt_client.disconnect()


def do_full_client_publish(mqtt_client: minimqtt.MQTT, message: str) -> None:
    """Connect, publish, and disconnect."""
    mqtt_topic = "qtpy/v1/__group_id__/__node_id__/__example__"
    mqtt_client.connect()
    mqtt_client.subscribe(mqtt_topic)
    mqtt_client.publish(mqtt_topic, message)
    mqtt_client.unsubscribe(mqtt_topic)
    mqtt_client.disconnect()
