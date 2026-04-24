"""Functions that handle API commands."""

from json import dumps, loads

import adafruit_minimqtt.adafruit_minimqtt as minimqtt

from snsr.core import get_app
from snsr.node.classes import (
    ActionPayload,
    DescriptorInformation,
    DescriptorPayload,
    SenderInformation,
    StatusInformation,
)
from snsr.node.mqtt import get_descriptor_topic, get_result_topic
from snsr.settings import settings


def can_handle_message(message: str) -> None | ActionPayload:
    """Return an ActionPayload if the node can respond to the message."""
    if not message:
        return None
    try:
        action_payload_information = loads(message)
    except ValueError:
        return None
    try:
        action_payload = ActionPayload.from_dict(action_payload_information)
    except (KeyError, TypeError):
        return None
    return action_payload


def handle_broadcast_message(client: minimqtt.MQTT, action_payload: ActionPayload) -> None:
    """Respond to a message sent to the broadcast topic for the node's group."""
    action = action_payload.action
    if action.command == "identify":
        handle_identify(client)
        return

    # Fallback: forward to node as a command for retained group messages
    handle_command_message(client, action_payload)


def handle_identify(client: minimqtt.MQTT) -> None:
    """Respond to the the identify command."""
    descriptor_topic = get_descriptor_topic(settings.node_group, settings.mqtt_client_id)
    descriptor_payload = get_descriptor_payload(descriptor_topic)
    client.publish(descriptor_topic, dumps(descriptor_payload.as_dict()))


def handle_command_message(client: minimqtt.MQTT, action_payload: ActionPayload) -> None:
    """Respond to a message sent to the command topic for the node."""
    from time import sleep

    result_topic = get_result_topic(settings.node_group, settings.mqtt_client_id)
    descriptor_topic = get_descriptor_topic(settings.node_group, settings.mqtt_client_id)
    action_information = action_payload.action

    app = get_app(action_information)
    result_information = app.handle_message()

    sender = get_sender_information(descriptor_topic)
    result_payload = ActionPayload(result_information, sender)
    client.publish(result_topic, dumps(result_payload.as_dict()))
    sleep(0.2)  # Allow the backend to send the message before invoking the completion which may sleep

    app.did_handle_message()


def get_descriptor_payload(descriptor_topic: str) -> DescriptorPayload:
    """Return a serialized string representation of the DescriptorPayload."""
    descriptor = DescriptorInformation(
        node_id=settings.mqtt_client_id,
        serial_number=settings.serial_number,
        hardware_name=settings.board_id,
        system_name=f"python-{settings.micropython_base}",
        python_implementation=settings.python_implementation,
        ip_address=settings.ip_address,
        notice=settings.notice_info,
    )
    sender = get_sender_information(descriptor_topic)
    payload = DescriptorPayload(descriptor=descriptor, sender=sender)
    return payload


def get_sender_information(descriptor_topic: str) -> SenderInformation:
    """Return a SenderInformation instance describing the client's current state."""
    from time import monotonic

    used_kb = settings.used_kb
    free_kb = settings.free_kb
    cpu_celsius = settings.cpu_temperature
    now = monotonic()
    status = StatusInformation(
        used_memory=f"{used_kb:.3f}", free_memory=f"{free_kb:.3f}", cpu_temperature=str(cpu_celsius)
    )
    sender = SenderInformation(descriptor_topic=descriptor_topic, sent_at=str(now), status=status)
    return sender
