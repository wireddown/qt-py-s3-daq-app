"""Functions that handle API commands."""

from json import dumps, loads

import adafruit_minimqtt.adafruit_minimqtt as minimqtt
from microcontroller import cpu

from snsr import apps
from snsr.node.classes import (
    ActionInformation,
    ActionPayload,
    DescriptorInformation,
    SenderInformation,
)
from snsr.node.mqtt import get_descriptor_topic
from snsr.settings import settings


def can_handle_message(message: str) -> None | ActionPayload:
    """Return an ActionPayload if the node can respond to the message."""
    if not message:
        return None
    try:
        action_payload_information = loads(message)
    except ValueError:
        return None
    action_payload = ActionPayload.from_dict(action_payload_information)
    return action_payload


def handle_broadcast_message(client: minimqtt.MQTT, action_payload: ActionPayload) -> None:
    """Respond to a message sent to the broadcast topic for the node's group."""
    action = action_payload.action
    if action.command == "identify":
        handle_identify(client)
        return

    # Fallback: forward to node as a command
    handle_command_message(client, action_payload)


def handle_identify(client: minimqtt.MQTT) -> None:
    """Respond to the the identify command."""
    from wifi import radio

    context: dict = client.user_data  # pyright: ignore reportAssignmentType -- the type for context is client-defined
    descriptor_topic = get_descriptor_topic(context["node_group"], context["node_identifier"])
    descriptor_message = get_descriptor_payload("node", cpu.uid.hex().lower(), str(radio.ipv4_address))
    client.publish(descriptor_topic, descriptor_message)


def handle_command_message(client: minimqtt.MQTT, action_payload: ActionPayload) -> None:
    """Respond to a message sent to the command topic for the node."""
    from time import sleep

    from snsr.node.mqtt import get_result_topic

    node_context: dict = client.user_data  # pyright: ignore reportAssignmentType -- the type for context is client-defined
    action_information = action_payload.action

    result_information = try_handle_qtpycmd_message(action_information)
    snsr_app_name = ""
    if not result_information:
        snsr_app_name = action_information.command.split(" ")[0]
        handle_message = apps.get_handler(snsr_app_name)
        result_information = handle_message(action_information)

    descriptor_topic = get_descriptor_topic(node_context["node_group"], node_context["node_identifier"])
    sender = build_sender_information(descriptor_topic)
    result_payload = ActionPayload(result_information, sender)
    result_topic = get_result_topic(node_context["node_group"], node_context["node_identifier"])
    client.publish(result_topic, dumps(result_payload.as_dict()))
    sleep(0.2)  # Allow the backend to send the message

    did_handle_message = apps.get_handler_completion(snsr_app_name)
    did_handle_message(action_information)


def try_handle_qtpycmd_message(action_information: ActionInformation) -> None | ActionInformation:
    """Handle the action if it is a 'qtpycmd' system action. Return None otherwise."""
    if action_information.command == "custom" and action_information.parameters["input"].startswith("qtpycmd "):
        system_command = action_information.parameters["input"]
        parts = system_command.split(" ")
        verb = parts[1]
        if verb == "get_apps":
            return handle_get_apps(action_information)
    return None


def handle_get_apps(received_action: ActionInformation) -> ActionInformation:
    """Handle the 'qtpycmd get_apps' action."""
    response_action = ActionInformation(
        command=received_action.parameters["input"],
        parameters={
            "output": apps.get_catalog(),
            "complete": True,
        },
        message_id=received_action.message_id,
    )
    return response_action


def get_descriptor_payload(role: str, serial_number: str, ip_address: str) -> str:
    """Return a serialized string representation of the DescriptorPayload."""
    from snsr.node.classes import DescriptorPayload
    from snsr.node.mqtt import format_mqtt_client_id

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

    from snsr.core import get_new_descriptor, get_notice_info
    from snsr.node.classes import NoticeInformation

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

    from snsr.node.classes import StatusInformation

    used_bytes = mem_alloc()
    free_bytes = mem_free()
    cpu_celsius = cpu.temperature
    monotonic_time = monotonic()
    status = StatusInformation(
        used_memory=str(used_bytes), free_memory=str(free_bytes), cpu_temperature=str(cpu_celsius)
    )
    sender = SenderInformation(descriptor_topic=descriptor_topic, sent_at=str(monotonic_time), status=status)
    return sender
