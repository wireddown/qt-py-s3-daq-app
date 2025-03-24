"""Classes and functions for control communication over MQTT."""

import os

import adafruit_connection_manager
import adafruit_minimqtt.adafruit_minimqtt as minimqtt
import wifi

_BROKER_IP_ADDRESS = "192.168.0.167"


def connect_to_wifi() -> wifi.Radio:
    """Connect to the SSID from settings.toml and return the radio instance."""
    wifi.radio.enabled = True
    wifi.radio.connect(os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD"))
    return wifi.radio


def disconnect_from_wifi(wifi: wifi.Radio) -> None:
    """Disconnect and disable the WiFi radio."""
    wifi.enabled = False


def format_wifi_information(wifi: wifi.Radio) -> list[str]:
    """Print details about the WiFi connection."""
    if not wifi.ap_info:
        return []

    lines = [
        "Connected to WiFi",
        "",
        "     Network information",
        f"Hostname: {wifi.hostname}",
        f"Tx Power: {wifi.tx_power} dBm",
        f"IP:       {wifi.ipv4_address}",
        f"DNS:      {wifi.ipv4_dns}",
        f"SSID:     {wifi.ap_info.ssid}",
        f"RSSI:     {wifi.ap_info.rssi} dBm",
        "",
    ]
    return lines


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
    if last_part == "broadcast":
        from microcontroller import cpu
        from wifi import radio

        from .core import get_descriptor_payload

        context: dict = client.user_data
        descriptor_topic = f"qtpy/v1/{context['node_group']}/{context['node_identifier']}/$DESCRIPTOR"
        descriptor_message = get_descriptor_payload("node", cpu.uid.hex().lower(), str(radio.ipv4_address))
        client.publish(descriptor_topic, descriptor_message)
    elif last_part == "command":
        from json import dumps, loads

        from .core import build_sender_information
        from .node.classes import ActionInformation, ActionPayload

        context: dict = client.user_data
        result_topic = f"qtpy/v1/{context['node_group']}/{context['node_identifier']}/result"
        action_payload_information = loads(message)
        action_payload = ActionPayload.from_dict(action_payload_information)
        action = action_payload.action
        sender = build_sender_information(f"qtpy/v1/{context['node_group']}/{context['node_identifier']}/$DESCRIPTOR")
        result_payload = ActionPayload(
            action=ActionInformation(
                command=action.command,
                parameters={
                    "output": f"received: {action.parameters['input']}",
                    "complete": True,
                },
                message_id=action.message_id,
            ),
            sender=sender,
        )
        client.publish(result_topic, dumps(result_payload.as_dict()))


def create_mqtt_client(radio: wifi.Radio, node_group: str, node_identifier: str) -> minimqtt.MQTT:
    """Create an MQTT client and set its callback functions."""
    # Set up a MiniMQTT Client
    pool = adafruit_connection_manager.get_radio_socketpool(radio)
    mqtt_client = minimqtt.MQTT(
        broker=_BROKER_IP_ADDRESS,
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
