"""Simple 'echo' app that repeats every message received."""

from snsr.apps import SnsrApp
from snsr.node.classes import ActionInformation


class EchoApp(SnsrApp):
    """Repeat every message received."""

    def handle_message(self) -> ActionInformation:
        """Handle a received action from the controlling host."""
        echo = self.action.parameters.get("input", self.action.command)
        response_action = ActionInformation(
            command=self.action.command,
            parameters={
                "output": f"received: {echo}",
                "complete": True,
            },
            message_id=self.action.message_id,
        )
        return response_action

    def did_handle_message(self) -> None:
        """Update the node after handling a message."""
