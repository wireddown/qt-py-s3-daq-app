"""An app that scans for QT Py sensor_nodes."""

import asyncio
import logging
import pathlib
import tkinter as tk
from tkinter import font

import ttkbootstrap as ttk
import ttkbootstrap.icons as ttk_icons
from ttkbootstrap import constants as bootstyle

from qtpy_datalogger import guikit

logger = logging.getLogger(pathlib.Path(__file__).stem)


class ScannerApp(guikit.AsyncWindow):
    """A GUI for discovering and communicating with QT Py sensor nodes."""

    def create_user_interface(self) -> None:
        """Create the main window and connect event handlers."""
        app_name = "QT Py Sensor Node Scanner"
        self.root_window.minsize(width=600, height=800)
        self.root_window.place_window_center()
        self.root_window.title(app_name)
        self.root = ttk.Frame(self.root_window)
        icon = tk.PhotoImage(master=self.root_window, data=ttk_icons.Icon.question)
        self.root_window.iconphoto(True, icon)

        icon_emoji = ttk_icons.Emoji.get("telescope")
        title_font = font.Font(weight="bold", size=24)
        title_label = ttk.Label(self.root, font=title_font, text=f"{icon_emoji} {app_name}", padding=16)
        title_label.grid()
        self.root.pack()

    async def on_loop(self) -> None:
        """Update the UI with new information."""
        await asyncio.sleep(0.1)

    def on_closing(self) -> None:
        """Clean up before exiting."""


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(ScannerApp))
