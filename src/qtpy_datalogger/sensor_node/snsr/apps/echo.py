"""Simple 'echo' app that repeats every message received."""

import adafruit_minimqtt.adafruit_minimqtt as minimqtt

from snsr.node.classes import ActionInformation


def main(client: minimqtt.MQTT, context: dict) -> None:
    """Update the app's state from the main loop."""


def handle_message(received_action: ActionInformation, context: dict) -> ActionInformation:
    """Handle a received action from the controlling host."""
    response_action = ActionInformation(
        command=received_action.command,
        parameters={
            "output": f"received: {received_action.parameters['input']}",
            "complete": True,
        },
        message_id=received_action.message_id,
    )
    return response_action


def did_handle_message(received_action: ActionInformation, context: dict) -> None:
    """Update the node after handling a message."""
