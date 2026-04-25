"""App that queries and demonstrates board resources like IO pins."""

from snsr.apps import SnsrApp
from snsr.node.classes import ActionInformation
from snsr.settings import settings


class QtpyCmdApp(SnsrApp):
    """Respond to 'custom' commands that start with 'qtpycmd '."""

    def handle_message(self) -> ActionInformation:
        """Handle a received action from the controlling host."""
        system_command = self.action.parameters["input"]
        parts = system_command.split(" ")
        verb = parts[1]
        if verb == "get_apps":
            return handle_get_apps(self.action)

        # Fallback to echo app
        from snsr.apps.echo import EchoApp

        echo = EchoApp(self.action)
        return echo.handle_message()

    def did_handle_message(self) -> None:
        """Update the node after handling a message."""


def handle_get_apps(received_action: ActionInformation) -> ActionInformation:
    """Handle the 'qtpycmd get_apps' action."""
    apps = settings.app_catalog
    response_action = ActionInformation(
        command=received_action.parameters["input"],
        parameters={
            "output": sorted(apps),
            "complete": True,
        },
        message_id=received_action.message_id,
    )
    return response_action
