"""Simple 'echo' app that repeats every message received."""

from snsr.node.classes import ActionInformation


def handle_message(received_action: ActionInformation) -> ActionInformation:
    """Handle a received action from the controlling host."""
    command = received_action.command
    if command == "custom":
        return handle_custom_action(received_action)
    return _get_default_result(received_action)


def handle_custom_action(received_action: ActionInformation) -> ActionInformation:
    """Handle the 'custom' action keyword."""
    custom_action = received_action.parameters["input"]
    if custom_action.startswith("qtpycmd "):
        parts = custom_action.split(" ")
        verb = parts[1]
        if verb == "query_apps":
            return handle_query_apps(received_action)
        if verb == "select_app":
            new_app = parts[2]
            return handle_select_app(received_action, new_app)
    return _get_default_result(received_action)


def handle_query_apps(received_action: ActionInformation) -> ActionInformation:
    """Handle the 'qtpycmd query_apps' action."""
    response_action = ActionInformation(
        command=received_action.parameters["input"],
        parameters={
            "output": [
                "echo",
                "SoilSwell",
            ]
        },
        message_id=received_action.message_id
    )
    return response_action


def handle_select_app(received_action: ActionInformation, selected_app: str) -> ActionInformation:
    """Handle the 'qtpycmd select_app {app_name}' action."""
    # if selected_app in app_index....
    response_action = ActionInformation(
        command=received_action.parameters["input"],
        parameters={
            "output": f"{selected_app} active"
        },
        message_id=received_action.message_id
    )
    return response_action



def _get_default_result(received_action: ActionInformation) -> ActionInformation:
    """Return the default response for this app."""
    response_action = ActionInformation(
        command=received_action.command,
        parameters={
            "output": f"received: {received_action.parameters['input']}",
            "complete": True,
        },
        message_id=received_action.message_id,
    )
    return response_action
