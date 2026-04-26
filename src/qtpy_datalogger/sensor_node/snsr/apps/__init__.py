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


def use_echo(received_action: ActionInformation) -> ActionInformation:
    """Use echo to handle the action."""
    from snsr.apps.echo import create_app

    echo_app = create_app(received_action)
    return echo_app.handle_message()
