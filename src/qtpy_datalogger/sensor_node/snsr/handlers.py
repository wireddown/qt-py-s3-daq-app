"""Functions that handle API commands."""

import adafruit_minimqtt.adafruit_minimqtt as minimqtt

from snsr import apps
from snsr.core import get_new_descriptor, get_notice_info
from snsr.node.classes import (
    ActionInformation,
    ActionPayload,
    DescriptorInformation,
    NoticeInformation,
    SenderInformation,
)
from snsr.node.mqtt import get_descriptor_topic, get_result_topic
from snsr.settings import settings


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

    context: dict = client.user_data  # pyright: ignore reportAssignmentType -- the type for context is client-defined
    action_payload_information = loads(message)
    action_payload = ActionPayload.from_dict(action_payload_information)
    action_information = action_payload.action

    result_information = try_handle_qtpycmd_message(action_information)
    if not result_information:
        handle_message = apps.get_handler(settings.selected_app)
        result_information = handle_message(action_information)

    descriptor_topic = get_descriptor_topic(context["node_group"], context["node_identifier"])
    sender = build_sender_information(descriptor_topic)
    result_payload = ActionPayload(action=result_information, sender=sender)
    result_topic = get_result_topic(context["node_group"], context["node_identifier"])
    client.publish(result_topic, dumps(result_payload.as_dict()))


def try_handle_qtpycmd_message(action_information: ActionInformation) -> ActionInformation | None:
    """Handle the action if it is a 'qtpycmd' system action. Return None otherwise."""
    if action_information.command == "custom" and action_information.parameters["input"].startswith("qtpycmd "):
        system_command = action_information.parameters["input"]
        parts = system_command.split(" ")
        verb = parts[1]
        if verb == "query_apps":
            return handle_query_apps(action_information)
        if verb == "select_app":
            new_app = parts[2]
            return handle_select_app(action_information, new_app)
    return None


def handle_query_apps(received_action: ActionInformation) -> ActionInformation:
    """Handle the 'qtpycmd query_apps' action."""
    response_action = ActionInformation(
        command=received_action.parameters["input"],
        parameters={
            "output": apps.get_catalog(),
            "complete": True,
        },
        message_id=received_action.message_id
    )
    return response_action


def handle_select_app(received_action: ActionInformation, selected_app: str) -> ActionInformation | None:
    """Handle the 'qtpycmd select_app {app_name}' action. Return None if the app is not in the catalog."""
    if selected_app not in apps.get_catalog():
        return None

    settings.selected_app = selected_app
    response_action = ActionInformation(
        command=received_action.parameters["input"],
        parameters={
            "output": f"{selected_app} active",
            "complete": True,
        },
        message_id=received_action.message_id
    )
    return response_action


def get_descriptor_payload(role: str, serial_number: str, ip_address: str) -> str:
    """Return a serialized string representation of the DescriptorPayload."""
    from json import dumps

    from snsr.node.classes import DescriptorPayload
    from snsr.node.mqtt import format_mqtt_client_id, get_descriptor_topic

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
