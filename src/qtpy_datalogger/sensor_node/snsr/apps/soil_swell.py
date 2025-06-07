"""Node-side soil_swell app that reads AI and I2C channels."""

from snsr.node.classes import ActionInformation


def handle_message(received_action: ActionInformation) -> ActionInformation:
    """Handle a received action from the controlling host."""
    response_action = ActionInformation(
        command=received_action.command,
        parameters={
            "output": f"soil_swell: {received_action.parameters['input']}",
            "complete": True,
        },
        message_id=received_action.message_id,
    )
    return response_action
