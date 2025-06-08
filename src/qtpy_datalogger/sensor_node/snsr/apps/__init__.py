"""Matching sensor_node apps for their host-side qtpy_datalogger.apps."""


def get_catalog() -> list[str]:
    """Return a list of the selectable apps."""
    from os import listdir

    files = listdir(str(__path__))  # noqa: PTH208 -- pathlib not available on CircuitPython
    apps = [file.split(".")[0] for file in files if not file.startswith("__init__")]
    return apps


def get_handler(snsr_app_name: str) -> object:
    """Return the handler that matches snsr_app_name."""
    if snsr_app_name == "soil_swell":
        from .soil_swell import handle_message

        return handle_message

    # Fallback to echo app handler
    from . import echo

    return echo.handle_message
