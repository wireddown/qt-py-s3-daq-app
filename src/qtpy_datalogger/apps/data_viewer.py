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
        self.build_window_menu()

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

    def build_window_menu(self) -> None:
        """Create the entries for the window menu bar."""
        self.root_window.option_add("*tearOff", False)
        self.menubar = tk.Menu(
            self.root_window,
            # No styling support here -- Windows Settings for Light vs Dark mode control the menubar
        )
        self.root_window.config(menu=self.menubar)

        # File menu
        file_menu = tk.Menu(self.menubar, postcommand=self.on_file_menu)
        file_menu.add_command(
            command=self.open_file,
            label="Open",
            accelerator="Ctrl-O",
            # Styling is supported here, but the bounding frame surrounding the menu entries follows Windows System settings
        )
        file_menu.add_command(
            command=self.reload_file,
            label="Reload",
            accelerator="F5",
        )
        file_menu.add_command(
            command=self.close_file,
            label="Close",
            accelerator="Ctrl-W",
            # Styling is supported here, but the bounding frame surrounding the menu entries follows Windows System settings
        )
        file_menu.add_separator(
            # Styling is supported here, but the bounding frame surrounding the menu entries follows Windows System settings
        )
        file_menu.add_command(
            command=self.exit,
            label="Exit",
            accelerator="Alt-F4"
        )
        self.menubar.add_cascade(
            label="File",
            menu=file_menu,
            underline=0,
        )

        # Edit menu
        edit_menu = tk.Menu(self.menubar)
        edit_menu.add_command(
            command=self.copy_canvas,
            label="Copy",
            accelerator="Ctrl-C",
        )
        self.menubar.add_cascade(
            label="Edit",
            menu=edit_menu,
            underline=0,
        )

        # View menu
        view_menu = tk.Menu(self.menubar)
        view_menu.add_command(
            command=self.change_theme,
            label="Theme",
        )
        view_menu.add_command(
            command=self.replay_data,
            label="Replay",
        )
        # View :: Plots submenu
        plots_menu = tk.Menu(view_menu)
        plots_menu.add_command(
            label="(none)",
        )
        view_menu.add_cascade(
            label="Plots",
            menu=plots_menu,
            underline=0,
        )
        self.menubar.add_cascade(
            label="View",
            menu=view_menu,
            underline=0,
        )

        # Help menu
        help_menu = tk.Menu(self.menubar)
        help_menu.add_command(
            command=self.show_about,
            label="About",
            accelerator="F1",
        )
        self.menubar.add_cascade(
            label="Help",
            menu=help_menu,
            underline=0,
        )

    def on_file_menu(self) -> None:
        """Handle the File menu opening."""

    def open_file(self) -> None:
        """Handle the File::Open menu command."""

    def reload_file(self) -> None:
        """Handle the File::Reload menu command."""

    def close_file(self) -> None:
        """Handle the File::Close menu command."""

    def copy_canvas(self) -> None:
        """Handle the Edit::Copy menu command."""

    def replay_data(self) -> None:
        """Handle the View::Replay menu command."""

    def change_theme(self) -> None:
        """Handle the View::Theme selection command."""

    def show_about(self) -> None:
        """Handle the Help::About menu command."""


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(DataViewer))
