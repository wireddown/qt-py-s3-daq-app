"""An app that collects data from a soil swell test."""

import asyncio
import atexit
import contextlib
import functools
import json
import logging
import math
import pathlib
import random
import shutil
import tempfile
import time
import tkinter as tk
import webbrowser
from enum import StrEnum
from tkinter import filedialog, font

import matplotlib.axes as mpl_axes
import matplotlib.figure as mpl_figure
import pandas as pd
import ttkbootstrap as ttk
import ttkbootstrap.dialogs as ttk_dialogs
import ttkbootstrap.icons as ttk_icons
import ttkbootstrap.themes.standard as ttk_themes
from tkfontawesome import icon_to_image
from ttkbootstrap import constants as bootstyle

from qtpy_datalogger import datatypes, guikit, ttkbootstrap_matplotlib

logger = logging.getLogger(pathlib.Path(__file__).stem)

app_icon_color = "#07a000"


class StyleKey(StrEnum):
    """A class that extends the palette names of ttkbootstrap styles."""

    Fg = "fg"
    SelectFg = "selectfg"


class SoilSwell(guikit.AsyncWindow):
    """A GUI that acquires, plots, and logs data from a soil swell test."""

    app_name = "Soil Swell Test"

    class CommandName(StrEnum):
        """Names used for menus and commands in the app."""

        File = "File"
        Exit = "Exit"
        View = "View"
        Theme = "Theme"
        Help = "Help"
        About = "About"

    def create_user_interface(self) -> None:  # noqa: PLR 0915 -- allow long function to create the UI
        """Create the main window and connect event handlers."""
        # Supports UI widget state
        self.theme_variable = tk.StringVar()
        self.acquire_variable = tk.BooleanVar()
        self.log_variable = tk.BooleanVar()
        self.svg_images: dict[str, tk.Image] = {}

        app_icon = icon_to_image("chart-line", fill=app_icon_color, scale_to_height=256)
        self.root_window.iconphoto(True, app_icon)
        self.build_window_menu()

        figure_dpi = 112
        # self.root_window.minsize
        self.root_window.columnconfigure(0, weight=1)
        self.root_window.rowconfigure(0, weight=1)

        main = ttk.Frame(self.root_window, name="main_frame", padding=16, style=bootstyle.SECONDARY)
        main.grid(column=0, row=0, sticky=tk.NSEW)
        main.columnconfigure(0, weight=1)  # Graph panel
        main.columnconfigure(1, weight=0)  # Control panel
        main.rowconfigure(0, weight=1)

        # matplotlib elements must be created before setting the theme or the button icons initialize with poor color contrast
        self.graph_frame = ttk.Frame(main, name="graph_frame", style=bootstyle.LIGHT)
        self.graph_frame.grid(column=0, row=0, sticky=tk.NSEW)
        self.graph_frame.columnconfigure(0, weight=1)
        self.graph_frame.rowconfigure(0, weight=1)
        plot_figure = mpl_figure.Figure(figsize=(7, 5), dpi=figure_dpi)
        self.canvas_figure = ttkbootstrap_matplotlib.create_styled_plot_canvas(plot_figure, self.graph_frame)
        plot_figure.subplots_adjust(
            left=0.10,
            bottom=0.10,
            right=0.95,
            top=0.97,
        )

        all_subplots = plot_figure.subplots(
            nrows=3,
            ncols=1,
            sharex=True,
        )
        self.position_axes: mpl_axes.Axes = all_subplots[0]
        self.displacement_axes: mpl_axes.Axes = all_subplots[1]
        self.g_level_axes: mpl_axes.Axes = all_subplots[2]
        self.position_axes.set_ylabel("LVDT position (cm)")
        self.displacement_axes.set_ylabel("Displacement (cm)")
        self.g_level_axes.set_ylabel("Acceleration (g)")
        self.g_level_axes.set_xlabel("Time (minutes)")

        ttk.Style().theme_use("vapor")

        tool_panel = ttk.Frame(main, name="tool_panel", style=bootstyle.PRIMARY)
        tool_panel.grid(column=1, row=0, sticky=tk.NSEW)
        tool_panel.columnconfigure(0, weight=1, minsize=36)
        tool_panel.rowconfigure(0, weight=0, minsize=24)  # Status
        tool_panel.rowconfigure(1, weight=0, minsize=24)  # Settings
        tool_panel.rowconfigure(2, weight=1, minsize=24)  # Action

        status_panel = ttk.Frame(tool_panel, name="status_panel", style=bootstyle.INFO)
        status_panel.grid(column=0, row=0, sticky=tk.NSEW, padx=4, pady=4)

        settings_panel = ttk.Frame(tool_panel, name="settings_panel", style=bootstyle.WARNING)
        settings_panel.grid(column=0, row=1, sticky=tk.NSEW, padx=4)

        action_panel = ttk.Frame(tool_panel, name="action_panel", style=bootstyle.DANGER)
        action_panel.grid(column=0, row=2, sticky=tk.NSEW, padx=4, pady=4)

        self.root_window.bind("<<ThemeChanged>>", self.on_theme_changed)

        self.update_window_title("Centrifuge Test")

    def build_window_menu(self) -> None:
        """Create the entries for the window menu bar."""
        self.menubar = tk.Menu(
            self.root_window,
        )
        self.root_window.config(menu=self.menubar)

        # File menu
        self.file_menu = tk.Menu(self.menubar, name="file_menu")
        self.menubar.add_cascade(
            label=SoilSwell.CommandName.File,
            menu=self.file_menu,
            underline=0,
        )
        self.file_menu.add_command(
            command=self.exit,
            label=SoilSwell.CommandName.Exit,
            accelerator="Alt-F4",
        )
        self.root_window.bind("<Alt-F4>", lambda e: self.exit())

        # View menu
        self.view_menu = tk.Menu(self.menubar, name="view_menu")
        self.menubar.add_cascade(
            label=SoilSwell.CommandName.View,
            menu=self.view_menu,
            underline=0,
        )
        # Themes submenu
        light_mode = ttk_icons.Emoji.get("BLACK SUN WITH RAYS")
        dark_mode = ttk_icons.Emoji.get("WANING CRESCENT MOON SYMBOL")
        debug_mode = ttk_icons.Emoji.get("WARNING SIGN")
        self.themes_menu = tk.Menu(self.view_menu, name="themes_menu")
        self.view_menu.add_cascade(
            label=SoilSwell.CommandName.Theme,
            menu=self.themes_menu,
            underline=0,
        )
        self.themes_menu.add_radiobutton(
            command=functools.partial(self.change_theme, "cosmo"),
            label=f"{light_mode}  Cosmo",
            variable=self.theme_variable,
        )
        self.themes_menu.add_radiobutton(
            command=functools.partial(self.change_theme, "flatly"),
            label=f"{light_mode}  Flatly",
            variable=self.theme_variable,
        )
        self.themes_menu.add_separator()
        self.themes_menu.add_radiobutton(
            command=functools.partial(self.change_theme, "cyborg"),
            label=f"{dark_mode}  Cyborg",
            variable=self.theme_variable,
        )
        self.themes_menu.add_radiobutton(
            command=functools.partial(self.change_theme, "darkly"),
            label=f"{dark_mode}  Darkly",
            variable=self.theme_variable,
        )
        self.themes_menu.add_separator()
        self.themes_menu.add_radiobutton(
            command=functools.partial(self.change_theme, "vapor"),
            label=f"{debug_mode}  Debug",
            variable=self.theme_variable,
        )

        # Help menu
        self.help_menu = tk.Menu(self.menubar, name="help_menu")
        self.menubar.add_cascade(
            label=SoilSwell.CommandName.Help,
            menu=self.help_menu,
            underline=0,
        )
        self.help_menu.add_command(
            command=self.show_about,
            label=SoilSwell.CommandName.About,
            accelerator="F1",
        )
        self.root_window.bind("<F1>", lambda e: self.show_about())

    def create_icon_button(  # noqa PLR0913 -- allow many parameters for a factory method
        self,
        parent: tk.Widget,
        text: str,
        icon_name: str,
        char_width: int = 15,
        spaces: int = 2,
        bootstyle: str = bootstyle.DEFAULT,
    ) -> ttk.Button:
        """Create a ttk.Button using the specified text and FontAwesome icon_name."""
        text_spacing = 3 * " "
        button_image = icon_to_image(icon_name, fill=guikit.hex_string_for_style(StyleKey.SelectFg), scale_to_height=24)
        self.svg_images[icon_name] = button_image
        button = ttk.Button(
            parent,
            text=text + spaces * text_spacing,
            image=button_image,
            compound=tk.RIGHT,
            width=char_width,
            padding=(4, 6, 4, 4),
            bootstyle=bootstyle,  # pyright: ignore callIssue -- the type hint for bootstrap omits its own additions
        )
        return button

    async def on_loop(self) -> None:
        """Update the UI with new information."""
        await asyncio.sleep(1e-6)

    def show_about(self) -> None:
        """Handle the Help::About menu command."""

    def change_theme(self, theme_name:str) -> None:
        """Handle the View::Theme selection command."""
        # >>> self.state.active_theme = theme_name
        ttk.Style().theme_use(theme_name)

    def on_theme_changed(self, event_args: tk.Event) -> None:
        """Handle the ThemeChanged event."""

    def style_menu(self, menu: tk.Menu) -> None:
        """Style every entry in the specified menu."""
        last_entry = menu.index(tk.END)
        if last_entry is None:
            raise ValueError()
        for index in range(last_entry + 1):
            self.style_menu_entry(menu, index)

    def style_menu_entry(self, menu: tk.Menu, index: int) -> None:
        """Style the specified menu entry."""
        # Force light theme for menus
        with contextlib.suppress(tk.TclError):
            menu.entryconfigure(
                index,
                background="grey94",
            )
        with contextlib.suppress(tk.TclError):
            menu.entryconfigure(
                index,
                foreground="grey5",
            )
        with contextlib.suppress(tk.TclError):
            menu.entryconfigure(
                index,
                selectcolor="grey5",
            )
        with contextlib.suppress(tk.TclError):
            menu.entryconfigure(
                index,
                activebackground="grey42",
            )

    def update_window_title(self, new_title: str) -> None:
        """Update the application's window title."""
        self.root_window.title(new_title)


if __name__ == "__main__":
    logger.debug(f"Launching {__package__}")
    asyncio.run(guikit.AsyncApp.create_and_run(SoilSwell))
