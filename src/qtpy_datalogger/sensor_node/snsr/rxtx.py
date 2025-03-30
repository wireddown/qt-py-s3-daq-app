"""Classes and functions for control and communication over MQTT."""

import os

import adafruit_connection_manager
import adafruit_minimqtt.adafruit_minimqtt as minimqtt
import wifi

from snsr.core import get_new_descriptor, get_notice_info
from snsr.node.classes import DescriptorInformation, NoticeInformation, SenderInformation
from snsr.node.mqtt import get_descriptor_topic, get_result_topic


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

        context: dict = client.user_data  # pyright: ignore reportAssignmentType -- the type for context is client-defined
        descriptor_topic = get_descriptor_topic(context["node_group"], context["node_identifier"])
        descriptor_message = get_descriptor_payload("node", cpu.uid.hex().lower(), str(radio.ipv4_address))
        client.publish(descriptor_topic, descriptor_message)
    elif last_part == "command":
        from json import dumps, loads

        from .node.classes import ActionInformation, ActionPayload

        context: dict = client.user_data  # pyright: ignore reportAssignmentType -- the type for context is client-defined
        action_payload_information = loads(message)
        action_payload = ActionPayload.from_dict(action_payload_information)
        action = action_payload.action
        descriptor_topic = get_descriptor_topic(context["node_group"], context["node_identifier"])
        sender = build_sender_information(descriptor_topic)
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
        result_topic = get_result_topic(context["node_group"], context["node_identifier"])
        client.publish(result_topic, dumps(result_payload.as_dict()))


def create_mqtt_client(radio: wifi.Radio, node_group: str, node_identifier: str) -> minimqtt.MQTT:
    """Create an MQTT client and set its callback functions."""
    # Set up a MiniMQTT Client
    pool = adafruit_connection_manager.get_radio_socketpool(radio)
    mqtt_client = minimqtt.MQTT(
        broker=os.getenv("QTPY_BROKER_IP_ADDRESS", ""),
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


def get_descriptor_payload(role: str, serial_number: str, ip_address: str) -> str:
    """Return a serialized string representation of the DescriptorPayload."""
    import json

    from snsr.node.classes import DescriptorPayload
    from snsr.node.mqtt import format_mqtt_client_id, get_descriptor_topic

    pid = 0
    group_id = os.getenv("QTPY_NODE_GROUP", "zone1")  # See https://github.com/wireddown/qt-py-s3-daq-app/issues/60

    descriptor = build_descriptor_information(role, serial_number, ip_address)
    client_id = format_mqtt_client_id(role, serial_number, pid)
    descriptor_topic = get_descriptor_topic(group_id, client_id)
    sender = build_sender_information(descriptor_topic)
    response = DescriptorPayload(descriptor=descriptor, sender=sender)
    return json.dumps(response.as_dict())


def build_descriptor_information(role: str, serial_number: str, ip_address: str) -> DescriptorInformation:
    """Return a DescriptorInformation instance describing and identifying the client."""
    from os import uname
    from sys import implementation, version_info

    from board import board_id

    pid = 0
    system_info = uname()
    micropython_base = ".".join([f"{version_number}" for version_number in version_info])
    python_implementation = f"{implementation.name}-{system_info.release}"
    notice_info = get_notice_info()
    notice = NoticeInformation(**notice_info)

    descriptor = get_new_descriptor(
        role=role,
        serial_number=serial_number,
        pid=pid,
        hardware_name=board_id,
        micropython_base=micropython_base,
        python_implementation=python_implementation,
        ip_address=ip_address,
        notice=notice,
    )
    return descriptor


def build_sender_information(descriptor_topic: str) -> SenderInformation:
    """Return a SenderInformation instance describing the client's current state."""
    import gc
    from time import monotonic

    from microcontroller import cpu

    from snsr.node.classes import SenderInformation, StatusInformation

    used_bytes = gc.mem_alloc()
    free_bytes = gc.mem_free()
    cpu_celsius = cpu.temperature
    monotonic_time = monotonic()
    status = StatusInformation(
        used_memory=str(used_bytes), free_memory=str(free_bytes), cpu_temperature=str(cpu_celsius)
    )
    sender = SenderInformation(descriptor_topic=descriptor_topic, sent_at=str(monotonic_time), status=status)
    return sender
