"""An app that scans for QT Py sensor_nodes."""

import asyncio
import logging
import pathlib

import qtpy_datalogger.guikit as guikit

logger = logging.getLogger(pathlib.Path(__file__).stem)


class ScannerApp(guikit.AsyncWindow):
    """A GUI for discovering and communicating with QT Py sensor nodes."""

    def create_user_interface(self) -> None:
        """Create the main window and connect event handlers."""

    async def on_loop(self) -> None:
        """Update the UI with new information."""

    def on_closing(self) -> None:
        """Clean up before exiting."""


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(ScannerApp))
