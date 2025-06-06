"""Functions that handle API commands."""

import adafruit_minimqtt.adafruit_minimqtt as minimqtt

from snsr.core import get_new_descriptor, get_notice_info
from snsr.node.classes import (
    ActionInformation,
    ActionPayload,
    DescriptorInformation,
    NoticeInformation,
    SenderInformation,
)
from snsr.node.mqtt import get_descriptor_topic, get_result_topic


def handle_broadcast_message(client: minimqtt.MQTT, message: str) -> None:
    """Respond to a message sent to the broadcast topic for the node's group."""
    from json import loads

    action_payload_information = loads(message)
    action_payload = ActionPayload.from_dict(action_payload_information)
    action = action_payload.action
    if action.command == "identify":
        handle_identify(client, action)

def handle_identify(client: minimqtt.MQTT, action: ActionInformation) -> None:
    """Respond to the the identify command."""
    from microcontroller import cpu
    from wifi import radio

    context: dict = client.user_data  # pyright: ignore reportAssignmentType -- the type for context is client-defined
    descriptor_topic = get_descriptor_topic(context["node_group"], context["node_identifier"])
    descriptor_message = get_descriptor_payload("node", cpu.uid.hex().lower(), str(radio.ipv4_address))
    client.publish(descriptor_topic, descriptor_message)


def handle_command_message(client: minimqtt.MQTT, message: str) -> None:
    """Respond to a message sent to the command topic for the node."""
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


def get_descriptor_payload(role: str, serial_number: str, ip_address: str) -> str:
    """Return a serialized string representation of the DescriptorPayload."""
    from json import dumps

    from snsr.node.classes import DescriptorPayload
    from snsr.node.mqtt import format_mqtt_client_id, get_descriptor_topic
    from snsr.settings import settings

    pid = 0
    descriptor = build_descriptor_information(role, serial_number, ip_address)
    client_id = format_mqtt_client_id(role, serial_number, pid)
    descriptor_topic = get_descriptor_topic(settings.node_group, client_id)
    sender = build_sender_information(descriptor_topic)
    response = DescriptorPayload(descriptor=descriptor, sender=sender)
    return dumps(response.as_dict())


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
    from gc import mem_alloc, mem_free
    from time import monotonic

    from microcontroller import cpu

    from snsr.node.classes import SenderInformation, StatusInformation

    used_bytes = mem_alloc()
    free_bytes = mem_free()
    cpu_celsius = cpu.temperature
    monotonic_time = monotonic()
    status = StatusInformation(
        used_memory=str(used_bytes), free_memory=str(free_bytes), cpu_temperature=str(cpu_celsius)
    )
    sender = SenderInformation(descriptor_topic=descriptor_topic, sent_at=str(monotonic_time), status=status)
    return sender
