"""An app that scans for QT Py sensor_nodes."""

import asyncio
import logging
import pathlib
import tkinter as tk

import ttkbootstrap as ttk
import ttkbootstrap.icons as ttk_icons
from ttkbootstrap import constants as bootstyle

from qtpy_datalogger import guikit

logger = logging.getLogger(pathlib.Path(__file__).stem)


class EmptyApp(guikit.AsyncWindow):
    """An empty GUI to use as a baseline for a new app."""

    def create_user_interface(self) -> None:
        """Create the main window and connect event handlers."""

    async def on_loop(self) -> None:
        """Update the UI with new information."""

    def on_closing(self) -> None:
        """Clean up before exiting."""


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(EmptyApp))
