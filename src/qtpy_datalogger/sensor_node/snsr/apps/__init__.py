"""Matching sensor_node apps for their host-side qtpy_datalogger.apps."""


def get_handler(selected_app: str) -> object:
    """Return the handler that matches the selected_app."""
    if selected_app == "echo":
        from .echo import handle_message

        return handle_message
    raise NotImplementedError(selected_app)
