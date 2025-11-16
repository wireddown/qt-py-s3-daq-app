"""Matching sensor_node apps for their host-side qtpy_datalogger.apps."""


def get_catalog() -> list[str]:
    """Return a list of the selectable apps."""
    from os import listdir

    files = listdir(str(__path__))  # noqa: PTH208 -- pathlib not available on CircuitPython
    apps = [file.split(".")[0] for file in files if not file.startswith("__init__")]
    return apps


def get_context(snsr_app_name: str) -> dict:
    """Return the runtime context that matches snsr_app_name."""
    from snsr.settings import settings

    context = settings.apps.setdefault(snsr_app_name, {})
    return context


def get_main(snsr_app_name: str) -> object:
    """Return the main function that matches snsr_app_name."""
    if snsr_app_name == "soil_swell":
        from .soil_swell import main

        return main

    # Fallback to echo app handler
    from . import echo

    return echo.main


def get_handler(snsr_app_name: str) -> object:
    """Return the handler that matches snsr_app_name."""
    if snsr_app_name == "soil_swell":
        from .soil_swell import handle_message

        return handle_message

    # Fallback to echo app handler
    from . import echo

    return echo.handle_message


def get_handler_completion(snsr_app_name: str) -> object:
    """Return the completion that matches snsr_app_name."""
    if snsr_app_name == "soil_swell":
        from .soil_swell import did_handle_message

        return did_handle_message

    # Fallback to echo app handler
    from . import echo

    return echo.did_handle_message
