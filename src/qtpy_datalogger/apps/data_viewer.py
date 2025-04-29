"""Plot data from CSV files."""

import asyncio
import logging
import pathlib
import tkinter as tk

import ttkbootstrap as ttk
import ttkbootstrap.icons as ttk_icons
from ttkbootstrap import constants as bootstyle

from qtpy_datalogger import guikit

logger = logging.getLogger(pathlib.Path(__file__).stem)


class DataViewer(guikit.AsyncWindow):
    """A GUI that loads a CSV data file and plots the columns."""

    def create_user_interface(self) -> None:
        """Create the main window and connect event handlers."""
        self.update_window_title("QT Py Data Viewer")
        ##self.root_window.minsize(width=870, height=600)
        self.root_window.columnconfigure(0, weight=1)
        self.root_window.rowconfigure(0, weight=1)

        main = ttk.Frame(self.root_window, name="main_frame", padding=16)
        main.grid(column=0, row=0, sticky=tk.NSEW)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)
        main.rowconfigure(1, weight=0)

        self.canvas_placeholder = ttk.Frame(main, name="canvas_placeholder", height=200, width=300, style=bootstyle.INFO)
        self.canvas_placeholder.grid(column=0, row=0, sticky=tk.NSEW)

        toolbar_row = ttk.Frame(main, name="toolbar_row", style=bootstyle.WARNING)
        toolbar_row.grid(column=0, row=1, sticky=tk.NSEW, pady=(8, 0))
        toolbar_row.columnconfigure(0, weight=1)
        toolbar_row.columnconfigure(1, weight=0)

        action_panel = ttk.Frame(toolbar_row, name="action_panel", height=50, width=200, style=bootstyle.SUCCESS)
        action_panel.grid(column=0, row=0, sticky=tk.EW, padx=(0, 8))

        toolbar = ttk.Frame(toolbar_row, name="toolbar", height=50, width=300, style=bootstyle.SECONDARY)
        toolbar.grid(column=1, row=0, sticky=tk.EW)

    def on_show(self) -> None:
        """Initialize UI before entering main loop."""

    async def on_loop(self) -> None:
        """Update the UI with new information."""

    def on_closing(self) -> None:
        """Clean up before exiting."""

    def update_window_title(self, new_title: str) -> None:
        """Update the application's window title."""
        self.root_window.title(new_title)


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(DataViewer))
