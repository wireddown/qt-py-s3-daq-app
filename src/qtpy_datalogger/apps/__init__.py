"""Apps for qtpy_datalogger."""

import logging
import runpy
from enum import StrEnum
from typing import NamedTuple

from qtpy_datalogger.datatypes import ExitCode

logger = logging.getLogger(__name__)


class Behavior(StrEnum):
    """Supported app start behaviors for qtpy_datalogger."""

    App = "App"
    List = "List"
    Module = "Module"


class AppInformation(NamedTuple):
    """Contains details about a qtpy_datalogger app."""

    name: str
    location: str


class Catalog:
    """Apps for qtpy_datalogger."""

    default_app = AppInformation("ttkbootstrap-demo", "ttkbootstrap.__main__")
    index = frozenset(
        {
            default_app,
            AppInformation("async-demo", "qtpy_datalogger.guikit"),
            AppInformation("scanner", "qtpy_datalogger.apps.scanner"),
            AppInformation("data-viewer", "qtpy_datalogger.apps.data_viewer"),
            AppInformation("8ch-adc-with-adxl", "#TODO"),
        }
    )

    @staticmethod
    def get_entries() -> list[str]:
        """Get the list of apps in the catalog."""
        all_names = sorted(e.name for e in Catalog.index)
        return all_names

    @staticmethod
    def get_location(name: str) -> str:
        """Get an app's location by its name."""
        for app_info in Catalog.index:
            if app_info.name == name:
                return app_info.location
        return Catalog.default_app.location


def handle_run(behavior: Behavior, app_name: str) -> None:
    """Handle the run CLI command."""
    logger.debug(f"behavior: '{behavior}', app_name: '{app_name}'")

    if behavior == Behavior.List:
        app_names = Catalog.get_entries()
        logger.info("Available QT Py datalogger apps")
        _ = [logger.info(f"- {name}") for name in app_names]
        raise SystemExit(ExitCode.Success)

    if behavior == Behavior.Module:
        logger.info(f"Running custom module '{app_name}'")
        location = app_name
    else:
        logger.info(f"Running app '{app_name}'")
        location = Catalog.get_location(app_name)

    try:
        runpy.run_module(location, run_name="__main__")
    except ImportError as e:
        if behavior == Behavior.Module:
            logger.error(f"The module '{app_name}' does not exist. Is it spelled correctly?")  # noqa: TRY400 -- user-facing, known error condition
            raise SystemExit(ExitCode.App_Lookup_Failure) from e
        raise
