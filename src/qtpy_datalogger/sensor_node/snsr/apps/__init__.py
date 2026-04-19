"""Matching sensor_node apps for their host-side qtpy_datalogger.apps."""

try:  # noqa: SIM105 -- contextlib is not available for CircuitPython
    from collections.abc import Callable
except ImportError:
    pass

from snsr.node.classes import ActionInformation


def get_catalog() -> list[str]:
    """Return a list of the selectable apps."""
    from os import listdir

    files = listdir(str(__path__))  # noqa: PTH208 -- pathlib not available on CircuitPython
    apps = [file.split(".")[0] for file in files if not file.startswith("__init__")]
    return apps


def get_handler(snsr_app_name: str) -> Callable[[ActionInformation], ActionInformation]:
    """Return the handler that matches snsr_app_name."""
    from snsr.apps import echo

    return echo.handle_message


def get_handler_completion(snsr_app_name: str) -> Callable[[ActionInformation], None]:
    """Return the completion that matches snsr_app_name."""
    from snsr.apps import echo

    return echo.did_handle_message
