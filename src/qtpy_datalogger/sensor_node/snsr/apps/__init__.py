"""Matching sensor_node apps for their host-side qtpy_datalogger.apps."""

from snsr.node.classes import ActionInformation


class SnsrApp:
    """Base class for sensor_node apps."""

    def __init__(self, action_information: ActionInformation) -> None:
        """Initialize a new SnsrApp."""
        self.action = action_information

    def handle_message(self) -> ActionInformation:
        """Handle a received action from the controlling host."""
        raise NotImplementedError()

    def did_handle_message(self) -> None:
        """Update the node after handling a message."""
        raise NotImplementedError()


def get_catalog() -> list[str]:
    """Return a list of the selectable apps."""
    from os import listdir

    files = listdir(str(__path__))
    apps = [file.split(".")[0] for file in files if not file.startswith("__init__")]
    return apps


def get_app(received_action: ActionInformation) -> SnsrApp:
    """Return the sensor_node app that matches received_action."""
    snsr_app_name = received_action.command.split(" ")[0]
    if snsr_app_name == "custom" and received_action.parameters["input"].startswith("qtpycmd "):
        from snsr.apps.qtpycmd import QtpyCmdApp

        return QtpyCmdApp(received_action)

    # Fallback to echo app handler
    from snsr.apps.echo import EchoApp

    return EchoApp(received_action)
